// kerf migrate-revisions — one-shot, idempotent backfill that gzips the
// legacy plaintext `file_revisions.content` column into `content_gz`
// for every row that hasn't been migrated yet.
//
// Phase 4 introduced compressed + diff-based revision storage. Existing
// rows continue to work unchanged because the read path (tools.
// ReconstructRevision) falls back to the plaintext column when
// content_gz is NULL. Running this command isn't required — it just
// reclaims disk by replacing plaintext with gzip on old rows.
//
// Run-once, idempotent: safe to re-run; rows that already have a non-NULL
// content_gz are skipped. Pass --prune-legacy to additionally clear the
// legacy `content` column once the gzip roundtrip has been verified for
// the row.
//
// This is intentionally a separate command, NOT executed on server boot.
// Backfilling can churn a large amount of disk and should be done at the
// operator's chosen time.
package main

import (
	"context"
	"flag"
	"log"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/internal/config"
	"github.com/imranp/kerf/backend/internal/db"
	"github.com/imranp/kerf/backend/internal/tools"
)

func main() {
	configFlag := flag.String("config", "", "path to kerf.toml (default: auto-detect)")
	pruneLegacy := flag.Bool("prune-legacy", false, "after gzip roundtrip succeeds, clear the legacy `content` column")
	batchSize := flag.Int("batch", 500, "rows to process per batch")
	dryRun := flag.Bool("dry-run", false, "scan + report what would be migrated without writing")
	flag.Parse()

	cfg, err := config.Load(*configFlag)
	if err != nil {
		log.Fatalf("config: %v", err)
	}
	log.Printf("config: loaded %s", cfg.SourcePath)

	ctx := context.Background()
	pool, err := db.Connect(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("db: %v", err)
	}
	defer pool.Close()

	var totalRows int
	if err := pool.QueryRow(ctx,
		`select count(*) from file_revisions where content_gz is null`).Scan(&totalRows); err != nil {
		log.Fatalf("count rows: %v", err)
	}
	log.Printf("found %d rows with NULL content_gz", totalRows)
	if *dryRun {
		log.Printf("dry-run: nothing written")
		return
	}
	if totalRows == 0 {
		log.Printf("nothing to do")
		return
	}

	processed, errs, prunedBytes := backfill(ctx, pool, *batchSize, *pruneLegacy)
	log.Printf("done: processed=%d errors=%d pruned-legacy-bytes=%d", processed, errs, prunedBytes)
}

// backfill walks every NULL-content_gz row in batches, compresses, and
// writes back. Returns (processed, errors, prunedBytes).
//
// Each row is handled in its own short transaction so a partial run
// can be resumed by simply re-invoking the command.
func backfill(ctx context.Context, pool *pgxpool.Pool, batch int, pruneLegacy bool) (int, int, int64) {
	if batch <= 0 {
		batch = 500
	}
	var (
		processed int
		errs      int
		pruned    int64
	)
	for {
		rows, err := pool.Query(ctx, `
			select id, content
			  from file_revisions
			 where content_gz is null
			 order by created_at asc
			 limit $1
		`, batch)
		if err != nil {
			log.Printf("query batch: %v", err)
			return processed, errs + 1, pruned
		}
		type todo struct {
			id      uuid.UUID
			content string
		}
		var jobs []todo
		for rows.Next() {
			var t todo
			if err := rows.Scan(&t.id, &t.content); err != nil {
				log.Printf("scan: %v", err)
				errs++
				continue
			}
			jobs = append(jobs, t)
		}
		rows.Close()
		if len(jobs) == 0 {
			break
		}

		for _, j := range jobs {
			if err := backfillOne(ctx, pool, j.id, j.content, pruneLegacy); err != nil {
				log.Printf("row %s: %v", j.id, err)
				errs++
				continue
			}
			processed++
			if pruneLegacy {
				pruned += int64(len(j.content))
			}
			if processed%500 == 0 {
				log.Printf("progress: processed=%d errors=%d", processed, errs)
			}
		}
	}
	return processed, errs, pruned
}

func backfillOne(ctx context.Context, pool *pgxpool.Pool, id uuid.UUID, content string, pruneLegacy bool) error {
	gz, err := tools.GzipForBackfill(content)
	if err != nil {
		return err
	}
	// Verify roundtrip before writing — protects against a buggy gzip
	// implementation flipping bytes silently.
	roundtrip, err := tools.GunzipForBackfill(gz)
	if err != nil {
		return err
	}
	if roundtrip != content {
		return errMismatch
	}
	if pruneLegacy {
		_, err = pool.Exec(ctx, `
			update file_revisions
			   set content_gz = $1, content = ''
			 where id = $2
			   and content_gz is null
		`, gz, id)
	} else {
		_, err = pool.Exec(ctx, `
			update file_revisions
			   set content_gz = $1
			 where id = $2
			   and content_gz is null
		`, gz, id)
	}
	return err
}

type errString string

func (e errString) Error() string { return string(e) }

const errMismatch = errString("gzip roundtrip mismatch")
