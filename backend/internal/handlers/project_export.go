package handlers

// Project zip export. Streams a single .zip artifact carrying every file
// row in the project (text + binary), the project's manifest, and its
// thumbnail. Symmetric with project_import.go.
//
// Layout inside the zip:
//
//   manifest.json           — {name, description, tags, created_at, files: [...]}
//   files/<path>            — literal text content for text-bearing kinds
//   blobs/<storage_key>     — raw bytes for kinds backed by Storage (e.g. step)
//   thumbnail.jpg           — present only when the project has one
//
// `path` is the project-relative slash-joined name walked from each row's
// parent_id chain. Manifest entries appear in BFS order so the importer
// can build parent_id chains in a single pass.
//
// Hard cap: 500 MB total uncompressed payload. We track running size as
// we copy; on overshoot we 413 the request without finishing the stream
// (the client will see a truncated zip — that's the price of avoiding a
// full pre-pass).

import (
	"archive/zip"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"

	"github.com/imranp/kerf/backend/internal/middleware"
)

// exportMaxBytes caps the running uncompressed payload an export will emit.
// 500 MB matches the import cap so a roundtrip is always feasible.
const exportMaxBytes = 500 * 1024 * 1024

// exportFileEntry is the per-file shape inside manifest.json.
type exportFileEntry struct {
	Path       string  `json:"path"`
	Kind       string  `json:"kind"`
	Content    *string `json:"content,omitempty"`
	Size       *int64  `json:"size,omitempty"`
	MimeType   *string `json:"mime_type,omitempty"`
	StorageKey *string `json:"storage_key,omitempty"`
}

// exportManifest is the top-level manifest.json shape.
type exportManifest struct {
	Version     int               `json:"version"`
	Name        string            `json:"name"`
	Description string            `json:"description"`
	Tags        []string          `json:"tags"`
	CreatedAt   string            `json:"created_at"`
	Files       []exportFileEntry `json:"files"`
}

// exportFileRow is the per-row shape we read out of `files` for the export.
type exportFileRow struct {
	ID         string
	ParentID   *string
	Name       string
	Kind       string
	Content    string
	StorageKey *string
	MimeType   *string
	Size       *int64
}

