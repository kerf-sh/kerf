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

// runLibraryPartDetail seeds a published project with one public Part
// inside it and drives GET /api/library/parts/{slug}. Phase 4 of the
// Library/Workshop split (ROADMAP row 74).
//
// Verifies:
//   - 200 with the expected fields when the slug matches a workshop
//     listing whose project contains a public Part.
//   - 404 with {"error":"part not found"} for an unknown slug.
//   - 404 when the listing exists but its Part is not public (visibility
//     filter applies the same way as the listing endpoint).
//   - 404 when the listing exists but the project visibility is private.
//   - The response carries the raw `content` JSON the frontend's
//     extractDoc() expects (distributors, photos parseable from there).
//   - Author payload includes `is_verified_publisher`.
func runLibraryPartDetail(ctx context.Context, env *testEnv, suite *Suite) {
	const sc = "library_part_detail"

	// --- Seed: one verified user, a workspace, two projects (public +
	//     private), three Parts (public-on-public, private-on-public,
	//     public-on-private). The schema uses workspaces+workspace_members
	//     for project ownership; the publisher identity comes from
	//     cloud_workshop_listings.user_id (not projects.owner_id which
	//     was dropped by the workspaces migration). ---
	verifiedID := uuid.New().String()
	if _, err := env.Pool.Exec(ctx, `
		insert into users(id, email, name, account_role, is_system, is_verified_publisher)
		values ($1, 'lib-verified@kerf.local', 'Lib Verified Co.', 'user', false, true)
	`, verifiedID); !suite.AssertNoError(sc, "seed user", err) {
		return
	}

	workspaceID := uuid.New().String()
	if _, err := env.Pool.Exec(ctx, `
		insert into workspaces(id, slug, name, created_by)
		values ($1, 'lib-ws', 'Lib WS', $2)
	`, workspaceID, verifiedID); !suite.AssertNoError(sc, "seed workspace", err) {
		return
	}

	publicProjID := uuid.New().String()
	privateProjID := uuid.New().String()
	if _, err := env.Pool.Exec(ctx, `
		insert into projects(id, workspace_id, name, description, visibility)
		values
		  ($1, $2, 'Public Lib Project', '', 'public'),
		  ($3, $2, 'Private Lib Project', '', 'private')
	`, publicProjID, workspaceID, privateProjID); !suite.AssertNoError(sc, "seed projects", err) {
		return
	}

	publicSlug := "public-lib-project"
	privateSlug := "private-lib-project"
	if _, err := env.Pool.Exec(ctx, `
		insert into cloud_workshop_listings(id, project_id, user_id, slug, title, description, published_at, updated_at)
		values
		  ($1, $2, $3, $4, 'Public Lib Project', '', now(), now()),
		  ($5, $6, $3, $7, 'Private Lib Project', '', now(), now())
	`, uuid.New().String(), publicProjID, verifiedID, publicSlug,
		uuid.New().String(), privateProjID, privateSlug,
	); !suite.AssertNoError(sc, "seed listings", err) {
		return
	}

	// Public Part inside the public project — should be returned by GET.
	publicPart := map[string]any{
		"version":      1,
		"name":         "10kΩ resistor 0805",
		"manufacturer": "Yageo",
		"mpn":          "RC0805FR-0710KL",
		"category":     "resistor",
		"visibility":   "public",
		"description":  "Generic 10k 1% 0805 chip resistor.",
		"datasheet_url": "https://example.com/datasheet.pdf",
		"distributors": []any{
			map[string]any{"name": "lcsc", "sku": "C17414", "price_usd": 0.01, "moq": 100},
			map[string]any{"name": "digikey", "sku": "311-10.0KCRCT-ND", "price_usd": 0.10, "moq": 1},
		},
		"photos": []any{
			map[string]any{"storage_key": "p/1.png", "primary": "true"},
		},
	}
	publicRaw, _ := json.Marshal(publicPart)
	if _, err := env.Pool.Exec(ctx, `
		insert into files(id, project_id, name, kind, content)
		values ($1, $2, '10k.part', 'part', $3)
	`, uuid.New().String(), publicProjID, string(publicRaw)); !suite.AssertNoError(sc, "seed public part", err) {
		return
	}

	// A NON-public Part (visibility='unlisted') in a project that is
	// itself public-listed but has no public Parts. We seed under a
	// SECOND public project + listing so the 404 case is "listing
	// exists, but no public Part inside".
	hiddenProjID := uuid.New().String()
	if _, err := env.Pool.Exec(ctx, `
		insert into projects(id, workspace_id, name, visibility)
		values ($1, $2, 'Hidden Parts Project', 'public')
	`, hiddenProjID, workspaceID); !suite.AssertNoError(sc, "seed hidden proj", err) {
		return
	}
	hiddenSlug := "hidden-parts-project"
	if _, err := env.Pool.Exec(ctx, `
		insert into cloud_workshop_listings(id, project_id, user_id, slug, title, description, published_at, updated_at)
		values ($1, $2, $3, $4, 'Hidden Parts', '', now(), now())
	`, uuid.New().String(), hiddenProjID, verifiedID, hiddenSlug); !suite.AssertNoError(sc, "seed hidden listing", err) {
		return
	}
	hiddenPart := map[string]any{
		"version":      1,
		"name":         "Unlisted thing",
		"visibility":   "unlisted",
		"distributors": []any{},
		"photos":       []any{},
	}
	hiddenRaw, _ := json.Marshal(hiddenPart)
	if _, err := env.Pool.Exec(ctx, `
		insert into files(id, project_id, name, kind, content)
		values ($1, $2, 'u.part', 'part', $3)
	`, uuid.New().String(), hiddenProjID, string(hiddenRaw)); !suite.AssertNoError(sc, "seed hidden part", err) {
		return
	}

	// Public Part inside a PRIVATE project — should NOT surface.
	privatePart := map[string]any{
		"version":      1,
		"name":         "Stash Cap",
		"visibility":   "public",
		"distributors": []any{},
		"photos":       []any{},
	}
	privateRaw, _ := json.Marshal(privatePart)
	if _, err := env.Pool.Exec(ctx, `
		insert into files(id, project_id, name, kind, content)
		values ($1, $2, 's.part', 'part', $3)
	`, uuid.New().String(), privateProjID, string(privateRaw)); !suite.AssertNoError(sc, "seed private-proj part", err) {
		return
	}

	// --- 200 OK on the happy path. ---
	row := getPartDetail(ctx, env, suite, sc, publicSlug, http.StatusOK)
	if row == nil {
		return
	}
	suite.AssertEqual(sc, "row.slug", publicSlug, row["slug"])
	suite.AssertEqual(sc, "row.name", "10kΩ resistor 0805", row["name"])
	suite.AssertEqual(sc, "row.manufacturer", "Yageo", row["manufacturer"])
	suite.AssertEqual(sc, "row.mpn", "RC0805FR-0710KL", row["mpn"])
	suite.AssertEqual(sc, "row.category", "resistor", row["category"])
	suite.AssertEqual(sc, "row.source_slug", publicSlug, row["source_slug"])

	// `content` is the raw JSON string the frontend parses for distributors.
	contentStr, _ := row["content"].(string)
	suite.Assert(sc, "row.content non-empty", contentStr != "",
		"expected content string, got empty")
	suite.AssertContains(sc, "row.content has distributors", contentStr, "lcsc")
	suite.AssertContains(sc, "row.content has datasheet", contentStr, "datasheet.pdf")

	// Author payload.
	author, _ := row["author"].(map[string]any)
	suite.AssertEqual(sc, "author.user_id", verifiedID, author["user_id"])
	suite.AssertEqual(sc, "author.is_verified_publisher", true, author["is_verified_publisher"])

	// id/file_id wired (matches the listing-row shape).
	suite.Assert(sc, "row.file_id non-empty", row["file_id"] != nil && row["file_id"] != "",
		"expected file_id")
	suite.Assert(sc, "row.project_id matches", row["project_id"] == publicProjID,
		"expected project_id="+publicProjID)

	// --- 404: unknown slug. ---
	if body := getPartDetailRaw(ctx, env, suite, sc, "nonexistent-slug-xyz", http.StatusNotFound); body != "" {
		suite.AssertContains(sc, "404 body has error key", body, "part not found")
	}

	// --- 404: slug exists but no public Part inside. ---
	getPartDetail(ctx, env, suite, sc, hiddenSlug, http.StatusNotFound)

	// --- 404: slug exists but project is private. ---
	getPartDetail(ctx, env, suite, sc, privateSlug, http.StatusNotFound)
}

