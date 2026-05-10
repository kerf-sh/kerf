// kerf seed-materials — seed the curated `kerf-system/materials` Library
// project from the manifest at <repo>/seed/materials/MANIFEST.json.
//
// Why a dedicated command (vs piggy-backing on library-import):
// library-import is parametric over a manifest the operator supplies and
// wires up a publisher account. The materials seed targets the existing
// `[system_user]` account, doesn't need a YAML manifest, and ships with
// the binary so any operator can run `npm run seed:materials` after a
// migration without first authoring a manifest. Once the dataset grows
// past ~50 entries we'll replace this with a manifest pipeline.
//
// Idempotency:
//   - The system user is identified by `[system_user].email` from
//     kerf.toml (the same row `kerf migrate` seeds). If absent, this
//     command exits with code 0 and a warning.
//   - The materials project is identified by (owner_id, name). On
//     re-run the project is reused; description/visibility are not
//     touched.
//   - Each .material file is identified by (project_id, name=Material.Name).
//     On re-run, an existing row is left alone — by design, so an
//     operator who locally tweaked a value isn't stomped on. To
//     force-update, delete the row first.
//
// Usage:
//
//	kerf seed-materials                     # uses ./kerf.toml + ./seed/materials/
//	kerf seed-materials --config ../kerf.toml --dir ../seed/materials
//	kerf seed-materials --dry-run           # plan only
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/internal/config"
	"github.com/imranp/kerf/backend/internal/db"
)

// ---- manifest types --------------------------------------------------------

type manifest struct {
	Version     int                `json:"version"`
	Description string             `json:"description"`
	Materials   []manifestMaterial `json:"materials"`
}

type manifestMaterial struct {
	Path     string `json:"path"`
	Name     string `json:"name"`
	Category string `json:"category"`
}

// projectName is the canonical name of the holding project. Mirrors the
// kerf-system convention: one project per curated library, owned by the
// system user.
const projectName = "Materials Library"

// projectVisibility — public so the materials show up in the Workshop
// once a workshop view exists for materials.
const projectVisibility = "public"

const projectDescription = "Curated engineering materials (E/ν/ρ/α/yield/k/cₚ) consumed by FEM, tolerance studies, drawing callouts, and Part defaults. Seeded from kerf's seed/materials/."

// ---- main ------------------------------------------------------------------

func main() {
	configFlag := flag.String("config", "", "path to kerf.toml (default: auto-detect)")
	dirFlag := flag.String("dir", "", "path to the seed/materials directory (default: ./seed/materials)")
	dryRun := flag.Bool("dry-run", false, "print the plan without writing")
	flag.Parse()

	cfg, err := config.Load(*configFlag)
	if err != nil {
		log.Fatalf("config: %v", err)
	}
	log.Printf("config: loaded %s", cfg.SourcePath)

	dir := *dirFlag
	if dir == "" {
		dir = defaultSeedDir()
	}
	mPath := filepath.Join(dir, "MANIFEST.json")
	m, err := loadManifest(mPath)
	if err != nil {
		log.Fatalf("manifest: %v", err)
	}
	log.Printf("manifest: %d materials in %s", len(m.Materials), mPath)

	ctx := context.Background()
	pool, err := db.Connect(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("db: %v", err)
	}
	defer pool.Close()

	stats, err := seedMaterials(ctx, pool, cfg, dir, m, *dryRun)
	if err != nil {
		log.Fatalf("seed: %v", err)
	}

	verb := "seeded"
	if *dryRun {
		verb = "would seed"
	}
	log.Printf("%s %d materials (%d new, %d skipped) into project %q",
		verb, stats.total, stats.created, stats.skipped, projectName)
}

// ---- manifest IO -----------------------------------------------------------

func loadManifest(path string) (*manifest, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read %s: %w", path, err)
	}
	var m manifest
	if err := json.Unmarshal(raw, &m); err != nil {
		return nil, fmt.Errorf("parse %s: %w", filepath.Base(path), err)
	}
	if m.Version != 1 {
		return nil, fmt.Errorf("manifest version=%d; expected 1", m.Version)
	}
	if len(m.Materials) == 0 {
		return nil, fmt.Errorf("manifest has no materials")
	}
	for i, mm := range m.Materials {
		if strings.TrimSpace(mm.Path) == "" {
			return nil, fmt.Errorf("materials[%d].path is required", i)
		}
		if strings.TrimSpace(mm.Name) == "" {
			return nil, fmt.Errorf("materials[%d].name is required", i)
		}
	}
	return &m, nil
}

// defaultSeedDir picks the most likely seed dir from the cwd. Tries
// ./seed/materials first; falls back to ../seed/materials so the
// command works from inside backend/ as well as from the repo root.
func defaultSeedDir() string {
	candidates := []string{
		"seed/materials",
		"../seed/materials",
	}
	for _, c := range candidates {
		if info, err := os.Stat(c); err == nil && info.IsDir() {
			abs, err := filepath.Abs(c)
			if err == nil {
				return abs
			}
			return c
		}
	}
	// Best guess if nothing is found — let the manifest read surface
	// the friendlier error.
	return "seed/materials"
}

// ---- seed ------------------------------------------------------------------