// ExportProject streams a zip containing the project's manifest, source
// content, binary blobs, and thumbnail. Member+ only.
func (d *Deps) ExportProject(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}

	// Project metadata.
	var (
		name        string
		description string
		tags        []string
		createdAt   string
		thumbKey    *string
	)
	err := d.Pool.QueryRow(r.Context(), `
		select name, description, coalesce(tags, '{}'),
		       to_char(created_at at time zone 'utc', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
		       thumbnail_storage_key
		from projects where id = $1
	`, pid).Scan(&name, &description, &tags, &createdAt, &thumbKey)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "project not found")
			return
		}
		genericServerError(w, err)
		return
	}

	// All non-deleted file rows. Order doesn't matter for the BFS pass —
	// we re-walk the parent chain in code.
	rows, err := d.Pool.Query(r.Context(), `
		select id, parent_id, name, kind, coalesce(content, ''),
		       storage_key, mime_type, size
		from files
		where project_id = $1 and deleted_at is null
	`, pid)
	if err != nil {
		genericServerError(w, err)
		return
	}
	byID := map[string]*exportFileRow{}
	for rows.Next() {
		var f exportFileRow
		if err := rows.Scan(&f.ID, &f.ParentID, &f.Name, &f.Kind, &f.Content,
			&f.StorageKey, &f.MimeType, &f.Size); err != nil {
			rows.Close()
			genericServerError(w, err)
			return
		}
		byID[f.ID] = &f
	}
	rows.Close()

	// Resolve project-relative path for every row by walking parent_id
	// upward. We memoize so deeply-nested trees are O(N) total.
	pathOf := map[string]string{}
	var resolve func(id string) string
	resolve = func(id string) string {
		if p, ok := pathOf[id]; ok {
			return p
		}
		f := byID[id]
		if f == nil {
			return ""
		}
		var p string
		if f.ParentID == nil || *f.ParentID == "" {
			p = f.Name
		} else {
			parent := resolve(*f.ParentID)
			if parent == "" {
				p = f.Name
			} else {
				p = parent + "/" + f.Name
			}
		}
		pathOf[id] = p
		return p
	}

	// Build the manifest entries in BFS order: roots first, then children
	// of roots, etc. The importer relies on this so it can attach
	// parent_id chains in one pass.
	roots := []string{}
	childrenOf := map[string][]string{}
	for id, f := range byID {
		if f.ParentID == nil || *f.ParentID == "" {
			roots = append(roots, id)
		} else {
			childrenOf[*f.ParentID] = append(childrenOf[*f.ParentID], id)
		}
	}
	ordered := []string{}
	queue := append([]string{}, roots...)
	for len(queue) > 0 {
		id := queue[0]
		queue = queue[1:]
		ordered = append(ordered, id)
		queue = append(queue, childrenOf[id]...)
	}

	// Build manifest + a parallel list of zip writes we'll perform.
	type pending struct {
		path string // path inside the zip
		// Exactly one of `content` or `blobKey` is set.
		content string
		blobKey string
	}
	manifest := exportManifest{
		Version:     1,
		Name:        name,
		Description: description,
		Tags:        tags,
		CreatedAt:   createdAt,
		Files:       make([]exportFileEntry, 0, len(ordered)),
	}
	pendings := []pending{}
	seenBlob := map[string]bool{}

	for _, id := range ordered {
		f := byID[id]
		rel := resolve(id)
		entry := exportFileEntry{
			Path: rel,
			Kind: f.Kind,
		}
		if f.MimeType != nil && *f.MimeType != "" {
			mt := *f.MimeType
			entry.MimeType = &mt
		}
		if f.Size != nil {
			sz := *f.Size
			entry.Size = &sz
		}

		switch {
		case f.Kind == "folder":
			// Folders are pure tree scaffolding. The importer recreates
			// them implicitly when it materializes children.
		case f.StorageKey != nil && *f.StorageKey != "":
			// Binary-backed row: store the key in the manifest, ship
			// the bytes under blobs/<key>. De-dupe on key in case two
			// rows somehow point at the same blob.
			key := *f.StorageKey
			entry.StorageKey = &key
			if !seenBlob[key] {
				seenBlob[key] = true
				pendings = append(pendings, pending{
					path:    "blobs/" + key,
					blobKey: key,
				})
			}
		default:
			// Text-bearing kind: ship literal bytes.
			c := f.Content
			entry.Content = &c
			pendings = append(pendings, pending{
				path:    "files/" + rel,
				content: f.Content,
			})
		}

		manifest.Files = append(manifest.Files, entry)
	}

	// Emit headers + start streaming.
	slug := slugifyName(name)
	short := pid
	if len(short) > 8 {
		short = short[:8]
	}
	filename := slug + "-" + short + ".zip"
	w.Header().Set("Content-Type", "application/zip")
	w.Header().Set("Content-Disposition", `attachment; filename="`+filename+`"`)

	zw := zip.NewWriter(w)
	defer zw.Close()

	var written int64
	guard := func(n int64) bool {
		written += n
		return written <= exportMaxBytes
	}

	// 1. manifest.json (always first, so the importer can read it without
	// scanning to the central directory).
	if err := writeZipJSON(zw, "manifest.json", manifest, guard); err != nil {
		writeExportError(w, err)
		return
	}

	// 2. files/<path> entries.
	for _, p := range pendings {
		if p.blobKey != "" {
			if err := writeZipBlob(r.Context(), zw, p.path, p.blobKey, d.storageGet, guard); err != nil {
				writeExportError(w, err)
				return
			}
		} else {
			if err := writeZipString(zw, p.path, p.content, guard); err != nil {
				writeExportError(w, err)
				return
			}
		}
	}

	// 3. thumbnail (if present).
	if thumbKey != nil && *thumbKey != "" && d.Storage != nil {
		if err := writeZipBlob(r.Context(), zw, "thumbnail.jpg", *thumbKey, d.storageGet, guard); err != nil {
			// Best-effort: a missing thumbnail blob shouldn't fail the
			// whole export. We just skip and let the rest stream.
			if !errors.Is(err, errExportTooLarge) {
				_ = err
			} else {
				writeExportError(w, err)
				return
			}
		}
	}
}

