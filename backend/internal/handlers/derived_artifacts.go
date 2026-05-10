package handlers

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"

	"github.com/imranp/kerf/backend/internal/middleware"
)

// derivedMaxPayloadBytes caps the stored payload at 16 MiB. Mirrors the
// server-side limit other binary-ish endpoints use (assets, photos) so a
// runaway frontend can't OOM the cache table.
const derivedMaxPayloadBytes = 16 << 20

// computeContentSHA hashes the canonical file content the same way the
// lookup handler does. Extracted so store + lookup can't drift.
func computeContentSHA(content string) string {
	sum := sha256.Sum256([]byte(content))
	return hex.EncodeToString(sum[:])
}

// derivedKindAllowed mirrors the migration's CHECK constraint. Kept in
// Go so we can return BAD_REQUEST cleanly before the SQL round-trip.
func derivedKindAllowed(k string) bool {
	switch k {
	case "jscad_mesh", "sketch_geom2", "circuit_board_3d":
		return true
	}
	return false
}

type derivedLookupReq struct {
	DerivedKind string `json:"derived_kind"`
}

// derivedLookupResp is the cache lookup shape. cached=true → payload_b64
// is set. cached=false → 501 with error="compile-on-demand-not-yet-wired"
// (the cache layer ships before the compile path; consumers should treat
// 501 as "not in cache, no compile available yet").
type derivedLookupResp struct {
	Cached      bool   `json:"cached"`
	DerivedKind string `json:"derived_kind"`
	PayloadB64  string `json:"payload_b64,omitempty"`
	Error       string `json:"error,omitempty"`
}

// LookupDerivedArtifact handles POST /api/projects/{pid}/files/{fid}/derived.
// Returns the cached compiled artifact for the source file at its current
// content hash, or 501 (compile-on-demand-not-yet-wired) when the cache
// is cold. Membership-gated against the source project so cross-project
// callers without access can't probe for existence.
func (d *Deps) LookupDerivedArtifact(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	fid := chi.URLParam(r, "fid")
	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}
	var body derivedLookupReq
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if !derivedKindAllowed(body.DerivedKind) {
		writeError(w, http.StatusBadRequest, "invalid derived_kind")
		return
	}
	// Resolve the file's current content. We hash the canonical DB copy
	// (filesystem mirror is best-effort and not guaranteed to be in sync
	// across consumers).
	var content string
	err := d.Pool.QueryRow(r.Context(),
		`select coalesce(content, '') from files
		 where id = $1 and project_id = $2 and deleted_at is null`,
		fid, pid).Scan(&content)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "file not found")
			return
		}
		genericServerError(w, err)
		return
	}
	hash := computeContentSHA(content)

	var payload []byte
	err = d.Pool.QueryRow(r.Context(), `
		update derived_artifacts
		   set last_accessed_at = now()
		 where source_file_id = $1 and content_sha256 = $2 and derived_kind = $3
		returning payload
	`, fid, hash, body.DerivedKind).Scan(&payload)
	if err != nil && !errors.Is(err, pgx.ErrNoRows) {
		genericServerError(w, err)
		return
	}
	if errors.Is(err, pgx.ErrNoRows) {
		// v1: no compile-on-demand path — cache miss is terminal. The
		// frontend can pre-warm via a follow-up admin/worker hook.
		writeJSON(w, http.StatusNotImplemented, derivedLookupResp{
			Cached:      false,
			DerivedKind: body.DerivedKind,
			Error:       "compile-on-demand-not-yet-wired",
		})
		return
	}
	writeJSON(w, http.StatusOK, derivedLookupResp{
		Cached:      true,
		DerivedKind: body.DerivedKind,
		PayloadB64:  base64.StdEncoding.EncodeToString(payload),
	})
}

type derivedStoreReq struct {
	DerivedKind string `json:"derived_kind"`
	PayloadB64  string `json:"payload_b64"`
}

type derivedStoreResp struct {
	Stored           bool   `json:"stored"`
	DerivedKind      string `json:"derived_kind"`
	PayloadSizeBytes int    `json:"payload_size_bytes"`
}

// StoreDerivedArtifact handles POST /api/projects/{pid}/files/{fid}/derived/store.
// Pairs with LookupDerivedArtifact: the frontend (or a worker) calls this
// after a successful local compile so the next consumer of the same
// (source_file, content_sha, kind) tuple gets a cache hit instead of a 501.
//
// Idempotent: a re-store at the same key updates the payload and bumps
// last_accessed_at. Membership-gated, same as lookup, so cross-project
// callers can't write into someone else's cache row.
func (d *Deps) StoreDerivedArtifact(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	fid := chi.URLParam(r, "fid")
	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}

	// Hard cap on the request body before we even look at JSON. The
	// 16 MiB cap is on the decoded payload; the b64-encoded body is
	// ~33% larger, so we add a slop budget to let a maximal payload
	// + JSON envelope through cleanly.
	r.Body = http.MaxBytesReader(w, r.Body, derivedMaxPayloadBytes*2+4096)

	var body derivedStoreReq
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if !derivedKindAllowed(body.DerivedKind) {
		writeError(w, http.StatusBadRequest, "invalid derived_kind")
		return
	}
	payload, err := base64.StdEncoding.DecodeString(body.PayloadB64)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid payload_b64")
		return
	}
	if len(payload) > derivedMaxPayloadBytes {
		writeError(w, http.StatusBadRequest, "payload exceeds 16MiB cap")
		return
	}

	// Mirror the lookup handler's hash logic exactly — we hash the DB's
	// canonical file content (not the filesystem mirror) so store and
	// lookup always agree on the cache key.
	var content string
	err = d.Pool.QueryRow(r.Context(),
		`select coalesce(content, '') from files
		 where id = $1 and project_id = $2 and deleted_at is null`,
		fid, pid).Scan(&content)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "file not found")
			return
		}
		genericServerError(w, err)
		return
	}
	hash := computeContentSHA(content)

	// ON CONFLICT keeps the call idempotent: a second store at the
	// same key updates the cached payload and bumps last_accessed_at
	// rather than erroring out.
	_, err = d.Pool.Exec(r.Context(), `
		insert into derived_artifacts(source_file_id, content_sha256, derived_kind, payload, payload_size_bytes)
		values ($1, $2, $3, $4, $5)
		on conflict (source_file_id, content_sha256, derived_kind) do update set
			payload            = excluded.payload,
			payload_size_bytes = excluded.payload_size_bytes,
			last_accessed_at   = now()
	`, fid, hash, body.DerivedKind, payload, len(payload))
	if err != nil {
		genericServerError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, derivedStoreResp{
		Stored:           true,
		DerivedKind:      body.DerivedKind,
		PayloadSizeBytes: len(payload),
	})
}

// PurgeDerivedArtifacts handles DELETE /api/projects/{pid}/files/{fid}/derived.
// Drops every cached entry for the file regardless of content_sha256.
// Used by tests + future cache-bust admin paths.
func (d *Deps) PurgeDerivedArtifacts(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	fid := chi.URLParam(r, "fid")
	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}
	// Confirm the file exists in this project (don't leak counts for
	// foreign files).
	var exists bool
	err := d.Pool.QueryRow(r.Context(),
		`select true from files where id = $1 and project_id = $2`,
		fid, pid).Scan(&exists)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "file not found")
			return
		}
		genericServerError(w, err)
		return
	}
	tag, err := d.Pool.Exec(r.Context(),
		`delete from derived_artifacts where source_file_id = $1`, fid)
	if err != nil {
		genericServerError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"purged": tag.RowsAffected()})
}
