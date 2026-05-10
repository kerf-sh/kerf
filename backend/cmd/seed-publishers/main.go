// kerf seed-publishers — seed the curated `kerf-system` verified-publisher
// account, its `kerf-system` workspace, and a small `Common Components`
// example library project from the JSON files at <repo>/seed/publishers/parts/.
//
// Why a dedicated command (vs piggy-backing on library-import):
// library-import is parametric over a YAML manifest the operator supplies and
// requires picking a publisher email + library name per invocation. The
// publisher seed targets a fixed `kerf-system` row (stable UUID, hardcoded
// slug + email), needs no manifest, and ships with the binary so any
// operator can run `npm run seed:publishers` after a migration to populate
// the verified-publisher fixture content. Once the dataset grows past one
// vendor we'll add per-vendor sub-directories under seed/publishers/ and
// loop over them here, not switch tools.
//
// Idempotency:
//
//   - The user is identified by a fixed UUID (seedUserID below). A stable
//     UUID rather than email-lookup means re-running the script never
//     creates a duplicate row even if the operator manually renamed the
//     row's email. Re-runs ensure account_role / is_system /
//     is_verified_publisher are correct, and patch name / avatar_url.
//   - The workspace is identified by `slug = 'kerf-system'`; the
//     workspace_members row is upserted by (workspace_id, user_id).
//   - The project is identified by (workspace_id, name='Common Components')
//     and reused on re-run; visibility and description are NOT clobbered
//     once the row exists.
//   - Each part file is identified by (project_id, name=<slug>.part). On
//     re-run an existing row is left alone — by design, so an operator
//     who locally tweaked a part isn't stomped on. To force-update a row,
//     delete it (or its file) first.
//
// Usage:
//
//	kerf seed-publishers                     # uses ./kerf.toml + ./seed/publishers/
//	kerf seed-publishers --config ../kerf.toml --dir ../seed/publishers
//	kerf seed-publishers --dry-run           # plan only
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
	"sort"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/internal/auth"
	"github.com/imranp/kerf/backend/internal/config"
	"github.com/imranp/kerf/backend/internal/db"
)

// ---- fixed identifiers -----------------------------------------------------

// seedUserID is the stable UUID of the kerf-system publisher user. The
// first 4 bytes are the ASCII hex of "kerf" (6b 65 72 66) so the row is
// recognisable on inspection. Variant + version bits are set per RFC 4122
// so the row passes the `uuid` Postgres type's strict format check.
const seedUserID = "6b657266-0000-4000-8000-000000000001"

const (
	seedUserEmail   = "system@kerf.local"
	seedUserName    = "Kerf System"
	seedWorkspace   = "kerf-system"
	seedWorkspaceN  = "Kerf System"
	seedProjectName = "Common Components"
	seedProjectDesc = "Curated example components — common SMD passives — owned by the kerf-system verified-publisher account. Demonstrates the Library Phase 3 verified-publisher pipeline; not intended as a complete catalog."
	seedProjectVis  = "public"
)

// ---- main ------------------------------------------------------------------

func main() {
	configFlag := flag.String("config", "", "path to kerf.toml (default: auto-detect)")
	dirFlag := flag.String("dir", "", "path to the seed/publishers directory (default: ./seed/publishers)")
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
	partsDir := filepath.Join(dir, "parts")
	parts, err := loadParts(partsDir)
	if err != nil {
		log.Fatalf("parts: %v", err)
	}
	log.Printf("parts: %d JSON files in %s", len(parts), partsDir)

	ctx := context.Background()
	pool, err := db.Connect(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("db: %v", err)
	}
	defer pool.Close()

	st, err := seed(ctx, pool, cfg, parts, *dryRun)
	if err != nil {
		log.Fatalf("seed: %v", err)
	}

	verb := "seeded"
	if *dryRun {
		verb = "would seed"
	}
	log.Printf("%s kerf-system + %d project + %d parts (%d new, %d skipped)",
		verb, st.projects, st.partsTotal, st.partsCreated, st.partsSkipped)
}

// ---- parts IO --------------------------------------------------------------

// seedPart is the in-memory representation of a single parts/<slug>.json
// entry. We keep the on-disk JSON shape verbatim (it IS the partDoc; see
// backend/internal/tools/part_tools.go) and the file's basename becomes
// the file's `name` in the DB after the .json → .part swap.
type seedPart struct {
	// FileName is `<slug>.part` — the value we store in files.name.
	FileName string
	// DisplayName is the part's `.name` field, used only for log output.
	DisplayName string
	// Content is the raw bytes we'll write into files.content. We
	// canonicalise via json.MarshalIndent so the on-disk source can be
	// hand-formatted differently from what's stored without tripping the
	// idempotency check (which compares by file row presence, not content).
	Content []byte
}

