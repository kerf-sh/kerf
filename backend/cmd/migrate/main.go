// kerf migrate — applies OSS schema migrations from the embedded
// `backend/migrations/` directory and seeds the system user.
//
// Cloud schema lives behind a separate command (backend/cloud/cmd/migrate)
// built with `-tags=cloud`. The two streams never share a tracking
// table or know about each other. Run OSS migrations first; cloud
// migrate refuses to start without the OSS schema in place.
package main

import (
	"bytes"
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
	"text/template"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/internal/auth"
	"github.com/imranp/kerf/backend/internal/config"
	"github.com/imranp/kerf/backend/internal/db"
	"github.com/imranp/kerf/backend/internal/migrate"
	migrations "github.com/imranp/kerf/backend/migrations"
)

func main() {
	configFlag := flag.String("config", "", "path to kerf.toml (default: auto-detect)")
	resetFlag := flag.Bool("reset", false, "drop and recreate the public schema before re-applying all migrations")
	seedDirFlag := flag.String("seed-dir", "", "path to seeds directory (default: backend/seeds)")
	noSeedFlag := flag.Bool("no-seed", false, "skip running the seed step after migrations")
	seedOnlyFlag := flag.Bool("seed-only", false, "skip migrations and only run the seed (e.g. after a password rotation)")
	flag.Parse()

	if *noSeedFlag && *seedOnlyFlag {
		log.Fatalf("--no-seed and --seed-only are mutually exclusive")
	}

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

	if !*seedOnlyFlag {
		if *resetFlag {
			log.Printf("reset: dropping public schema")
			if err := migrate.Reset(ctx, pool); err != nil {
				log.Fatalf("reset: %v", err)
			}
		}

		runner := &migrate.Runner{FS: migrations.FS, Table: "schema_migrations"}
		if err := runner.EnsureTable(ctx, pool); err != nil {
			log.Fatalf("ensure migrations table: %v", err)
		}
		applied, err := runner.Applied(ctx, pool)
		if err != nil {
			log.Fatalf("load applied: %v", err)
		}
		files, err := runner.Load(".")
		if err != nil {
			log.Fatalf("load files: %v", err)
		}

		pending := 0
		for _, m := range files {
			if applied[m.Version] {
				continue
			}
			pending++
			if err := runner.Apply(ctx, pool, m); err != nil {
				log.Fatalf("apply %s: %v", m.Filename, err)
			}
			log.Printf("applied %s", m.Filename)
		}
		if pending == 0 {
			log.Printf("no pending OSS migrations (applied=%d)", len(applied))
		} else {
			log.Printf("done: %d OSS migration(s) applied", pending)
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

// runSeed renders backend/seeds/seed.sql via text/template and executes
// it inside a single transaction.
func runSeed(ctx context.Context, pool *pgxpool.Pool, cfg *config.Config, override string) error {
	if cfg.SystemUserPassword == "" {
		log.Printf("warning: system_user.password is empty; skipping system user seed")
		return nil
	}
	if cfg.SystemUserEmail == "" {
		log.Printf("warning: system_user.email is empty; skipping system user seed")
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

func resolveSeedsDir(override string) (string, error) {
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
		filepath.Join(cwd, "seeds"),
		filepath.Join(cwd, "backend", "seeds"),
	}
	for _, c := range candidates {
		if info, err := os.Stat(c); err == nil && info.IsDir() {
			return c, nil
		}
	}
	return "", fmt.Errorf("could not find seeds directory; tried %v", candidates)
}

func sqlSafeIdent(v string) string {
	return strings.ReplaceAll(v, "'", "''")
}
