package sim

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/internal/config"
	"github.com/imranp/kerf/backend/internal/storage"
)

type Worker struct {
	cfg         *config.Config
	pool        *pgxpool.Pool
	storage     storage.Storage
	driver      *Driver
	pollInterval time.Duration
}

func New(cfg *config.Config, pool *pgxpool.Pool, store storage.Storage) *Worker {
	return &Worker{
		cfg:           cfg,
		pool:          pool,
		storage:       store,
		driver:        NewDriver(cfg),
		pollInterval:  5 * time.Second,
	}
}

func (w *Worker) Run(ctx context.Context) {
	n := w.cfg.SIMWorkers
	if n <= 0 {
		log.Printf("sim: workers disabled (sim_workers=%d)", n)
		return
	}
	if w.storage == nil {
		log.Printf("sim: storage not configured; worker pool not started")
		return
	}
	log.Printf("sim: starting %d worker(s)", n)
	var wg sync.WaitGroup
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			w.loop(ctx, id)
		}(i)
	}
	go func() {
		<-ctx.Done()
		wg.Wait()
		log.Printf("sim: worker pool stopped")
	}()
}

func (w *Worker) loop(ctx context.Context, workerID int) {
	for {
		if ctx.Err() != nil {
			return
		}
		ran, err := w.runOne(ctx)
		if err != nil {
			log.Printf("sim[%d]: runOne: %v", workerID, err)
			select {
			case <-ctx.Done():
				return
			case <-time.After(2 * time.Second):
			}
			continue
		}
		if !ran {
			select {
			case <-ctx.Done():
				return
			case <-time.After(w.pollInterval):
			}
		}
	}
}

func (w *Worker) runOne(ctx context.Context) (bool, error) {
	job, err := w.claimNextJob(ctx)
	if err != nil {
		return false, err
	}
	if job == nil {
		return false, nil
	}

	timeout := time.Duration(w.cfg.SIMTimeoutSec) * time.Second
	if timeout <= 0 {
		timeout = 5 * time.Minute
	}
	jobCtx, cancel := context.WithTimeout(ctx, timeout+30*time.Second)
	defer cancel()

	if err := w.processJob(jobCtx, job); err != nil {
		_, dbErr := w.pool.Exec(ctx, `
			update sim_jobs
			set status = 'error', error = $2, finished_at = now()
			where id = $1
		`, job.ID, truncateErr(err.Error()))
		if dbErr != nil {
			log.Printf("sim: mark error (job=%s): %v (orig: %v)", job.ID, dbErr, err)
		} else {
			log.Printf("sim: job=%s file=%s failed: %v", job.ID, job.FileID, err)
		}
		return true, nil
	}
	return true, nil
}

type claimedJob struct {
	ID         string
	FileID     string
	ProjectID  string
	StorageKey string
	InputSpec  InputSpec
	Netlist    string
}

func (w *Worker) claimNextJob(ctx context.Context) (*claimedJob, error) {
	tx, err := w.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	var (
		jobID, fileID, projectID string
		storageKey              *string
		inputSpec               []byte
		netlist                 string
	)
	err = tx.QueryRow(ctx, `
		select j.id, j.file_id, f.project_id, f.storage_key, j.input_spec
		from sim_jobs j
		join files f on f.id = j.file_id
		where j.status = 'queued' and f.deleted_at is null
		order by j.created_at asc
		for update of j skip locked
		limit 1
	`).Scan(&jobID, &fileID, &projectID, &storageKey, &inputSpec)
	if err != nil {
		if err == pgx.ErrNoRows {
			return nil, nil
		}
		return nil, fmt.Errorf("claim: %w", err)
	}
	if storageKey == nil || *storageKey == "" {
		_, err = tx.Exec(ctx, `
			update sim_jobs
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
		update sim_jobs
		set status='running', started_at=now()
		where id = $1
	`, jobID)
	if err != nil {
		return nil, err
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}

	var spec InputSpec
	if err := json.Unmarshal(inputSpec, &spec); err != nil {
		spec = InputSpec{}
	}

	netlist = ""

	return &claimedJob{
		ID:         jobID,
		FileID:     fileID,
		ProjectID:  projectID,
		StorageKey: *storageKey,
		InputSpec:  spec,
		Netlist:    netlist,
	}, nil
}

func (w *Worker) processJob(ctx context.Context, job *claimedJob) error {
	rc, _, err := w.storage.Get(ctx, job.StorageKey)
	if err != nil {
		return fmt.Errorf("download file: %w", err)
	}
	defer func() { _ = rc.Close() }()
	netlistBytes, err := readAllCapped(rc, 500*1024*1024)
	if err != nil {
		return fmt.Errorf("read file: %w", err)
	}
	if len(netlistBytes) == 0 {
		return fmt.Errorf("empty netlist file")
	}
	netlist := string(netlistBytes)

	driverCtx, cancel := context.WithTimeout(ctx, time.Duration(w.cfg.SIMTimeoutSec)*time.Second)
	defer cancel()
	result, err := w.driver.RunSpice(driverCtx, netlist, job.InputSpec)
	if err != nil {
		return fmt.Errorf("sim driver: %w", err)
	}

	resultJSON, err := json.Marshal(result)
	if err != nil {
		return fmt.Errorf("encode result: %w", err)
	}

	tx, err := w.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin tx: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	_, err = tx.Exec(ctx, `
		update sim_jobs
		set status='done', result_json=$2, finished_at=now(), error=null
		where id = $1
	`, job.ID, resultJSON)
	if err != nil {
		return fmt.Errorf("update job: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit: %w", err)
	}
	log.Printf("sim: job=%s file=%s done", job.ID, job.FileID)
	return nil
}

func readAllCapped(r io.Reader, cap int) ([]byte, error) {
	buf := make([]byte, 0, 4096)
	tr := io.LimitReader(r, int64(cap)+1)
	for {
		b := make([]byte, 4096)
		n, err := tr.Read(b)
		buf = append(buf, b[:n]...)
		if err == io.EOF {
			if len(buf) > cap {
				return nil, fmt.Errorf("file exceeds %d bytes", cap)
			}
			return buf, nil
		}
		if err != nil {
			return nil, err
		}
	}
}

func truncateErr(s string) string {
	const max = 800
	if len(s) <= max {
		return s
	}
	return s[:max] + "..."
}
