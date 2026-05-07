//go:build cloud
// +build cloud

package billing

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/cloud/email"
	"github.com/imranp/kerf/backend/cloud/fx"
	"github.com/imranp/kerf/backend/internal/config"
	kmw "github.com/imranp/kerf/backend/internal/middleware"
)

// Handlers wires the billing endpoints. Constructed by cloud.Service so
// the OSS handlers package never imports cloud code (which would defeat
// the build-tag isolation).
type Handlers struct {
	Pool     *pgxpool.Pool
	Cfg      *config.Config
	FX       *fx.Fetcher
	Paystack *Client
	// Mailer is non-nil in production cloud builds; the webhook path
	// fires a receipt email through it after a successful charge. nil
	// in unit tests that exercise the billing logic without standing up
	// the email subsystem — the webhook short-circuits the email step
	// when nil.
	Mailer *email.Mailer
}

// Mount attaches billing routes onto whichever routers are provided.
//
// The caller has already routed under /api/billing (or whatever prefix
// they choose) — Mount itself does NOT add a /billing prefix. This lets
// the caller mount the authenticated and public subsets as siblings:
//
//	r.Route("/api/billing", func(api chi.Router) {
//	    api.Group(func(public chi.Router)  { h.Mount(nil, public) })
//	    api.Group(func(authed chi.Router)  {
//	        authed.Use(RequireAuth(...))
//	        h.Mount(authed, nil)
//	    })
//	})
//
// Either router may be nil to skip that subset. Routes mounted:
//
//	POST /topup    (authed)   — initiate a Paystack top-up
//	GET  /me       (authed)   — balance + recent invoices/usage
//	GET  /usage    (authed)   — paginated usage events
//	POST /webhook  (public)   — Paystack webhook (HMAC-authed)
func (h *Handlers) Mount(authed chi.Router, public chi.Router) {
	if authed != nil {
		authed.Post("/topup", h.Topup)
		authed.Get("/me", h.Me)
		authed.Get("/usage", h.Usage)
	}
	if public != nil {
		public.Post("/webhook", h.Webhook)
	}
}

// --- response/request shapes ---

type topupRequest struct {
	AmountUSD   float64 `json:"amount_usd"`
	CallbackURL string  `json:"callback_url,omitempty"`
}

type topupResponse struct {
	AuthorizationURL string  `json:"authorization_url"`
	Reference        string  `json:"reference"`
	AmountUSD        float64 `json:"amount_usd"`
	AmountZAR        float64 `json:"amount_zar"`
	FXRate           float64 `json:"fx_rate"`
}

type meResponse struct {
	CreditsUSD     float64       `json:"credits_usd"`
	RecentInvoices []invoiceView `json:"recent_invoices"`
	RecentUsage    []usageView   `json:"recent_usage"`
}

type invoiceView struct {
	ID        string     `json:"id"`
	Reference string     `json:"reference"`
	Status    string     `json:"status"`
	AmountUSD float64    `json:"amount_usd"`
	AmountZAR float64    `json:"amount_zar"`
	FXRate    float64    `json:"fx_rate"`
	CreatedAt time.Time  `json:"created_at"`
	PaidAt    *time.Time `json:"paid_at,omitempty"`
}

type usageView struct {
	ID           string    `json:"id"`
	Kind         string    `json:"kind"`
	Model        *string   `json:"model,omitempty"`
	InputTokens  int       `json:"input_tokens"`
	OutputTokens int       `json:"output_tokens"`
	BytesDelta   int64     `json:"bytes_delta"`
	USDCost      float64   `json:"usd_cost"`
	ProjectID    *string   `json:"project_id,omitempty"`
	CreatedAt    time.Time `json:"created_at"`
}

type usageListResponse struct {
	Events []usageView `json:"events"`
	From   time.Time   `json:"from"`
	To     time.Time   `json:"to"`
}

// --- helpers ---

func writeJSON(w http.ResponseWriter, status int, body interface{}) {
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

// userEmail looks up the caller's email for Paystack initialize.
func userEmail(ctx context.Context, pool *pgxpool.Pool, userID string) (string, error) {
	var email string
	err := pool.QueryRow(ctx, `select email from users where id = $1`, userID).Scan(&email)
	return email, err
}

// --- POST /billing/topup ---

func (h *Handlers) Topup(w http.ResponseWriter, r *http.Request) {
	uid := kmw.UserID(r.Context())
	if uid == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return
	}
	var req topupRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if req.AmountUSD <= 0 {
		writeError(w, http.StatusBadRequest, "amount_usd must be > 0")
		return
	}
	if h.Paystack == nil {
		writeError(w, http.StatusServiceUnavailable, "paystack not configured")
		return
	}

	// Compute ZAR amount with spread baked in. We capture this rate on
	// the invoice so any later refund reuses what the user actually paid.
	rate, _, ok := h.FX.RateWithSpread(
		h.Cfg.Cloud.FX.BaseCurrency,
		h.Cfg.Cloud.FX.SettlementCurrency,
		h.Cfg.Cloud.FX.SpreadPct,
	)
	if !ok || rate <= 0 {
		writeError(w, http.StatusServiceUnavailable, "fx rate unavailable")
		return
	}
	amountZAR := req.AmountUSD * rate
	amountZARCents := int(amountZAR * 100)

	email, err := userEmail(r.Context(), h.Pool, uid)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "user lookup failed")
		return
	}

	reference := uuid.NewString()

	// Persist the invoice as 'pending' before calling Paystack. This way,
	// if the provider call succeeds but our DB write fails afterwards, we
	// don't end up with a charge no row references.
	if _, err := h.Pool.Exec(r.Context(), `
        insert into cloud_invoices
            (user_id, reference, status, amount_usd, amount_zar, fx_rate)
        values ($1, $2, 'pending', $3, $4, $5)
    `, uid, reference, req.AmountUSD, amountZAR, rate); err != nil {
		writeError(w, http.StatusInternalServerError, fmt.Sprintf("invoice insert: %v", err))
		return
	}

	authURL, _, err := h.Paystack.InitializeTransaction(
		r.Context(), email, amountZARCents, reference, req.CallbackURL,
	)
	if err != nil {
		// Mark abandoned so we don't keep retrying via stale references.
		_, _ = h.Pool.Exec(r.Context(),
			`update cloud_invoices set status = 'abandoned' where reference = $1`,
			reference,
		)
		writeError(w, http.StatusBadGateway, fmt.Sprintf("paystack: %v", err))
		return
	}

	writeJSON(w, http.StatusOK, topupResponse{
		AuthorizationURL: authURL,
		Reference:        reference,
		AmountUSD:        req.AmountUSD,
		AmountZAR:        amountZAR,
		FXRate:           rate,
	})
}

