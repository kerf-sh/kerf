// Package tessellate runs server-side STEP → glTF binary (.glb) conversion
// for the Performance Phase 3 pre-tessellation pipeline. The actual STEP
// parsing happens in a Node subprocess via scripts/step-tessellate.mjs
// (which loads occt-import-js, the same library the browser uses); this
// package owns the Go-side worker pool and DB plumbing.
//
// Why a Node sidecar (Option B) rather than wazero (Option A): occt-import-js
// is Emscripten-compiled and expects a substantial chunk of the browser /
// Node runtime — Module["FS"] virtual filesystem, Module["onRuntimeInitialized"]
// callbacks, atexit hooks, the works. Re-implementing that against wazero
// is well beyond a "few hours of glue" and is the very class of problem
// the brief flagged as a fall-back trigger. The JS glue ships an
// ENVIRONMENT_IS_NODE branch that "just works", and the per-job startup
// cost is negligible compared to the OCCT parse itself for any non-trivial
// STEP file. Cons: production deploys must include `node` on PATH.
package tessellate

import (
	"context"
	"fmt"
	"log"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/internal/config"
	"github.com/imranp/kerf/backend/internal/storage"
)

// Worker pulls queued step_tessellation_jobs and runs them through the
// Node sidecar. Multiple workers can share the same Pool/Storage — each
// claims rows atomically via the SELECT ... FOR UPDATE SKIP LOCKED dance
// in claimNextJob.
type Worker struct {
	cfg     *config.Config
	pool    *pgxpool.Pool
	storage storage.Storage
	driver  Driver

	pollInterval time.Duration
}

// Driver is the swappable backend that turns a STEP byte stream into a
// .glb byte stream. The default driver shells out to a Node sidecar; tests
// can plug in a stub.
type Driver interface {
	Tessellate(ctx context.Context, step []byte) ([]byte, error)
}

// New builds a Worker that uses the default Node sidecar driver.
func New(cfg *config.Config, pool *pgxpool.Pool, store storage.Storage) *Worker {
	return &Worker{
		cfg:          cfg,
		pool:         pool,
		storage:      store,
		driver:       NewNodeSidecarDriver(cfg),
		pollInterval: 5 * time.Second,
	}
}

// WithDriver replaces the default driver. Used by tests.
func (w *Worker) WithDriver(d Driver) *Worker {
	w.driver = d
	return w
}

// Run starts a goroutine pool of size cfg.StepTessellateWorkers. Each
// goroutine loops until ctx is cancelled. Returns immediately; the pool
// runs in the background. Idempotent / no-op when StepTessellateWorkers
// is 0.
func (w *Worker) Run(ctx context.Context) {
	n := w.cfg.StepTessellateWorkers
	if n <= 0 {
		log.Printf("tessellate: workers disabled (step_tessellate_workers=%d)", n)
		return
	}
	if w.storage == nil {
		log.Printf("tessellate: storage not configured; worker pool not started")
		return
	}
	log.Printf("tessellate: starting %d worker(s)", n)
	var wg sync.WaitGroup
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			w.loop(ctx, id)
		}(i)
	}
	// We don't wait on wg here — Run is fire-and-forget. The wait only
	// matters during graceful shutdown, which the caller can implement by
	// cancelling the ctx and observing process exit.
	go func() {
		<-ctx.Done()
		wg.Wait()
		log.Printf("tessellate: worker pool stopped")
	}()
}

// loop is one worker goroutine. Pulls a job, runs it, repeat. Sleeps
// w.pollInterval between empty queue scans.
func (w *Worker) loop(ctx context.Context, workerID int) {
	for {
		if ctx.Err() != nil {
			return
		}
		ran, err := w.runOne(ctx)
		if err != nil {
			// Log and back off briefly so a hot DB error doesn't busy-loop.
			log.Printf("tessellate[%d]: runOne: %v", workerID, err)
			select {
			case <-ctx.Done():
				return
			case <-time.After(2 * time.Second):
			}
			continue
		}
		if !ran {
			// Empty queue — wait before polling again. Replace with a
			// LISTEN/NOTIFY in a future round if latency matters.
			select {
			case <-ctx.Done():
				return
			case <-time.After(w.pollInterval):
			}
		}
	}
}

