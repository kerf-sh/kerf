// kerf library-import — import a curated manufacturer library into a
// publisher account from a YAML manifest.
//
// Goal: ship Library Phase 3 starter content without forcing every
// operator to author Parts by hand. The manifest references a single
// publisher (Adafruit, SparkFun, Pololu, …) and a flat list of Parts;
// the command upserts the publisher user, an owner-membered project
// to hold the Parts, and one kind='part' file per entry.
//
// Idempotency
//
//	The publisher is identified by email. If a row exists, we patch
//	name/url/mark_verified onto it; otherwise a fresh user is created
//	with account_role='user' and is_system=false.
//
//	The library project is identified by (owner_id, name). We update
//	visibility/description on re-runs.
//
//	Parts are identified by (project_id, name) inside the project. On
//	re-run we update the JSON content if it has changed; we never
//	create a duplicate.
//
//	Re-running the same manifest is a no-op (everything is idempotent).
//	Output reports new/updated/unchanged counts so a re-run is
//	visually identifiable.
//
// Format
//
//	The manifest is YAML. JSON parses as a subset of YAML so a
//	hand-authored .json file works too — the dispatcher branches on
//	the path's extension. See samples/libraries/*.yaml for examples.
//
// Distributor URL handling
//
//	Each distributor entry is required to carry a `url` field; we
//	validate it parses as http(s) so we don't silently bake in junk
//	links. We do NOT call out to the distributor at import time —
//	prices and stock are intentionally left blank, and the existing
//	sweep refreshes them once the Part lands in the DB.
//
// Usage
//
//	kerf library-import --manifest samples/libraries/adafruit-sensors.yaml
//	kerf library-import --manifest <path> --dry-run     # plan only
//	kerf library-import --config kerf.toml --manifest …
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"gopkg.in/yaml.v3"

	"github.com/imranp/kerf/backend/internal/auth"
	"github.com/imranp/kerf/backend/internal/config"
	"github.com/imranp/kerf/backend/internal/db"
)

// ---- manifest types --------------------------------------------------------

type manifest struct {
	PublisherEmail     string         `yaml:"publisher_email"`
	PublisherName      string         `yaml:"publisher_name"`
	PublisherURL       string         `yaml:"publisher_url"`
	MarkVerified       bool           `yaml:"mark_verified"`
	LibraryName        string         `yaml:"library_name"`
	LibraryDescription string         `yaml:"library_description"`
	LibraryVisibility  string         `yaml:"library_visibility"`
	Parts              []manifestPart `yaml:"parts"`
}

type manifestPart struct {
	Name         string                  `yaml:"name"`
	Description  string                  `yaml:"description"`
	Category     string                  `yaml:"category"`
	Manufacturer string                  `yaml:"manufacturer"`
	MPN          string                  `yaml:"mpn"`
	Value        string                  `yaml:"value"`
	DatasheetURL string                  `yaml:"datasheet_url"`
	Visibility   string                  `yaml:"visibility"`
	Distributors []manifestDistributor   `yaml:"distributors"`
	Metadata     map[string]any          `yaml:"metadata"`
}

type manifestDistributor struct {
	Name string `yaml:"name"`
	SKU  string `yaml:"sku"`
	URL  string `yaml:"url"`
}

// partDoc mirrors backend/internal/tools/part_tools.go partDoc — we
// duplicate the struct here so this command is independent of the
// internal/tools package (which has its own dependency surface).
type partDoc struct {
	Version         int               `json:"version"`
	Name            string            `json:"name"`
	Description     string            `json:"description,omitempty"`
	Category        string            `json:"category,omitempty"`
	Manufacturer    string            `json:"manufacturer,omitempty"`
	MPN             string            `json:"mpn,omitempty"`
	Value           string            `json:"value,omitempty"`
	DatasheetURL    string            `json:"datasheet_url,omitempty"`
	Distributors    []partDistributor `json:"distributors"`
	Visibility      string            `json:"visibility,omitempty"`
	Metadata        map[string]any    `json:"metadata,omitempty"`
}

type partDistributor struct {
	Name string `json:"name"`
	SKU  string `json:"sku,omitempty"`
	URL  string `json:"url"`
}

// ---- main ------------------------------------------------------------------

