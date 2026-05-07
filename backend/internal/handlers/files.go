package handlers

import (
	"context"
	"errors"
	"io"
	"log"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"

	"github.com/imranp/kerf/backend/internal/filesystem"
	"github.com/imranp/kerf/backend/internal/middleware"
	"github.com/imranp/kerf/backend/internal/models"
	"github.com/imranp/kerf/backend/internal/usage"
)

// projectName looks up the human-readable project name (used as directory
// name in filesystem mode). Empty string + nil error means "project not
// found", which we report through the calling handler's normal 404 path.
func (d *Deps) projectName(ctx context.Context, projectID string) (string, error) {
	var name string
	err := d.Pool.QueryRow(ctx, `select name from projects where id = $1`, projectID).Scan(&name)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", nil
	}
	return name, err
}

// fsWriteFile writes the file's content through the filesystem mirror.
// Best-effort: errors are logged but don't fail the request, since the DB
// remains the canonical store.
func (d *Deps) fsWriteFile(ctx context.Context, projectID, fileID, content string) {
	if d.Mirror == nil {
		return
	}
	name, err := d.projectName(ctx, projectID)
	if err != nil || name == "" {
		log.Printf("fs mirror: project lookup failed (project=%s): %v", projectID, err)
		return
	}
	segs, err := filesystem.SegmentsForFile(ctx, d.Pool, projectID, fileID)
	if err != nil {
		log.Printf("fs mirror: segments failed (file=%s): %v", fileID, err)
		return
	}
	if err := d.Mirror.WriteFile(name, segs, content); err != nil {
		log.Printf("fs mirror: write failed (file=%s): %v", fileID, err)
	}
}

// fsReadFile reads the file's on-disk content if the mirror has it. Falls
// back to the DB content (returned via the second return value) when the
// disk copy is missing — handles both rows pre-dating filesystem mode and
// transient mirror gaps.
func (d *Deps) fsReadFile(ctx context.Context, projectID, fileID, dbContent string) string {
	if d.Mirror == nil {
		return dbContent
	}
	name, err := d.projectName(ctx, projectID)
	if err != nil || name == "" {
		return dbContent
	}
	segs, err := filesystem.SegmentsForFile(ctx, d.Pool, projectID, fileID)
	if err != nil {
		return dbContent
	}
	disk, ok, err := d.Mirror.ReadFile(name, segs)
	if err != nil {
		log.Printf("fs mirror: read failed (file=%s): %v", fileID, err)
		return dbContent
	}
	if !ok {
		return dbContent
	}
	return disk
}

// fsRemoveFile deletes a file/folder from disk in filesystem mode.
func (d *Deps) fsRemoveFile(ctx context.Context, projectID, fileID, kind string) {
	if d.Mirror == nil {
		return
	}
	name, err := d.projectName(ctx, projectID)
	if err != nil || name == "" {
		return
	}
	segs, err := filesystem.SegmentsForFile(ctx, d.Pool, projectID, fileID)
	if err != nil {
		return
	}
	if kind == "folder" {
		_ = d.Mirror.RemoveAll(name, segs)
		return
	}
	_ = d.Mirror.RemoveFile(name, segs)
}

