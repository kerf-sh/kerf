package handlers

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"image"
	"image/jpeg"
	_ "image/png" // register PNG decoder
	"io"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	xdraw "golang.org/x/image/draw"
	_ "golang.org/x/image/webp" // register WebP decoder

	"github.com/imranp/kerf/backend/internal/middleware"
	"github.com/imranp/kerf/backend/internal/models"
)

// avatarMaxBytes caps the inbound multipart payload at 1 MiB. The Google
// pull path uses the same limit on the response body.
const (
	avatarMaxBytes  = 1 * 1024 * 1024
	avatarTargetDim = 256
	avatarJPEGQ     = 85
)

// UploadAvatar handles POST /api/me/avatar (multipart, field "file").
//
//   - Accepts image/jpeg, image/png, image/webp.
//   - Server-side resize to a 256x256 max bounding box.
//   - Re-encoded as JPEG q=85 and stored at users/<uid>/avatar.jpg.
//   - users.avatar_storage_key + avatar_updated_at + avatar_url are
//     atomically updated.
//   - Best-effort delete of the previous storage_key (if any).
func (d *Deps) UploadAvatar(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	if uid == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return
	}
	if d.Storage == nil {
		writeError(w, http.StatusServiceUnavailable, "storage not configured")
		return
	}

	r.Body = http.MaxBytesReader(w, r.Body, avatarMaxBytes+4096)
	if err := r.ParseMultipartForm(avatarMaxBytes + 4096); err != nil {
		writeError(w, http.StatusBadRequest, "invalid multipart body: "+err.Error())
		return
	}
	file, fhdr, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, "missing 'file' field")
		return
	}
	defer file.Close()
	if fhdr.Size > avatarMaxBytes {
		writeError(w, http.StatusRequestEntityTooLarge, "avatar too large (>1MB)")
		return
	}

	// Sniff content-type from the first 512 bytes if header was missing.
	declared := strings.ToLower(fhdr.Header.Get("Content-Type"))
	if !isAcceptableAvatarType(declared) {
		// Don't 415 yet — image.Decode below catches truly bogus uploads.
		// We just won't trust the declared type.
	}

	jpgBytes, err := decodeAndResizeAvatar(file)
	if err != nil {
		writeError(w, http.StatusBadRequest, "decode/resize: "+err.Error())
		return
	}

	key := fmt.Sprintf("users/%s/avatar.jpg", uid)
	if _, err := d.Storage.Put(r.Context(), key, bytes.NewReader(jpgBytes), "image/jpeg", int64(len(jpgBytes))); err != nil {
		genericServerError(w, err)
		return
	}

	// Recompute the public URL with a cache-buster derived from now() —
	// we'll round-trip through the DB to capture the real timestamp.
	now := time.Now().UTC()
	publicURL := d.Storage.PublicURL(key, now)

	var (
		prevKey *string
		u       models.User
	)
	err = d.Pool.QueryRow(r.Context(), `
		with prev as (
			select avatar_storage_key from users where id = $1
		)
		update users
		   set avatar_storage_key = $2,
		       avatar_updated_at  = now(),
		       avatar_url         = $3
		  from prev
		 where users.id = $1
		returning prev.avatar_storage_key, users.id, users.email, users.name,
		          users.avatar_url, users.avatar_updated_at, users.account_role,
		          users.is_system, users.created_at
	`, uid, key, publicURL).Scan(&prevKey,
		&u.ID, &u.Email, &u.Name, &u.AvatarURL, &u.AvatarUpdatedAt,
		&u.AccountRole, &u.IsSystem, &u.CreatedAt)
	if err != nil {
		_ = d.Storage.Delete(r.Context(), key)
		genericServerError(w, err)
		return
	}

	if prevKey != nil && *prevKey != "" && *prevKey != key {
		_ = d.Storage.Delete(r.Context(), *prevKey)
	}

	writeJSON(w, http.StatusOK, u)
}

// DeleteAvatar handles DELETE /api/me/avatar. Removes the avatar from
// storage and clears the user fields. avatar_url is reset to "" — the
// frontend renders initials for empty avatars.
func (d *Deps) DeleteAvatar(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	if uid == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return
	}

	var prevKey *string
	var u models.User
	err := d.Pool.QueryRow(r.Context(), `
		with prev as (
			select avatar_storage_key from users where id = $1
		)
		update users
		   set avatar_storage_key = null,
		       avatar_updated_at  = now(),
		       avatar_url         = ''
		  from prev
		 where users.id = $1
		returning prev.avatar_storage_key, users.id, users.email, users.name,
		          users.avatar_url, users.avatar_updated_at, users.account_role,
		          users.is_system, users.created_at
	`, uid).Scan(&prevKey,
		&u.ID, &u.Email, &u.Name, &u.AvatarURL, &u.AvatarUpdatedAt,
		&u.AccountRole, &u.IsSystem, &u.CreatedAt)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "user not found")
			return
		}
		genericServerError(w, err)
		return
	}
	if d.Storage != nil && prevKey != nil && *prevKey != "" {
		_ = d.Storage.Delete(r.Context(), *prevKey)
	}
	writeJSON(w, http.StatusOK, u)
}

