package handlers

import (
	"errors"
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"

	"github.com/imranp/kerf/backend/internal/middleware"
	"github.com/imranp/kerf/backend/internal/models"
)

// ListMembers returns the project's members (anyone with project access can read).
func (d *Deps) ListMembers(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}
	rows, err := d.Pool.Query(r.Context(), `
		select m.user_id, m.project_id, m.role, m.created_at,
		       u.id, u.email, u.name, u.avatar_url, u.account_role, u.is_system, u.created_at
		from project_members m
		join users u on u.id = m.user_id
		where m.project_id = $1
		order by m.created_at asc
	`, pid)
	if err != nil {
		genericServerError(w, err)
		return
	}
	defer rows.Close()
	out := []models.Member{}
	for rows.Next() {
		var m models.Member
		if err := rows.Scan(&m.UserID, &m.ProjectID, &m.Role, &m.CreatedAt,
			&m.User.ID, &m.User.Email, &m.User.Name, &m.User.AvatarURL, &m.User.AccountRole, &m.User.IsSystem, &m.User.CreatedAt); err != nil {
			genericServerError(w, err)
			return
		}
		out = append(out, m)
	}
	writeJSON(w, http.StatusOK, out)
}

type addMemberReq struct {
	Email string `json:"email"`
	Role  string `json:"role"`
}

// AddMember invites a user to the project (owner only).
func (d *Deps) AddMember(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	if !requireOwner(w, r, d.Pool, pid, uid) {
		return
	}
	var body addMemberReq
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	body.Email = strings.TrimSpace(strings.ToLower(body.Email))
	if body.Email == "" {
		writeError(w, http.StatusBadRequest, "email is required")
		return
	}
	if body.Role != "editor" && body.Role != "viewer" && body.Role != "owner" {
		writeError(w, http.StatusBadRequest, "invalid role")
		return
	}
	var u models.User
	err := d.Pool.QueryRow(r.Context(),
		`select id, email, name, avatar_url, account_role, is_system, created_at from users where email = $1`,
		body.Email).Scan(&u.ID, &u.Email, &u.Name, &u.AvatarURL, &u.AccountRole, &u.IsSystem, &u.CreatedAt)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "user not found")
			return
		}
		genericServerError(w, err)
		return
	}
	var m models.Member
	err = d.Pool.QueryRow(r.Context(), `
		insert into project_members(project_id, user_id, role)
		values ($1,$2,$3)
		on conflict (project_id, user_id) do update set role = excluded.role
		returning user_id, project_id, role, created_at
	`, pid, u.ID, body.Role).Scan(&m.UserID, &m.ProjectID, &m.Role, &m.CreatedAt)
	if err != nil {
		genericServerError(w, err)
		return
	}
	m.User = u
	writeJSON(w, http.StatusCreated, m)
}

type updateMemberReq struct {
	Role string `json:"role"`
}

// UpdateMember changes a member's role (owner only).
func (d *Deps) UpdateMember(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	memberID := chi.URLParam(r, "uid")
	if !requireOwner(w, r, d.Pool, pid, uid) {
		return
	}
	var body updateMemberReq
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if body.Role != "editor" && body.Role != "viewer" && body.Role != "owner" {
		writeError(w, http.StatusBadRequest, "invalid role")
		return
	}
	var m models.Member
	err := d.Pool.QueryRow(r.Context(), `
		update project_members set role = $3
		where project_id = $1 and user_id = $2
		returning user_id, project_id, role, created_at
	`, pid, memberID, body.Role).Scan(&m.UserID, &m.ProjectID, &m.Role, &m.CreatedAt)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "member not found")
			return
		}
		genericServerError(w, err)
		return
	}
	if err := d.Pool.QueryRow(r.Context(),
		`select id, email, name, avatar_url, account_role, is_system, created_at from users where id = $1`,
		memberID).Scan(&m.User.ID, &m.User.Email, &m.User.Name, &m.User.AvatarURL, &m.User.AccountRole, &m.User.IsSystem, &m.User.CreatedAt); err != nil {
		genericServerError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, m)
}

// RemoveMember removes a member (owner only). Cannot remove the project owner.
func (d *Deps) RemoveMember(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	memberID := chi.URLParam(r, "uid")
	if !requireOwner(w, r, d.Pool, pid, uid) {
		return
	}
	var ownerID string
	err := d.Pool.QueryRow(r.Context(), `select owner_id from projects where id = $1`, pid).Scan(&ownerID)
	if err != nil {
		genericServerError(w, err)
		return
	}
	if ownerID == memberID {
		writeError(w, http.StatusBadRequest, "cannot remove project owner")
		return
	}
	if _, err := d.Pool.Exec(r.Context(),
		`delete from project_members where project_id = $1 and user_id = $2`,
		pid, memberID); err != nil {
		genericServerError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