type stats struct {
	total   int
	created int
	skipped int
}

func seedMaterials(ctx context.Context, pool *pgxpool.Pool, cfg *config.Config, dir string, m *manifest, dryRun bool) (stats, error) {
	st := stats{total: len(m.Materials)}

	// Resolve the system user. We do NOT auto-create one — the migrator
	// already does that during the standard install path.
	email := strings.ToLower(strings.TrimSpace(cfg.SystemUserEmail))
	if email == "" {
		log.Printf("[system_user].email is empty in %s; nothing to seed", cfg.SourcePath)
		return st, nil
	}
	var ownerID string
	err := pool.QueryRow(ctx, `select id from users where lower(email) = $1`, email).Scan(&ownerID)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			log.Printf("system user %s not found — run `kerf migrate` first to seed it", email)
			return st, nil
		}
		return st, fmt.Errorf("lookup system user: %w", err)
	}

	tx, err := pool.Begin(ctx)
	if err != nil {
		return st, fmt.Errorf("begin: %w", err)
	}
	defer tx.Rollback(ctx)

	projectID, projectCreated, err := upsertProject(ctx, tx, ownerID)
	if err != nil {
		return st, fmt.Errorf("project: %w", err)
	}
	verb := "reused"
	if projectCreated {
		verb = "created"
	}
	log.Printf("project %q (%s) — %s", projectName, projectID, verb)

	for _, mm := range m.Materials {
		fileName := filenameFor(mm.Name)
		body, err := os.ReadFile(filepath.Join(dir, mm.Path))
		if err != nil {
			return st, fmt.Errorf("read %s: %w", mm.Path, err)
		}
		// Sanity: confirm the file is well-formed JSON before we even
		// look at the DB. Catches a typo'd .material in the seed.
		var probe map[string]any
		if err := json.Unmarshal(body, &probe); err != nil {
			return st, fmt.Errorf("%s is not valid JSON: %w", mm.Path, err)
		}

		var existingID string
		err = tx.QueryRow(ctx, `
			select id from files
			 where project_id = $1
			   and name = $2
			   and kind = 'material'
			   and deleted_at is null
		`, projectID, fileName).Scan(&existingID)
		switch {
		case err == nil:
			st.skipped++
			log.Printf("  %s — skipped (already present as %s)", mm.Name, existingID)
			continue
		case errors.Is(err, pgx.ErrNoRows):
			// Insert.
			if _, err := tx.Exec(ctx, `
				insert into files(project_id, parent_id, name, kind, content)
				values ($1, null, $2, 'material', $3)
			`, projectID, fileName, string(body)); err != nil {
				return st, fmt.Errorf("insert %s: %w", mm.Name, err)
			}
			st.created++
			log.Printf("  %s — seeded", mm.Name)
		default:
			return st, fmt.Errorf("lookup %s: %w", mm.Name, err)
		}
	}

	if dryRun {
		return st, nil
	}
	if err := tx.Commit(ctx); err != nil {
		return st, fmt.Errorf("commit: %w", err)
	}
	return st, nil
}

// upsertProject finds or creates the holding project for the materials
// library. Identified by (owner_id, name) per the same convention
// library-import follows.
func upsertProject(ctx context.Context, tx pgx.Tx, ownerID string) (id string, created bool, err error) {
	row := tx.QueryRow(ctx,
		`select id from projects where owner_id = $1 and name = $2`,
		ownerID, projectName)
	if err := row.Scan(&id); err != nil {
		if !errors.Is(err, pgx.ErrNoRows) {
			return "", false, err
		}
		err = tx.QueryRow(ctx, `
			insert into projects(owner_id, name, description, visibility, tags)
			values ($1, $2, $3, $4, ARRAY['mechanical']::text[])
			returning id
		`, ownerID, projectName, projectDescription, projectVisibility).Scan(&id)
		if err != nil {
			return "", false, fmt.Errorf("insert project: %w", err)
		}
		// Owner-membership row mirroring CreateProject's two-step.
		if _, err := tx.Exec(ctx,
			`insert into project_members(project_id, user_id, role)
			 values ($1, $2, 'owner')`,
			id, ownerID); err != nil {
			return "", false, fmt.Errorf("insert membership: %w", err)
		}
		return id, true, nil
	}
	return id, false, nil
}

// filenameFor turns a Material name into a `<slug>.material` filesystem
// name. Same heuristic library-import uses for parts. Note: this mirrors
// the manifest's `path` field for the on-disk seed, but we slug the
// .Name rather than reusing the manifest path so that operator-renamed
// .material files in projects still collide on a re-seed.
func filenameFor(name string) string {
	var b strings.Builder
	prevDash := false
	for _, r := range strings.ToLower(strings.TrimSpace(name)) {
		switch {
		case r >= 'a' && r <= 'z', r >= '0' && r <= '9':
			b.WriteRune(r)
			prevDash = false
		default:
			if !prevDash && b.Len() > 0 {
				b.WriteByte('-')
				prevDash = true
			}
		}
	}
	out := strings.Trim(b.String(), "-")
	if out == "" {
		out = "material"
	}
	return out + ".material"
}

// silence unused-import warnings at build time.
var _ = time.Now