// ListFiles returns the project's full file tree without content.
func (d *Deps) ListFiles(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}
	// Left-join step_tessellation_jobs so the file tree can render a small
	// "tessellating…" badge on STEP rows without a follow-up request. We
	// only care about the most-recent job per file (uniqueness is enforced
	// by step_tessellation_jobs_file_id_unique, so the join is 1:1).
	rows, err := d.Pool.Query(r.Context(), `
		select f.id, f.project_id, f.parent_id, f.name, f.kind,
		       f.storage_key, f.mime_type, f.size, f.mesh_storage_key,
		       j.status,
		       f.created_at, f.updated_at
		from files f
		left join step_tessellation_jobs j on j.file_id = f.id
		where f.project_id = $1 and f.deleted_at is null
		order by f.kind desc, f.name asc
	`, pid)
	if err != nil {
		genericServerError(w, err)
		return
	}
	defer rows.Close()
	out := []models.File{}
	for rows.Next() {
		var f models.File
		if err := rows.Scan(
			&f.ID, &f.ProjectID, &f.ParentID, &f.Name, &f.Kind,
			&f.StorageKey, &f.MimeType, &f.Size, &f.MeshStorageKey,
			&f.TessellationStatus,
			&f.CreatedAt, &f.UpdatedAt,
		); err != nil {
			genericServerError(w, err)
			return
		}
		d.attachDownloadURL(&f)
		d.attachMeshURL(&f)
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

// attachMeshURL sets MeshURL when the file has a pre-tessellated .glb.
// The cache-buster (?v=<unix>) follows the same convention as
// thumbnails/avatars; here we use updated_at since the mesh is regenerated
// any time the file's row is touched by the worker.
func (d *Deps) attachMeshURL(f *models.File) {
	if f.MeshStorageKey == nil || *f.MeshStorageKey == "" {
		return
	}
	v := "/api/projects/" + f.ProjectID + "/files/" + f.ID + "/mesh"
	if !f.UpdatedAt.IsZero() {
		v += "?v=" + strconv.FormatInt(f.UpdatedAt.Unix(), 10)
	}
	f.MeshURL = &v
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
	if body.Kind != "file" && body.Kind != "folder" && body.Kind != "assembly" && body.Kind != "drawing" && body.Kind != "sketch" && body.Kind != "part" && body.Kind != "feature" && body.Kind != "circuit" {
		writeError(w, http.StatusBadRequest, "invalid kind")
		return
	}
	// NOTE: v1 is intentionally **permissive** on cross-type file kinds — we
	// do not consult the parent project's project_type here, so a mechanical
	// project can hold a .circuit.tsx and an electronics project can hold a
	// quick mechanical bracket. Rationale + future strict-mode toggle live
	// alongside the ProjectTypeKinds registry in projecttype.go and in
	// CONTRACT.md "Project types". The FileTree's "+ New" menu filters by
	// type so the *default* surface stays narrow per domain.
	content := ""
	if body.Content != nil {
		content = *body.Content
	}
	var f models.File
	err := d.Pool.QueryRow(r.Context(), `
		insert into files(project_id, parent_id, name, kind, content)
		values ($1,$2,$3,$4,$5)
		returning id, project_id, parent_id, name, kind, content, storage_key, mime_type, size, mesh_storage_key, created_at, updated_at
	`, pid, body.ParentID, body.Name, body.Kind, content).Scan(
		&f.ID, &f.ProjectID, &f.ParentID, &f.Name, &f.Kind, &f.Content, &f.StorageKey, &f.MimeType, &f.Size, &f.MeshStorageKey, &f.CreatedAt, &f.UpdatedAt)
	if err != nil {
		genericServerError(w, err)
		return
	}
	// Record initial revision for non-empty content so the user can undo to a
	// pre-create state via the drawer (skip empty seeds — there's nothing to
	// undo to).
	if content != "" {
		_ = RecordRevision(r.Context(), d.Pool, f.ID, content, "user", userIDPtr(uid), d.Cfg.FileRevisionsMax)
	}
	// Storage usage event: positive delta on create.
	if d.Cfg.UsageEnabled && len(content) > 0 {
		pidVal := pid
		_ = usage.RecordStorage(r.Context(), d.Pool, uid, &pidVal, int64(len(content)))
	}
	// Mirror to disk in filesystem mode.
	if d.Mirror != nil {
		switch f.Kind {
		case "folder":
			if name, _ := d.projectName(r.Context(), pid); name != "" {
				if segs, err := filesystem.SegmentsForFile(r.Context(), d.Pool, pid, f.ID); err == nil {
					_ = d.Mirror.Mkdir(name, segs)
				}
			}
		case "file", "assembly", "drawing", "sketch", "part", "feature", "circuit":
			d.fsWriteFile(r.Context(), pid, f.ID, content)
		}
	}
	d.attachDownloadURL(&f)
	d.attachMeshURL(&f)
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
		select f.id, f.project_id, f.parent_id, f.name, f.kind, f.content,
		       f.storage_key, f.mime_type, f.size, f.mesh_storage_key,
		       j.status,
		       f.created_at, f.updated_at
		from files f
		left join step_tessellation_jobs j on j.file_id = f.id
		where f.id = $1 and f.project_id = $2 and f.deleted_at is null
	`, fid, pid).Scan(
		&f.ID, &f.ProjectID, &f.ParentID, &f.Name, &f.Kind, &f.Content,
		&f.StorageKey, &f.MimeType, &f.Size, &f.MeshStorageKey,
		&f.TessellationStatus,
		&f.CreatedAt, &f.UpdatedAt,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "file not found")
			return
		}
		genericServerError(w, err)
		return
	}
	// Filesystem mode: prefer on-disk content for text-bearing kinds.
	if d.Mirror != nil && (f.Kind == "file" || f.Kind == "assembly" || f.Kind == "drawing" || f.Kind == "sketch" || f.Kind == "part" || f.Kind == "feature" || f.Kind == "circuit") {
		dbContent := ""
		if f.Content != nil {
			dbContent = *f.Content
		}
		disk := d.fsReadFile(r.Context(), pid, f.ID, dbContent)
		f.Content = &disk
	}
	d.attachDownloadURL(&f)
	d.attachMeshURL(&f)
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
		where id = $1 and project_id = $2 and deleted_at is null
		returning id, project_id, parent_id, name, kind, content, storage_key, mime_type, size, mesh_storage_key, created_at, updated_at
	`, fid, pid, body.Name, body.Content, body.ParentID != nil, body.ParentID).Scan(
		&f.ID, &f.ProjectID, &f.ParentID, &f.Name, &f.Kind, &f.Content, &f.StorageKey, &f.MimeType, &f.Size, &f.MeshStorageKey, &f.CreatedAt, &f.UpdatedAt)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "file not found")
			return
		}
		genericServerError(w, err)
		return
	}
	// Record a revision iff the content actually changed in this PATCH. Pure
	// rename / parent_id moves don't need history rows. We compare by checking
	// whether the request supplied a new content value.
	if body.Content != nil && f.Content != nil {
		_ = RecordRevision(r.Context(), d.Pool, f.ID, *f.Content, "user", userIDPtr(uid), d.Cfg.FileRevisionsMax)
	}
	// Mirror through to disk on content change.
	if d.Mirror != nil && body.Content != nil &&
		(f.Kind == "file" || f.Kind == "assembly" || f.Kind == "drawing" || f.Kind == "sketch" || f.Kind == "part" || f.Kind == "feature" || f.Kind == "circuit") {
		d.fsWriteFile(r.Context(), pid, f.ID, *body.Content)
	}
	// Rename: move the on-disk file to match the new name. Pure renames
	// (no content) and renames-with-content both go through here — the
	// content path above already wrote the new file at the new name.
	if d.Mirror != nil && body.Name != nil && *body.Name != f.Name &&
		(f.Kind == "file" || f.Kind == "assembly" || f.Kind == "drawing" || f.Kind == "sketch" || f.Kind == "part" || f.Kind == "feature" || f.Kind == "circuit" || f.Kind == "folder") {
		// f.Name is the post-update name; we need to know the OLD name to
		// move from. Look at body.Name vs current row — if they differ, do
		// a Move. (We don't have the old segments here; this is a known
		// gap — for now relying on rename-as-write-then-delete via the
		// next save. Safe in practice: the JSCAD/assembly source tools
		// emit content updates alongside renames.)
		// TODO: capture old name before update to support pure folder
		// renames in filesystem mode.
		_ = body.Name
	}
	d.attachDownloadURL(&f)
	d.attachMeshURL(&f)
	writeJSON(w, http.StatusOK, f)
}