// runOne claims the next queued job and processes it. Returns ran=true
// iff a job was processed (success or error).
func (w *Worker) runOne(ctx context.Context) (bool, error) {
	job, err := w.claimNextJob(ctx)
	if err != nil {
		return false, err
	}
	if job == nil {
		return false, nil
	}

	// Outer per-job timeout includes storage I/O + sidecar runtime.
	timeout := time.Duration(w.cfg.StepTessellateTimeoutSec) * time.Second
	if timeout <= 0 {
		timeout = 5 * time.Minute
	}
	jobCtx, cancel := context.WithTimeout(ctx, timeout+30*time.Second)
	defer cancel()

	if err := w.processJob(jobCtx, job); err != nil {
		// Mark failed; no retry in v1. Operator can re-enqueue manually
		// (UPDATE step_tessellation_jobs SET status='queued', error=NULL
		//  WHERE file_id = ?).
		_, dbErr := w.pool.Exec(ctx, `
			update step_tessellation_jobs
			set status = 'error', error = $2, finished_at = now()
			where id = $1
		`, job.ID, err.Error())
		if dbErr != nil {
			log.Printf("tessellate: mark error (job=%s): %v (orig: %v)", job.ID, dbErr, err)
		} else {
			log.Printf("tessellate: job=%s file=%s failed: %v", job.ID, job.FileID, err)
		}
		return true, nil
	}
	return true, nil
}

// claimedJob is the row shape returned by claimNextJob.
type claimedJob struct {
	ID         string
	FileID     string
	ProjectID  string
	StorageKey string
}

// claimNextJob atomically picks one queued job and flips it to 'running'.
// Uses SELECT ... FOR UPDATE SKIP LOCKED so multiple workers don't race
// on the same row.
func (w *Worker) claimNextJob(ctx context.Context) (*claimedJob, error) {
	tx, err := w.pool.Begin(ctx)
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
		if err == pgx.ErrNoRows {
			return nil, nil
		}
		return nil, fmt.Errorf("claim: %w", err)
	}
	if storageKey == nil || *storageKey == "" {
		// File row has no blob — mark error, commit, move on.
		_, err = tx.Exec(ctx, `
			update step_tessellation_jobs
			set status='error', error='file has no storage_key', finished_at=now()
			where id = $1
		`, jobID)
		if err != nil {
			return nil, err
		}
		if err := tx.Commit(ctx); err != nil {
			return nil, err
		}
		return nil, nil
	}

	_, err = tx.Exec(ctx, `
		update step_tessellation_jobs
		set status='running', started_at=now()
		where id = $1
	`, jobID)
	if err != nil {
		return nil, err
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}
	return &claimedJob{
		ID:         jobID,
		FileID:     fileID,
		ProjectID:  projectID,
		StorageKey: *storageKey,
	}, nil
}

// processJob downloads the STEP, runs the driver, uploads the .glb, and
// updates the file row + job row to reflect success.
func (w *Worker) processJob(ctx context.Context, job *claimedJob) error {
	// 1. Download STEP from Storage.
	rc, _, err := w.storage.Get(ctx, job.StorageKey)
	if err != nil {
		return fmt.Errorf("download step: %w", err)
	}
	defer func() { _ = rc.Close() }()
	stepBytes, err := readAllCapped(rc, 500*1024*1024) // 500 MB hard cap; well above StepMaxBytes.
	if err != nil {
		return fmt.Errorf("read step: %w", err)
	}
	if len(stepBytes) == 0 {
		return fmt.Errorf("empty step file")
	}

	// 2. Tessellate via the driver (Node sidecar by default).
	driverCtx, cancel := context.WithTimeout(ctx,
		time.Duration(w.cfg.StepTessellateTimeoutSec)*time.Second)
	defer cancel()
	glb, err := w.driver.Tessellate(driverCtx, stepBytes)
	if err != nil {
		return fmt.Errorf("tessellate: %w", err)
	}
	if len(glb) == 0 {
		return fmt.Errorf("driver returned empty glb")
	}

	// 3. Upload the .glb to a deterministic key alongside the original.
	meshKey := fmt.Sprintf("projects/%s/assets/%s-tessellated.glb", job.ProjectID, job.FileID)
	if _, err := w.storage.Put(ctx, meshKey, byteReader(glb), "model/gltf-binary", int64(len(glb))); err != nil {
		return fmt.Errorf("upload glb: %w", err)
	}

	// 4. Atomically update both rows. If the file was soft-deleted between
	// claim and now we still write the job row but not the (gone) file —
	// the GLB blob will be orphaned but harmless.
	tx, err := w.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin tx: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()
	_, err = tx.Exec(ctx, `
		update files
		set mesh_storage_key = $2, updated_at = now()
		where id = $1 and deleted_at is null
	`, job.FileID, meshKey)
	if err != nil {
		return fmt.Errorf("update file: %w", err)
	}
	_, err = tx.Exec(ctx, `
		update step_tessellation_jobs
		set status='done', mesh_storage_key=$2, finished_at=now(), error=null
		where id = $1
	`, job.ID, meshKey)
	if err != nil {
		return fmt.Errorf("update job: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit: %w", err)
	}
	log.Printf("tessellate: file=%s glb=%dB done", job.FileID, len(glb))
	return nil
}
