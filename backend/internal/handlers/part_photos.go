package handlers

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"image"
	_ "image/jpeg" // register decoder
	"image/jpeg"
	_ "image/png" // register decoder
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"golang.org/x/image/draw"
	_ "golang.org/x/image/webp" // register decoder

	"github.com/imranp/kerf/backend/internal/middleware"
)

// Per-photo cap. Larger than avatars (we keep more detail on product shots).
const maxPartPhotoBytes = 5 * 1024 * 1024
const partPhotoLongestSide = 1024

// partPhoto mirrors the JS-side normalizePhoto in src/lib/part.js. We
// deserialize/reserialize the Part JSON here so the persisted shape stays in
// sync with the frontend regardless of which side wrote it last.
type partPhoto struct {
	StorageKey string `json:"storage_key"`
	MimeType   string `json:"mime_type"`
	Caption    string `json:"caption,omitempty"`
	Primary    bool   `json:"primary,omitempty"`
	Width      int    `json:"width,omitempty"`
	Height     int    `json:"height,omitempty"`
	Bytes      int    `json:"bytes,omitempty"`
}

// loadPartFile reads a file row, asserts kind='part', returns its parsed JSON
// content as a generic map so we can mutate the photos array without losing
// fields we don't model in Go.
func (d *Deps) loadPartFile(r *http.Request, pid, fid string) (string, map[string]any, error) {
	var (
		kind    string
		content string
	)
	err := d.Pool.QueryRow(r.Context(),
		`select kind, content from files where id = $1 and project_id = $2 and deleted_at is null`,
		fid, pid).Scan(&kind, &content)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return "", nil, errPartNotFound
		}
		return "", nil, err
	}
	if kind != "part" {
		return "", nil, errPartNotFound
	}
	doc := map[string]any{}
	if strings.TrimSpace(content) != "" {
		_ = json.Unmarshal([]byte(content), &doc)
	}
	if _, ok := doc["photos"]; !ok {
		doc["photos"] = []any{}
	}
	return content, doc, nil
}

var errPartNotFound = errors.New("part file not found")

// AddPartPhoto handles `POST /api/projects/{pid}/files/{fid}/photos`.
// Multipart, single field `file` (image/jpeg|png|webp). 5 MB cap, resized so
// the longest side ≤ 1024 px, re-encoded as JPEG q=85.
func (d *Deps) AddPartPhoto(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	fid := chi.URLParam(r, "fid")
	role := requireMember(w, r, d.Pool, pid, uid)
	if role == "" {
		return
	}
	if role == "viewer" {
		writeError(w, http.StatusForbidden, "viewer cannot edit parts")
		return
	}
	if d.Storage == nil {
		writeError(w, http.StatusServiceUnavailable, "storage not configured")
		return
	}

	r.Body = http.MaxBytesReader(w, r.Body, maxPartPhotoBytes+1<<20)
	if err := r.ParseMultipartForm(8 << 20); err != nil {
		writeError(w, http.StatusBadRequest, "invalid multipart body: "+err.Error())
		return
	}
	file, fhdr, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, "missing 'file' field")
		return
	}
	defer file.Close()
	if fhdr.Size > maxPartPhotoBytes {
		writeError(w, http.StatusRequestEntityTooLarge, "photo too large (>5MB)")
		return
	}

	img, _, err := image.Decode(file)
	if err != nil {
		writeError(w, http.StatusBadRequest, "could not decode image (jpeg/png/webp expected)")
		return
	}
	resized := resizeFitWithin(img, partPhotoLongestSide)
	var buf bytes.Buffer
	if err := jpeg.Encode(&buf, resized, &jpeg.Options{Quality: 85}); err != nil {
		genericServerError(w, err)
		return
	}

	_, doc, err := d.loadPartFile(r, pid, fid)
	if err != nil {
		if errors.Is(err, errPartNotFound) {
			writeError(w, http.StatusNotFound, "part not found")
			return
		}
		genericServerError(w, err)
		return
	}

	key := fmt.Sprintf("parts/%s/photo-%s.jpg", fid, uuid.New().String())
	if _, err := d.Storage.Put(r.Context(), key, &buf, "image/jpeg", int64(buf.Len())); err != nil {
		genericServerError(w, err)
		return
	}

	photos, _ := doc["photos"].([]any)
	hasPrimary := false
	for _, p := range photos {
		m, _ := p.(map[string]any)
		if m != nil && m["primary"] == true {
			hasPrimary = true
			break
		}
	}
	bounds := resized.Bounds()
	newPhoto := map[string]any{
		"storage_key": key,
		"mime_type":   "image/jpeg",
		"width":       bounds.Dx(),
		"height":      bounds.Dy(),
		"bytes":       buf.Len(),
	}
	if !hasPrimary {
		newPhoto["primary"] = true
	}
	doc["photos"] = append(photos, newPhoto)

	if err := d.savePartContent(r, pid, fid, uid, doc); err != nil {
		_ = d.Storage.Delete(r.Context(), key)
		genericServerError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, newPhoto)
}