// errExportTooLarge is the sentinel returned when a write would push the
// cumulative payload above exportMaxBytes. The HTTP response is best-effort
// 413 only when no bytes have been flushed yet; otherwise the client sees
// a truncated zip — there's no way to retract a streamed body.
var errExportTooLarge = errors.New("export exceeds 500MB cap")

// storageGet adapts the Storage interface to the writer helper signature.
func (d *Deps) storageGet(ctx context.Context, key string) (io.ReadCloser, error) {
	if d.Storage == nil {
		return nil, fmt.Errorf("storage not configured")
	}
	rc, _, err := d.Storage.Get(ctx, key)
	return rc, err
}

// writeZipString writes a single in-memory string as a deflate-compressed
// zip entry.
func writeZipString(zw *zip.Writer, path string, content string, guard func(int64) bool) error {
	if !guard(int64(len(content))) {
		return errExportTooLarge
	}
	wr, err := zw.Create(path)
	if err != nil {
		return err
	}
	_, err = io.Copy(wr, strings.NewReader(content))
	return err
}

// writeZipJSON serializes v as JSON and writes it to the zip at path.
func writeZipJSON(zw *zip.Writer, path string, v any, guard func(int64) bool) error {
	buf, err := jsonMarshalIndent(v)
	if err != nil {
		return err
	}
	return writeZipString(zw, path, string(buf), guard)
}

// writeZipBlob copies bytes from a Storage.Get reader into a zip entry,
// enforcing the running-size guard as it goes.
func writeZipBlob(ctx context.Context, zw *zip.Writer, path string, key string,
	get func(context.Context, string) (io.ReadCloser, error), guard func(int64) bool) error {
	rc, err := get(ctx, key)
	if err != nil {
		return err
	}
	defer rc.Close()
	wr, err := zw.Create(path)
	if err != nil {
		return err
	}
	// Stream in 64KB chunks so the guard fires promptly on huge blobs.
	buf := make([]byte, 64*1024)
	for {
		n, rerr := rc.Read(buf)
		if n > 0 {
			if !guard(int64(n)) {
				return errExportTooLarge
			}
			if _, werr := wr.Write(buf[:n]); werr != nil {
				return werr
			}
		}
		if rerr == io.EOF {
			return nil
		}
		if rerr != nil {
			return rerr
		}
	}
}

// writeExportError flushes a best-effort error message. Once we've started
// streaming the zip body we can't actually change the status code — these
// errors are surfaced through truncation.
func writeExportError(w http.ResponseWriter, err error) {
	if errors.Is(err, errExportTooLarge) {
		// Best-effort: only effective when we haven't flushed yet.
		http.Error(w, "project export exceeds 500MB cap", http.StatusRequestEntityTooLarge)
		return
	}
	// Other errors: log via the chi recoverer trail; client sees truncated zip.
}

// jsonMarshalIndent is a thin wrapper kept separate so tests can swap it.
func jsonMarshalIndent(v any) ([]byte, error) {
	return json.MarshalIndent(v, "", "  ")
}

// slugifyName produces a filename-safe slug from a project name. We keep
// alphanumerics, dash, underscore, and squash everything else into '-'.
func slugifyName(name string) string {
	name = strings.TrimSpace(name)
	if name == "" {
		return "project"
	}
	var b strings.Builder
	prevDash := false
	for _, r := range name {
		switch {
		case r >= 'a' && r <= 'z',
			r >= 'A' && r <= 'Z',
			r >= '0' && r <= '9',
			r == '-' || r == '_':
			b.WriteRune(r)
			prevDash = false
		default:
			if !prevDash && b.Len() > 0 {
				b.WriteByte('-')
				prevDash = true
			}
		}
	}
	out := strings.Trim(b.String(), "-_")
	if out == "" {
		return "project"
	}
	if len(out) > 60 {
		out = out[:60]
	}
	return strings.ToLower(out)
}