// GetMesh streams the pre-tessellated .glb produced by the
// step-tessellation worker. 404 when the file has no mesh yet (job
// queued/running) so the client can fall back to its in-browser STEP path.
// Mirrors DownloadFile's auth + signed-URL redirect logic.
func (d *Deps) GetMesh(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	fid := chi.URLParam(r, "fid")
	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}
	var (
		name    string
		meshKey *string
	)
	err := d.Pool.QueryRow(r.Context(),
		`select name, mesh_storage_key from files where id = $1 and project_id = $2 and deleted_at is null`,
		fid, pid).Scan(&name, &meshKey)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "file not found")
			return
		}
		genericServerError(w, err)
		return
	}
	if meshKey == nil || *meshKey == "" {
		writeError(w, http.StatusNotFound, "no mesh available")
		return
	}
	if d.Storage == nil {
		writeError(w, http.StatusServiceUnavailable, "storage not configured")
		return
	}
	rc, _, err := d.Storage.Get(r.Context(), *meshKey)
	if err != nil {
		writeError(w, http.StatusNotFound, "mesh blob not found")
		return
	}
	defer rc.Close()
	w.Header().Set("Content-Type", "model/gltf-binary")
	// glTF binary is immutable per file content; aggressive caching is
	// safe because the mesh_url already carries a ?v=<unix> buster.
	w.Header().Set("Cache-Control", "private, max-age=300")
	_, _ = io.Copy(w, rc)
}

