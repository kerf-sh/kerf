package handlers

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/imranp/kerf/backend/internal/middleware"
	"github.com/imranp/kerf/backend/internal/models"
	"github.com/imranp/kerf/backend/internal/usage"
)

// Per-chunk PUT body cap. Backed by configured chunk size + a small slack to
// tolerate the very last chunk being padded with metadata under unusual
// content-encodings. We don't accept arbitrary bytes here — anything beyond
// the configured chunk size is rejected.
const chunkSlackBytes = 64 * 1024

// initUploadReq is the JSON body for `POST /uploads`.
type initUploadReq struct {
	Filename string `json:"filename"`
	Size     int64  `json:"size"`
	MIME     string `json:"mime"`
	SHA256   string `json:"sha256"`
}

type initUploadResp struct {
	UploadID       string `json:"upload_id"`
	ChunkSize      int64  `json:"chunk_size"`
	ReceivedChunks []int  `json:"received_chunks"`
	TotalChunks    int    `json:"total_chunks"`
	Complete       bool   `json:"complete"`
}

type uploadStatusResp struct {
	UploadID       string `json:"upload_id"`
	ReceivedChunks []int  `json:"received_chunks"`
	TotalChunks    int    `json:"total_chunks"`
	BytesReceived  int64  `json:"bytes_received"`
	Complete       bool   `json:"complete"`
}

type finalizeUploadReq struct {
	Kind     string  `json:"kind"`
	ParentID *string `json:"parent_id"`
}

// uploadKey returns the temp storage prefix used by the chunked-upload
// helpers. Keeping this off the project root sidesteps any clash with
// real `projects/...` keys.
func uploadKey(uploadID string) string {
	return uploadID
}

// InitUpload starts (or resumes) a chunked upload session.
//
// Idempotency: if the project already has a *complete* session with the same
// SHA-256, we return its id with `complete:true` so the client can call
// finalize directly without re-sending bytes. If a session for the same
// SHA exists and is still in flight, we return its id along with
// `received_chunks` so the client only sends the missing ones.
func (d *Deps) InitUpload(w http.ResponseWriter, r *http.Request) {
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

	var body initUploadReq
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	body.Filename = strings.TrimSpace(body.Filename)
	body.SHA256 = strings.ToLower(strings.TrimSpace(body.SHA256))
	if body.Filename == "" {
		writeError(w, http.StatusBadRequest, "filename required")
		return
	}
	if body.Size <= 0 {
		writeError(w, http.StatusBadRequest, "size must be > 0")
		return
	}
	if d.Cfg.StepMaxBytes > 0 && body.Size > d.Cfg.StepMaxBytes {
		writeError(w, http.StatusRequestEntityTooLarge,
			fmt.Sprintf("file too large (>%d bytes)", d.Cfg.StepMaxBytes))
		return
	}
	if len(body.SHA256) != 64 {
		writeError(w, http.StatusBadRequest, "sha256 must be a 64-char hex digest")
		return
	}
	if _, err := hex.DecodeString(body.SHA256); err != nil {
		writeError(w, http.StatusBadRequest, "sha256 must be hex")
		return
	}

	chunkSize := d.Cfg.UploadChunkSize
	if chunkSize <= 0 {
		chunkSize = 5_242_880
	}
	totalChunks := int((body.Size + chunkSize - 1) / chunkSize)
	if totalChunks <= 0 {
		totalChunks = 1
	}

	// Idempotency / resume: look for an existing upload session for the
	// same project+sha that hasn't expired. If we find a *complete* one,
	// the caller can just re-finalize (rare, but covers double-clicks).
	var (
		existingID       string
		existingComplete bool
		existingReceived []int32
		existingBytes    int64
		existingTotal    int
	)
	err := d.Pool.QueryRow(r.Context(), `
		select id, complete, received_chunks, bytes_received, total_chunks
		from upload_sessions
		where project_id = $1 and sha256 = $2 and expires_at > now()
		order by created_at desc
		limit 1
	`, pid, body.SHA256).Scan(&existingID, &existingComplete, &existingReceived, &existingBytes, &existingTotal)
	if err == nil {
		writeJSON(w, http.StatusOK, initUploadResp{
			UploadID:       existingID,
			ChunkSize:      chunkSize,
			ReceivedChunks: int32sliceToInt(existingReceived),
			TotalChunks:    existingTotal,
			Complete:       existingComplete,
		})
		return
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		genericServerError(w, err)
		return
	}

	// Fresh upload session.
	upID := uuid.New().String()
	storageKey := uploadKey(upID)
	ttl := d.Cfg.UploadSessionTTL
	if ttl <= 0 {
		ttl = 24 * time.Hour
	}
	expiresAt := time.Now().Add(ttl)

	_, err = d.Pool.Exec(r.Context(), `
		insert into upload_sessions
		  (id, project_id, user_id, filename, size, mime, sha256,
		   storage_key, chunk_size, total_chunks, expires_at)
		values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
	`, upID, pid, uid, body.Filename, body.Size, nullableString(body.MIME), body.SHA256,
		storageKey, chunkSize, totalChunks, expiresAt)
	if err != nil {
		genericServerError(w, err)
		return
	}

	writeJSON(w, http.StatusCreated, initUploadResp{
		UploadID:       upID,
		ChunkSize:      chunkSize,
		ReceivedChunks: []int{},
		TotalChunks:    totalChunks,
		Complete:       false,
	})
}

