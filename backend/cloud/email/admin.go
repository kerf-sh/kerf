//go:build cloud
// +build cloud

package email

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/internal/auth"
	"github.com/imranp/kerf/backend/internal/config"
	kmw "github.com/imranp/kerf/backend/internal/middleware"
)

// AdminHandlers wires the admin endpoints. Built by cloud_enabled.go in
// the cloud-tagged main and mounted under /api/admin/email.
//
// Admin role is enforced inside each handler (mirrors the distributor
// admin pattern in backend/internal/handlers/distributor_admin.go).
type AdminHandlers struct {
	Pool   *pgxpool.Pool
	Cfg    *config.Config
	Mailer *Mailer
}

// Mount attaches the admin routes onto the supplied router. The caller
// has already routed under /api/admin/email and applied RequireAuth.
func (h *AdminHandlers) Mount(r chi.Router) {
	r.Get("/providers", h.ListProviders)
	r.Put("/providers/{provider}", h.UpsertProvider)
	r.Delete("/providers/{provider}", h.DeleteProvider)
	r.Post("/test", h.TestSend)
	r.Get("/log", h.ListLog)
}

// providerView is the public (no secret material) row description.
type providerView struct {
	Provider           string     `json:"provider"`
	Enabled            bool       `json:"enabled"`
	HasSecret          bool       `json:"has_secret"`
	RateLimitPerMinute int        `json:"rate_limit_per_minute"`
	LastUsedAt         *time.Time `json:"last_used_at,omitempty"`
	UpdatedAt          time.Time  `json:"updated_at"`
	Active             bool       `json:"active"` // is this the precedence-winning provider?
}

func (h *AdminHandlers) requireAdmin(w http.ResponseWriter, r *http.Request) bool {
	uid := kmw.UserID(r.Context())
	if uid == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return false
	}
	var role string
	err := h.Pool.QueryRow(r.Context(),
		`select account_role from users where id = $1`, uid).Scan(&role)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return false
	}
	if role != "admin" && role != "system" {
		writeError(w, http.StatusForbidden, "admin access required")
		return false
	}
	return true
}

// GET /api/admin/email/providers — returns one row per provider
// (resend/ses/smtp), including unconfigured ones so the UI can render
// "Add credentials" affordances.
func (h *AdminHandlers) ListProviders(w http.ResponseWriter, r *http.Request) {
	if !h.requireAdmin(w, r) {
		return
	}
	rows, err := h.Pool.Query(r.Context(), `
        select provider, enabled, secret_encrypted, rate_limit_per_minute,
               last_used_at, updated_at
          from cloud_email_credentials
    `)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer rows.Close()

	known := map[string]providerView{}
	for rows.Next() {
		var (
			name      string
			enabled   bool
			secret    []byte
			rateLimit int
			lastUsed  *time.Time
			updatedAt time.Time
		)
		if err := rows.Scan(&name, &enabled, &secret, &rateLimit, &lastUsed, &updatedAt); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		known[name] = providerView{
			Provider:           name,
			Enabled:            enabled,
			HasSecret:          len(secret) > 0,
			RateLimitPerMinute: rateLimit,
			LastUsedAt:         lastUsed,
			UpdatedAt:          updatedAt,
		}
	}

	// Mark the precedence-winning enabled row as Active. activeProvider
	// reads the live providers map; it returns nil if no enabled row has
	// successfully decrypted, which is the more useful signal than just
	// "first enabled in the DB."
	activeName := ""
	if h.Mailer != nil {
		if p := h.Mailer.activeProvider(); p != nil {
			activeName = p.Name()
		}
	}

	out := make([]providerView, 0, len(providerOrder))
	for _, name := range providerOrder {
		if v, ok := known[name]; ok {
			v.Active = (v.Provider == activeName)
			out = append(out, v)
		} else {
			out = append(out, providerView{
				Provider:           name,
				Enabled:            false,
				HasSecret:          false,
				RateLimitPerMinute: 60,
			})
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"providers": out, "active": activeName})
}

type upsertProviderReq struct {
	Enabled            *bool        `json:"enabled,omitempty"`
	RateLimitPerMinute *int         `json:"rate_limit_per_minute,omitempty"`
	Secret             *Credentials `json:"secret,omitempty"`
}

// PUT /api/admin/email/providers/:provider
func (h *AdminHandlers) UpsertProvider(w http.ResponseWriter, r *http.Request) {
	if !h.requireAdmin(w, r) {
		return
	}
	provider := chi.URLParam(r, "provider")
	if !knownProvider(provider) {
		writeError(w, http.StatusBadRequest, "unknown provider")
		return
	}
	var body upsertProviderReq
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if body.Secret == nil {
		writeError(w, http.StatusBadRequest, "secret payload is required")
		return
	}
	if err := validateCredentials(provider, *body.Secret); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	enabled := true
	if body.Enabled != nil {
		enabled = *body.Enabled
	}
	rateLimit := 60
	if body.RateLimitPerMinute != nil && *body.RateLimitPerMinute > 0 {
		rateLimit = *body.RateLimitPerMinute
	}
	plain, err := json.Marshal(body.Secret)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "encode secret: "+err.Error())
		return
	}
	enc, err := auth.EncryptSecret(secretDomain, h.Cfg.JWTSecret, string(plain))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "encrypt: "+err.Error())
		return
	}
	if _, err := h.Pool.Exec(r.Context(), `
        insert into cloud_email_credentials
            (provider, enabled, secret_encrypted, rate_limit_per_minute)
        values ($1, $2, $3, $4)
        on conflict (provider) do update set
            enabled = excluded.enabled,
            secret_encrypted = excluded.secret_encrypted,
            rate_limit_per_minute = excluded.rate_limit_per_minute,
            updated_at = now()
    `, provider, enabled, enc, rateLimit); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if h.Mailer != nil {
		if err := h.Mailer.Reload(r.Context()); err != nil {
			writeError(w, http.StatusInternalServerError, "reload: "+err.Error())
			return
		}
	}
	w.WriteHeader(http.StatusNoContent)
}

