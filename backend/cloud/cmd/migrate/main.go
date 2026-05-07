//go:build cloud
// +build cloud

// kerf migrate-cloud — applies cloud-only migrations from the embedded
// backend/cloud/migrations/ directory.
//
// Tracked in `cloud_schema_migrations` (separate from the OSS
// `schema_migrations` table) so the two streams stay independent.
// Refuses to start unless the OSS schema is already in place — this
// command is strictly additive.
package main

import (
	"context"
	"errors"
	"flag"
	"log"

	"github.com/jackc/pgx/v5"

	cloudMigrations "github.com/imranp/kerf/backend/cloud/migrations"
	"github.com/imranp/kerf/backend/internal/config"
	"github.com/imranp/kerf/backend/internal/db"
	"github.com/imranp/kerf/backend/internal/migrate"
)

func main() {
	configFlag := flag.String("config", "", "path to kerf.toml (default: auto-detect)")
	resetFlag := flag.Bool("reset", false, "drop and recreate the public schema before re-applying all migrations (DESTRUCTIVE — also drops OSS schema)")
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

	if *resetFlag {
		log.Printf("reset: dropping public schema (this also wipes OSS data — re-run kerf-migrate after)")
		if err := migrate.Reset(ctx, pool); err != nil {
			log.Fatalf("reset: %v", err)
		}
		log.Printf("reset done. Run `kerf-migrate` first to recreate the OSS schema, then re-run this command.")
		return
	}

	// Refuse to run before the OSS schema is in place. The cloud tables
	// reference users(id) — applying cloud migrations against a fresh DB
	// would error with a less helpful message.
	if !ossSchemaPresent(ctx, pool) {
		log.Fatalf("OSS schema not found (no `users` table). Run `kerf-migrate` first.")
	}

	runner := &migrate.Runner{FS: cloudMigrations.FS, Table: "cloud_schema_migrations"}
	if err := runner.EnsureTable(ctx, pool); err != nil {
		log.Fatalf("ensure cloud migrations table: %v", err)
	}
	applied, err := runner.Applied(ctx, pool)
	if err != nil {
		log.Fatalf("load applied: %v", err)
	}
	files, err := runner.Load(".")
	if err != nil {
		log.Fatalf("load cloud files: %v", err)
	}

	pending := 0
	for _, m := range files {
		if applied[m.Version] {
			continue
		}
		pending++
		if err := runner.Apply(ctx, pool, m); err != nil {
			log.Fatalf("apply cloud %s: %v", m.Filename, err)
		}
		log.Printf("applied cloud %s", m.Filename)
	}
	if pending == 0 {
		log.Printf("no pending cloud migrations (applied=%d)", len(applied))
	} else {
		log.Printf("done: %d cloud migration(s) applied", pending)
	}
}

// ossSchemaPresent returns true iff the canonical OSS `users` table
// exists in the public schema.
func ossSchemaPresent(ctx context.Context, pool interface {
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
}) bool {
	var exists bool
	err := pool.QueryRow(ctx, `
		select exists(
			select 1 from information_schema.tables
			where table_schema = 'public' and table_name = 'users'
		)
	`).Scan(&exists)
	if err != nil {
		if errors.Is(err, context.Canceled) {
			return false
		}
		return false
	}
	return exists
}