// --- GET /billing/me ---

func (h *Handlers) Me(w http.ResponseWriter, r *http.Request) {
	uid := kmw.UserID(r.Context())
	if uid == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return
	}

	var balance float64
	err := h.Pool.QueryRow(r.Context(),
		`select credits_usd from cloud_user_balances where user_id = $1`,
		uid,
	).Scan(&balance)
	if err != nil && !errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	invoices, err := loadRecentInvoices(r.Context(), h.Pool, uid, 20)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	usage, err := loadRecentUsage(r.Context(), h.Pool, uid, 20)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	writeJSON(w, http.StatusOK, meResponse{
		CreditsUSD:     balance,
		RecentInvoices: invoices,
		RecentUsage:    usage,
	})
}

// --- GET /billing/usage?from=&to= ---

func (h *Handlers) Usage(w http.ResponseWriter, r *http.Request) {
	uid := kmw.UserID(r.Context())
	if uid == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return
	}
	now := time.Now().UTC()
	defaultFrom := time.Date(now.Year(), now.Month(), 1, 0, 0, 0, 0, time.UTC)
	defaultTo := defaultFrom.AddDate(0, 1, 0)

	from, err := parseTimeOrDefault(r.URL.Query().Get("from"), defaultFrom)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid from")
		return
	}
	to, err := parseTimeOrDefault(r.URL.Query().Get("to"), defaultTo)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid to")
		return
	}

	limit := 200
	if v := r.URL.Query().Get("limit"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 && n <= 1000 {
			limit = n
		}
	}

	rows, err := h.Pool.Query(r.Context(), `
        select id, kind, model, input_tokens, output_tokens, bytes_delta,
               usd_cost, project_id, created_at
        from usage_events
        where user_id = $1 and created_at >= $2 and created_at < $3
        order by created_at desc
        limit $4
    `, uid, from, to, limit)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer rows.Close()

	out := make([]usageView, 0, 32)
	for rows.Next() {
		var v usageView
		if err := rows.Scan(
			&v.ID, &v.Kind, &v.Model,
			&v.InputTokens, &v.OutputTokens, &v.BytesDelta,
			&v.USDCost, &v.ProjectID, &v.CreatedAt,
		); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		out = append(out, v)
	}
	writeJSON(w, http.StatusOK, usageListResponse{Events: out, From: from, To: to})
}

// --- shared loaders ---

func loadRecentInvoices(ctx context.Context, pool *pgxpool.Pool, userID string, limit int) ([]invoiceView, error) {
	rows, err := pool.Query(ctx, `
        select id, reference, status, amount_usd, amount_zar, fx_rate,
               created_at, paid_at
        from cloud_invoices
        where user_id = $1
        order by created_at desc
        limit $2
    `, userID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := make([]invoiceView, 0, limit)
	for rows.Next() {
		var v invoiceView
		if err := rows.Scan(
			&v.ID, &v.Reference, &v.Status,
			&v.AmountUSD, &v.AmountZAR, &v.FXRate,
			&v.CreatedAt, &v.PaidAt,
		); err != nil {
			return nil, err
		}
		out = append(out, v)
	}
	return out, nil
}

func loadRecentUsage(ctx context.Context, pool *pgxpool.Pool, userID string, limit int) ([]usageView, error) {
	rows, err := pool.Query(ctx, `
        select id, kind, model, input_tokens, output_tokens, bytes_delta,
               usd_cost, project_id, created_at
        from usage_events
        where user_id = $1
        order by created_at desc
        limit $2
    `, userID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := make([]usageView, 0, limit)
	for rows.Next() {
		var v usageView
		if err := rows.Scan(
			&v.ID, &v.Kind, &v.Model,
			&v.InputTokens, &v.OutputTokens, &v.BytesDelta,
			&v.USDCost, &v.ProjectID, &v.CreatedAt,
		); err != nil {
			return nil, err
		}
		out = append(out, v)
	}
	return out, nil
}

func parseTimeOrDefault(s string, def time.Time) (time.Time, error) {
	if s == "" {
		return def, nil
	}
	// Accept RFC3339 first, then date-only YYYY-MM-DD.
	if t, err := time.Parse(time.RFC3339, s); err == nil {
		return t, nil
	}
	if t, err := time.Parse("2006-01-02", s); err == nil {
		return t, nil
	}
	return time.Time{}, fmt.Errorf("invalid time: %q", s)
}