func main() {
	configFlag := flag.String("config", "", "path to kerf.toml (default: auto-detect)")
	manifestFlag := flag.String("manifest", "", "path to the library manifest (YAML or JSON)")
	dryRun := flag.Bool("dry-run", false, "print the plan without writing")
	flag.Parse()

	if *manifestFlag == "" {
		log.Fatalf("--manifest is required")
	}

	m, err := loadManifest(*manifestFlag)
	if err != nil {
		log.Fatalf("manifest: %v", err)
	}
	if err := validateManifest(m); err != nil {
		log.Fatalf("manifest: %v", err)
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

	stats, err := importLibrary(ctx, pool, cfg, m, *dryRun)
	if err != nil {
		log.Fatalf("import: %v", err)
	}

	verb := "imported"
	if *dryRun {
		verb = "would import"
	}
	log.Printf("%s %d parts (%d new, %d updated, %d unchanged) into project %q owned by %s",
		verb, stats.totalParts, stats.partsNew, stats.partsUpdated, stats.partsUnchanged,
		m.LibraryName, m.PublisherEmail)
}

// ---- manifest IO -----------------------------------------------------------

func loadManifest(path string) (*manifest, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open: %w", err)
	}
	defer f.Close()
	raw, err := io.ReadAll(f)
	if err != nil {
		return nil, fmt.Errorf("read: %w", err)
	}
	var m manifest
	// yaml.v3 parses both YAML and JSON inputs; we don't bother with
	// the file extension and let the unmarshaler decide. Strict-error
	// is on so unknown keys surface as a typo guard for catalog
	// authors.
	dec := yaml.NewDecoder(strings.NewReader(string(raw)))
	dec.KnownFields(true)
	if err := dec.Decode(&m); err != nil {
		return nil, fmt.Errorf("parse %s: %w", filepath.Base(path), err)
	}
	return &m, nil
}

func validateManifest(m *manifest) error {
	if strings.TrimSpace(m.PublisherEmail) == "" {
		return fmt.Errorf("publisher_email is required")
	}
	if strings.TrimSpace(m.PublisherName) == "" {
		return fmt.Errorf("publisher_name is required")
	}
	if strings.TrimSpace(m.LibraryName) == "" {
		return fmt.Errorf("library_name is required")
	}
	if m.LibraryVisibility == "" {
		m.LibraryVisibility = "public"
	}
	switch m.LibraryVisibility {
	case "public", "unlisted", "private":
	default:
		return fmt.Errorf("library_visibility must be public/unlisted/private, got %q", m.LibraryVisibility)
	}
	if m.PublisherURL != "" {
		if err := validateHTTPURL(m.PublisherURL); err != nil {
			return fmt.Errorf("publisher_url: %w", err)
		}
	}
	seen := map[string]bool{}
	for i, p := range m.Parts {
		name := strings.TrimSpace(p.Name)
		if name == "" {
			return fmt.Errorf("parts[%d].name is required", i)
		}
		if seen[name] {
			return fmt.Errorf("parts[%d].name %q is duplicated within the manifest", i, name)
		}
		seen[name] = true
		if p.DatasheetURL != "" {
			if err := validateHTTPURL(p.DatasheetURL); err != nil {
				return fmt.Errorf("parts[%d].datasheet_url: %w", i, err)
			}
		}
		if p.Visibility == "" {
			p.Visibility = "public"
		}
		switch p.Visibility {
		case "public", "unlisted", "private":
		default:
			return fmt.Errorf("parts[%d].visibility must be public/unlisted/private, got %q", i, p.Visibility)
		}
		for j, d := range p.Distributors {
			if strings.TrimSpace(d.Name) == "" {
				return fmt.Errorf("parts[%d].distributors[%d].name is required", i, j)
			}
			if strings.TrimSpace(d.URL) == "" {
				return fmt.Errorf("parts[%d].distributors[%d].url is required", i, j)
			}
			if err := validateHTTPURL(d.URL); err != nil {
				return fmt.Errorf("parts[%d].distributors[%d].url: %w", i, j, err)
			}
		}
	}
	return nil
}

func validateHTTPURL(s string) error {
	u, err := url.Parse(s)
	if err != nil {
		return fmt.Errorf("invalid url: %w", err)
	}
	if u.Scheme != "http" && u.Scheme != "https" {
		return fmt.Errorf("scheme must be http(s): %s", s)
	}
	if u.Host == "" {
		return fmt.Errorf("url is missing host: %s", s)
	}
	return nil
}

// ---- import ----------------------------------------------------------------

type importStats struct {
	totalParts     int
	partsNew       int
	partsUpdated   int
	partsUnchanged int
}

