package handlers

// Project zip import. Reverses project_export.go: takes a multipart upload
// of a zip produced by ExportProject (or any zip that follows the same
// layout), creates a fresh project in the caller's chosen workspace, and
// inserts every file row in a single transaction.
//
// Layout consumed:
//
//   manifest.json           — required; defines order + path + kind
//   files/<path>            — text content (looked up by path)
//   blobs/<storage_key>     — binary content (looked up by *source* key)
//   thumbnail.jpg           — optional
//
// Hard caps:
//   - 5,000 manifest entries
//   - 500 MB total uncompressed
//   - 50 MB per individual file
//
// Storage keys in the source manifest are NOT reused: every blob round-trips
// through Storage.Put under a fresh key scoped to the new project. This
// keeps the importer compatible with renamed/migrated buckets.

import (
	"archive/zip"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"path"
	"strings"

	"github.com/google/uuid"

	"github.com/imranp/kerf/backend/internal/middleware"
	"github.com/imranp/kerf/backend/internal/models"
)

const (
	importMaxBytes      = 500 * 1024 * 1024 // 500 MB total uncompressed
	importMaxFileBytes  = 50 * 1024 * 1024  // 50 MB per individual file
	importMaxManifestN  = 5000              // max files per import
	importMultipartSlop = 4096              // grace bytes for multipart framing
)