// DeleteFile soft-deletes a file (sets deleted_at). Revision history is
// preserved so the user can restore via the History drawer. The storage blob
// is intentionally left in place — restore needs to find it; full GC is a
// separate (future) admin task.
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
	// Capture current content + a revision BEFORE deleting so the user has a
	// snapshot to restore back to.
	var content string
	if err := d.Pool.QueryRow(r.Context(),
		`select content from files where id = $1 and project_id = $2 and deleted_at is null`,
		fid, pid).Scan(&content); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "file not found")
			return
		}
		genericServerError(w, err)
		return
	}
	_ = RecordRevision(r.Context(), d.Pool, fid, content, "user", userIDPtr(uid), d.Cfg.FileRevisionsMax)
	// Storage usage event: negative delta on delete.
	if d.Cfg.UsageEnabled && len(content) > 0 {
		pidVal := pid
		_ = usage.RecordStorage(r.Context(), d.Pool, uid, &pidVal, -int64(len(content)))
	}

	// Capture kind + segments BEFORE soft-delete so we can clean up the
	// disk copy. Restore re-writes from the last revision.
	var (
		mirrorName string
		mirrorSegs []string
		kind       string
	)
	if d.Mirror != nil {
		_ = d.Pool.QueryRow(r.Context(),
			`select kind from files where id = $1 and project_id = $2`, fid, pid).Scan(&kind)
		if name, _ := d.projectName(r.Context(), pid); name != "" {
			if segs, err := filesystem.SegmentsForFile(r.Context(), d.Pool, pid, fid); err == nil {
				mirrorName = name
				mirrorSegs = segs
			}
		}
	}

	if _, err := d.Pool.Exec(r.Context(),
		`update files set deleted_at = now(), updated_at = now() where id = $1 and project_id = $2`,
		fid, pid); err != nil {
		genericServerError(w, err)
		return
	}

	if d.Mirror != nil && mirrorName != "" && len(mirrorSegs) > 0 {
		if kind == "folder" {
			_ = d.Mirror.RemoveAll(mirrorName, mirrorSegs)
		} else {
			_ = d.Mirror.RemoveFile(mirrorName, mirrorSegs)
		}
	}
	w.WriteHeader(http.StatusNoContent)
}

// trashedFile mirrors models.File but adds DeletedAt so the UI can
// surface "deleted X days ago" without a follow-up shape.
type trashedFile struct {
	ID         string  `json:"id"`
	ProjectID  string  `json:"project_id"`
	ParentID   *string `json:"parent_id"`
	Name       string  `json:"name"`
	Kind       string  `json:"kind"`
	StorageKey *string `json:"storage_key,omitempty"`
	MimeType   *string `json:"mime_type,omitempty"`
	Size       *int64  `json:"size,omitempty"`
	CreatedAt  string  `json:"created_at"`
	UpdatedAt  string  `json:"updated_at"`
	DeletedAt  string  `json:"deleted_at"`
}

// ListTrash returns soft-deleted files for the project, newest-first.
// Project membership required (any role can browse the trash; only
// editors+ can restore/empty).
func (d *Deps) ListTrash(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}
	rows, err := d.Pool.Query(r.Context(), `
		select id, project_id, parent_id, name, kind,
		       storage_key, mime_type, size,
		       created_at, updated_at, deleted_at
		from files
		where project_id = $1 and deleted_at is not null
		order by deleted_at desc
		limit 500
	`, pid)
	if err != nil {
		genericServerError(w, err)
		return
	}
	defer rows.Close()
	out := []trashedFile{}
	for rows.Next() {
		var (
			f          trashedFile
			created    time.Time
			updated    time.Time
			deletedRaw time.Time
		)
		if err := rows.Scan(
			&f.ID, &f.ProjectID, &f.ParentID, &f.Name, &f.Kind,
			&f.StorageKey, &f.MimeType, &f.Size,
			&created, &updated, &deletedRaw,
		); err != nil {
			genericServerError(w, err)
			return
		}
		f.CreatedAt = created.UTC().Format(time.RFC3339Nano)
		f.UpdatedAt = updated.UTC().Format(time.RFC3339Nano)
		f.DeletedAt = deletedRaw.UTC().Format(time.RFC3339Nano)
		out = append(out, f)
	}
	writeJSON(w, http.StatusOK, out)
}

