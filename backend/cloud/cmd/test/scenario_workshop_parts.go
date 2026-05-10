//go:build cloud
// +build cloud

package main

import (
	"context"
	"encoding/json"
	"io"
	"net/http"

	"github.com/google/uuid"
)

// runWorkshopParts seeds two libraries with mixed Part visibilities and
// drives GET /api/workshop/parts. Verifies:
//
//   - Only Parts with content.visibility='public' AND a non-private
//     containing project surface.
//   - ?verified_only=true filters to Parts owned by users where
//     is_verified_publisher=true.
//   - ?search=<q> does case-insensitive ILIKE over name/manufacturer/mpn.
//   - ?category=<c> exact-matches.
//   - Author payload carries is_verified_publisher.
func runWorkshopParts(ctx context.Context, env *testEnv, suite *Suite) {
	const sc = "workshop_parts"

	// --- Seed users: one verified publisher, one regular. ---
	verifiedID := uuid.New().String()
	regularID := uuid.New().String()
	if _, err := env.Pool.Exec(ctx, `
		insert into users(id, email, name, account_role, is_system, is_verified_publisher)
		values
		  ($1, 'verified@kerf.local', 'Verified Co.', 'user', false, true),
		  ($2, 'regular@kerf.local',  'Regular Co.',  'user', false, false)
	`, verifiedID, regularID); !suite.AssertNoError(sc, "seed users", err) {
		return
	}

	// --- Seed workspaces + memberships post-1746577400000. ---
	verifiedWS := uuid.New().String()
	regularWS := uuid.New().String()
	if _, err := env.Pool.Exec(ctx, `
		insert into workspaces(id, slug, name, created_by)
		values
		  ($1, $2, 'Verified WS', $3),
		  ($4, $5, 'Regular WS',  $6)
	`, verifiedWS, "verified-ws-"+verifiedWS[:8], verifiedID,
		regularWS, "regular-ws-"+regularWS[:8], regularID,
	); !suite.AssertNoError(sc, "seed workspaces", err) {
		return
	}
	if _, err := env.Pool.Exec(ctx, `
		insert into workspace_members(workspace_id, user_id, role)
		values ($1, $2, 'owner'), ($3, $4, 'owner')
	`, verifiedWS, verifiedID, regularWS, regularID,
	); !suite.AssertNoError(sc, "seed workspace_members", err) {
		return
	}

	// --- Seed two projects: one verified-owned (public), one regular-owned
	//     (also public). Visibility column is the project-level filter. ---
	verifiedProjID := uuid.New().String()
	regularProjID := uuid.New().String()
	if _, err := env.Pool.Exec(ctx, `
		insert into projects(id, workspace_id, name, description, visibility)
		values
		  ($1, $2, 'Verified Library', '', 'public'),
		  ($3, $4, 'Regular Library',  '', 'public')
	`, verifiedProjID, verifiedWS, regularProjID, regularWS); !suite.AssertNoError(sc, "seed projects", err) {
		return
	}

	// And one PRIVATE project with a public Part inside — the part should
	// NOT appear (project visibility filter is the gate).
	privateProjID := uuid.New().String()
	if _, err := env.Pool.Exec(ctx, `
		insert into projects(id, workspace_id, name, visibility)
		values ($1, $2, 'Private Stash', 'private')
	`, privateProjID, regularWS); !suite.AssertNoError(sc, "seed private proj", err) {
		return
	}

	// --- Seed Parts. ---
	type seedPart struct {
		fileID       string
		projectID    string
		name         string
		manufacturer string
		mpn          string
		category     string
		visibility   string // public|unlisted|private
	}
	seeds := []seedPart{
		{
			fileID:       uuid.New().String(),
			projectID:    verifiedProjID,
			name:         "10kΩ resistor 0805",
			manufacturer: "Yageo",
			mpn:          "RC0805FR-0710KL",
			category:     "resistor",
			visibility:   "public",
		},
		{
			fileID:       uuid.New().String(),
			projectID:    verifiedProjID,
			name:         "Hidden Resistor",
			manufacturer: "Yageo",
			mpn:          "HIDDEN-1",
			category:     "resistor",
			visibility:   "private", // skipped — not 'public'
		},
		{
			fileID:       uuid.New().String(),
			projectID:    regularProjID,
			name:         "100nF X7R 0805",
			manufacturer: "Murata",
			mpn:          "GRM21BR71H104KA01L",
			category:     "capacitor",
			visibility:   "public",
		},
		{
			fileID:       uuid.New().String(),
			projectID:    regularProjID,
			name:         "Unlisted thing",
			manufacturer: "Acme",
			mpn:          "U-1",
			category:     "misc",
			visibility:   "unlisted", // skipped — not 'public'
		},
		{
			fileID:       uuid.New().String(),
			projectID:    privateProjID,
			name:         "Hidden Cap",
			manufacturer: "Murata",
			mpn:          "HIDDEN-CAP",
			category:     "capacitor",
			visibility:   "public", // skipped — project private
		},
	}
	for _, p := range seeds {
		content := map[string]any{
			"version":      1,
			"name":         p.name,
			"manufacturer": p.manufacturer,
			"mpn":          p.mpn,
			"category":     p.category,
			"visibility":   p.visibility,
			"distributors": []any{},
			"photos":       []any{},
		}
		raw, _ := json.Marshal(content)
		if _, err := env.Pool.Exec(ctx, `
			insert into files(id, project_id, name, kind, content)
			values ($1, $2, $3, 'part', $4)
		`, p.fileID, p.projectID, p.name+".part", string(raw)); !suite.AssertNoError(sc, "seed part "+p.mpn, err) {
			return
		}
	}

	// --- GET /api/workshop/parts → 2 public Parts. ---
	all := getParts(ctx, env, suite, sc, "")
	if all == nil {
		return
	}
	suite.AssertEqual(sc, "default rows count", 2, len(all.Rows))

	// Verify ordering: verified publisher first, then by updated_at desc.
	if len(all.Rows) >= 1 {
		suite.AssertEqual(sc, "row[0] is verified publisher",
			true, all.Rows[0].Author.IsVerifiedPublisher)
	}
	if len(all.Rows) >= 2 {
		suite.AssertEqual(sc, "row[1] is regular publisher",
			false, all.Rows[1].Author.IsVerifiedPublisher)
	}

	// Author payload sanity.
	if len(all.Rows) >= 1 {
		suite.AssertEqual(sc, "row[0].author.user_id",
			verifiedID, all.Rows[0].Author.UserID)
	}

	// --- ?verified_only=true → only verified-publisher's Part. ---
	verified := getParts(ctx, env, suite, sc, "?verified_only=true")
	if verified == nil {
		return
	}
	suite.AssertEqual(sc, "verified_only count", 1, len(verified.Rows))
	if len(verified.Rows) >= 1 {
		suite.AssertEqual(sc, "verified_only mpn",
			"RC0805FR-0710KL", verified.Rows[0].MPN)
	}

	// --- ?search= ILIKE on name. ---
	byName := getParts(ctx, env, suite, sc, "?search=resistor")
	if byName == nil {
		return
	}
	suite.AssertEqual(sc, "search 'resistor' rows", 1, len(byName.Rows))

	// Case-insensitive search. Also matches manufacturer.
	byMfr := getParts(ctx, env, suite, sc, "?search=MURATA")
	if byMfr == nil {
		return
	}
	suite.AssertEqual(sc, "search 'MURATA' (case-insensitive)", 1, len(byMfr.Rows))

	// MPN substring.
	byMPN := getParts(ctx, env, suite, sc, "?search=GRM21")
	if byMPN == nil {
		return
	}
	suite.AssertEqual(sc, "search 'GRM21' rows", 1, len(byMPN.Rows))

	// No-hit search.
	none := getParts(ctx, env, suite, sc, "?search=nonexistent-xyz123")
	if none == nil {
		return
	}
	suite.AssertEqual(sc, "search no-hit rows", 0, len(none.Rows))

	// --- ?category= exact match. ---
	caps := getParts(ctx, env, suite, sc, "?category=capacitor")
	if caps == nil {
		return
	}
	suite.AssertEqual(sc, "category capacitor rows", 1, len(caps.Rows))
	if len(caps.Rows) >= 1 {
		suite.AssertEqual(sc, "category capacitor → MPN", "GRM21BR71H104KA01L", caps.Rows[0].MPN)
	}

	// Category that doesn't exist.
	missing := getParts(ctx, env, suite, sc, "?category=inductor")
	if missing == nil {
		return
	}
	suite.AssertEqual(sc, "category inductor → 0", 0, len(missing.Rows))
}

