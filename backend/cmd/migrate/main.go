package main

import (
	"bytes"
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"text/template"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/internal/auth"
	"github.com/imranp/kerf/backend/internal/config"
	"github.com/imranp/kerf/backend/internal/db"
)

func main() {
	envFlag := flag.String("env", "local", "environment to load (local|dev|main)")
	resetFlag := flag.Bool("reset", false, "drop and recreate the public schema before re-applying all migrations")
	dirFlag := flag.String("dir", "", "path to migrations directory (default: backend/migrations)")
	seedDirFlag := flag.String("seed-dir", "", "path to seeds directory (default: backend/seeds)")
	noSeedFlag := flag.Bool("no-seed", false, "skip running the seed step after migrations (rare; for migration-only deploys)")
	seedOnlyFlag := flag.Bool("seed-only", false, "skip migrations and only run the seed (useful when re-seeding after a password rotation)")
	flag.Parse()

	if *noSeedFlag && *seedOnlyFlag {
		log.Fatalf("--no-seed and --seed-only are mutually exclusive")
	}

	cfg, err := config.Load(*envFlag)
	if err != nil {
		log.Fatalf("config: %v", err)
	}

	ctx := context.Background()
	pool, err := db.Connect(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("db: %v", err)
	}
	defer pool.Close()

	if !*seedOnlyFlag {
		migDir, err := resolveMigrationsDir(*dirFlag)
		if err != nil {
			log.Fatalf("migrations dir: %v", err)
		}

		if *resetFlag {
			log.Printf("reset: dropping public schema")
			if _, err := pool.Exec(ctx, `drop schema public cascade; create schema public;`); err != nil {
				log.Fatalf("reset: %v", err)
			}
		}

		if err := ensureMigrationsTable(ctx, pool); err != nil {
			log.Fatalf("ensure migrations table: %v", err)
		}

		applied, err := loadAppliedVersions(ctx, pool)
		if err != nil {
			log.Fatalf("load applied: %v", err)
		}

		files, err := loadMigrationFiles(migDir)
		if err != nil {
			log.Fatalf("load files: %v", err)
		}

		pending := 0
		for _, m := range files {
			if applied[m.Version] {
				continue
			}
			pending++
			if err := applyMigration(ctx, pool, m); err != nil {
				log.Fatalf("apply %s: %v", m.Filename, err)
			}
			log.Printf("applied %s", m.Filename)
		}

		if pending == 0 {
			log.Printf("no pending migrations (env=%s, applied=%d)", cfg.Env, len(applied))
		} else {
			log.Printf("done: %d migration(s) applied (env=%s)", pending, cfg.Env)
		}
	} else {
		log.Printf("seed-only: skipping migrations")
	}

	if *noSeedFlag {
		log.Printf("no-seed: skipping seed step")
		return
	}

	if err := runSeed(ctx, pool, cfg, *seedDirFlag); err != nil {
		log.Fatalf("seed: %v", err)
	}
}

type migration struct {
	Version  string
	Filename string
	Path     string
	SQL      string
}

func ensureMigrationsTable(ctx context.Context, pool *pgxpool.Pool) error {
	_, err := pool.Exec(ctx, `
		create table if not exists schema_migrations (
			version text primary key,
			applied_at timestamptz not null default now()
		);
	`)
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
		return nil, err
	}
	var out []migration
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".sql") {
			continue
		}
		name := e.Name()
		idx := strings.Index(name, "_")
		if idx <= 0 {
			return nil, fmt.Errorf("invalid migration filename %q (expected <ts>_<slug>.sql)", name)
		}
		version := name[:idx]
		path := filepath.Join(dir, name)
		bytes, err := os.ReadFile(path)
		if err != nil {
			return nil, fmt.Errorf("read %s: %w", path, err)
		}
		out = append(out, migration{
			Version:  version,
			Filename: name,
			Path:     path,
			SQL:      string(bytes),
		})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Filename < out[j].Filename })
	return out, nil
}

func applyMigration(ctx context.Context, pool *pgxpool.Pool, m migration) error {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if _, err := tx.Exec(ctx, m.SQL); err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `insert into schema_migrations(version) values ($1) on conflict do nothing`, m.Version); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

// resolveMigrationsDir picks the migrations dir relative to the cwd or backend/.
func resolveMigrationsDir(override string) (string, error) {
	return resolveSubDir(override, "migrations")
}

// resolveSeedsDir picks the seeds dir relative to the cwd or backend/.
func resolveSeedsDir(override string) (string, error) {
	return resolveSubDir(override, "seeds")
}

func resolveSubDir(override, name string) (string, error) {
	if override != "" {
		abs, err := filepath.Abs(override)
		if err != nil {
			return "", err
		}
		return abs, nil
	}
	cwd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	candidates := []string{
		filepath.Join(cwd, name),
		filepath.Join(cwd, "backend", name),
	}
	for _, c := range candidates {
		if info, err := os.Stat(c); err == nil && info.IsDir() {
			return c, nil
		}
	}
	return "", fmt.Errorf("could not find %s directory; tried %v", name, candidates)
}

// runSeed renders backend/seeds/seed.sql via text/template and executes it
// inside a single transaction. The system user's password hash is passed as
// SQL parameter $1 to avoid quote-escaping issues.
//
// If SYSTEM_USER_PASSWORD is empty, this logs a warning and returns nil so
// that local environments without a configured password still bring the
// migrator up cleanly.
func runSeed(ctx context.Context, pool *pgxpool.Pool, cfg *config.Config, override string) error {
	if cfg.SystemUserPassword == "" {
		log.Printf("warning: SYSTEM_USER_PASSWORD is empty; skipping system user seed")
		return nil
	}
	if cfg.SystemUserEmail == "" {
		log.Printf("warning: SYSTEM_USER_EMAIL is empty; skipping system user seed")
		return nil
	}

	seedDir, err := resolveSeedsDir(override)
	if err != nil {
		return err
	}
	seedPath := filepath.Join(seedDir, "seed.sql")
	raw, err := os.ReadFile(seedPath)
	if err != nil {
		return fmt.Errorf("read %s: %w", seedPath, err)
	}

	tmpl, err := template.New("seed").Parse(string(raw))
	if err != nil {
		return fmt.Errorf("parse seed template: %w", err)
	}

	name := cfg.SystemUserName
	if name == "" {
		name = "Kerf System"
	}

	data := struct {
		SystemEmail string
		SystemName  string
	}{
		SystemEmail: sqlSafeIdent(strings.ToLower(strings.TrimSpace(cfg.SystemUserEmail))),
		SystemName:  sqlSafeIdent(name),
	}

	var rendered bytes.Buffer
	if err := tmpl.Execute(&rendered, data); err != nil {
		return fmt.Errorf("render seed template: %w", err)
	}

	hash, err := auth.HashPassword(cfg.SystemUserPassword, cfg.PasswordPepper)
	if err != nil {
		return fmt.Errorf("hash system password: %w", err)
	}

	tx, err := pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if _, err := tx.Exec(ctx, rendered.String(), hash); err != nil {
		return fmt.Errorf("exec seed: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return err
	}

	log.Printf("seeded system user: %s", data.SystemEmail)
	return nil
}

// sqlSafeIdent doubles single-quote characters so a value can be safely
// substituted into a single-quoted SQL literal by text/template. Email and
// name come from operator-controlled env vars, but we still defend against
// stray apostrophes (e.g. names).
func sqlSafeIdent(v string) string {
	return strings.ReplaceAll(v, "'", "''")
}