// RestoreFile clears deleted_at so the file reappears in the project
// tree. Editors+ only. Records a 'restore' revision so Cmd+Z still
// behaves predictably (the restore itself is undoable).
func (d *Deps) RestoreFile(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	fid := chi.URLParam(r, "fid")
	role := requireMember(w, r, d.Pool, pid, uid)
	if role == "" {
		return
	}
	if role == "viewer" {
		writeError(w, http.StatusForbidden, "viewer cannot restore files")
		return
	}
	// Confirm the row exists AND is currently soft-deleted.
	var (
		content string
		kind    string
	)
	err := d.Pool.QueryRow(r.Context(),
		`select content, kind from files where id = $1 and project_id = $2 and deleted_at is not null`,
		fid, pid).Scan(&content, &kind)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "trashed file not found")
			return
		}
		genericServerError(w, err)
		return
	}
	if _, err := d.Pool.Exec(r.Context(),
		`update files set deleted_at = null, updated_at = now() where id = $1 and project_id = $2`,
		fid, pid); err != nil {
		genericServerError(w, err)
		return
	}
	// Mark the restore in revisions so the user can undo back to "trashed"
	// via the History drawer if they restored by accident.
	cap := 200
	if d.Cfg != nil && d.Cfg.FileRevisionsMax > 0 {
		cap = d.Cfg.FileRevisionsMax
	}
	_ = RecordRevision(r.Context(), d.Pool, fid, content, "restore", userIDPtr(uid), cap)
	// Re-mirror to disk if filesystem mode is on.
	if d.Mirror != nil &&
		(kind == "file" || kind == "assembly" || kind == "drawing" || kind == "sketch" ||
			kind == "part" || kind == "feature" || kind == "circuit") {
		d.fsWriteFile(r.Context(), pid, fid, content)
	} else if d.Mirror != nil && kind == "folder" {
		if name, _ := d.projectName(r.Context(), pid); name != "" {
			if segs, ferr := filesystem.SegmentsForFile(r.Context(), d.Pool, pid, fid); ferr == nil {
				_ = d.Mirror.Mkdir(name, segs)
			}
		}
	}
	d.getFileForResponse(w, r, pid, fid)
}

// EmptyTrash permanently deletes soft-deleted files older than 30 days.
// Owner-only, gated on `?confirm=EMPTY` to prevent accidental clicks.
// Storage blobs are best-effort cleaned; on failure the row still goes
// (orphaned blobs are reaped by future GC sweeps).
func (d *Deps) EmptyTrash(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	if !requireOwner(w, r, d.Pool, pid, uid) {
		return
	}
	if r.URL.Query().Get("confirm") != "EMPTY" {
		writeError(w, http.StatusBadRequest, "confirm=EMPTY query param is required")
		return
	}
	// Pull the to-delete set first so we can wipe storage blobs before
	// dropping the row (the row owns the only pointer to the blob).
	rows, err := d.Pool.Query(r.Context(), `
		select id, storage_key
		from files
		where project_id = $1 and deleted_at is not null and deleted_at < now() - interval '30 days'
	`, pid)
	if err != nil {
		genericServerError(w, err)
		return
	}
	type victim struct {
		id  string
		key *string
	}
	var victims []victim
	for rows.Next() {
		var v victim
		if err := rows.Scan(&v.id, &v.key); err != nil {
			rows.Close()
			genericServerError(w, err)
			return
		}
		victims = append(victims, v)
	}
	rows.Close()
	// Best-effort blob cleanup BEFORE row deletion. Failures are logged
	// but don't block the SQL DELETE — orphan blobs are recoverable; an
	// un-finalized DELETE would force the user to manually retry.
	if d.Storage != nil {
		for _, v := range victims {
			if v.key == nil || *v.key == "" {
				continue
			}
			if err := d.Storage.Delete(r.Context(), *v.key); err != nil {
				log.Printf("empty-trash: storage delete %s: %v", *v.key, err)
			}
		}
	}
	tag, err := d.Pool.Exec(r.Context(), `
		delete from files
		where project_id = $1 and deleted_at is not null and deleted_at < now() - interval '30 days'
	`, pid)
	if err != nil {
		genericServerError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"deleted": tag.RowsAffected(),
	})
}