// runWorkshopListings extends the existing Workshop coverage with
// project-listing + part-browse cross-cutting tests (publish a project,
// list both endpoints, verify they don't conflict on slug routing).
func runWorkshopListings(ctx context.Context, env *testEnv, suite *Suite) {
	const sc = "workshop_listings"

	// Seed a single user + workspace + public project.
	userID := CloudTestUserID
	wsID := uuid.New().String()
	if _, err := env.Pool.Exec(ctx, `
		insert into workspaces(id, slug, name, created_by)
		values ($1, $2, 'Cool WS', $3)
	`, wsID, "cool-ws-"+wsID[:8], userID); !suite.AssertNoError(sc, "seed workspace", err) {
		return
	}
	if _, err := env.Pool.Exec(ctx, `
		insert into workspace_members(workspace_id, user_id, role)
		values ($1, $2, 'owner')
	`, wsID, userID); !suite.AssertNoError(sc, "seed workspace_member", err) {
		return
	}
	projID := uuid.New().String()
	if _, err := env.Pool.Exec(ctx, `
		insert into projects(id, workspace_id, name, description, visibility)
		values ($1, $2, 'Cool Project', 'a project', 'public')
	`, projID, wsID); !suite.AssertNoError(sc, "seed project", err) {
		return
	}

	// --- Publish ---
	body, _ := json.Marshal(map[string]string{
		"project_id":  projID,
		"title":       "Cool Project",
		"description": "Hello",
	})
	resp, err := http.Post(env.HTTPServer.URL+"/api/workshop/publish",
		"application/json", io.NopCloser(bytesReader(body)))
	if !suite.AssertNoError(sc, "POST /publish", err) {
		return
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	if !suite.AssertEqual(sc, "publish status 201", 201, resp.StatusCode) {
		suite.Failf(sc, "publish body: %s", string(raw))
		return
	}
	var pubOut struct {
		Slug string `json:"slug"`
		ID   string `json:"id"`
	}
	_ = json.Unmarshal(raw, &pubOut)
	suite.Assert(sc, "publish slug non-empty", pubOut.Slug != "",
		"slug="+pubOut.Slug)

	// --- /api/workshop/{slug} resolves the listing ---
	resp2, err := http.Get(env.HTTPServer.URL + "/api/workshop/" + pubOut.Slug)
	if !suite.AssertNoError(sc, "GET /{slug}", err) {
		return
	}
	defer resp2.Body.Close()
	raw2, _ := io.ReadAll(resp2.Body)
	if !suite.AssertEqual(sc, "GET slug status 200", 200, resp2.StatusCode) {
		suite.Failf(sc, "/{slug} body: %s", string(raw2))
	}

	var detail struct {
		Slug      string `json:"slug"`
		Title     string `json:"title"`
		ProjectID string `json:"project_id"`
	}
	_ = json.Unmarshal(raw2, &detail)
	suite.AssertEqual(sc, "detail.slug", pubOut.Slug, detail.Slug)
	suite.AssertEqual(sc, "detail.project_id", projID, detail.ProjectID)

	// --- /api/workshop/parts coexists with /api/workshop/{slug}: chi's
	//     pattern resolver MUST route /parts to ListParts (not Get(slug='parts')).
	//     We seed a public Part to confirm /parts returns it. ---
	partID := uuid.New().String()
	partContent, _ := json.Marshal(map[string]any{
		"version":      1,
		"name":         "Test Part",
		"mpn":          "TP-1",
		"visibility":   "public",
		"distributors": []any{},
		"photos":       []any{},
	})
	if _, err := env.Pool.Exec(ctx, `
		insert into files(id, project_id, name, kind, content)
		values ($1, $2, 'tp.part', 'part', $3)
	`, partID, projID, string(partContent)); !suite.AssertNoError(sc, "seed part", err) {
		return
	}

	parts := getParts(ctx, env, suite, sc, "")
	if parts == nil {
		return
	}
	suite.Assert(sc, "/parts returns the seeded Part",
		len(parts.Rows) >= 1,
		"expected >=1 row, got "+itoa(len(parts.Rows)))

	// /api/workshop/ listing index also returns the published listing.
	resp3, err := http.Get(env.HTTPServer.URL + "/api/workshop/")
	if suite.AssertNoError(sc, "GET /workshop/", err) {
		defer resp3.Body.Close()
		raw3, _ := io.ReadAll(resp3.Body)
		var idx struct {
			Listings []map[string]any `json:"listings"`
		}
		_ = json.Unmarshal(raw3, &idx)
		suite.Assert(sc, "/workshop/ has >=1 listing",
			len(idx.Listings) >= 1,
			"expected >=1 listing, got "+itoa(len(idx.Listings)))
	}
}

// --- helpers --------------------------------------------------------------

type partRow struct {
	FileID       string `json:"file_id"`
	ProjectID    string `json:"project_id"`
	Name         string `json:"name"`
	Manufacturer string `json:"manufacturer"`
	MPN          string `json:"mpn"`
	Category     string `json:"category"`
	Author       struct {
		UserID              string `json:"user_id"`
		Name                string `json:"name"`
		IsVerifiedPublisher bool   `json:"is_verified_publisher"`
	} `json:"author"`
}

type partsResp struct {
	Rows  []partRow `json:"rows"`
	Limit int       `json:"limit"`
	Total int       `json:"total"`
}

// getParts hits GET /api/workshop/parts<query> (query starts with '?' or
// is empty) and returns the decoded partsResp; nil on a status mismatch.
func getParts(ctx context.Context, env *testEnv, suite *Suite, sc, query string) *partsResp {
	resp, err := http.Get(env.HTTPServer.URL + "/api/workshop/parts" + query)
	if !suite.AssertNoError(sc, "GET /parts"+query, err) {
		return nil
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	if !suite.AssertEqual(sc, "GET /parts"+query+" status", 200, resp.StatusCode) {
		suite.Failf(sc, "/parts%s body: %s", query, string(raw))
		return nil
	}
	var out partsResp
	if err := json.Unmarshal(raw, &out); !suite.AssertNoError(sc, "decode /parts"+query, err) {
		return nil
	}
	return &out
}

// itoa is a tiny helper to avoid importing strconv just for one call site.
func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var b [20]byte
	i := len(b)
	for n > 0 {
		i--
		b[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		b[i] = '-'
	}
	return string(b[i:])
}

// bytesReader avoids depending on bytes.NewReader from main scope.
func bytesReader(b []byte) *byteReader { return &byteReader{b: b} }

type byteReader struct {
	b   []byte
	pos int
}

func (r *byteReader) Read(p []byte) (int, error) {
	if r.pos >= len(r.b) {
		return 0, io.EOF
	}
	n := copy(p, r.b[r.pos:])
	r.pos += n
	return n, nil
}
