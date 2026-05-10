//go:build cloud
// +build cloud

package main

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"

	"github.com/google/uuid"
)

// runLibrarySubmissions seeds a target Library workspace + project, then
// drives the manufacturer-PR submission flow end-to-end:
//
//   - User submits a valid Part → 201 + id, row visible in admin queue.
//   - User submits a Part missing required fields → 400.
//   - User submits to an unknown workspace → 404.
//   - Admin approves submission → status='approved', new files row
//     (kind='part') appears in the target project, payload preserved.
//   - Admin re-approves the same row → 409 (terminal status).
//   - User submits a second Part, admin rejects with note → status
//     ='rejected', reviewer + note stamped, no new files row created.
//
// Library Phase 3, ROADMAP row 73.
func runLibrarySubmissions(ctx context.Context, env *testEnv, suite *Suite) {
	const sc = "library_submissions"

	// --- Promote the cloud test user to 'admin' so the admin endpoints
	// admit them. We flip back via ResetState between scenarios; nothing
	// else in this scenario relies on the role afterwards. ---
	if _, err := env.Pool.Exec(ctx,
		`update users set account_role = 'admin' where id = $1`,
		CloudTestUserID,
	); !suite.AssertNoError(sc, "promote test user to admin", err) {
		return
	}

	// --- Seed the target Library workspace + a single Library project.
	// Mirrors the seed-publishers layout: one workspace per publisher,
	// one project (Common Components) inside it. ---
	wsID := uuid.New().String()
	wsSlug := "lib-target-" + wsID[:8]
	if _, err := env.Pool.Exec(ctx, `
		insert into workspaces(id, slug, name, created_by)
		values ($1, $2, 'Lib Target', $3)
	`, wsID, wsSlug, CloudTestUserID); !suite.AssertNoError(sc, "seed workspace", err) {
		return
	}
	if _, err := env.Pool.Exec(ctx, `
		insert into workspace_members(workspace_id, user_id, role)
		values ($1, $2, 'owner')
	`, wsID, CloudTestUserID); !suite.AssertNoError(sc, "seed membership", err) {
		return
	}
	projID := uuid.New().String()
	if _, err := env.Pool.Exec(ctx, `
		insert into projects(id, workspace_id, name, description, visibility)
		values ($1, $2, 'Common Components', 'curated', 'public')
	`, projID, wsID); !suite.AssertNoError(sc, "seed project", err) {
		return
	}

	// --- Happy path: valid submission lands as pending. ---
	validPart := map[string]any{
		"version":      1,
		"name":         "0.1µF cap 0805",
		"manufacturer": "Murata",
		"mpn":          "GRM21BR71H104KA01L",
		"category":     "capacitor",
		"description":  "X7R 0.1µF 50V 10% 0805 ceramic cap.",
	}
	subID := postSubmission(ctx, env, suite, sc, wsSlug, validPart, http.StatusCreated)
	if !suite.Assert(sc, "submission id non-empty", subID != "", "expected id") {
		return
	}

	// --- Validation: missing required field (no manufacturer). ---
	bad := map[string]any{
		"name":        "Mystery cap",
		"mpn":         "X-1",
		"category":    "capacitor",
		"description": "no manufacturer field",
	}
	postSubmission(ctx, env, suite, sc, wsSlug, bad, http.StatusBadRequest)

	// --- Unknown workspace slug. ---
	postSubmission(ctx, env, suite, sc, "this-slug-does-not-exist", validPart, http.StatusNotFound)

	// --- Admin lists the queue and sees exactly the one pending row. ---
	listResp := listSubmissions(ctx, env, suite, sc, "pending", http.StatusOK)
	if listResp != nil {
		subs, _ := listResp["submissions"].([]any)
		suite.AssertEqual(sc, "queue length=1", 1, len(subs))
		if len(subs) > 0 {
			row, _ := subs[0].(map[string]any)
			suite.AssertEqual(sc, "queue row id matches", subID, row["id"])
			suite.AssertEqual(sc, "queue row status", "pending", row["status"])
			suite.AssertEqual(sc, "queue row workspace slug", wsSlug, row["target_workspace_slug"])
		}
	}

	// --- Admin approves. ---
	approveResp := reviewSubmission(ctx, env, suite, sc, subID, "approve", "looks good", http.StatusOK)
	if approveResp != nil {
		suite.AssertEqual(sc, "approve status", "approved", approveResp["status"])
	}

	// A new files row landed in the target project.
	var fileCount int
	var fileContent, fileName string
	err := env.Pool.QueryRow(ctx, `
		select count(*), coalesce(min(name), ''), coalesce(min(content), '')
		  from files
		 where project_id = $1 and kind = 'part' and deleted_at is null
	`, projID).Scan(&fileCount, &fileName, &fileContent)
	if suite.AssertNoError(sc, "count approved files", err) {
		suite.AssertEqual(sc, "approved file count", 1, fileCount)
		suite.AssertContains(sc, "approved file content has mpn", fileContent, "GRM21BR71H104KA01L")
		suite.Assert(sc, "approved file name ends .part", strings.HasSuffix(fileName, ".part"),
			"got "+fileName)
	}

	// --- Re-approving the same row is a 409 (terminal). ---
	reviewSubmission(ctx, env, suite, sc, subID, "approve", "", http.StatusConflict)

	// --- Reject path: submit a second part, then reject it. ---
	secondPart := map[string]any{
		"version":      1,
		"name":         "Junk part",
		"manufacturer": "ACME",
		"mpn":          "REJ-001",
		"category":     "other",
		"description":  "intentionally rejectable",
	}
	subID2 := postSubmission(ctx, env, suite, sc, wsSlug, secondPart, http.StatusCreated)
	rejectResp := reviewSubmission(ctx, env, suite, sc, subID2, "reject", "duplicate of REJ-000", http.StatusOK)
	if rejectResp != nil {
		suite.AssertEqual(sc, "reject status", "rejected", rejectResp["status"])
		suite.AssertEqual(sc, "reject note echoed", "duplicate of REJ-000", rejectResp["review_note"])
	}

	// File count unchanged after rejection.
	var afterReject int
	if err := env.Pool.QueryRow(ctx, `
		select count(*) from files
		 where project_id = $1 and kind = 'part' and deleted_at is null
	`, projID).Scan(&afterReject); suite.AssertNoError(sc, "count after reject", err) {
		suite.AssertEqual(sc, "files unchanged after reject", 1, afterReject)
	}

	// --- DB-level: rejected row carries the reviewer + note. ---
	var status, note, reviewer string
	if err := env.Pool.QueryRow(ctx, `
		select status, review_note, coalesce(reviewer_id::text, '')
		  from library_part_submissions where id = $1
	`, subID2).Scan(&status, &note, &reviewer); suite.AssertNoError(sc, "load rejected row", err) {
		suite.AssertEqual(sc, "rejected row status", "rejected", status)
		suite.AssertEqual(sc, "rejected row note stamped", "duplicate of REJ-000", note)
		suite.AssertEqual(sc, "rejected row reviewer stamped", CloudTestUserID, reviewer)
	}
}