// PutChunk handles `PUT /uploads/{uid}/chunks/{n}` (raw bytes).
func (d *Deps) PutChunk(w http.ResponseWriter, r *http.Request) {
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

	upID := chi.URLParam(r, "uid")
	chunkIdxStr := chi.URLParam(r, "n")
	chunkIdx, err := strconv.Atoi(chunkIdxStr)
	if err != nil || chunkIdx < 0 {
		writeError(w, http.StatusBadRequest, "invalid chunk index")
		return
	}

	sess, ok := d.loadUploadSession(w, r, pid, upID)
	if !ok {
		return
	}
	if sess.Complete {
		writeError(w, http.StatusConflict, "upload already complete")
		return
	}
	if chunkIdx >= sess.TotalChunks {
		writeError(w, http.StatusBadRequest, "chunk index out of range")
		return
	}

	// Cap the body to one chunk (+slack). The configured chunk size is
	// load-bearing — any client claiming a bigger chunk is rejected.
	maxBody := sess.ChunkSize + chunkSlackBytes
	r.Body = http.MaxBytesReader(w, r.Body, maxBody)

	// Buffer to count bytes; the storage layer reads from this.
	cr := &countingReader{r: r.Body}
	if err := d.Storage.PutChunk(r.Context(), sess.StorageKey, chunkIdx, cr); err != nil {
		writeError(w, http.StatusInternalServerError, "chunk store: "+err.Error())
		return
	}

	// Update the session row idempotently (if we already had this index in
	// received_chunks, leave bytes_received alone). Postgres array_position
	// returns NULL when the value is absent.
	_, err = d.Pool.Exec(r.Context(), `
		update upload_sessions
		set received_chunks = case
		      when array_position(received_chunks, $2::int) is null
		        then array_append(received_chunks, $2::int)
		      else received_chunks
		    end,
		    bytes_received = case
		      when array_position(received_chunks, $2::int) is null
		        then bytes_received + $3
		      else bytes_received
		    end
		where id = $1
	`, upID, chunkIdx, cr.n)
	if err != nil {
		genericServerError(w, err)
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

// GetUpload returns the status of a chunked upload.
func (d *Deps) GetUpload(w http.ResponseWriter, r *http.Request) {
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
	upID := chi.URLParam(r, "uid")
	sess, ok := d.loadUploadSession(w, r, pid, upID)
	if !ok {
		return
	}
	writeJSON(w, http.StatusOK, uploadStatusResp{
		UploadID:       sess.ID,
		ReceivedChunks: int32sliceToInt(sess.ReceivedChunks),
		TotalChunks:    sess.TotalChunks,
		BytesReceived:  sess.BytesReceived,
		Complete:       sess.Complete,
	})
}

// FinalizeUpload concatenates the chunks, verifies SHA-256, moves the blob
// into permanent storage, and creates the matching `files` row.
func (d *Deps) FinalizeUpload(w http.ResponseWriter, r *http.Request) {
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

	var body finalizeUploadReq
	// Tolerate an empty body — `kind` defaults to 'step'.
	if r.ContentLength > 0 {
		if err := decodeJSON(r, &body); err != nil {
			writeError(w, http.StatusBadRequest, "invalid body")
			return
		}
	}
	if body.Kind == "" {
		body.Kind = "step"
	}
	if body.Kind != "step" {
		writeError(w, http.StatusBadRequest, "only kind='step' is supported")
		return
	}

	upID := chi.URLParam(r, "uid")
	sess, ok := d.loadUploadSession(w, r, pid, upID)
	if !ok {
		return
	}

	// Verify all chunks have landed.
	if len(sess.ReceivedChunks) != sess.TotalChunks {
		writeError(w, http.StatusBadRequest,
			fmt.Sprintf("missing chunks: have %d of %d", len(sess.ReceivedChunks), sess.TotalChunks))
		return
	}

	// Optional parent_id (must be a folder in the same project).
	var parentID *string
	if body.ParentID != nil && *body.ParentID != "" {
		v := *body.ParentID
		if _, err := uuid.Parse(v); err != nil {
			writeError(w, http.StatusBadRequest, "invalid parent_id")
			return
		}
		var pkind string
		if err := d.Pool.QueryRow(r.Context(),
			`select kind from files where id = $1 and project_id = $2 and deleted_at is null`,
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

	// Destination key — same shape as the simple multipart upload path.
	finalKey := fmt.Sprintf("projects/%s/assets/%s-%s",
		pid, uuid.New().String(), sanitizeFilename(sess.Filename))

	// Concat to permanent storage.
	size, err := d.Storage.ConcatChunksTo(r.Context(), sess.StorageKey, finalKey)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "assemble chunks: "+err.Error())
		return
	}

	// Verify SHA-256 by streaming the assembled object back through the
	// hasher. Mismatch → wipe everything, return 422.
	rc, _, err := d.Storage.Get(r.Context(), finalKey)
	if err != nil {
		_ = d.Storage.Delete(r.Context(), finalKey)
		_ = d.Storage.DeleteUpload(r.Context(), sess.StorageKey)
		_, _ = d.Pool.Exec(r.Context(), `delete from upload_sessions where id = $1`, sess.ID)
		writeError(w, http.StatusInternalServerError, "verify read: "+err.Error())
		return
	}
	hasher := sha256.New()
	if _, err := io.Copy(hasher, rc); err != nil {
		_ = rc.Close()
		_ = d.Storage.Delete(r.Context(), finalKey)
		_ = d.Storage.DeleteUpload(r.Context(), sess.StorageKey)
		_, _ = d.Pool.Exec(r.Context(), `delete from upload_sessions where id = $1`, sess.ID)
		writeError(w, http.StatusInternalServerError, "verify hash: "+err.Error())
		return
	}
	_ = rc.Close()
	gotSHA := hex.EncodeToString(hasher.Sum(nil))
	if gotSHA != sess.SHA256 {
		_ = d.Storage.Delete(r.Context(), finalKey)
		_ = d.Storage.DeleteUpload(r.Context(), sess.StorageKey)
		_, _ = d.Pool.Exec(r.Context(), `delete from upload_sessions where id = $1`, sess.ID)
		writeJSON(w, http.StatusUnprocessableEntity, map[string]string{
			"error": "checksum mismatch",
			"code":  "CHECKSUM_MISMATCH",
		})
		return
	}

	mimeType := sess.MIME
	if mimeType == "" {
		mimeType = "model/step"
	}

	var f models.File
	err = d.Pool.QueryRow(r.Context(), `
		insert into files(project_id, parent_id, name, kind, content, storage_key, mime_type, size)
		values ($1,$2,$3,'step','',$4,$5,$6)
		returning id, project_id, parent_id, name, kind, content, storage_key, mime_type, size, created_at, updated_at
	`, pid, parentID, sess.Filename, finalKey, mimeType, size).Scan(
		&f.ID, &f.ProjectID, &f.ParentID, &f.Name, &f.Kind, &f.Content,
		&f.StorageKey, &f.MimeType, &f.Size, &f.CreatedAt, &f.UpdatedAt)
	if err != nil {
		_ = d.Storage.Delete(r.Context(), finalKey)
		_ = d.Storage.DeleteUpload(r.Context(), sess.StorageKey)
		_, _ = d.Pool.Exec(r.Context(), `delete from upload_sessions where id = $1`, sess.ID)
		genericServerError(w, err)
		return
	}

	// Wipe temp chunks + session row — done.
	_ = d.Storage.DeleteUpload(r.Context(), sess.StorageKey)
	_, _ = d.Pool.Exec(r.Context(), `delete from upload_sessions where id = $1`, sess.ID)

	if d.Cfg.UsageEnabled && size > 0 {
		pidVal := pid
		_ = usage.RecordStorage(r.Context(), d.Pool, uid, &pidVal, size)
	}

	// Performance Phase 3: enqueue server-side STEP pre-tessellation. The
	// background worker pool (cmd/server boots one) picks the row up,
	// runs occt-import-js via the Node sidecar, and stamps mesh_storage_key
	// so the frontend can prefer the cheap GLTFLoader path. Failure is
	// non-fatal — the upload itself succeeded; the frontend falls back to
	// in-browser STEP parsing if the .glb never appears.
	if _, qerr := d.Pool.Exec(r.Context(),
		`insert into step_tessellation_jobs (file_id) values ($1) on conflict (file_id) do nothing`,
		f.ID); qerr != nil {
		// Log via the request logger; don't bother the client.
		// (genericServerError would 500 on what's actually a successful upload.)
		fmt.Printf("uploads: enqueue tessellate job (file=%s): %v\n", f.ID, qerr)
	}

	d.attachDownloadURL(&f)
	writeJSON(w, http.StatusCreated, f)
}

// CancelUpload aborts and wipes an in-flight upload.
func (d *Deps) CancelUpload(w http.ResponseWriter, r *http.Request) {
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
	upID := chi.URLParam(r, "uid")

	// Loading the session also enforces project ownership.
	sess, ok := d.loadUploadSession(w, r, pid, upID)
	if !ok {
		return
	}
	if d.Storage != nil {
		_ = d.Storage.DeleteUpload(r.Context(), sess.StorageKey)
	}
	_, err := d.Pool.Exec(r.Context(), `delete from upload_sessions where id = $1`, sess.ID)
	if err != nil {
		genericServerError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// uploadSession is the in-memory shape of an upload_sessions row.
type uploadSession struct {
	ID             string
	ProjectID      string
	UserID         string
	Filename       string
	Size           int64
	MIME           string
	SHA256         string
	StorageKey     string
	ChunkSize      int64
	TotalChunks    int
	ReceivedChunks []int32
	BytesReceived  int64
	Complete       bool
	ExpiresAt      time.Time
}

// loadUploadSession fetches an upload_sessions row, scoped to the given
// project. Returns false (and writes the appropriate error) if the row is
// missing, expired, or owned by a different project.
func (d *Deps) loadUploadSession(w http.ResponseWriter, r *http.Request, projectID, uploadID string) (*uploadSession, bool) {
	if _, err := uuid.Parse(uploadID); err != nil {
		writeError(w, http.StatusBadRequest, "invalid upload id")
		return nil, false
	}
	var s uploadSession
	var mime *string
	err := d.Pool.QueryRow(r.Context(), `
		select id, project_id, user_id, filename, size, mime, sha256, storage_key,
		       chunk_size, total_chunks, received_chunks, bytes_received, complete, expires_at
		from upload_sessions
		where id = $1 and project_id = $2
	`, uploadID, projectID).Scan(
		&s.ID, &s.ProjectID, &s.UserID, &s.Filename, &s.Size, &mime, &s.SHA256, &s.StorageKey,
		&s.ChunkSize, &s.TotalChunks, &s.ReceivedChunks, &s.BytesReceived, &s.Complete, &s.ExpiresAt,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "upload not found")
			return nil, false
		}
		genericServerError(w, err)
		return nil, false
	}
	if mime != nil {
		s.MIME = *mime
	}
	if s.ExpiresAt.Before(time.Now()) {
		writeError(w, http.StatusGone, "upload expired")
		return nil, false
	}
	return &s, true
}

// countingReader wraps io.Reader and tracks bytes read.
type countingReader struct {
	r io.Reader
	n int64
}

func (c *countingReader) Read(p []byte) (int, error) {
	n, err := c.r.Read(p)
	c.n += int64(n)
	return n, err
}

func nullableString(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

func int32sliceToInt(in []int32) []int {
	if len(in) == 0 {
		return []int{}
	}
	out := make([]int, len(in))
	for i, v := range in {
		out[i] = int(v)
	}
	return out
}
