package handlers

import (
	"errors"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"

	"github.com/imranp/kerf/backend/internal/middleware"
	"github.com/imranp/kerf/backend/internal/models"
)

// ListFiles returns the project's full file tree without content.
func (d *Deps) ListFiles(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}
	rows, err := d.Pool.Query(r.Context(), `
		select id, project_id, parent_id, name, kind, storage_key, mime_type, size, created_at, updated_at
		from files
		where project_id = $1
		order by kind desc, name asc
	`, pid)
	if err != nil {
		genericServerError(w, err)
		return
	}
	defer rows.Close()
	out := []models.File{}
	for rows.Next() {
		var f models.File
		if err := rows.Scan(&f.ID, &f.ProjectID, &f.ParentID, &f.Name, &f.Kind, &f.StorageKey, &f.MimeType, &f.Size, &f.CreatedAt, &f.UpdatedAt); err != nil {
			genericServerError(w, err)
			return
		}
		d.attachDownloadURL(&f)
		out = append(out, f)
	}
	writeJSON(w, http.StatusOK, out)
}

// attachDownloadURL sets the DownloadURL for files backed by Storage.
func (d *Deps) attachDownloadURL(f *models.File) {
	if f.StorageKey == nil || *f.StorageKey == "" {
		return
	}
	url := "/api/projects/" + f.ProjectID + "/files/" + f.ID + "/download"
	f.DownloadURL = &url
}

type createFileReq struct {
	Name     string  `json:"name"`
	Kind     string  `json:"kind"`
	ParentID *string `json:"parent_id"`
	Content  *string `json:"content"`
}

// CreateFile creates a file or folder.
func (d *Deps) CreateFile(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	role := requireMember(w, r, d.Pool, pid, uid)
	if role == "" {
		return
	}
	if role == "viewer" {
		writeError(w, http.StatusForbidden, "viewer cannot create files")
		return
	}
	var body createFileReq
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if body.Name == "" {
		writeError(w, http.StatusBadRequest, "name is required")
		return
	}
	if body.Kind == "" {
		body.Kind = "file"
	}
	if body.Kind != "file" && body.Kind != "folder" && body.Kind != "assembly" {
		writeError(w, http.StatusBadRequest, "invalid kind")
		return
	}
	content := ""
	if body.Content != nil {
		content = *body.Content
	}
	var f models.File
	err := d.Pool.QueryRow(r.Context(), `
		insert into files(project_id, parent_id, name, kind, content)
		values ($1,$2,$3,$4,$5)
		returning id, project_id, parent_id, name, kind, content, storage_key, mime_type, size, created_at, updated_at
	`, pid, body.ParentID, body.Name, body.Kind, content).Scan(
		&f.ID, &f.ProjectID, &f.ParentID, &f.Name, &f.Kind, &f.Content, &f.StorageKey, &f.MimeType, &f.Size, &f.CreatedAt, &f.UpdatedAt)
	if err != nil {
		genericServerError(w, err)
		return
	}
	d.attachDownloadURL(&f)
	writeJSON(w, http.StatusCreated, f)
}

// GetFile returns a single file with content.
func (d *Deps) GetFile(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	fid := chi.URLParam(r, "fid")
	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}
	var f models.File
	err := d.Pool.QueryRow(r.Context(), `
		select id, project_id, parent_id, name, kind, content, storage_key, mime_type, size, created_at, updated_at
		from files where id = $1 and project_id = $2
	`, fid, pid).Scan(&f.ID, &f.ProjectID, &f.ParentID, &f.Name, &f.Kind, &f.Content, &f.StorageKey, &f.MimeType, &f.Size, &f.CreatedAt, &f.UpdatedAt)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "file not found")
			return
		}
		genericServerError(w, err)
		return
	}
	d.attachDownloadURL(&f)
	writeJSON(w, http.StatusOK, f)
}

type updateFileReq struct {
	Name     *string `json:"name"`
	Content  *string `json:"content"`
	ParentID *string `json:"parent_id"`
}

// UpdateFile patches a file's name/content/parent.
func (d *Deps) UpdateFile(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	fid := chi.URLParam(r, "fid")
	role := requireMember(w, r, d.Pool, pid, uid)
	if role == "" {
		return
	}
	if role == "viewer" {
		writeError(w, http.StatusForbidden, "viewer cannot edit files")
		return
	}
	var body updateFileReq
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	var f models.File
	err := d.Pool.QueryRow(r.Context(), `
		update files set
			name      = coalesce($3, name),
			content   = coalesce($4, content),
			parent_id = case when $5::boolean then $6 else parent_id end,
			updated_at = now()
		where id = $1 and project_id = $2
		returning id, project_id, parent_id, name, kind, content, storage_key, mime_type, size, created_at, updated_at
	`, fid, pid, body.Name, body.Content, body.ParentID != nil, body.ParentID).Scan(
		&f.ID, &f.ProjectID, &f.ParentID, &f.Name, &f.Kind, &f.Content, &f.StorageKey, &f.MimeType, &f.Size, &f.CreatedAt, &f.UpdatedAt)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "file not found")
			return
		}
		genericServerError(w, err)
		return
	}
	d.attachDownloadURL(&f)
	writeJSON(w, http.StatusOK, f)
}

// DeleteFile removes a file (cascades to children).
func (d *Deps) DeleteFile(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	fid := chi.URLParam(r, "fid")
	role := requireMember(w, r, d.Pool, pid, uid)
	if role == "" {
		return
	}
	if role == "viewer" {
		writeError(w, http.StatusForbidden, "viewer cannot delete files")
		return
	}
	// Capture storage_key (if any) before deleting so we can clean up the blob.
	var storageKey *string
	_ = d.Pool.QueryRow(r.Context(),
		`select storage_key from files where id = $1 and project_id = $2`, fid, pid).Scan(&storageKey)
	if _, err := d.Pool.Exec(r.Context(),
		`delete from files where id = $1 and project_id = $2`, fid, pid); err != nil {
		genericServerError(w, err)
		return
	}
	if d.Storage != nil && storageKey != nil && *storageKey != "" {
		_ = d.Storage.Delete(r.Context(), *storageKey)
	}
	w.WriteHeader(http.StatusNoContent)
}