// postSubmission issues POST /api/library/submissions and returns the
// `id` field on success; empty otherwise.
func postSubmission(ctx context.Context, env *testEnv, suite *Suite, sc, slug string, payload map[string]any, wantStatus int) string {
	body := map[string]any{
		"target_workspace_slug": slug,
		"payload":               payload,
	}
	raw, _ := json.Marshal(body)
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost,
		env.HTTPServer.URL+"/api/library/submissions", bytes.NewReader(raw))
	req.Header.Set("content-type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if !suite.AssertNoError(sc, "POST /library/submissions", err) {
		return ""
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(resp.Body)
	if !suite.AssertEqual(sc, "POST status", wantStatus, resp.StatusCode) {
		suite.Failf(sc, "POST body: %s", string(respBody))
		return ""
	}
	if wantStatus != http.StatusCreated {
		return ""
	}
	var out map[string]any
	if err := json.Unmarshal(respBody, &out); !suite.AssertNoError(sc, "decode submit", err) {
		return ""
	}
	id, _ := out["id"].(string)
	return id
}

// listSubmissions issues GET /api/admin/library/submissions?status=...
// and returns the decoded JSON object on success; nil otherwise.
func listSubmissions(ctx context.Context, env *testEnv, suite *Suite, sc, status string, wantStatus int) map[string]any {
	url := env.HTTPServer.URL + "/api/admin/library/submissions"
	if status != "" {
		url += "?status=" + status
	}
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	resp, err := http.DefaultClient.Do(req)
	if !suite.AssertNoError(sc, "GET admin submissions", err) {
		return nil
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(resp.Body)
	if !suite.AssertEqual(sc, "GET admin status", wantStatus, resp.StatusCode) {
		suite.Failf(sc, "GET body: %s", string(respBody))
		return nil
	}
	if wantStatus != http.StatusOK {
		return nil
	}
	var out map[string]any
	if err := json.Unmarshal(respBody, &out); !suite.AssertNoError(sc, "decode list", err) {
		return nil
	}
	return out
}

// reviewSubmission issues PUT /api/admin/library/submissions/{id} with
// the given action + note and returns the decoded response on success.
func reviewSubmission(ctx context.Context, env *testEnv, suite *Suite, sc, id, action, note string, wantStatus int) map[string]any {
	body := map[string]any{"action": action, "review_note": note}
	raw, _ := json.Marshal(body)
	req, _ := http.NewRequestWithContext(ctx, http.MethodPut,
		env.HTTPServer.URL+"/api/admin/library/submissions/"+id, bytes.NewReader(raw))
	req.Header.Set("content-type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if !suite.AssertNoError(sc, "PUT review "+action, err) {
		return nil
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(resp.Body)
	if !suite.AssertEqual(sc, "PUT review status", wantStatus, resp.StatusCode) {
		suite.Failf(sc, "PUT body: %s", string(respBody))
		return nil
	}
	if wantStatus != http.StatusOK {
		return nil
	}
	var out map[string]any
	if err := json.Unmarshal(respBody, &out); !suite.AssertNoError(sc, "decode review", err) {
		return nil
	}
	return out
}