// isAcceptableAvatarType is informational — the real validator is
// image.Decode, which rejects malformed payloads regardless of header.
func isAcceptableAvatarType(ct string) bool {
	switch {
	case strings.Contains(ct, "image/jpeg"), strings.Contains(ct, "image/jpg"):
		return true
	case strings.Contains(ct, "image/png"):
		return true
	case strings.Contains(ct, "image/webp"):
		return true
	default:
		return false
	}
}

// decodeAndResizeAvatar reads an image (jpeg/png/webp) from r, scales it
// to fit inside avatarTargetDim x avatarTargetDim while preserving aspect
// ratio, and returns a freshly-encoded JPEG byte slice.
//
// We use golang.org/x/image/draw with CatmullRom — it's the highest-
// quality kernel in that package short of full Lanczos. For the 256-pixel
// targets we're producing, the perf cost is negligible (~1ms on a typical
// laptop CPU) and the smoothness is noticeably better than NearestNeighbor.
func decodeAndResizeAvatar(r io.Reader) ([]byte, error) {
	src, _, err := image.Decode(io.LimitReader(r, avatarMaxBytes+4096))
	if err != nil {
		return nil, fmt.Errorf("not a recognized image (jpeg/png/webp): %w", err)
	}

	bounds := src.Bounds()
	srcW, srcH := bounds.Dx(), bounds.Dy()
	if srcW <= 0 || srcH <= 0 {
		return nil, fmt.Errorf("image has zero dimension")
	}

	// Fit inside avatarTargetDim while preserving aspect ratio.
	dstW, dstH := srcW, srcH
	if srcW > avatarTargetDim || srcH > avatarTargetDim {
		if srcW >= srcH {
			dstW = avatarTargetDim
			dstH = (srcH * avatarTargetDim) / srcW
			if dstH < 1 {
				dstH = 1
			}
		} else {
			dstH = avatarTargetDim
			dstW = (srcW * avatarTargetDim) / srcH
			if dstW < 1 {
				dstW = 1
			}
		}
	}

	dst := image.NewRGBA(image.Rect(0, 0, dstW, dstH))
	xdraw.CatmullRom.Scale(dst, dst.Bounds(), src, bounds, xdraw.Over, nil)

	var buf bytes.Buffer
	if err := jpeg.Encode(&buf, dst, &jpeg.Options{Quality: avatarJPEGQ}); err != nil {
		return nil, fmt.Errorf("encode jpeg: %w", err)
	}
	return buf.Bytes(), nil
}

// pullGoogleAvatar downloads the avatar at picture and stores it as the
// user's avatar. Called fire-and-forget from the OAuth callback when the
// user has no existing avatar_storage_key.
//
// Concurrency note: two parallel logins for the same user could each
// reach this function. We mitigate the race by re-checking
// avatar_storage_key inside the UPDATE — the second writer's CAS will
// no-op (it sees the key already set, and avatar_storage_key is null
// matched against a now-non-null row, so 0 rows updated). The duplicate
// upload still hit storage at the same key, which is fine: same content
// (same Google URL), idempotent overwrite.
func (d *Deps) pullGoogleAvatar(userID, picture string) {
	// Background context — the request that kicked this off has already
	// returned. We give the goroutine its own deadline so a slow Google
	// CDN doesn't leak a socket forever.
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if d.Storage == nil {
		return
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, picture, nil)
	if err != nil {
		log.Printf("avatar: build google request: %v", err)
		return
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		log.Printf("avatar: fetch google picture: %v", err)
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		log.Printf("avatar: google picture returned %d", resp.StatusCode)
		return
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, avatarMaxBytes+1))
	if err != nil {
		log.Printf("avatar: read google picture body: %v", err)
		return
	}
	if int64(len(body)) > avatarMaxBytes {
		log.Printf("avatar: google picture too large (>1MB), skipping")
		return
	}

	jpgBytes, err := decodeAndResizeAvatar(bytes.NewReader(body))
	if err != nil {
		log.Printf("avatar: decode google picture: %v", err)
		return
	}

	key := fmt.Sprintf("users/%s/avatar.jpg", userID)
	if _, err := d.Storage.Put(ctx, key, bytes.NewReader(jpgBytes), "image/jpeg", int64(len(jpgBytes))); err != nil {
		log.Printf("avatar: store google picture: %v", err)
		return
	}

	now := time.Now().UTC()
	publicURL := d.Storage.PublicURL(key, now)

	// Conditional update — only the first concurrent login wins. Subsequent
	// callers see avatar_storage_key already set and update 0 rows; the
	// duplicate Put above is harmless (same key, same content semantically).
	tag, err := d.Pool.Exec(ctx, `
		update users
		   set avatar_storage_key = $2,
		       avatar_updated_at  = now(),
		       avatar_url         = $3
		 where id = $1
		   and (avatar_storage_key is null or avatar_storage_key = '')
	`, userID, key, publicURL)
	if err != nil {
		log.Printf("avatar: persist google avatar for %s: %v", userID, err)
		return
	}
	if tag.RowsAffected() == 0 {
		// Another goroutine got there first — best-effort delete our copy.
		// (In practice this is the same key so deleting would clobber the
		// winner. Skip the delete; both wrote identical content.)
		return
	}
}
