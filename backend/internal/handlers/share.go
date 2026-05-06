package handlers

import (
	"context"
	"errors"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"

	"github.com/imranp/kerf/backend/internal/auth"
	"github.com/imranp/kerf/backend/internal/middleware"
	"github.com/imranp/kerf/backend/internal/models"
)

type createShareReq struct {
	Role      string     `json:"role"`
	ExpiresAt *time.Time `json:"expires_at"`
	MaxUses   *int       `json:"max_uses"`
}

// CreateShareLink mints a share link (owner or editor).
func (d *Deps) CreateShareLink(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	role := requireMember(w, r, d.Pool, pid, uid)
	if role == "" {
		return
	}
	if role == "viewer" {
		writeError(w, http.StatusForbidden, "viewer cannot create share links")
		return
	}
	var body createShareReq
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if body.Role != "editor" && body.Role != "viewer" {
		writeError(w, http.StatusBadRequest, "invalid role")
		return
	}
	token, err := auth.IssueShareToken()
	if err != nil {
		genericServerError(w, err)
		return
	}
	var s models.ShareLink
	err = d.Pool.QueryRow(r.Context(), `
		insert into share_links(project_id, token, role, expires_at, max_uses, created_by)
		values ($1,$2,$3,$4,$5,$6)
		returning id, project_id, token, role, expires_at, revoked_at, max_uses, uses, created_at
	`, pid, token, body.Role, body.ExpiresAt, body.MaxUses, uid).Scan(
		&s.ID, &s.ProjectID, &s.Token, &s.Role, &s.ExpiresAt, &s.RevokedAt, &s.MaxUses, &s.Uses, &s.CreatedAt)
	if err != nil {
		genericServerError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, s)
}

// ListShareLinks returns the project's share links with token redacted.
func (d *Deps) ListShareLinks(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}
	rows, err := d.Pool.Query(r.Context(), `
		select id, project_id, role, expires_at, revoked_at, max_uses, uses, created_at
		from share_links
		where project_id = $1
		order by created_at desc
	`, pid)
	if err != nil {
		genericServerError(w, err)
		return
	}
	defer rows.Close()
	out := []models.ShareLink{}
	for rows.Next() {
		var s models.ShareLink
		if err := rows.Scan(&s.ID, &s.ProjectID, &s.Role, &s.ExpiresAt, &s.RevokedAt, &s.MaxUses, &s.Uses, &s.CreatedAt); err != nil {
			genericServerError(w, err)
			return
		}
		out = append(out, s)
	}
	writeJSON(w, http.StatusOK, out)
}

// DeleteShareLink revokes (deletes) a share link (owner only).
func (d *Deps) DeleteShareLink(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	lid := chi.URLParam(r, "lid")
	if !requireOwner(w, r, d.Pool, pid, uid) {
		return
	}
	if _, err := d.Pool.Exec(r.Context(),
		`delete from share_links where id = $1 and project_id = $2`, lid, pid); err != nil {
		genericServerError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

type shareInfoResp struct {
	Project       models.Project `json:"project"`
	Role          string         `json:"role"`
	RequiresLogin bool           `json:"requires_login"`
}

// LookupShare returns project details for a share token (no auth required).
func (d *Deps) LookupShare(w http.ResponseWriter, r *http.Request) {
	token := chi.URLParam(r, "token")
	link, ok := d.fetchActiveShare(w, r.Context(), token)
	if !ok {
		return
	}
	var p models.Project
	if err := d.Pool.QueryRow(r.Context(), `
		select id, owner_id, name, description, visibility, created_at, updated_at
		from projects where id = $1
	`, link.ProjectID).Scan(&p.ID, &p.OwnerID, &p.Name, &p.Description, &p.Visibility, &p.CreatedAt, &p.UpdatedAt); err != nil {
		genericServerError(w, err)
		return
	}
	uid := middleware.UserID(r.Context())
	requiresLogin := uid == ""
	writeJSON(w, http.StatusOK, shareInfoResp{
		Project:       p,
		Role:          link.Role,
		RequiresLogin: requiresLogin,
	})
}

// AcceptShare adds the caller to the project at the link's role and increments uses.
func (d *Deps) AcceptShare(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	if uid == "" {
		writeError(w, http.StatusUnauthorized, "login required")
		return
	}
	token := chi.URLParam(r, "token")
	link, ok := d.fetchActiveShare(w, r.Context(), token)
	if !ok {
		return
	}
	var ownerID string
	if err := d.Pool.QueryRow(r.Context(),
		`select owner_id from projects where id = $1`, link.ProjectID).Scan(&ownerID); err != nil {
		genericServerError(w, err)
		return
	}
	if ownerID != uid {
		_, err := d.Pool.Exec(r.Context(), `
			insert into project_members(project_id, user_id, role)
			values ($1,$2,$3)
			on conflict (project_id, user_id) do nothing
		`, link.ProjectID, uid, link.Role)
		if err != nil {
			genericServerError(w, err)
			return
		}
	}
	if _, err := d.Pool.Exec(r.Context(),
		`update share_links set uses = uses + 1 where id = $1`, link.ID); err != nil {
		genericServerError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"project_id": link.ProjectID})
}

// fetchActiveShare loads a share by token and validates expiry/revocation/uses.
// On any failure it writes the appropriate response and returns ok=false.
func (d *Deps) fetchActiveShare(w http.ResponseWriter, ctx context.Context, token string) (models.ShareLink, bool) {
	var s models.ShareLink
	err := d.Pool.QueryRow(ctx, `
		select id, project_id, role, expires_at, revoked_at, max_uses, uses, created_at
		from share_links where token = $1
	`, token).Scan(&s.ID, &s.ProjectID, &s.Role, &s.ExpiresAt, &s.RevokedAt, &s.MaxUses, &s.Uses, &s.CreatedAt)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "share link not found")
			return s, false
		}
		genericServerError(w, err)
		return s, false
	}
	if s.RevokedAt != nil {
		writeError(w, http.StatusGone, "share link revoked")
		return s, false
	}
	if s.ExpiresAt != nil && time.Now().After(*s.ExpiresAt) {
		writeError(w, http.StatusGone, "share link expired")
		return s, false
	}
	if s.MaxUses != nil && s.Uses >= *s.MaxUses {
		writeError(w, http.StatusGone, "share link exhausted")
		return s, false
	}
	return s, true
}
