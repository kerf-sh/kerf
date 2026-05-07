// Package migrate is a tiny migration runner shared by the OSS and
// cloud migrate commands. Each command supplies its own embedded SQL
// filesystem and its own tracking-table name; the two streams stay
// fully independent.
//
// SQL filename format: `<unix_millis>_<slug>.sql`. Files are sorted
// lexicographically (which is why the millis prefix matters), applied
// in transaction, and recorded by `<version>` in the chosen table.
package migrate

import (
	"context"
	"fmt"
	"io/fs"
	"sort"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"
)

// Runner applies SQL files from FS into a single tracking Table.
type Runner struct {
	FS    fs.FS
	Table string // e.g. "schema_migrations" or "cloud_schema_migrations"
}

// Migration is one parsed SQL file.
type Migration struct {
	Version  string
	Filename string
	SQL      string
}

// EnsureTable creates the migrations tracking table if missing.
func (r *Runner) EnsureTable(ctx context.Context, pool *pgxpool.Pool) error {
	q := fmt.Sprintf(`
		create table if not exists %s (
			version text primary key,
			applied_at timestamptz not null default now()
		);`, r.Table)
	_, err := pool.Exec(ctx, q)
	return err
}

// Applied returns the set of versions already applied.
func (r *Runner) Applied(ctx context.Context, pool *pgxpool.Pool) (map[string]bool, error) {
	q := fmt.Sprintf(`select version from %s`, r.Table)
	rows, err := pool.Query(ctx, q)
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

// Load reads every *.sql file from the embedded FS at the given root
// (typically "." for an embed.FS rooted at the migration dir, or the
// dir name when embedding from a parent).
func (r *Runner) Load(root string) ([]Migration, error) {
	entries, err := fs.ReadDir(r.FS, root)
	if err != nil {
		return nil, fmt.Errorf("readdir %q: %w", root, err)
	}
	var out []Migration
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".sql") {
			continue
		}
		name := e.Name()
		idx := strings.Index(name, "_")
		if idx <= 0 {
			return nil, fmt.Errorf("invalid migration filename %q (expected <ts>_<slug>.sql)", name)
		}
		path := name
		if root != "." && root != "" {
			path = root + "/" + name
		}
		raw, err := fs.ReadFile(r.FS, path)
		if err != nil {
			return nil, fmt.Errorf("read %s: %w", path, err)
		}
		out = append(out, Migration{
			Version:  name[:idx],
			Filename: name,
			SQL:      string(raw),
		})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Filename < out[j].Filename })
	return out, nil
}

// Apply runs one migration in a transaction, recording the version.
func (r *Runner) Apply(ctx context.Context, pool *pgxpool.Pool, m Migration) error {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if _, err := tx.Exec(ctx, m.SQL); err != nil {
		return err
	}
	q := fmt.Sprintf(
		`insert into %s(version) values ($1) on conflict do nothing`, r.Table)
	if _, err := tx.Exec(ctx, q, m.Version); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

// Reset drops the public schema and recreates it. Destructive; intended
// for dev only. Both the OSS and cloud commands gate this behind a
// --reset flag.
func Reset(ctx context.Context, pool *pgxpool.Pool) error {
	_, err := pool.Exec(ctx, `drop schema public cascade; create schema public;`)
	return err
}
