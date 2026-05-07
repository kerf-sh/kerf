package handlers

import (
	"context"
	"errors"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/internal/middleware"
	"github.com/imranp/kerf/backend/internal/models"
	"github.com/imranp/kerf/backend/internal/tools"
)

// FileRevision is the shape returned by the list/get endpoints. The list
// route returns ContentPreview only; the single-revision route fills Content.
type FileRevision struct {
	ID             string    `json:"id"`
	FileID         string    `json:"file_id"`
	Source         string    `json:"source"`
	UserID         *string   `json:"user_id"`
	UserName       *string   `json:"user_name,omitempty"`
	CreatedAt      time.Time `json:"created_at"`
	Content        *string   `json:"content,omitempty"`
	ContentPreview *string   `json:"content_preview,omitempty"`
}

// RecordRevision inserts a revision row for a file and prunes anything beyond
// `capacity` (oldest evicted). userID is optional — pass nil when the writer
// isn't an authenticated user (e.g. a tool call running outside the request
// auth scope, or a soft-delete with no caller info).
//
// As of Phase 4, storage is base-snapshot + Myers diff with gzip
// compression: every Nth row is a kind='base' row holding the full
// gzipped content, intervening rows store gzipped diffs against their
// parent. The internal heuristics live in `tools.WriteRevision`; this
// HTTP-flavored entrypoint just handles the userID *string → *uuid.UUID
// conversion + non-fatal error semantics callers expect.
//
// This is a best-effort write — we return the error so callers can decide
// whether to abort. In practice, callers log + continue: a missing revision
// row shouldn't fail the user's actual edit.
func RecordRevision(ctx context.Context, pool *pgxpool.Pool, fileID, content, source string, userID *string, capacity int) error {
	if pool == nil || fileID == "" {
		return nil
	}
	var uid *uuid.UUID
	if userID != nil && *userID != "" {
		u, err := uuid.Parse(*userID)
		if err == nil && u != uuid.Nil {
			uid = &u
		}
	}
	_, err := tools.WriteRevision(ctx, pool, fileID, content, source, uid, capacity)
	return err
}

// helper: returns a pointer to userID if non-empty, else nil.
func userIDPtr(uid string) *string {
	if uid == "" {
		return nil
	}
	return &uid
}

// ListRevisions returns the most-recent revisions for a file, with a 200-char
// content preview per row. Newest first. `?limit=` caps the page (default 50,
// max 200).
//
// The preview uses the dedicated content_preview column when present
// (every Phase-4 row writes it on insert) and falls back to a left()
// snapshot of the legacy plaintext column for pre-migration rows. We
// never reconstruct full content here — list-paths must stay O(1) per
// row regardless of base/diff layout.
func (d *Deps) ListRevisions(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	fid := chi.URLParam(r, "fid")
	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}
	// Confirm file exists in this project (independent of soft-delete: history
	// is still readable for soft-deleted files so they can be restored).
	var exists bool
	err := d.Pool.QueryRow(r.Context(),
		`select exists(select 1 from files where id = $1 and project_id = $2)`,
		fid, pid).Scan(&exists)
	if err != nil {
		genericServerError(w, err)
		return
	}
	if !exists {
		writeError(w, http.StatusNotFound, "file not found")
		return
	}

	limit := 50
	if v := r.URL.Query().Get("limit"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			limit = n
		}
	}
	if limit > 200 {
		limit = 200
	}

	rows, err := d.Pool.Query(r.Context(), `
		select fr.id, fr.file_id, fr.source, fr.user_id, u.name,
		       fr.created_at,
		       coalesce(fr.content_preview, left(fr.content, 200))
		  from file_revisions fr
		  left join users u on u.id = fr.user_id
		 where fr.file_id = $1
		 order by fr.created_at desc
		 limit $2
	`, fid, limit)
	if err != nil {
		genericServerError(w, err)
		return
	}
	defer rows.Close()

	out := []FileRevision{}
	for rows.Next() {
		var (
			rev      FileRevision
			userName *string
			preview  string
		)
		if err := rows.Scan(&rev.ID, &rev.FileID, &rev.Source, &rev.UserID, &userName, &rev.CreatedAt, &preview); err != nil {
			genericServerError(w, err)
			return
		}
		if userName != nil && *userName != "" {
			n := *userName
			rev.UserName = &n
		}
		p := preview
		rev.ContentPreview = &p
		out = append(out, rev)
	}
	writeJSON(w, http.StatusOK, out)
}