// DeletePartPhoto handles `DELETE /api/projects/{pid}/files/{fid}/photos?key=<storage_key>`.
func (d *Deps) DeletePartPhoto(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	fid := chi.URLParam(r, "fid")
	key := strings.TrimSpace(r.URL.Query().Get("key"))
	if key == "" {
		writeError(w, http.StatusBadRequest, "key is required")
		return
	}
	role := requireMember(w, r, d.Pool, pid, uid)
	if role == "" {
		return
	}
	if role == "viewer" {
		writeError(w, http.StatusForbidden, "viewer cannot edit parts")
		return
	}
	_, doc, err := d.loadPartFile(r, pid, fid)
	if err != nil {
		if errors.Is(err, errPartNotFound) {
			writeError(w, http.StatusNotFound, "part not found")
			return
		}
		genericServerError(w, err)
		return
	}
	photos, _ := doc["photos"].([]any)
	out := photos[:0]
	removedPrimary := false
	for _, p := range photos {
		m, _ := p.(map[string]any)
		if m == nil {
			continue
		}
		if m["storage_key"] == key {
			if m["primary"] == true {
				removedPrimary = true
			}
			continue
		}
		out = append(out, m)
	}
	// Promote first remaining photo to primary if we removed the primary.
	if removedPrimary && len(out) > 0 {
		first, _ := out[0].(map[string]any)
		if first != nil {
			first["primary"] = true
		}
	}
	doc["photos"] = out
	if err := d.savePartContent(r, pid, fid, uid, doc); err != nil {
		genericServerError(w, err)
		return
	}
	if d.Storage != nil {
		_ = d.Storage.Delete(r.Context(), key)
	}
	w.WriteHeader(http.StatusNoContent)
}

// SetPartPhotoPrimary handles `PATCH /api/projects/{pid}/files/{fid}/photos/primary?key=<storage_key>`.
func (d *Deps) SetPartPhotoPrimary(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	fid := chi.URLParam(r, "fid")
	key := strings.TrimSpace(r.URL.Query().Get("key"))
	if key == "" {
		writeError(w, http.StatusBadRequest, "key is required")
		return
	}
	role := requireMember(w, r, d.Pool, pid, uid)
	if role == "" {
		return
	}
	if role == "viewer" {
		writeError(w, http.StatusForbidden, "viewer cannot edit parts")
		return
	}
	_, doc, err := d.loadPartFile(r, pid, fid)
	if err != nil {
		if errors.Is(err, errPartNotFound) {
			writeError(w, http.StatusNotFound, "part not found")
			return
		}
		genericServerError(w, err)
		return
	}
	photos, _ := doc["photos"].([]any)
	matched := false
	for _, p := range photos {
		m, _ := p.(map[string]any)
		if m == nil {
			continue
		}
		if m["storage_key"] == key {
			m["primary"] = true
			matched = true
		} else {
			delete(m, "primary")
		}
	}
	if !matched {
		writeError(w, http.StatusNotFound, "photo not found")
		return
	}
	if err := d.savePartContent(r, pid, fid, uid, doc); err != nil {
		genericServerError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// savePartContent re-serializes the Part doc and writes it through the same
// PATCH path used by file edits — that records a `file_revisions` row, so
// every photo upload/delete is undoable via the existing Cmd+Z flow.
func (d *Deps) savePartContent(r *http.Request, pid, fid, uid string, doc map[string]any) error {
	body, err := json.MarshalIndent(doc, "", "  ")
	if err != nil {
		return err
	}
	content := string(body)
	if _, err := d.Pool.Exec(r.Context(),
		`update files set content = $3, updated_at = now()
		 where id = $1 and project_id = $2 and deleted_at is null`,
		fid, pid, content); err != nil {
		return err
	}
	_ = RecordRevision(r.Context(), d.Pool, fid, content, "user", userIDPtr(uid), d.Cfg.FileRevisionsMax)
	return nil
}

// resizeFitWithin scales an image so its longest side equals `maxSide`,
// preserving aspect ratio. Uses CatmullRom for noticeably smoother output
// than NearestNeighbor at negligible cost (~ms for our sizes).
func resizeFitWithin(src image.Image, maxSide int) image.Image {
	b := src.Bounds()
	w, h := b.Dx(), b.Dy()
	if w <= maxSide && h <= maxSide {
		return src
	}
	scale := float64(maxSide) / float64(w)
	if h > w {
		scale = float64(maxSide) / float64(h)
	}
	nw := int(float64(w) * scale)
	nh := int(float64(h) * scale)
	dst := image.NewRGBA(image.Rect(0, 0, nw, nh))
	draw.CatmullRom.Scale(dst, dst.Bounds(), src, b, draw.Over, nil)
	return dst
}
