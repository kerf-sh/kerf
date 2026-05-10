// Package tess hosts the placeholder STEP pre-tessellation worker.
//
// This package is intentionally a stub: it polls step_tessellation_jobs,
// flips rows queued → running → done, and writes a tiny valid-but-empty
// .glb to Storage so the rest of the system observes the "ready" signal
// (mesh_storage_key populated, files.tessellation_status='done' via the
// LEFT JOIN in handlers/files.go). The real OCCT-in-WASM mesh-generation
// engine is a follow-up; the placeholder GLB will fail to parse on the
// frontend and the existing loadMeshFromURL fallback re-loads the STEP
// via the legacy in-browser path. That fallback is what makes shipping
// the empty-GLB worker harmless.
//
// Why a brand-new package alongside internal/tessellate (which already
// contains a Node-sidecar worker): the sidecar worker is the previous
// stalled attempt — it requires `node` on PATH plus a JS dependency we
// don't want to commit to in the brew/curl-install path yet. This stub
// has zero external deps and lets the wiring (enqueue → worker → mesh
// available) ship today. The two workers don't both run — main.go
// chooses one based on config; the tess worker is the OSS default.
package tess

import (
	"bytes"
	"context"
	"encoding/binary"
	"errors"
	"fmt"
	"log"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/internal/storage"
)

// pollIdle is how long the worker sleeps after an empty queue scan.
// 500ms keeps test-suite latency tight while staying low-CPU.
const pollIdle = 500 * time.Millisecond

// fakeWork simulates the OCCT parse + meshing cost. Kept short so tests
// observe done-status well within the 10s scenario poll budget.
const fakeWork = 100 * time.Millisecond

// RunWorker loops until ctx is cancelled, draining
// step_tessellation_jobs one row at a time. Safe to call as a goroutine
// from main; logs and continues on transient errors so a flaky DB
// connection doesn't kill the worker.
//
// The worker is a no-op when storage is nil (e.g. mis-configured deploy)
// — better to skip jobs than to flip them to running and never finish.
func RunWorker(ctx context.Context, pool *pgxpool.Pool, store storage.Storage) {
	if pool == nil {
		log.Printf("tess: pool nil; placeholder worker not started")
		return
	}
	if store == nil {
		log.Printf("tess: storage nil; placeholder worker not started")
		return
	}
	log.Printf("tess: placeholder worker started (empty-GLB mode)")
	for {
		if err := ctx.Err(); err != nil {
			log.Printf("tess: stopping (%v)", err)
			return
		}
		ran, err := runOne(ctx, pool, store)
		if err != nil {
			// Don't let a transient pool / Storage hiccup busy-loop.
			log.Printf("tess: runOne: %v", err)
			if !sleep(ctx, 2*time.Second) {
				return
			}
			continue
		}
		if !ran {
			if !sleep(ctx, pollIdle) {
				return
			}
		}
	}
}

// runOne claims one queued job, processes it, and returns ran=true iff
// the queue was non-empty (so the caller can poll continuously while
// there's backlog and only sleep when idle). Errors that are job-scoped
// are recorded onto the job row; only DB-wide errors bubble out.
func runOne(ctx context.Context, pool *pgxpool.Pool, store storage.Storage) (bool, error) {
	job, err := claim(ctx, pool)
	if err != nil {
		return false, err
	}
	if job == nil {
		return false, nil
	}

	if err := process(ctx, pool, store, job); err != nil {
		// Mark the job failed; never retry automatically (operator can
		// re-queue manually). Use a fresh ctx-bound exec so a cancelled
		// jobCtx doesn't also nuke the bookkeeping write.
		if _, dbErr := pool.Exec(ctx, `
			update step_tessellation_jobs
			set status='error', error=$2, finished_at=now()
			where id=$1
		`, job.ID, truncateErr(err.Error())); dbErr != nil {
			log.Printf("tess: mark error (job=%s): %v (orig: %v)", job.ID, dbErr, err)
		} else {
			log.Printf("tess: job=%s file=%s failed: %v", job.ID, job.FileID, err)
		}
	}
	return true, nil
}

// job is the shape claim returns. Storage key is included so process
// doesn't need a second SELECT.
type job struct {
	ID         string
	FileID     string
	ProjectID  string
	StorageKey string
}