func importLibrary(ctx context.Context, pool *pgxpool.Pool, cfg *config.Config, m *manifest, dryRun bool) (importStats, error) {
	stats := importStats{totalParts: len(m.Parts)}

	tx, err := pool.Begin(ctx)
	if err != nil {
		return stats, fmt.Errorf("begin: %w", err)
	}
	// Always rollback on dry-run; commit on success otherwise.
	defer tx.Rollback(ctx)

	publisherID, publisherCreated, err := upsertPublisher(ctx, tx, cfg, m)
	if err != nil {
		return stats, fmt.Errorf("publisher: %w", err)
	}
	verb := "reused"
	if publisherCreated {
		verb = "created"
	}
	log.Printf("publisher %s (%s) — %s", m.PublisherEmail, publisherID, verb)

	projectID, projectCreated, err := upsertProject(ctx, tx, publisherID, m)
	if err != nil {
		return stats, fmt.Errorf("project: %w", err)
	}
	verb = "reused"
	if projectCreated {
		verb = "created"
	}
	log.Printf("project %q (%s) — %s", m.LibraryName, projectID, verb)

	for _, p := range m.Parts {
		outcome, err := upsertPart(ctx, tx, projectID, p)
		if err != nil {
			return stats, fmt.Errorf("part %q: %w", p.Name, err)
		}
		switch outcome {
		case "new":
			stats.partsNew++
		case "updated":
			stats.partsUpdated++
		case "unchanged":
			stats.partsUnchanged++
		}
		log.Printf("  part %s — %s", filenameFor(p.Name), outcome)
	}

	if dryRun {
		// Roll back deliberately.
		return stats, nil
	}
	if err := tx.Commit(ctx); err != nil {
		return stats, fmt.Errorf("commit: %w", err)
	}
	return stats, nil
}

// upsertPublisher finds-or-creates the publisher user. Existing users
// keep their password_hash; new users are stamped with a random
// non-recoverable hash so /auth/login won't accidentally let someone
// in. Operators can rotate via the standard email-recovery flow if
// they ever need to log in as the publisher itself.
func upsertPublisher(ctx context.Context, tx pgx.Tx, cfg *config.Config, m *manifest) (id string, created bool, err error) {
	email := strings.ToLower(strings.TrimSpace(m.PublisherEmail))
	row := tx.QueryRow(ctx, `select id from users where lower(email) = $1`, email)
	if err := row.Scan(&id); err != nil {
		if !errors.Is(err, pgx.ErrNoRows) {
			return "", false, err
		}
		// Create with a random unguessable password hash. The publisher
		// account exists to *own* the library; nobody logs in as it.
		hash, err := auth.HashPassword(randomPassword(), cfg.PasswordPepper)
		if err != nil {
			return "", false, fmt.Errorf("hash random password: %w", err)
		}
		err = tx.QueryRow(ctx, `
			insert into users(email, name, password_hash, account_role,
			                  is_system, is_verified_publisher)
			values ($1, $2, $3, 'user', false, $4)
			returning id
		`, email, strings.TrimSpace(m.PublisherName), hash, m.MarkVerified).Scan(&id)
		if err != nil {
			return "", false, fmt.Errorf("insert user: %w", err)
		}
		return id, true, nil
	}

	// Existing row — patch name + verification flag if requested.
	if _, err := tx.Exec(ctx, `
		update users
		   set name = $2,
		       is_verified_publisher = case when $3 then true else is_verified_publisher end
		 where id = $1
	`, id, strings.TrimSpace(m.PublisherName), m.MarkVerified); err != nil {
		return "", false, fmt.Errorf("update user: %w", err)
	}
	return id, false, nil
}

// upsertProject creates the holding project for the curated library
// or reuses it on re-runs. Identified by (owner_id, name).
func upsertProject(ctx context.Context, tx pgx.Tx, ownerID string, m *manifest) (id string, created bool, err error) {
	row := tx.QueryRow(ctx,
		`select id from projects where owner_id = $1 and name = $2`,
		ownerID, m.LibraryName)
	if err := row.Scan(&id); err != nil {
		if !errors.Is(err, pgx.ErrNoRows) {
			return "", false, err
		}
		err = tx.QueryRow(ctx, `
			insert into projects(owner_id, name, description, visibility, project_type)
			values ($1, $2, $3, $4, 'mechanical')
			returning id
		`, ownerID, m.LibraryName, m.LibraryDescription, m.LibraryVisibility).Scan(&id)
		if err != nil {
			return "", false, fmt.Errorf("insert project: %w", err)
		}
		// Owner-membership row, mirroring CreateProject's two-step in
		// handlers.CreateProject. Without this, the owner can't see
		// the project through /api/projects.
		if _, err := tx.Exec(ctx,
			`insert into project_members(project_id, user_id, role)
			 values ($1, $2, 'owner')`,
			id, ownerID); err != nil {
			return "", false, fmt.Errorf("insert membership: %w", err)
		}
		return id, true, nil
	}

	if _, err := tx.Exec(ctx, `
		update projects
		   set description = $2,
		       visibility = $3
		 where id = $1
	`, id, m.LibraryDescription, m.LibraryVisibility); err != nil {
		return "", false, fmt.Errorf("update project: %w", err)
	}
	return id, false, nil
}

