package handlers

// Distributor administration + per-Part manual refresh.
//
// The admin surface (GET / PUT / DELETE under /api/admin/distributors)
// is gated to users with account_role = 'admin' OR 'system'. The
// per-Part refresh (POST /api/projects/.../files/.../distributors/
// refresh) is a normal project-member route — anyone with editor
// access can trigger a refresh on parts they're allowed to edit.

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"

	"github.com/imranp/kerf/backend/internal/distributors"
	"github.com/imranp/kerf/backend/internal/middleware"
)

// DistributorRegistry is the slice of *distributors.Registry the Deps
// struct exposes to admin handlers. Defined as an interface so tests
// can inject a fake (and so the handlers package doesn't have to
// import the concrete type more than once).
type DistributorRegistry interface {
	Meta() []distributors.ServiceMeta
	Reload(ctx context.Context) error
	Upsert(ctx context.Context, name string, enabled bool, ratePerMin int, creds distributors.Credentials) (distributors.ServiceMeta, error)
	Delete(ctx context.Context, name string) error
	Has(name string) bool
}

// requireAdmin returns true (and writes the appropriate error
// otherwise) when the caller's account_role is 'admin' or 'system'.
func requireAdmin(w http.ResponseWriter, r *http.Request, d *Deps) bool {
	uid := middleware.UserID(r.Context())
	if uid == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return false
	}
	var role string
	err := d.Pool.QueryRow(r.Context(),
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

// ListDistributors GET /api/admin/distributors. Returns one row per
// distributor, including unconfigured ones (so the UI can render an
// "add credentials" affordance for each).
func (d *Deps) ListDistributors(w http.ResponseWriter, r *http.Request) {
	if !requireAdmin(w, r, d) {
		return
	}
	if d.Distributors == nil {
		writeJSON(w, http.StatusOK, map[string]any{"distributors": []any{}})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"distributors": d.Distributors.Meta(),
	})
}

type updateDistributorReq struct {
	Enabled            *bool                     `json:"enabled,omitempty"`
	RateLimitPerMinute *int                      `json:"rate_limit_per_minute,omitempty"`
	Secret             *distributorSecretPayload `json:"secret,omitempty"`
}

type distributorSecretPayload struct {
	ClientID     string `json:"client_id,omitempty"`
	ClientSecret string `json:"client_secret,omitempty"`
	APIKey       string `json:"api_key,omitempty"`
}

// UpdateDistributor PUT /api/admin/distributors/:name. Validates the
// payload shape per distributor, encrypts the secret, and writes the
// row. On success, reloads the registry so the change is live.
func (d *Deps) UpdateDistributor(w http.ResponseWriter, r *http.Request) {
	if !requireAdmin(w, r, d) {
		return
	}
	if d.Distributors == nil {
		writeError(w, http.StatusServiceUnavailable, "distributor registry not initialized")
		return
	}
	name := chi.URLParam(r, "name")
	if !isKnownDistributor(name) {
		writeError(w, http.StatusBadRequest, "unknown distributor")
		return
	}
	var body updateDistributorReq
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	enabled := true
	if body.Enabled != nil {
		enabled = *body.Enabled
	}
	rate := 60
	if body.RateLimitPerMinute != nil {
		rate = *body.RateLimitPerMinute
	}
	if body.Secret == nil {
		writeError(w, http.StatusBadRequest, "secret payload is required (PUT replaces credentials)")
		return
	}
	creds := distributors.Credentials{
		ClientID:     body.Secret.ClientID,
		ClientSecret: body.Secret.ClientSecret,
		APIKey:       body.Secret.APIKey,
	}
	meta, err := d.Distributors.Upsert(r.Context(), name, enabled, rate, creds)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if err := d.Distributors.Reload(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "reload failed: "+err.Error())
		return
	}
	writeJSON(w, http.StatusOK, meta)
}

// DeleteDistributor DELETE /api/admin/distributors/:name. Idempotent.
func (d *Deps) DeleteDistributor(w http.ResponseWriter, r *http.Request) {
	if !requireAdmin(w, r, d) {
		return
	}
	if d.Distributors == nil {
		writeError(w, http.StatusServiceUnavailable, "distributor registry not initialized")
		return
	}
	name := chi.URLParam(r, "name")
	if !isKnownDistributor(name) {
		writeError(w, http.StatusBadRequest, "unknown distributor")
		return
	}
	if err := d.Distributors.Delete(r.Context(), name); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if err := d.Distributors.Reload(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "reload failed: "+err.Error())
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// isKnownDistributor whitelists the distributor names the system
// understands. Keeps the URL parameter from being used to insert
// arbitrary rows.
func isKnownDistributor(name string) bool {
	for _, n := range distributors.AllProviders() {
		if name == n {
			return true
		}
	}
	return false
}

// RefreshPartDistributors POST /api/projects/:pid/files/:fid/
// distributors/refresh. Triggers a synchronous distributor lookup for
// the named Part and writes the refreshed JSON back. Returns the
// updated Part content + a count of entries touched.
func (d *Deps) RefreshPartDistributors(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	fid := chi.URLParam(r, "fid")
	role := requireMember(w, r, d.Pool, pid, uid)
	if role == "" {
		return
	}
	if role == "viewer" {
		writeError(w, http.StatusForbidden, "viewer cannot refresh distributors")
		return
	}
	if d.Distributors == nil {
		writeError(w, http.StatusServiceUnavailable, "distributor registry not initialized")
		return
	}

	// Pull the file. Must be kind='part' and live (not soft-deleted).
	var (
		kind    string
		content string
	)
	err := d.Pool.QueryRow(r.Context(),
		`select kind, content from files where id = $1 and project_id = $2 and deleted_at is null`,
		fid, pid).Scan(&kind, &content)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "file not found")
			return
		}
		genericServerError(w, err)
		return
	}
	if kind != "part" {
		writeError(w, http.StatusBadRequest, "file is not a Part")
		return
	}

	// 30-second cap on the synchronous refresh — the per-entry HTTP
	// timeout is 10s but multiple distributors plus rate-limit waits
	// can stack up.
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()

	concrete, ok := d.Distributors.(*distributors.Registry)
	if !ok {
		writeError(w, http.StatusInternalServerError, "registry type mismatch")
		return
	}
	newContent, n, err := distributors.RefreshPart(ctx, concrete, content)
	if err != nil {
		writeError(w, http.StatusBadGateway, err.Error())
		return
	}

	if n > 0 && newContent != content {
		if _, err := d.Pool.Exec(r.Context(),
			`update files set content = $2, updated_at = now() where id = $1 and deleted_at is null`,
			fid, newContent); err != nil {
			genericServerError(w, err)
			return
		}
		uidPtr := userIDPtr(uid)
		_ = RecordRevision(r.Context(), d.Pool, fid, newContent, "tool", uidPtr, d.Cfg.FileRevisionsMax)
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"updated": n,
		"content": newContent,
	})
}

// userIDPtr is shared with revisions.go.