func loadParts(dir string) ([]seedPart, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, fmt.Errorf("read %s: %w", dir, err)
	}
	out := make([]seedPart, 0, len(entries))
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		name := e.Name()
		if !strings.HasSuffix(strings.ToLower(name), ".json") {
			continue
		}
		path := filepath.Join(dir, name)
		raw, err := os.ReadFile(path)
		if err != nil {
			return nil, fmt.Errorf("read %s: %w", path, err)
		}
		// Sanity check: confirm the file parses as a partDoc-shaped
		// JSON object. We don't validate every field strictly — the
		// runtime tooling tolerates partials — but we DO require a
		// non-empty `name` so the log line is meaningful.
		var probe struct {
			Name string `json:"name"`
		}
		if err := json.Unmarshal(raw, &probe); err != nil {
			return nil, fmt.Errorf("%s is not valid JSON: %w", name, err)
		}
		display := strings.TrimSpace(probe.Name)
		if display == "" {
			return nil, fmt.Errorf("%s: missing required `name` field", name)
		}

		// Re-marshal in a canonical shape so on-disk pretty-printing
		// drift doesn't break a future content-equality check.
		var doc map[string]any
		if err := json.Unmarshal(raw, &doc); err != nil {
			return nil, fmt.Errorf("%s normalise: %w", name, err)
		}
		canonical, err := json.MarshalIndent(doc, "", "  ")
		if err != nil {
			return nil, fmt.Errorf("%s remarshal: %w", name, err)
		}

		fileName := strings.TrimSuffix(name, filepath.Ext(name)) + ".part"
		out = append(out, seedPart{
			FileName:    fileName,
			DisplayName: display,
			Content:     canonical,
		})
	}
	// Stable order so log output is reproducible across runs.
	sort.Slice(out, func(i, j int) bool { return out[i].FileName < out[j].FileName })
	if len(out) == 0 {
		return nil, fmt.Errorf("no .json parts found in %s", dir)
	}
	return out, nil
}

// defaultSeedDir picks the most likely seed dir from the cwd. Tries
// ./seed/publishers first; falls back to ../seed/publishers so the
// command works from inside backend/ as well as from the repo root.
func defaultSeedDir() string {
	for _, c := range []string{"seed/publishers", "../seed/publishers"} {
		if info, err := os.Stat(c); err == nil && info.IsDir() {
			abs, err := filepath.Abs(c)
			if err == nil {
				return abs
			}
			return c
		}
	}
	return "seed/publishers"
}

// ---- seed ------------------------------------------------------------------

type stats struct {
	projects     int
	partsTotal   int
	partsCreated int
	partsSkipped int
}

func seed(ctx context.Context, pool *pgxpool.Pool, cfg *config.Config, parts []seedPart, dryRun bool) (stats, error) {
	st := stats{partsTotal: len(parts)}

	tx, err := pool.Begin(ctx)
	if err != nil {
		return st, fmt.Errorf("begin: %w", err)
	}
	defer tx.Rollback(ctx)

	userID, userCreated, err := upsertSystemUser(ctx, tx, cfg)
	if err != nil {
		return st, fmt.Errorf("user: %w", err)
	}
	verb := "reused"
	if userCreated {
		verb = "created"
	}
	log.Printf("user %s (%s) — %s", seedUserEmail, userID, verb)

	wsID, wsCreated, err := upsertSystemWorkspace(ctx, tx, userID)
	if err != nil {
		return st, fmt.Errorf("workspace: %w", err)
	}
	verb = "reused"
	if wsCreated {
		verb = "created"
	}
	log.Printf("workspace %q (%s) — %s", seedWorkspace, wsID, verb)

	projectID, projectCreated, err := upsertProject(ctx, tx, wsID)
	if err != nil {
		return st, fmt.Errorf("project: %w", err)
	}
	verb = "reused"
	if projectCreated {
		verb = "created"
	}
	st.projects = 1
	log.Printf("project %q (%s) — %s", seedProjectName, projectID, verb)

	for _, p := range parts {
		var existingID string
		err := tx.QueryRow(ctx, `
			select id from files
			 where project_id = $1
			   and name = $2
			   and kind = 'part'
			   and deleted_at is null
		`, projectID, p.FileName).Scan(&existingID)
		switch {
		case err == nil:
			st.partsSkipped++
			log.Printf("  %s — skipped (already present as %s)", p.DisplayName, existingID)
			continue
		case errors.Is(err, pgx.ErrNoRows):
			if _, err := tx.Exec(ctx, `
				insert into files(project_id, parent_id, name, kind, content)
				values ($1, null, $2, 'part', $3)
			`, projectID, p.FileName, string(p.Content)); err != nil {
				return st, fmt.Errorf("insert %s: %w", p.FileName, err)
			}
			st.partsCreated++
			log.Printf("  %s — seeded as %s", p.DisplayName, p.FileName)
		default:
			return st, fmt.Errorf("lookup %s: %w", p.FileName, err)
		}
	}

	if dryRun {
		// Roll back deliberately.
		return st, nil
	}
	if err := tx.Commit(ctx); err != nil {
		return st, fmt.Errorf("commit: %w", err)
	}
	return st, nil
}

