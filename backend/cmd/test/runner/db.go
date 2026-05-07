// Package runner provides the harness used by the kerf test CLI. It boots
// an in-process kerf HTTP server backed by a real Postgres database so
// scenarios can drive the public API exactly as a real client would.
package runner

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"
)

// migration is one entry from the backend/migrations directory.
type migration struct {
	Version  string
	Filename string
	SQL      string
}

// ApplyMigrations brings the schema up to date, applying every .sql file
// under dir in lexicographic order. Skips migrations already recorded in
// the schema_migrations table.
func ApplyMigrations(ctx context.Context, pool *pgxpool.Pool, dir string) error {
	if _, err := pool.Exec(ctx, `
		create table if not exists schema_migrations (
			version text primary key,
			applied_at timestamptz not null default now()
		);
	`); err != nil {
		return fmt.Errorf("ensure schema_migrations: %w", err)
	}

	applied, err := loadAppliedVersions(ctx, pool)
	if err != nil {
		return fmt.Errorf("load applied: %w", err)
	}

	files, err := loadMigrationFiles(dir)
	if err != nil {
		return fmt.Errorf("load files: %w", err)
	}

	for _, m := range files {
		if applied[m.Version] {
			continue
		}
		tx, err := pool.Begin(ctx)
		if err != nil {
			return err
		}
		if _, err := tx.Exec(ctx, m.SQL); err != nil {
			_ = tx.Rollback(ctx)
			return fmt.Errorf("apply %s: %w", m.Filename, err)
		}
		if _, err := tx.Exec(ctx,
			`insert into schema_migrations(version) values ($1) on conflict do nothing`,
			m.Version); err != nil {
			_ = tx.Rollback(ctx)
			return fmt.Errorf("record %s: %w", m.Filename, err)
		}
		if err := tx.Commit(ctx); err != nil {
			return err
		}
	}
	return nil
}

// ResetSchema drops and recreates the public schema, then re-applies every
// migration. Used between scenarios so each starts from a clean slate.
func ResetSchema(ctx context.Context, pool *pgxpool.Pool, dir string) error {
	if _, err := pool.Exec(ctx, `drop schema public cascade; create schema public;`); err != nil {
		return fmt.Errorf("drop schema: %w", err)
	}
	return ApplyMigrations(ctx, pool, dir)
}

// DropSchema removes everything from the test DB on teardown. Best-effort:
// if the pool is already closed we just no-op.
func DropSchema(ctx context.Context, pool *pgxpool.Pool) error {
	if pool == nil {
		return nil
	}
	_, err := pool.Exec(ctx, `drop schema public cascade; create schema public;`)
	return err
}

func loadAppliedVersions(ctx context.Context, pool *pgxpool.Pool) (map[string]bool, error) {
	rows, err := pool.Query(ctx, `select version from schema_migrations`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := map[string]bool{}
	for rows.Next() {
		var v string
		if err := rows.Scan(&v); err != nil {
			return nil, err
		}
		out[v] = true
	}
	return out, rows.Err()
}

func loadMigrationFiles(dir string) ([]migration, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, fmt.Errorf("read %s: %w", dir, err)
	}
	var out []migration
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".sql") {
			continue
		}
		idx := strings.Index(e.Name(), "_")
		if idx <= 0 {
			return nil, fmt.Errorf("invalid migration filename %q", e.Name())
		}
		path := filepath.Join(dir, e.Name())
		raw, err := os.ReadFile(path)
		if err != nil {
			return nil, fmt.Errorf("read %s: %w", path, err)
		}
		out = append(out, migration{
			Version:  e.Name()[:idx],
			Filename: e.Name(),
			SQL:      string(raw),
		})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Filename < out[j].Filename })
	return out, nil
}

// FindMigrationsDir locates backend/migrations relative to the working
// directory or the binary path. Walks up a few levels so the runner works
// from /, backend/, or backend/cmd/test/.
func FindMigrationsDir() (string, error) {
	cwd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	candidates := []string{
		filepath.Join(cwd, "migrations"),
		filepath.Join(cwd, "backend", "migrations"),
		filepath.Join(cwd, "..", "migrations"),
		filepath.Join(cwd, "..", "..", "migrations"),
		filepath.Join(cwd, "..", "..", "..", "migrations"),
	}
	for _, c := range candidates {
		if info, err := os.Stat(c); err == nil && info.IsDir() {
			abs, _ := filepath.Abs(c)
			return abs, nil
		}
	}
	return "", fmt.Errorf("could not locate backend/migrations (tried %v)", candidates)
}
