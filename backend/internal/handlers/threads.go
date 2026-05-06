package handlers

import (
	"errors"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"

	"github.com/imranp/kerf/backend/internal/middleware"
	"github.com/imranp/kerf/backend/internal/models"
)


// ListThreads returns threads for a project, optionally filtered by file_id.
func (d *Deps) ListThreads(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}
	fileID := r.URL.Query().Get("file_id")
	var (
		rows pgx.Rows
		err  error
	)
	if fileID != "" {
		rows, err = d.Pool.Query(r.Context(), `
			select id, project_id, file_id, title, is_starred, last_message_at, created_at
			from chat_threads
			where project_id = $1 and file_id = $2
			order by coalesce(last_message_at, created_at) desc
		`, pid, fileID)
	} else {
		rows, err = d.Pool.Query(r.Context(), `
			select id, project_id, file_id, title, is_starred, last_message_at, created_at
			from chat_threads
			where project_id = $1
			order by coalesce(last_message_at, created_at) desc
		`, pid)
	}
	if err != nil {
		genericServerError(w, err)
		return
	}
	defer rows.Close()
	out := []models.Thread{}
	for rows.Next() {
		var t models.Thread
		if err := rows.Scan(&t.ID, &t.ProjectID, &t.FileID, &t.Title, &t.IsStarred, &t.LastMessageAt, &t.CreatedAt); err != nil {
			genericServerError(w, err)
			return
		}
		out = append(out, t)
	}
	writeJSON(w, http.StatusOK, out)
}

type createThreadReq struct {
	Title  string  `json:"title"`
	FileID *string `json:"file_id"`
}

// CreateThread creates a thread, then evicts oldest non-starred threads beyond the cap.
func (d *Deps) CreateThread(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	role := requireMember(w, r, d.Pool, pid, uid)
	if role == "" {
		return
	}
	if role == "viewer" {
		writeError(w, http.StatusForbidden, "viewer cannot create threads")
		return
	}
	var body createThreadReq
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if body.Title == "" {
		body.Title = "New chat"
	}
	var t models.Thread
	err := d.Pool.QueryRow(r.Context(), `
		insert into chat_threads(project_id, file_id, title)
		values ($1,$2,$3)
		returning id, project_id, file_id, title, is_starred, last_message_at, created_at
	`, pid, body.FileID, body.Title).Scan(
		&t.ID, &t.ProjectID, &t.FileID, &t.Title, &t.IsStarred, &t.LastMessageAt, &t.CreatedAt)
	if err != nil {
		genericServerError(w, err)
		return
	}
	d.evictOldThreads(r, pid)
	writeJSON(w, http.StatusCreated, t)
}

func (d *Deps) evictOldThreads(r *http.Request, projectID string) {
	cap := d.Cfg.MaxThreadsPerProject
	if cap <= 0 {
		return
	}
	_, _ = d.Pool.Exec(r.Context(), `
		delete from chat_threads
		where id in (
			select id from chat_threads
			where project_id = $1 and is_starred = false
			order by coalesce(last_message_at, created_at) desc
			offset $2
		)
	`, projectID, cap)
}

type updateThreadReq struct {
	Title     *string `json:"title"`
	IsStarred *bool   `json:"is_starred"`
}

// UpdateThread patches the thread title or star state.
func (d *Deps) UpdateThread(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	tid := chi.URLParam(r, "tid")
	role := requireMember(w, r, d.Pool, pid, uid)
	if role == "" {
		return
	}
	if role == "viewer" {
		writeError(w, http.StatusForbidden, "viewer cannot edit threads")
		return
	}
	var body updateThreadReq
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	var t models.Thread
	err := d.Pool.QueryRow(r.Context(), `
		update chat_threads set
			title      = coalesce($3, title),
			is_starred = coalesce($4, is_starred),
			updated_at = now()
		where id = $1 and project_id = $2
		returning id, project_id, file_id, title, is_starred, last_message_at, created_at
	`, tid, pid, body.Title, body.IsStarred).Scan(
		&t.ID, &t.ProjectID, &t.FileID, &t.Title, &t.IsStarred, &t.LastMessageAt, &t.CreatedAt)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "thread not found")
			return
		}
		genericServerError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, t)
}

// DeleteThread removes a thread (cascades to messages).
func (d *Deps) DeleteThread(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	tid := chi.URLParam(r, "tid")
	role := requireMember(w, r, d.Pool, pid, uid)
	if role == "" {
		return
	}
	if role == "viewer" {
		writeError(w, http.StatusForbidden, "viewer cannot delete threads")
		return
	}
	if _, err := d.Pool.Exec(r.Context(),
		`delete from chat_threads where id = $1 and project_id = $2`, tid, pid); err != nil {
		genericServerError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