// upsertSystemUser finds-or-creates the kerf-system user at a stable UUID
// and ensures the verified-publisher / system-account flags are set. We
// look up by id (not email) so a runtime rename of the email column
// doesn't cause a duplicate insert. On re-runs, name + verification
// flags + role are restored to the canonical values; password_hash is
// left alone if it already exists (so an operator who reset it for any
// reason isn't clobbered).
func upsertSystemUser(ctx context.Context, tx pgx.Tx, cfg *config.Config) (id string, created bool, err error) {
	row := tx.QueryRow(ctx, `select id from users where id = $1`, seedUserID)
	if err := row.Scan(&id); err != nil {
		if !errors.Is(err, pgx.ErrNoRows) {
			return "", false, err
		}
		// Insert. Use a random unguessable bcrypt hash so /auth/login
		// can't be used against this account by accident — this is a
		// content-owner row, not a login.
		hash, err := auth.HashPassword(randomPassword(), cfg.PasswordPepper)
		if err != nil {
			return "", false, fmt.Errorf("hash random password: %w", err)
		}
		_, err = tx.Exec(ctx, `
			insert into users(id, email, name, password_hash, account_role,
			                  is_system, is_verified_publisher, avatar_url)
			values ($1, $2, $3, $4, 'system', true, true, '')
		`, seedUserID, seedUserEmail, seedUserName, hash)
		if err != nil {
			return "", false, fmt.Errorf("insert user: %w", err)
		}
		return seedUserID, true, nil
	}

	// Existing row — re-stamp the flags. We deliberately do NOT touch
	// email, password_hash, or avatar_storage_key, so an operator's
	// local edits survive a re-seed.
	if _, err := tx.Exec(ctx, `
		update users
		   set name                  = $2,
		       account_role          = 'system',
		       is_system             = true,
		       is_verified_publisher = true
		 where id = $1
	`, seedUserID, seedUserName); err != nil {
		return "", false, fmt.Errorf("update user: %w", err)
	}
	return seedUserID, false, nil
}

// upsertSystemWorkspace finds-or-creates the kerf-system workspace,
// identified by its slug. The owning workspace_members row is upserted
// in lockstep so the kerf-system user is always reachable through the
// usual workspace-membership joins.
func upsertSystemWorkspace(ctx context.Context, tx pgx.Tx, userID string) (id string, created bool, err error) {
	row := tx.QueryRow(ctx, `select id from workspaces where slug = $1`, seedWorkspace)
	if err := row.Scan(&id); err != nil {
		if !errors.Is(err, pgx.ErrNoRows) {
			return "", false, err
		}
		err = tx.QueryRow(ctx, `
			insert into workspaces(slug, name, created_by)
			values ($1, $2, $3)
			returning id
		`, seedWorkspace, seedWorkspaceN, userID).Scan(&id)
		if err != nil {
			return "", false, fmt.Errorf("insert workspace: %w", err)
		}
		if _, err := tx.Exec(ctx, `
			insert into workspace_members(workspace_id, user_id, role)
			values ($1, $2, 'owner')
			on conflict (workspace_id, user_id) do nothing
		`, id, userID); err != nil {
			return "", false, fmt.Errorf("insert membership: %w", err)
		}
		return id, true, nil
	}
	// Existing — make sure ownership is wired up. A previous run that
	// raced or was interrupted between the workspaces insert and the
	// membership insert would otherwise leave the user without a row.
	if _, err := tx.Exec(ctx, `
		insert into workspace_members(workspace_id, user_id, role)
		values ($1, $2, 'owner')
		on conflict (workspace_id, user_id) do update set role = 'owner'
	`, id, userID); err != nil {
		return "", false, fmt.Errorf("repair membership: %w", err)
	}
	return id, false, nil
}

// upsertProject creates the holding project for the curated component
// library or reuses it on re-runs. Identified by (workspace_id, name)
// since projects.name isn't globally unique.
func upsertProject(ctx context.Context, tx pgx.Tx, workspaceID string) (id string, created bool, err error) {
	row := tx.QueryRow(ctx,
		`select id from projects where workspace_id = $1 and name = $2`,
		workspaceID, seedProjectName)
	if err := row.Scan(&id); err != nil {
		if !errors.Is(err, pgx.ErrNoRows) {
			return "", false, err
		}
		err = tx.QueryRow(ctx, `
			insert into projects(workspace_id, name, description, visibility, tags)
			values ($1, $2, $3, $4, ARRAY['electronics']::text[])
			returning id
		`, workspaceID, seedProjectName, seedProjectDesc, seedProjectVis).Scan(&id)
		if err != nil {
			return "", false, fmt.Errorf("insert project: %w", err)
		}
		return id, true, nil
	}
	return id, false, nil
}

// randomPassword returns a high-entropy-ish string for the system
// user's bcrypt-hashed password. Nobody is meant to log in as
// kerf-system; this is just to satisfy the column. Bcrypt itself
// salts the hash, so a non-crypto-grade input here is fine.
func randomPassword() string {
	return fmt.Sprintf("kerf-system-%d-%d", os.Getpid(), os.Getpid()*13)
}
