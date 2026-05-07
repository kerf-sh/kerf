//go:build cloud
// +build cloud

package main

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"
)

const (
	defaultTestDSN = "postgres://postgres:postgres@localhost:5432/kerf_test_cloud?sslmode=disable"
	envTestDSN     = "KERF_TEST_DATABASE_URL"
)

// resolveTestDSN returns the connection string for the cloud test DB. We
// keep a distinct default DB name (kerf_test_cloud) from any OSS test
// runner default so the two suites can run in parallel.
func resolveTestDSN() string {
	if v := strings.TrimSpace(os.Getenv(envTestDSN)); v != "" {
		return v
	}
	return defaultTestDSN
}

// applyAllMigrations resets the public schema and applies the OSS
// migrations followed by the cloud migrations.
//
// Order matters: cloud migrations reference OSS tables (e.g.
// cloud_user_balances → users). The resolver tries `backend/migrations`
// and `backend/cloud/migrations` relative to a few likely cwd anchors so
// the runner works whether you `go run` from repo root or from `backend/`.
func applyAllMigrations(ctx context.Context, pool *pgxpool.Pool) error {
	ossDir, err := findMigrationsDir("migrations")
	if err != nil {
		return fmt.Errorf("oss migrations: %w", err)
	}
	cloudDir, err := findCloudMigrationsDir()
	if err != nil {
		return fmt.Errorf("cloud migrations: %w", err)
	}

	// Drop and recreate to guarantee a clean slate. We don't track applied
	// versions in the test runner — every boot is a from-scratch apply.
	if _, err := pool.Exec(ctx, `drop schema public cascade; create schema public;`); err != nil {
		return fmt.Errorf("reset schema: %w", err)
	}

	files, err := loadSQLFiles(ossDir)
	if err != nil {
		return fmt.Errorf("load oss files: %w", err)
	}
	cloudFiles, err := loadSQLFiles(cloudDir)
	if err != nil {
		return fmt.Errorf("load cloud files: %w", err)
	}
	files = append(files, cloudFiles...)

	for _, f := range files {
		if _, err := pool.Exec(ctx, f.sql); err != nil {
			return fmt.Errorf("apply %s: %w", f.name, err)
		}
	}
	return nil
}

// resetRows truncates app data tables but leaves the schema in place. We
// skip the migrations bookkeeping (we don't have one in the runner) and
// any extension tables. Test scenarios call this between runs so they
// don't see each other's rows.
//
// NOTE: We use TRUNCATE with CASCADE so foreign keys don't trip us up.
// `restart identity` resets bigint sequences for safety.
func resetRows(ctx context.Context, pool *pgxpool.Pool) error {
	const sql = `
        truncate table
            cloud_workshop_likes,
            cloud_workshop_listings,
            cloud_invoices,
            cloud_paystack_customers,
            cloud_user_balances,
            cloud_fx_rates,
            usage_events,
            refresh_tokens,
            project_members,
            share_links,
            files,
            projects,
            users
        restart identity cascade;
    `
	_, err := pool.Exec(ctx, sql)
	return err
}

// dropSchema is invoked on shutdown when --keep-db is not set. We use
// `drop schema cascade` to also remove the test users and roles.
func dropSchema(ctx context.Context, pool *pgxpool.Pool) error {
	_, err := pool.Exec(ctx, `drop schema public cascade; create schema public;`)
	return err
}

// --- helpers ---

type sqlFile struct {
	name string
	sql  string
}

func loadSQLFiles(dir string) ([]sqlFile, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var out []sqlFile
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".sql") {
			continue
		}
		raw, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, err
		}
		out = append(out, sqlFile{name: e.Name(), sql: string(raw)})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].name < out[j].name })
	return out, nil
}

// findMigrationsDir walks upward from cwd looking for backend/migrations
// (or just migrations, for callers that already cd'd into backend/).
func findMigrationsDir(name string) (string, error) {
	cwd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	candidates := []string{
		filepath.Join(cwd, name),
		filepath.Join(cwd, "backend", name),
		filepath.Join(cwd, "..", name),
		filepath.Join(cwd, "..", "..", "..", name),       // backend/cloud/cmd/test/.. up to backend/
		filepath.Join(cwd, "..", "..", "..", "..", name), // repo-root style
	}
	for _, c := range candidates {
		if info, err := os.Stat(c); err == nil && info.IsDir() {
			abs, _ := filepath.Abs(c)
			return abs, nil
		}
	}
	return "", fmt.Errorf("could not find %s directory; tried %v", name, candidates)
}

// findCloudMigrationsDir handles the nested layout: backend/cloud/migrations.
func findCloudMigrationsDir() (string, error) {
	cwd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	candidates := []string{
		filepath.Join(cwd, "cloud", "migrations"),
		filepath.Join(cwd, "backend", "cloud", "migrations"),
		filepath.Join(cwd, "..", "cloud", "migrations"),
		filepath.Join(cwd, "..", "..", "..", "migrations"), // when run from backend/cloud/cmd/test
	}
	for _, c := range candidates {
		if info, err := os.Stat(c); err == nil && info.IsDir() {
			abs, _ := filepath.Abs(c)
			return abs, nil
		}
	}
	return "", fmt.Errorf("could not find cloud migrations dir; tried %v", candidates)
}
