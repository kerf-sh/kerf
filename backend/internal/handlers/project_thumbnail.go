package handlers

// Project thumbnails: a small JPEG snapshot of the editor's viewport that the
// frontend renders client-side and uploads on idle. The Projects list shows
// these as <img>s; the workshop card pulls them too.
//
// Storage shape:
//   - blob at  projects/<pid>/thumbnail.jpg
//   - row     projects.thumbnail_storage_key, projects.thumbnail_updated_at
//   - URL     served via Storage.PublicURL with the updated_at as cache buster
//
// Efficiency: the frontend already debounces uploads (~2s after save settle)
// and skips when the file kind is STEP / drawing / dirty. Server-side we
// further:
//   - cap the inbound payload at 512 KiB (a 256x256 JPEG @ q=0.7 is ~30 KB)
//   - decode + re-encode at q=80 to strip metadata and normalize size
//   - reject anything that doesn't decode as an image
//   - swap the storage_key idempotently (same blob path overwrites in place)
//
// We keep ONE thumbnail per project — replacing on every accepted upload.
// Old key cleanup isn't necessary because the path is stable.

import (
	"bytes"
	"fmt"
	"image"
	"image/jpeg"
	_ "image/png"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"golang.org/x/image/draw"

	"github.com/imranp/kerf/backend/internal/middleware"
)

const (
	thumbMaxBytes  = 512 * 1024 // 512 KiB
	thumbTargetDim = 512        // 512×512 max bounding box (JPEG)
	thumbJPEGQ     = 80
)

// UploadProjectThumbnail accepts POST /api/projects/{pid}/thumbnail
// (multipart, field "file"). Member+ only.
//
// Returns the updated Project shape so the caller can update its UI without
// a second GET.
func (d *Deps) UploadProjectThumbnail(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	role := requireMember(w, r, d.Pool, pid, uid)
	if role == "" {
		return
	}
	if role == "viewer" {
		writeError(w, http.StatusForbidden, "viewers cannot upload thumbnails")
		return
	}
	if d.Storage == nil {
		writeError(w, http.StatusServiceUnavailable, "storage not configured")
		return
	}

	r.Body = http.MaxBytesReader(w, r.Body, thumbMaxBytes+4096)
	if err := r.ParseMultipartForm(thumbMaxBytes + 4096); err != nil {
		writeError(w, http.StatusBadRequest, "invalid multipart body: "+err.Error())
		return
	}
	file, fhdr, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, "missing 'file' field")
		return
	}
	defer file.Close()
	if fhdr.Size > thumbMaxBytes {
		writeError(w, http.StatusRequestEntityTooLarge, "thumbnail too large (>512KB)")
		return
	}
	declared := strings.ToLower(fhdr.Header.Get("Content-Type"))
	if !strings.HasPrefix(declared, "image/") && declared != "" {
		writeError(w, http.StatusUnsupportedMediaType, "unsupported content-type: "+declared)
		return
	}

	jpgBytes, err := decodeAndResizeThumbnail(file)
	if err != nil {
		writeError(w, http.StatusBadRequest, "decode/resize: "+err.Error())
		return
	}

	key := fmt.Sprintf("projects/%s/thumbnail.jpg", pid)
	if _, err := d.Storage.Put(r.Context(), key, bytes.NewReader(jpgBytes), "image/jpeg", int64(len(jpgBytes))); err != nil {
		genericServerError(w, err)
		return
	}

	now := time.Now().UTC()
	publicURL := d.Storage.PublicURL(key, now)

	// Update both columns + return the row in the same shape ListProjects
	// emits so the client can swap the card optimistically.
	var updatedAt time.Time
	err = d.Pool.QueryRow(r.Context(), `
		update projects
		   set thumbnail_storage_key = $2,
		       thumbnail_updated_at  = now()
		 where id = $1
		returning thumbnail_updated_at
	`, pid, key).Scan(&updatedAt)
	if err != nil {
		_ = d.Storage.Delete(r.Context(), key)
		genericServerError(w, err)
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"id":            pid,
		"thumbnail_url": publicURL,
		"updated_at":    updatedAt,
	})
}

// decodeAndResizeThumbnail accepts JPEG/PNG, optionally downscales to fit
// thumbTargetDim, re-encodes as JPEG at thumbJPEGQ. Returns the encoded
// byte slice. Errors on undecodable input or zero-pixel images.
func decodeAndResizeThumbnail(r io.Reader) ([]byte, error) {
	src, _, err := image.Decode(r)
	if err != nil {
		return nil, err
	}
	bounds := src.Bounds()
	if bounds.Dx() == 0 || bounds.Dy() == 0 {
		return nil, fmt.Errorf("zero-pixel image")
	}
	// Downscale only — never upscale.
	w, h := bounds.Dx(), bounds.Dy()
	if w > thumbTargetDim || h > thumbTargetDim {
		ratio := float64(thumbTargetDim) / float64(max(w, h))
		nw := int(float64(w) * ratio)
		nh := int(float64(h) * ratio)
		dst := image.NewRGBA(image.Rect(0, 0, nw, nh))
		draw.CatmullRom.Scale(dst, dst.Bounds(), src, bounds, draw.Over, nil)
		src = dst
	}
	var buf bytes.Buffer
	if err := jpeg.Encode(&buf, src, &jpeg.Options{Quality: thumbJPEGQ}); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}
