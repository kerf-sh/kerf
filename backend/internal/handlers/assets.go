package handlers

import (
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/imranp/kerf/backend/internal/middleware"
	"github.com/imranp/kerf/backend/internal/models"
)

// upload limits.
const (
	maxAssetBytes  = 100 * 1024 * 1024 // 100 MB hard cap on multipart body.
	maxStepBytes   = 50 * 1024 * 1024
	signedURLBytes = 5 * 1024 * 1024 // files >5MB redirect when presigned URLs are available.
	signedURLTTL   = 15 * time.Minute
)

// UploadAsset handles `POST /api/projects/{pid}/assets` (multipart).
//
//   - field `file`      — the binary
//   - field `kind`      — must be "step" in v1
//   - field `parent_id` — optional UUID of parent folder
func (d *Deps) UploadAsset(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	role := requireMember(w, r, d.Pool, pid, uid)
	if role == "" {
		return
	}
	if role == "viewer" {
		writeError(w, http.StatusForbidden, "viewer cannot upload")
		return
	}
	if d.Storage == nil {
		writeError(w, http.StatusServiceUnavailable, "storage not configured")
		return
	}

	r.Body = http.MaxBytesReader(w, r.Body, maxAssetBytes)
	if err := r.ParseMultipartForm(32 << 20); err != nil {
		writeError(w, http.StatusBadRequest, "invalid multipart body: "+err.Error())
		return
	}

	kind := strings.TrimSpace(r.FormValue("kind"))
	if kind == "" {
		kind = "step"
	}
	if kind != "step" {
		writeError(w, http.StatusBadRequest, "only kind='step' is supported")
		return
	}

	file, fhdr, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, "missing 'file' field")
		return
	}
	defer file.Close()

	if fhdr.Size > maxStepBytes {
		writeError(w, http.StatusRequestEntityTooLarge, "file too large (>50MB)")
		return
	}

	// Optional parent_id.
	var parentID *string
	if v := strings.TrimSpace(r.FormValue("parent_id")); v != "" {
		if _, err := uuid.Parse(v); err != nil {
			writeError(w, http.StatusBadRequest, "invalid parent_id")
			return
		}
		// Verify parent belongs to project and is a folder.
		var pkind string
		if err := d.Pool.QueryRow(r.Context(),
			`select kind from files where id = $1 and project_id = $2`,
			v, pid).Scan(&pkind); err != nil {
			if errors.Is(err, pgx.ErrNoRows) {
				writeError(w, http.StatusBadRequest, "parent not found")
				return
			}
			genericServerError(w, err)
			return
		}
		if pkind != "folder" {
			writeError(w, http.StatusBadRequest, "parent must be a folder")
			return
		}
		parentID = &v
	}

	contentType := fhdr.Header.Get("Content-Type")
	if contentType == "" {
		contentType = guessAssetContentType(fhdr.Filename)
	}

	key := fmt.Sprintf("projects/%s/assets/%s-%s",
		pid, uuid.New().String(), sanitizeFilename(fhdr.Filename))

	pr, err := d.Storage.Put(r.Context(), key, file, contentType, fhdr.Size)
	if err != nil {
		genericServerError(w, err)
		return
	}

	var f models.File
	err = d.Pool.QueryRow(r.Context(), `
		insert into files(project_id, parent_id, name, kind, content, storage_key, mime_type, size)
		values ($1,$2,$3,'step','',$4,$5,$6)
		returning id, project_id, parent_id, name, kind, content, storage_key, mime_type, size, created_at, updated_at
	`, pid, parentID, fhdr.Filename, key, pr.ContentType, pr.Size).Scan(
		&f.ID, &f.ProjectID, &f.ParentID, &f.Name, &f.Kind, &f.Content,
		&f.StorageKey, &f.MimeType, &f.Size, &f.CreatedAt, &f.UpdatedAt)
	if err != nil {
		_ = d.Storage.Delete(r.Context(), key)
		genericServerError(w, err)
		return
	}
	d.attachDownloadURL(&f)
	writeJSON(w, http.StatusCreated, f)
}