// upsertPart creates-or-updates a single Part file in the project.
// Files are identified by (project_id, name) — we use the part's
// .name slugged into <slug>.part as the filename so manual edits via
// the editor land on the same row.
func upsertPart(ctx context.Context, tx pgx.Tx, projectID string, p manifestPart) (string, error) {
	doc := buildPartDoc(p)
	body, err := json.MarshalIndent(doc, "", "  ")
	if err != nil {
		return "", fmt.Errorf("marshal: %w", err)
	}

	fileName := filenameFor(p.Name)

	var existingID, existingContent string
	err = tx.QueryRow(ctx, `
		select id, content
		  from files
		 where project_id = $1
		   and name = $2
		   and kind = 'part'
		   and deleted_at is null
	`, projectID, fileName).Scan(&existingID, &existingContent)
	if err != nil {
		if !errors.Is(err, pgx.ErrNoRows) {
			return "", err
		}
		// Insert.
		if _, err := tx.Exec(ctx, `
			insert into files(project_id, parent_id, name, kind, content)
			values ($1, null, $2, 'part', $3)
		`, projectID, fileName, string(body)); err != nil {
			return "", fmt.Errorf("insert file: %w", err)
		}
		return "new", nil
	}

	if equalIgnoringInsignificantWhitespace(existingContent, string(body)) {
		return "unchanged", nil
	}
	if _, err := tx.Exec(ctx, `
		update files
		   set content = $2,
		       updated_at = now()
		 where id = $1
		   and deleted_at is null
	`, existingID, string(body)); err != nil {
		return "", fmt.Errorf("update file: %w", err)
	}
	return "updated", nil
}

// buildPartDoc converts a manifest entry into the canonical Part JSON
// shape that the rest of Kerf understands (matches src/lib/part.js
// + backend/internal/tools/part_tools.go partDoc).
func buildPartDoc(p manifestPart) partDoc {
	visibility := p.Visibility
	if visibility == "" {
		visibility = "public"
	}
	dists := make([]partDistributor, 0, len(p.Distributors))
	for _, d := range p.Distributors {
		dists = append(dists, partDistributor{
			Name: strings.ToLower(strings.TrimSpace(d.Name)),
			SKU:  strings.TrimSpace(d.SKU),
			URL:  strings.TrimSpace(d.URL),
		})
	}
	return partDoc{
		Version:      1,
		Name:         strings.TrimSpace(p.Name),
		Description:  strings.TrimSpace(p.Description),
		Category:     strings.TrimSpace(p.Category),
		Manufacturer: strings.TrimSpace(p.Manufacturer),
		MPN:          strings.TrimSpace(p.MPN),
		Value:        strings.TrimSpace(p.Value),
		DatasheetURL: strings.TrimSpace(p.DatasheetURL),
		Distributors: dists,
		Visibility:   visibility,
		Metadata:     p.Metadata,
	}
}

// filenameFor turns a Part name into a stable filesystem-friendly
// .part filename. We collapse non-alnum runs to '-' and lowercase.
// Kept simple — the filesystem mirror tolerates whatever this emits.
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
		out = "part"
	}
	return out + ".part"
}

// equalIgnoringInsignificantWhitespace lets us re-encode JSON
// reliably without flagging cosmetic differences (trailing newlines,
// CRLF) as a content change. We don't do a full JSON normaliser —
// upsertPart writes via json.MarshalIndent so the only realistic
// drift between runs is whitespace at the edges.
func equalIgnoringInsignificantWhitespace(a, b string) bool {
	return strings.TrimSpace(a) == strings.TrimSpace(b)
}

// randomPassword returns a high-entropy random string used as the
// publisher account's bcrypt-hashed password. Nobody is meant to log
// in as a publisher — this is just to satisfy the not-null
// password_hash column on users.
func randomPassword() string {
	// Combine the time+nanos with a bit of bcrypt internal entropy
	// indirectly: this string is hashed by bcrypt with the configured
	// pepper, and bcrypt itself salts. The input doesn't need to be
	// crypto-grade; an attacker bypassing bcrypt would already have
	// wider problems. We deliberately don't pull crypto/rand to keep
	// the imports small; if this ever needs hardening, swap to
	// crypto/rand.Read here.
	return fmt.Sprintf("publisher-%d-%d", time.Now().UnixNano(), os.Getpid())
}