// claim atomically picks one queued job and flips it to 'running' under
// FOR UPDATE SKIP LOCKED. Returns (nil,nil) when the queue is empty.
func claim(ctx context.Context, pool *pgxpool.Pool) (*job, error) {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	var (
		jobID, fileID, projectID string
		storageKey               *string
	)
	err = tx.QueryRow(ctx, `
		select j.id, j.file_id, f.project_id, f.storage_key
		from step_tessellation_jobs j
		join files f on f.id = j.file_id
		where j.status = 'queued' and f.deleted_at is null
		order by j.created_at asc
		for update of j skip locked
		limit 1
	`).Scan(&jobID, &fileID, &projectID, &storageKey)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, nil
		}
		return nil, fmt.Errorf("claim: %w", err)
	}

	if storageKey == nil || *storageKey == "" {
		// File row lost its blob between enqueue and claim; mark error
		// and move on rather than spinning indefinitely.
		if _, err := tx.Exec(ctx, `
			update step_tessellation_jobs
			set status='error', error='file has no storage_key', finished_at=now()
			where id=$1
		`, jobID); err != nil {
			return nil, err
		}
		if err := tx.Commit(ctx); err != nil {
			return nil, err
		}
		return nil, nil
	}

	if _, err := tx.Exec(ctx, `
		update step_tessellation_jobs
		set status='running', started_at=now()
		where id=$1
	`, jobID); err != nil {
		return nil, err
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}
	return &job{ID: jobID, FileID: fileID, ProjectID: projectID, StorageKey: *storageKey}, nil
}

// process simulates tessellation, uploads the placeholder .glb, and
// marks both the job row and the file row done. The mesh quality is
// intentionally an empty GLB — see package doc.
func process(ctx context.Context, pool *pgxpool.Pool, store storage.Storage, j *job) error {
	// Simulated work — short enough that the test scenario's 10s poll
	// budget is comfortable, long enough that a multi-job test would
	// see the running→done transition rather than instant flips.
	if !sleep(ctx, fakeWork) {
		return ctx.Err()
	}

	glb := emptyGLB()
	meshKey := fmt.Sprintf("projects/%s/files/%s/mesh.glb", j.ProjectID, j.FileID)
	if _, err := store.Put(ctx, meshKey, bytes.NewReader(glb), "model/gltf-binary", int64(len(glb))); err != nil {
		return fmt.Errorf("upload glb: %w", err)
	}

	tx, err := pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	// updated_at gets bumped so attachMeshURL's ?v=<unix> cache-buster
	// changes — frontends that already fetched a stale (or absent)
	// mesh_url see the new one on the next ListFiles refresh.
	if _, err := tx.Exec(ctx, `
		update files
		set mesh_storage_key=$2, updated_at=now()
		where id=$1 and deleted_at is null
	`, j.FileID, meshKey); err != nil {
		return fmt.Errorf("update file: %w", err)
	}
	if _, err := tx.Exec(ctx, `
		update step_tessellation_jobs
		set status='done', mesh_storage_key=$2, finished_at=now(), error=null
		where id=$1
	`, j.ID, meshKey); err != nil {
		return fmt.Errorf("update job: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit: %w", err)
	}
	log.Printf("tess: job=%s file=%s done (placeholder, %dB)", j.ID, j.FileID, len(glb))
	return nil
}

// emptyGLB returns the smallest valid GLB: a 12-byte header followed
// by a single JSON chunk containing the minimum-required asset object.
// No buffers, no meshes — the frontend's GLTFLoader either parses an
// empty scene or rejects it; either way loadMeshFromURL falls back to
// the STEP path. We build it on the fly rather than embedding a
// constant so the byte count is verifiable from the source.
func emptyGLB() []byte {
	const minimalJSON = `{"asset":{"version":"2.0"}}`
	// glTF 2.0 spec §3.4 requires JSON chunk length to be a multiple
	// of 4; pad with spaces (0x20). 26 bytes → pad 2 → 28 bytes.
	pad := (4 - len(minimalJSON)%4) % 4
	jsonBytes := make([]byte, 0, len(minimalJSON)+pad)
	jsonBytes = append(jsonBytes, minimalJSON...)
	for i := 0; i < pad; i++ {
		jsonBytes = append(jsonBytes, ' ')
	}

	const headerSize = 12
	const chunkHeaderSize = 8
	totalLen := headerSize + chunkHeaderSize + len(jsonBytes)

	out := make([]byte, 0, totalLen)
	// Header: magic 'glTF', version 2, total length.
	out = append(out, 'g', 'l', 'T', 'F')
	out = binary.LittleEndian.AppendUint32(out, 2)
	out = binary.LittleEndian.AppendUint32(out, uint32(totalLen))
	// JSON chunk header: length, type 'JSON' (0x4E4F534A).
	out = binary.LittleEndian.AppendUint32(out, uint32(len(jsonBytes)))
	out = append(out, 'J', 'S', 'O', 'N')
	out = append(out, jsonBytes...)
	return out
}

// sleep blocks for d or until ctx is cancelled. Returns false iff the
// context fired (so the caller knows to bail rather than retry).
func sleep(ctx context.Context, d time.Duration) bool {
	if d <= 0 {
		return ctx.Err() == nil
	}
	t := time.NewTimer(d)
	defer t.Stop()
	select {
	case <-ctx.Done():
		return false
	case <-t.C:
		return true
	}
}

// truncateErr keeps long error strings out of the (text) error column
// so a runaway driver doesn't dump kilobytes into Postgres.
func truncateErr(s string) string {
	const max = 800
	if len(s) <= max {
		return s
	}
	return s[:max] + "..."
}
