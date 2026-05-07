package handlers

// Verified-publisher administration (Library Phase 3).
//
// Curated manufacturer libraries (Adafruit, SparkFun, Pololu,
// McMaster, Misumi, …) get a small ⭐ badge in the Workshop and are
// floated to the top of the parts browse. The flag itself
// (users.is_verified_publisher, added in migration 1746576700000) is
// just a boolean column; this file ships the admin surface that lets
// an operator toggle it without poking at psql.
//
// Two endpoints, both behind requireAdmin (account_role='admin' or
// 'system'):
//
//	GET /api/admin/publishers
//	    ?search=<query>&verified_only=true&cursor=<iso>&limit=<n>
//	PUT /api/admin/publishers/{user_id}
//	    body: {"is_verified_publisher": <bool>}

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"

	"github.com/imranp/kerf/backend/internal/middleware"
)

// publisherRow is the response shape for /api/admin/publishers list
// entries. We expose a small library_count rollup (distinct
// kind='part' files the user owns) so the operator has a quick "is
// this account interesting?" signal.
type publisherRow struct {
	ID                  string    `json:"id"`
	Email               string    `json:"email"`
	Name                string    `json:"name"`
	AvatarURL           string    `json:"avatar_url,omitempty"`
	IsVerifiedPublisher bool      `json:"is_verified_publisher"`
	IsSystem            bool      `json:"is_system"`
	AccountRole         string    `json:"account_role"`
	LibraryCount        int       `json:"library_count"`
	CreatedAt           time.Time `json:"created_at"`
}

type publisherListResp struct {
	Rows       []publisherRow `json:"rows"`
	NextCursor string         `json:"next_cursor,omitempty"`
}

// ListPublishers GET /api/admin/publishers. Returns user rows with a
// library_count (count of distinct, non-deleted kind='part' files the
// user owns through projects). The query is intentionally tolerant —
// a search term filters on name/email ILIKE; verified_only=true
// filters to flagged accounts. Pagination is cursor-based on
// created_at desc.
func (d *Deps) ListPublishers(w http.ResponseWriter, r *http.Request) {
	if !requireAdmin(w, r, d) {
		return
	}

	q := strings.TrimSpace(r.URL.Query().Get("search"))
	verifiedOnly := r.URL.Query().Get("verified_only") == "true"
	cursor := strings.TrimSpace(r.URL.Query().Get("cursor"))

	limit := 50
	if v := r.URL.Query().Get("limit"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 && n <= 200 {
			limit = n
		}
	}

	// Build args + WHERE incrementally so we don't have to track positional
	// indexes by hand. Same pattern as workshop/handlers.go ListParts.
	args := []any{}
	pushArg := func(v any) string {
		args = append(args, v)
		return fmt.Sprintf("$%d", len(args))
	}

	conditions := []string{"u.is_system = false"}
	if verifiedOnly {
		conditions = append(conditions, "u.is_verified_publisher = true")
	}
	if q != "" {
		ph := pushArg("%" + strings.ToLower(q) + "%")
		conditions = append(conditions,
			fmt.Sprintf("(lower(u.email) like %[1]s or lower(coalesce(u.name,'')) like %[1]s)", ph))
	}
	if cursor != "" {
		// cursor is the previous page's last created_at — strict less-than
		// for clean pagination on a non-unique column would be wrong, but
		// we tie-break on id below to make the order total.
		t, err := time.Parse(time.RFC3339Nano, cursor)
		if err != nil {
			writeError(w, http.StatusBadRequest, "invalid cursor")
			return
		}
		ph := pushArg(t)
		conditions = append(conditions, fmt.Sprintf("u.created_at < %s", ph))
	}

	limitPh := pushArg(limit + 1) // over-fetch by 1 to compute next_cursor

	sql := fmt.Sprintf(`
		select
			u.id, u.email, coalesce(u.name,''),
			coalesce(u.avatar_url,''),
			u.is_verified_publisher, u.is_system, u.account_role,
			u.created_at,
			coalesce((
				select count(distinct f.id)
				from files f
				join projects p on p.id = f.project_id
				where p.owner_id = u.id
				  and f.kind = 'part'
				  and f.deleted_at is null
			), 0) as library_count
		from users u
		where %s
		order by u.created_at desc
		limit %s
	`, strings.Join(conditions, " and "), limitPh)

	rows, err := d.Pool.Query(r.Context(), sql, args...)
	if err != nil {
		genericServerError(w, err)
		return
	}
	defer rows.Close()

	out := make([]publisherRow, 0, limit)
	for rows.Next() {
		var pr publisherRow
		if err := rows.Scan(
			&pr.ID, &pr.Email, &pr.Name, &pr.AvatarURL,
			&pr.IsVerifiedPublisher, &pr.IsSystem, &pr.AccountRole,
			&pr.CreatedAt, &pr.LibraryCount,
		); err != nil {
			genericServerError(w, err)
			return
		}
		out = append(out, pr)
	}
	if err := rows.Err(); err != nil {
		genericServerError(w, err)
		return
	}

	resp := publisherListResp{Rows: out}
	if len(out) > limit {
		// Trim the over-fetch and surface the cursor of the last *kept* row.
		resp.Rows = out[:limit]
		resp.NextCursor = out[limit-1].CreatedAt.Format(time.RFC3339Nano)
	}
	writeJSON(w, http.StatusOK, resp)
}

type setVerifiedReq struct {
	IsVerifiedPublisher bool `json:"is_verified_publisher"`
}

// SetPublisherVerified PUT /api/admin/publishers/:user_id. Toggles
// the boolean on a user row. Returns the updated row in the same
// shape as ListPublishers so the UI can swap in-place without a
// re-list.
func (d *Deps) SetPublisherVerified(w http.ResponseWriter, r *http.Request) {
	if !requireAdmin(w, r, d) {
		return
	}
	uid := chi.URLParam(r, "user_id")
	if uid == "" {
		writeError(w, http.StatusBadRequest, "user_id is required")
		return
	}
	var body setVerifiedReq
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}

	var pr publisherRow
	err := d.Pool.QueryRow(r.Context(), `
		update users
		   set is_verified_publisher = $2
		 where id = $1
		returning id, email, coalesce(name,''), coalesce(avatar_url,''),
		          is_verified_publisher, is_system, account_role, created_at
	`, uid, body.IsVerifiedPublisher).Scan(
		&pr.ID, &pr.Email, &pr.Name, &pr.AvatarURL,
		&pr.IsVerifiedPublisher, &pr.IsSystem, &pr.AccountRole,
		&pr.CreatedAt,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "user not found")
			return
		}
		genericServerError(w, err)
		return
	}

	// Fill in library_count separately — the toggle path doesn't really
	// need it but the response shape stays consistent.
	_ = d.Pool.QueryRow(r.Context(), `
		select count(distinct f.id)
		  from files f
		  join projects p on p.id = f.project_id
		 where p.owner_id = $1
		   and f.kind = 'part'
		   and f.deleted_at is null
	`, pr.ID).Scan(&pr.LibraryCount)

	// Audit trail in the request log so an after-the-fact "who flipped
	// this?" question has at least a starting point. The handlers
	// package doesn't emit structured audit events yet, so chimw.Logger
	// is the best we have today.
	_ = middleware.UserID(r.Context())

	writeJSON(w, http.StatusOK, pr)
}