// getPartDetail hits GET /api/library/parts/{slug} and returns the
// decoded JSON-object body when status == wantStatus; nil otherwise.
// Status mismatch is recorded as a failure on the suite.
func getPartDetail(ctx context.Context, env *testEnv, suite *Suite, sc, slug string, wantStatus int) map[string]any {
	body := getPartDetailRaw(ctx, env, suite, sc, slug, wantStatus)
	if body == "" || wantStatus != http.StatusOK {
		return nil
	}
	var out map[string]any
	if err := json.Unmarshal([]byte(body), &out); !suite.AssertNoError(sc, "decode "+slug, err) {
		return nil
	}
	return out
}

// getPartDetailRaw is the byte-level sibling of getPartDetail; returns
// the body as a string and asserts on the HTTP status code.
func getPartDetailRaw(ctx context.Context, env *testEnv, suite *Suite, sc, slug string, wantStatus int) string {
	resp, err := http.Get(env.HTTPServer.URL + "/api/library/parts/" + slug)
	if !suite.AssertNoError(sc, "GET /library/parts/"+slug, err) {
		return ""
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	if !suite.AssertEqual(sc, "GET /library/parts/"+slug+" status", wantStatus, resp.StatusCode) {
		suite.Failf(sc, "/library/parts/%s body: %s", slug, string(raw))
		return ""
	}
	return string(raw)
}