// GetRevision returns a single revision with full content, reconstructing
// from base + diffs as needed.
func (d *Deps) GetRevision(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	fid := chi.URLParam(r, "fid")
	rid := chi.URLParam(r, "rid")
	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}
	var (
		rev      FileRevision
		userName *string
	)
	// Pull metadata only — content comes from a reconstructor walk.
	err := d.Pool.QueryRow(r.Context(), `
		select fr.id, fr.file_id, fr.source, fr.user_id, u.name, fr.created_at
		  from file_revisions fr
		  left join users u on u.id = fr.user_id
		 inner join files f on f.id = fr.file_id
		 where fr.id = $1 and fr.file_id = $2 and f.project_id = $3
	`, rid, fid, pid).Scan(&rev.ID, &rev.FileID, &rev.Source, &rev.UserID, &userName, &rev.CreatedAt)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "revision not found")
			return
		}
		genericServerError(w, err)
		return
	}
	if userName != nil && *userName != "" {
		n := *userName
		rev.UserName = &n
	}
	content, err := tools.ReconstructRevision(r.Context(), d.Pool, rid)
	if err != nil {
		genericServerError(w, err)
		return
	}
	rev.Content = &content
	writeJSON(w, http.StatusOK, rev)
}

// RestoreRevision applies the revision's content to the file (clearing
// deleted_at if set), and inserts a new 'restore' revision row so the restore
// itself is undoable. Returns the updated File.
//
// Reconstructs the target revision via tools.ReconstructRevision; the
// restore row is itself written through the standard RecordRevision
// path, so it lands as a kind='base' (when its parent's run-length is at
// the cap) or as a normal diff against the prior write.
func (d *Deps) RestoreRevision(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	fid := chi.URLParam(r, "fid")
	rid := chi.URLParam(r, "rid")
	role := requireMember(w, r, d.Pool, pid, uid)
	if role == "" {
		return
	}
	if role == "viewer" {
		writeError(w, http.StatusForbidden, "viewer cannot restore revisions")
		return
	}

	// Confirm the revision belongs to this file + project before walking
	// the chain.
	var exists bool
	if err := d.Pool.QueryRow(r.Context(), `
		select exists(
		  select 1 from file_revisions fr
		    inner join files f on f.id = fr.file_id
		   where fr.id = $1 and fr.file_id = $2 and f.project_id = $3
		)
	`, rid, fid, pid).Scan(&exists); err != nil {
		genericServerError(w, err)
		return
	}
	if !exists {
		writeError(w, http.StatusNotFound, "revision not found")
		return
	}

	content, err := tools.ReconstructRevision(r.Context(), d.Pool, rid)
	if err != nil {
		genericServerError(w, err)
		return
	}

	// Apply: clear soft-delete, set content, bump updated_at.
	if _, err := d.Pool.Exec(r.Context(), `
		update files set
			content = $1,
			deleted_at = null,
			updated_at = now()
		 where id = $2 and project_id = $3
	`, content, fid, pid); err != nil {
		genericServerError(w, err)
		return
	}

	// Record the restore as a new revision so it's undoable.
	cap := 200
	if d.Cfg != nil && d.Cfg.FileRevisionsMax > 0 {
		cap = d.Cfg.FileRevisionsMax
	}
	if err := RecordRevision(r.Context(), d.Pool, fid, content, "restore", userIDPtr(uid), cap); err != nil {
		// Non-fatal: the file was actually restored. Log via genericServerError
		// would be wrong (it'd 500 a successful restore). Drop silently.
		_ = err
	}

	// Return the updated file.
	d.getFileForResponse(w, r, pid, fid)
}

// getFileForResponse loads + writes a file row using the same shape as GetFile,
// but as an internal helper so handlers can chain it after a mutation.
func (d *Deps) getFileForResponse(w http.ResponseWriter, r *http.Request, pid, fid string) {
	var f models.File
	err := d.Pool.QueryRow(r.Context(), `
		select id, project_id, parent_id, name, kind, content, storage_key, mime_type, size, created_at, updated_at
		  from files where id = $1 and project_id = $2 and deleted_at is null
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