// DownloadFile streams (or redirects to) the binary asset behind a file row.
func (d *Deps) DownloadFile(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	fid := chi.URLParam(r, "fid")
	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}
	var (
		name        string
		key         *string
		mimeType    *string
		size        *int64
	)
	err := d.Pool.QueryRow(r.Context(),
		`select name, storage_key, mime_type, size from files where id = $1 and project_id = $2`,
		fid, pid).Scan(&name, &key, &mimeType, &size)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "file not found")
			return
		}
		genericServerError(w, err)
		return
	}
	if key == nil || *key == "" {
		writeError(w, http.StatusBadRequest, "file has no storage backing")
		return
	}
	if d.Storage == nil {
		writeError(w, http.StatusServiceUnavailable, "storage not configured")
		return
	}

	// Big-file optimization: redirect to a presigned URL if available.
	if size != nil && *size >= signedURLBytes {
		if signed, err := d.Storage.SignedURL(r.Context(), *key, signedURLTTL); err == nil && signed != "" {
			http.Redirect(w, r, signed, http.StatusFound)
			return
		}
	}

	rc, ct, err := d.Storage.Get(r.Context(), *key)
	if err != nil {
		writeError(w, http.StatusNotFound, "blob not found")
		return
	}
	defer rc.Close()
	if mimeType != nil && *mimeType != "" {
		ct = *mimeType
	}
	w.Header().Set("Content-Type", ct)
	if size != nil && *size > 0 {
		w.Header().Set("Content-Length", strconv.FormatInt(*size, 10))
	}
	w.Header().Set("Content-Disposition", `attachment; filename="`+sanitizeFilename(name)+`"`)
	_, _ = io.Copy(w, rc)
}

// ServeBlob serves an arbitrary storage key (local backend only).
// Auth + project-membership is enforced by looking up the storage_key against
// the files table and checking the caller's role on the owning project.
func (d *Deps) ServeBlob(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	if uid == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return
	}
	if d.Storage == nil {
		writeError(w, http.StatusServiceUnavailable, "storage not configured")
		return
	}
	rawKey := chi.URLParam(r, "*")
	if rawKey == "" {
		// /api/blobs/{key} → key is the entire wildcard suffix.
		rawKey = chi.URLParam(r, "key")
	}
	if rawKey == "" {
		writeError(w, http.StatusBadRequest, "missing key")
		return
	}
	// chi already URL-decodes path params, but be safe.
	if dec, err := url.PathUnescape(rawKey); err == nil {
		rawKey = dec
	}

	var (
		projectID string
		name      string
		mimeType  *string
		size      *int64
	)
	err := d.Pool.QueryRow(r.Context(),
		`select project_id, name, mime_type, size from files where storage_key = $1`,
		rawKey).Scan(&projectID, &name, &mimeType, &size)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "blob not found")
			return
		}
		genericServerError(w, err)
		return
	}

	role, _, err := projectRole(r.Context(), d.Pool, projectID, uid)
	if err != nil {
		genericServerError(w, err)
		return
	}
	if role == "" {
		writeError(w, http.StatusForbidden, "forbidden")
		return
	}

	rc, ct, err := d.Storage.Get(r.Context(), rawKey)
	if err != nil {
		writeError(w, http.StatusNotFound, "blob not found")
		return
	}
	defer rc.Close()
	if mimeType != nil && *mimeType != "" {
		ct = *mimeType
	}
	w.Header().Set("Content-Type", ct)
	if size != nil && *size > 0 {
		w.Header().Set("Content-Length", strconv.FormatInt(*size, 10))
	}
	w.Header().Set("Content-Disposition", `inline; filename="`+sanitizeFilename(name)+`"`)
	_, _ = io.Copy(w, rc)
}

func sanitizeFilename(name string) string {
	name = filepath.Base(name)
	if name == "." || name == "/" || name == "" {
		return "download"
	}
	var b strings.Builder
	for _, r := range name {
		if r == '"' || r == '\\' || r == '\n' || r == '\r' {
			b.WriteByte('_')
			continue
		}
		b.WriteRune(r)
	}
	return b.String()
}

func guessAssetContentType(name string) string {
	ext := strings.ToLower(filepath.Ext(name))
	switch ext {
	case ".step", ".stp":
		return "model/step"
	}
	return "application/octet-stream"
}