// ImportProject creates a new project from a zip artifact uploaded as
// multipart "file". Caller must pass `?workspace_id=<uuid>` and be a
// member of that workspace.
func (d *Deps) ImportProject(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())

	wsID := strings.TrimSpace(r.URL.Query().Get("workspace_id"))
	if wsID == "" {
		// Allow the body field as a fallback for clients that prefer not
		// to mix querystrings with multipart.
		if v := strings.TrimSpace(r.FormValue("workspace_id")); v != "" {
			wsID = v
		}
	}
	if wsID == "" {
		writeError(w, http.StatusBadRequest, "workspace_id is required")
		return
	}
	if requireWorkspaceMember(w, r, d.Pool, wsID, uid) == "" {
		return
	}
	if d.Storage == nil {
		writeError(w, http.StatusServiceUnavailable, "storage not configured")
		return
	}

	r.Body = http.MaxBytesReader(w, r.Body, importMaxBytes+importMultipartSlop)
	if err := r.ParseMultipartForm(32 << 20); err != nil {
		writeError(w, http.StatusBadRequest, "invalid multipart body: "+err.Error())
		return
	}
	file, fhdr, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, "missing 'file' field")
		return
	}
	defer file.Close()
	if fhdr.Size > importMaxBytes {
		writeError(w, http.StatusRequestEntityTooLarge, "import zip too large (>500MB)")
		return
	}

	// archive/zip.NewReader needs a ReaderAt + size; multipart File is one
	// of those (it backs to a temp file when over the in-memory threshold).
	zr, err := zip.NewReader(file, fhdr.Size)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid zip: "+err.Error())
		return
	}

	// Index zip entries by name for O(1) lookup. We also enforce caps as
	// we build the index — a malicious zip can't OOM us by just listing
	// 10M entries.
	zipByName := map[string]*zip.File{}
	var totalUncompressed int64
	for _, e := range zr.File {
		if strings.HasSuffix(e.Name, "/") {
			continue // skip pure-directory entries
		}
		// Reject path traversal in zip member names. archive/zip already
		// blocks absolute paths but `..` segments are merely "valid".
		if !safeZipPath(e.Name) {
			writeError(w, http.StatusBadRequest, "zip member rejected: "+e.Name)
			return
		}
		// Validate per-file size cap on the *uncompressed* size declared
		// in the central directory. We re-check while reading so a lying
		// header can't bypass us.
		if int64(e.UncompressedSize64) > importMaxFileBytes {
			writeError(w, http.StatusRequestEntityTooLarge,
				"zip entry exceeds 50MB: "+e.Name)
			return
		}
		totalUncompressed += int64(e.UncompressedSize64)
		if totalUncompressed > importMaxBytes {
			writeError(w, http.StatusRequestEntityTooLarge,
				"zip uncompressed size exceeds 500MB")
			return
		}
		zipByName[e.Name] = e
	}

	// Read manifest.json first.
	manEntry, ok := zipByName["manifest.json"]
	if !ok {
		writeError(w, http.StatusBadRequest, "manifest.json missing from zip")
		return
	}
	manReader, err := manEntry.Open()
	if err != nil {
		writeError(w, http.StatusBadRequest, "cannot open manifest.json: "+err.Error())
		return
	}
	manBytes, err := io.ReadAll(io.LimitReader(manReader, importMaxFileBytes))
	manReader.Close()
	if err != nil {
		writeError(w, http.StatusBadRequest, "cannot read manifest.json: "+err.Error())
		return
	}
	var manifest exportManifest
	if err := json.Unmarshal(manBytes, &manifest); err != nil {
		writeError(w, http.StatusBadRequest, "manifest.json malformed: "+err.Error())
		return
	}
	if strings.TrimSpace(manifest.Name) == "" {
		writeError(w, http.StatusBadRequest, "manifest.name is required")
		return
	}
	if len(manifest.Files) > importMaxManifestN {
		writeError(w, http.StatusRequestEntityTooLarge,
			fmt.Sprintf("manifest has %d files, max is %d", len(manifest.Files), importMaxManifestN))
		return
	}

	// Validate every manifest path before we touch the DB. Three rules:
	//   1. No path traversal / absolute paths.
	//   2. Paths are unique within the manifest.
	//   3. Kind is one of the known set (the schema enforces this too,
	//      but a clean 400 is friendlier than a 500).
	seenPaths := map[string]bool{}
	for i := range manifest.Files {
		entry := &manifest.Files[i]
		entry.Path = strings.TrimSpace(entry.Path)
		if entry.Path == "" {
			writeError(w, http.StatusBadRequest, "manifest entry missing path")
			return
		}
		if !safeZipPath(entry.Path) {
			writeError(w, http.StatusBadRequest, "manifest path rejected: "+entry.Path)
			return
		}
		if seenPaths[entry.Path] {
			writeError(w, http.StatusBadRequest, "duplicate manifest path: "+entry.Path)
			return
		}
		seenPaths[entry.Path] = true
		if !validImportKind(entry.Kind) {
			writeError(w, http.StatusBadRequest, "manifest entry has invalid kind: "+entry.Kind)
			return
		}
	}

	// Insert in a transaction. We keep a path→fileID map so each entry's
	// parent_id can be set to the row created for its parent path. The
	// manifest is in BFS order, so a parent always lands before its
	// children.
	tx, err := d.Pool.Begin(r.Context())
	if err != nil {
		genericServerError(w, err)
		return
	}
	defer tx.Rollback(r.Context())

	var newProject models.Project
	err = tx.QueryRow(r.Context(), `
		insert into projects(workspace_id, name, description, tags)
		values ($1, $2, $3, coalesce($4::text[], '{}'))
		returning id, workspace_id, name, description, visibility, tags, created_at, updated_at
	`, wsID, manifest.Name, manifest.Description, manifest.Tags).Scan(
		&newProject.ID, &newProject.WorkspaceID, &newProject.Name, &newProject.Description,
		&newProject.Visibility, &newProject.Tags, &newProject.CreatedAt, &newProject.UpdatedAt)
	if err != nil {
		genericServerError(w, err)
		return
	}

	// Track storage_keys we've actually persisted so we can clean up on
	// transaction rollback — Storage.Put isn't transactional.
	committedKeys := []string{}
	rollbackBlobs := func() {
		for _, k := range committedKeys {
			_ = d.Storage.Delete(r.Context(), k)
		}
	}

	pathToID := map[string]string{} // manifest path → new file id

	for _, entry := range manifest.Files {
		parentID := (*string)(nil)
		dir := path.Dir(entry.Path)
		if dir != "." && dir != "/" && dir != "" {
			pid, ok := pathToID[dir]
			if !ok {
				rollbackBlobs()
				writeError(w, http.StatusBadRequest,
					"manifest entry references missing parent: "+dir+" (for "+entry.Path+")")
				return
			}
			parentID = &pid
		}

		baseName := path.Base(entry.Path)

		var (
			content    string
			storageKey *string
			mimeType   *string
			size       *int64
		)

		switch {
		case entry.Kind == "folder":
			// Folders carry no content. They reserve a path so children
			// can resolve.
		case entry.StorageKey != nil && *entry.StorageKey != "":
			// Binary-backed entry. Pull from blobs/<source-key>, push to
			// a fresh key under the new project, attach to the row.
			srcKey := *entry.StorageKey
			zipPath := "blobs/" + srcKey
			zEntry, ok := zipByName[zipPath]
			if !ok {
				rollbackBlobs()
				writeError(w, http.StatusBadRequest,
					"manifest references missing blob: "+srcKey)
				return
			}
			rc, err := zEntry.Open()
			if err != nil {
				rollbackBlobs()
				writeError(w, http.StatusBadRequest,
					"cannot open blob "+srcKey+": "+err.Error())
				return
			}
			// Read into memory bounded by the per-file cap. STEP imports
			// at the cap (~50MB) are fine to buffer.
			payload, err := io.ReadAll(io.LimitReader(rc, importMaxFileBytes+1))
			rc.Close()
			if err != nil {
				rollbackBlobs()
				writeError(w, http.StatusBadRequest, "blob read: "+err.Error())
				return
			}
			if int64(len(payload)) > importMaxFileBytes {
				rollbackBlobs()
				writeError(w, http.StatusRequestEntityTooLarge,
					"blob exceeds per-file cap: "+srcKey)
				return
			}
			ct := "application/octet-stream"
			if entry.MimeType != nil && *entry.MimeType != "" {
				ct = *entry.MimeType
			} else {
				ct = guessAssetContentType(baseName)
			}
			newKey := fmt.Sprintf("projects/%s/assets/%s-%s",
				newProject.ID, uuid.New().String(), sanitizeFilename(baseName))
			pr, err := d.Storage.Put(r.Context(), newKey,
				bytes.NewReader(payload), ct, int64(len(payload)))
			if err != nil {
				rollbackBlobs()
				genericServerError(w, err)
				return
			}
			committedKeys = append(committedKeys, newKey)
			storageKey = &newKey
			mt := pr.ContentType
			mimeType = &mt
			sz := pr.Size
			size = &sz
		default:
			// Text-bearing kind. Prefer manifest.content; fall back to
			// reading files/<path> from the zip.
			if entry.Content != nil {
				content = *entry.Content
			} else {
				zPath := "files/" + entry.Path
				zEntry, ok := zipByName[zPath]
				if !ok {
					rollbackBlobs()
					writeError(w, http.StatusBadRequest,
						"manifest entry has no content and no zip member: "+zPath)
					return
				}
				rc, err := zEntry.Open()
				if err != nil {
					rollbackBlobs()
					writeError(w, http.StatusBadRequest,
						"cannot open "+zPath+": "+err.Error())
					return
				}
				payload, err := io.ReadAll(io.LimitReader(rc, importMaxFileBytes+1))
				rc.Close()
				if err != nil {
					rollbackBlobs()
					writeError(w, http.StatusBadRequest, "read "+zPath+": "+err.Error())
					return
				}
				if int64(len(payload)) > importMaxFileBytes {
					rollbackBlobs()
					writeError(w, http.StatusRequestEntityTooLarge,
						"file exceeds per-file cap: "+entry.Path)
					return
				}
				content = string(payload)
			}
		}

		var newID string
		if storageKey != nil {
			err = tx.QueryRow(r.Context(), `
				insert into files(project_id, parent_id, name, kind, content, storage_key, mime_type, size)
				values ($1, $2, $3, $4, '', $5, $6, $7)
				returning id
			`, newProject.ID, parentID, baseName, entry.Kind, *storageKey, mimeType, size).Scan(&newID)
		} else {
			err = tx.QueryRow(r.Context(), `
				insert into files(project_id, parent_id, name, kind, content)
				values ($1, $2, $3, $4, $5)
				returning id
			`, newProject.ID, parentID, baseName, entry.Kind, content).Scan(&newID)
		}
		if err != nil {
			rollbackBlobs()
			genericServerError(w, err)
			return
		}
		pathToID[entry.Path] = newID
	}

	if err := tx.Commit(r.Context()); err != nil {
		rollbackBlobs()
		genericServerError(w, err)
		return
	}

	newProject.MyRole = "owner"
	writeJSON(w, http.StatusCreated, newProject)
}

// safeZipPath rejects absolute paths, parent traversal, and Windows-style
// drive letters. We use forward-slash semantics throughout (zip standard).
func safeZipPath(p string) bool {
	if p == "" {
		return false
	}
	if strings.HasPrefix(p, "/") || strings.HasPrefix(p, `\`) {
		return false
	}
	// Drive-letter prefix on Windows (e.g. "C:foo").
	if len(p) >= 2 && p[1] == ':' {
		return false
	}
	if strings.Contains(p, `\`) {
		// Be strict: reject backslash separators to keep the path canon-
		// ical. The exporter never emits these.
		return false
	}
	for _, seg := range strings.Split(p, "/") {
		if seg == "" || seg == "." || seg == ".." {
			return false
		}
	}
	return true
}

// validImportKind mirrors the schema's CHECK constraint on files.kind.
// We surface invalid values as 400 for a cleaner error than the DB's
// integrity-violation noise.
func validImportKind(k string) bool {
	switch k {
	case "file", "folder", "assembly", "drawing", "sketch", "part",
		"feature", "circuit", "equations", "material", "simulation", "step":
		return true
	}
	return false
}