// DELETE /api/admin/email/providers/:provider
func (h *AdminHandlers) DeleteProvider(w http.ResponseWriter, r *http.Request) {
	if !h.requireAdmin(w, r) {
		return
	}
	provider := chi.URLParam(r, "provider")
	if !knownProvider(provider) {
		writeError(w, http.StatusBadRequest, "unknown provider")
		return
	}
	if _, err := h.Pool.Exec(r.Context(),
		`delete from cloud_email_credentials where provider = $1`, provider,
	); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if h.Mailer != nil {
		if err := h.Mailer.Reload(r.Context()); err != nil {
			writeError(w, http.StatusInternalServerError, "reload: "+err.Error())
			return
		}
	}
	w.WriteHeader(http.StatusNoContent)
}

type testSendReq struct {
	To       string         `json:"to"`
	Template string         `json:"template"`
	Vars     map[string]any `json:"vars,omitempty"`
}

// POST /api/admin/email/test  {to, template, vars?}
//
// Renders + enqueues a single test send. Returns the row id so the
// caller can poll /api/admin/email/log to see the send result.
func (h *AdminHandlers) TestSend(w http.ResponseWriter, r *http.Request) {
	if !h.requireAdmin(w, r) {
		return
	}
	var body testSendReq
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if body.To == "" || body.Template == "" {
		writeError(w, http.StatusBadRequest, "to and template required")
		return
	}
	if !validTemplate(body.Template) {
		writeError(w, http.StatusBadRequest, "unknown template")
		return
	}
	// Default the AppURL var so test sends look like real ones.
	if body.Vars == nil {
		body.Vars = map[string]any{}
	}
	if _, ok := body.Vars["AppURL"]; !ok {
		body.Vars["AppURL"] = h.Cfg.CORSOrigin
	}
	if h.Mailer == nil {
		writeError(w, http.StatusServiceUnavailable, "mailer not initialized")
		return
	}
	if err := h.Mailer.SendTemplate(r.Context(), body.Template, body.To, "", body.Vars); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]string{"status": "queued"})
}

type logRow struct {
	ID        string     `json:"id"`
	UserID    *string    `json:"user_id,omitempty"`
	Template  string     `json:"template"`
	ToEmail   string     `json:"to_email"`
	Provider  *string    `json:"provider,omitempty"`
	Status    string     `json:"status"`
	Error     *string    `json:"error,omitempty"`
	SentAt    *time.Time `json:"sent_at,omitempty"`
	CreatedAt time.Time  `json:"created_at"`
}

// GET /api/admin/email/log?limit=50&before=<rfc3339>
func (h *AdminHandlers) ListLog(w http.ResponseWriter, r *http.Request) {
	if !h.requireAdmin(w, r) {
		return
	}
	limit := 50
	if v := r.URL.Query().Get("limit"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 && n <= 500 {
			limit = n
		}
	}
	args := []any{limit}
	beforeClause := ""
	if v := r.URL.Query().Get("before"); v != "" {
		t, err := time.Parse(time.RFC3339, v)
		if err != nil {
			writeError(w, http.StatusBadRequest, "invalid before")
			return
		}
		// Place the cursor at $1 so the limit shifts to $2. Doing this
		// in two steps (rather than fmt.Sprintf'ing the placeholder
		// indexes) keeps the SQL stable when this gets a third filter.
		args = []any{t, limit}
		beforeClause = " and created_at < $1 "
	}
	q := fmt.Sprintf(`
        select id, user_id, template, to_email, provider, status, error,
               sent_at, created_at
          from cloud_email_log
         where 1=1 %s
         order by created_at desc
         limit $%d
    `, beforeClause, len(args))
	rows, err := h.Pool.Query(r.Context(), q, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer rows.Close()
	out := make([]logRow, 0, limit)
	for rows.Next() {
		var v logRow
		if err := rows.Scan(
			&v.ID, &v.UserID, &v.Template, &v.ToEmail, &v.Provider,
			&v.Status, &v.Error, &v.SentAt, &v.CreatedAt,
		); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		out = append(out, v)
	}
	writeJSON(w, http.StatusOK, map[string]any{"entries": out})
}

// --- helpers ---

func knownProvider(p string) bool {
	for _, n := range providerOrder {
		if n == p {
			return true
		}
	}
	return false
}

// loadCredentials decrypts and returns the credentials for a single
// provider. Used by tests / admin tooling — the mailer uses Reload().
func loadCredentials(ctx context.Context, pool *pgxpool.Pool, cfg *config.Config, provider string) (Credentials, error) {
	var enc []byte
	err := pool.QueryRow(ctx,
		`select secret_encrypted from cloud_email_credentials where provider = $1`,
		provider,
	).Scan(&enc)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return Credentials{}, fmt.Errorf("no credentials configured for %s", provider)
		}
		return Credentials{}, err
	}
	plain, err := auth.DecryptSecret(secretDomain, cfg.JWTSecret, enc)
	if err != nil {
		return Credentials{}, err
	}
	var c Credentials
	if err := json.Unmarshal([]byte(plain), &c); err != nil {
		return Credentials{}, err
	}
	return c, nil
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if body == nil {
		return
	}
	_ = json.NewEncoder(w).Encode(body)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}
