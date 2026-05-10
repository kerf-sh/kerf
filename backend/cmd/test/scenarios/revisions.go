package scenarios

// End-to-end scenario for the Phase-4 diff-based + compressed revision
// pipeline. Drives the public API + DB columns to verify:
//
//   1. Every PATCH writes a file_revisions row.
//   2. The first row is kind='base'; subsequent small edits land as
//      kind='diff' against the previous revision.
//   3. After more than DiffsPerBase consecutive diffs, the chain
//      forces a fresh kind='base' snapshot — bounding read-path
//      reconstruction depth.
//   4. content_sha256 is populated on every new row and matches a
//      hash of the reconstructed content.
//   5. content_gz is non-NULL (legacy plaintext column ignored).
//   6. Restore-revision returns content matching what was originally
//      written, even for revisions that live deep in a diff chain.

import (
	"bytes"
	"context"
	"crypto/sha256"
	"fmt"
	"strings"

	"github.com/imranp/kerf/backend/cmd/test/runner"
	"github.com/imranp/kerf/backend/internal/tools"
)

// Revisions exercises diff/base selection, compression, hash verification,
// and restore round-tripping.
func Revisions(s *runner.Suite, env *runner.Env) {
	c := env.Client
	ctx := context.Background()

	owner, status, raw := registerWS(c, "rev-owner@example.com", "revpass1hunter", "Rev Owner")
	if !s.Status("register rev owner", status, 201, raw) {
		return
	}

	var proj struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects",
		map[string]string{
			"name":         "Revisions project",
			"workspace_id": owner.DefaultWorkspace.ID,
		}, owner.AccessToken, &proj)
	if !s.Status("create rev project", status, 201, raw) {
		return
	}
	pid := proj.ID

	// --- Create a JSCAD file with seed content. ---
	type fileResp struct {
		ID   string `json:"id"`
		Kind string `json:"kind"`
	}
	var f fileResp
	// Build a ~30KB JSCAD-flavoured seed. Real CAD source files run
	// 10-200 KB, so the compression assertion below mirrors production.
	var sb strings.Builder
	sb.WriteString("// kerf revision-test seed\n")
	for i := 0; i < 600; i++ {
		fmt.Fprintf(&sb, "const v%04d = vec3(%d, %d, %d); // node %d\n",
			i, i*7%53, i*13%89, i*31%41, i)
	}
	seed := sb.String()
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{"name": "shape.jscad", "kind": "file", "content": seed},
		owner.AccessToken, &f)
	if !s.Status("create shape.jscad", status, 201, raw) {
		return
	}
	s.NotEmpty("file.id", f.ID)

	// --- Write 5 progressively-modified revisions via PATCH. ---
	contents := []string{seed}
	for i := 1; i <= 5; i++ {
		body := fmt.Sprintf("%s// edit %d\nconst x = %d;\n", seed, i, i)
		contents = append(contents, body)
		status, raw, _ = c.Do("PATCH", "/api/projects/"+pid+"/files/"+f.ID,
			map[string]string{"content": body}, owner.AccessToken)
		s.Status(fmt.Sprintf("patch shape #%d", i), status, 200, raw)
	}

	// --- DB inspection: 6 revision rows (1 create + 5 patches). ---
	var revCount int
	if err := env.Pool.QueryRow(ctx,
		`select count(*) from file_revisions where file_id = $1`, f.ID).Scan(&revCount); s.NoError("count revs", err) {
		s.Equal("revision count after 5 edits", revCount, 6)
	}

	// First row is kind='base'.
	var firstKind string
	if err := env.Pool.QueryRow(ctx, `
		select kind from file_revisions
		 where file_id = $1
		 order by created_at asc
		 limit 1
	`, f.ID).Scan(&firstKind); s.NoError("first kind lookup", err) {
		s.Equal("first revision kind=base", firstKind, "base")
	}

	// Trailing rows after the first are kind='diff' (DiffsPerBase is
	// well above 5, so all four follow-on rows are diffs).
	var diffCount int
	if err := env.Pool.QueryRow(ctx, `
		select count(*) from file_revisions
		 where file_id = $1 and kind = 'diff'
	`, f.ID).Scan(&diffCount); s.NoError("count diff rows", err) {
		s.Equal("5 diff rows after first base", diffCount, 5)
	}

	// content_gz is non-NULL on every row, content_sha256 is non-NULL
	// on every row, and content_sha256 is exactly 32 bytes.
	var (
		gzNullCount   int
		hashNullCount int
		hashLenWrong  int
	)
	if err := env.Pool.QueryRow(ctx, `
		select count(*) from file_revisions
		 where file_id = $1 and content_gz is null
	`, f.ID).Scan(&gzNullCount); s.NoError("count null gz", err) {
		s.Equal("no NULL content_gz rows", gzNullCount, 0)
	}
	if err := env.Pool.QueryRow(ctx, `
		select count(*) from file_revisions
		 where file_id = $1 and content_sha256 is null
	`, f.ID).Scan(&hashNullCount); s.NoError("count null sha", err) {
		s.Equal("no NULL content_sha256 rows", hashNullCount, 0)
	}
	if err := env.Pool.QueryRow(ctx, `
		select count(*) from file_revisions
		 where file_id = $1 and octet_length(content_sha256) <> 32
	`, f.ID).Scan(&hashLenWrong); s.NoError("count wrong-len sha", err) {
		s.Equal("all content_sha256 are 32 bytes", hashLenWrong, 0)
	}

	// --- List revisions via the API; verify newest-first ordering. ---
	type apiRev struct {
		ID             string  `json:"id"`
		Source         string  `json:"source"`
		ContentPreview *string `json:"content_preview"`
	}
	var listed []apiRev
	status, raw, _ = c.DoJSON("GET",
		"/api/projects/"+pid+"/files/"+f.ID+"/revisions?limit=50",
		nil, owner.AccessToken, &listed)
	if s.Status("GET /revisions", status, 200, raw) {
		s.Equal("listed 6 revisions", len(listed), 6)
	}

	// --- Reconstruct each revision via GET single + verify content matches
	// what we wrote. The list is newest-first, so listed[i] corresponds
	// to contents[len-1-i]. ---
	type apiRevFull struct {
		ID      string  `json:"id"`
		Content *string `json:"content"`
	}
	for i, lr := range listed {
		var got apiRevFull
		status, raw, _ = c.DoJSON("GET",
			"/api/projects/"+pid+"/files/"+f.ID+"/revisions/"+lr.ID,
			nil, owner.AccessToken, &got)
		if !s.Status(fmt.Sprintf("GET revision %d", i), status, 200, raw) {
			continue
		}
		if !s.True(fmt.Sprintf("revision %d has content", i), got.Content != nil, "") {
			continue
		}
		want := contents[len(contents)-1-i]
		s.Equal(fmt.Sprintf("revision %d content matches", i), *got.Content, want)
	}

	// --- Hash check: pick the oldest revision (deepest in the chain
	// once we've forced extra writes below) and confirm the
	// reconstructed text really hashes to content_sha256. ---
	var (
		oldestID   string
		oldestHash []byte
	)
	if err := env.Pool.QueryRow(ctx, `
		select id, content_sha256 from file_revisions
		 where file_id = $1
		 order by created_at asc
		 limit 1
	`, f.ID).Scan(&oldestID, &oldestHash); s.NoError("load oldest hash", err) {
		s.Equal("oldest hash is 32 bytes", len(oldestHash), 32)
	}
	if oldestID != "" {
		got, err := tools.ReconstructRevision(ctx, env.Pool, oldestID)
		if s.NoError("reconstruct oldest", err) {
			h := sha256.Sum256([]byte(got))
			s.True("recomputed hash matches stored",
				bytes.Equal(h[:], oldestHash),
				"hash mismatch on oldest rev")
			s.Equal("oldest rev content matches seed", got, contents[0])
		}
	}

	// --- Force a new base via DiffsPerBase+1 consecutive edits. ---
	// One small change per iteration so each lands as a diff until the
	// chain hits DiffsPerBase, at which point the next write becomes a
	// fresh kind='base' snapshot.
	for i := 0; i < tools.DiffsPerBase+1; i++ {
		body := fmt.Sprintf("%s// burst %d\n", seed, i)
		status, raw, _ = c.Do("PATCH", "/api/projects/"+pid+"/files/"+f.ID,
			map[string]string{"content": body}, owner.AccessToken)
		if !s.Status(fmt.Sprintf("patch burst #%d", i), status, 200, raw) {
			return
		}
	}

	// At least 2 base rows exist now: the original + the forced one.
	var baseCount int
	if err := env.Pool.QueryRow(ctx, `
		select count(*) from file_revisions
		 where file_id = $1 and kind = 'base'
	`, f.ID).Scan(&baseCount); s.NoError("count base rows", err) {
		s.True("burst forced extra base", baseCount >= 2,
			"got base_count=%d, want >=2", baseCount)
	}

	// The most-recent revision must be reconstructable end-to-end via
	// the public single-revision endpoint.
	var newestID string
	if err := env.Pool.QueryRow(ctx, `
		select id from file_revisions
		 where file_id = $1
		 order by created_at desc
		 limit 1
	`, f.ID).Scan(&newestID); s.NoError("load newest id", err) {
		var got apiRevFull
		status, raw, _ = c.DoJSON("GET",
			"/api/projects/"+pid+"/files/"+f.ID+"/revisions/"+newestID,
			nil, owner.AccessToken, &got)
		if s.Status("GET newest revision", status, 200, raw) {
			expected := fmt.Sprintf("%s// burst %d\n", seed, tools.DiffsPerBase)
			if got.Content != nil {
				s.Equal("newest content matches", *got.Content, expected)
			}
		}
	}

	// --- Restore an early revision and confirm the file content snaps
	// back to what we originally wrote at that point. We pick the
	// revision corresponding to contents[3] ("// edit 3"). ---
	var targetID string
	target := contents[3]
	if err := env.Pool.QueryRow(ctx, `
		select fr.id from file_revisions fr
		 where fr.file_id = $1
		 order by fr.created_at asc
		 offset 3 limit 1
	`, f.ID).Scan(&targetID); s.NoError("locate target rev", err) {
		s.NotEmpty("target rev id", targetID)
	}
	if targetID != "" {
		// First reconstruct via the helper to confirm the chain still
		// produces the right content even after the burst forced a new
		// base in between.
		got, err := tools.ReconstructRevision(ctx, env.Pool, targetID)
		if s.NoError("reconstruct target", err) {
			s.Equal("reconstructed target == contents[3]", got, target)
		}

		// Now restore via the public API.
		var restoredFile struct {
			ID      string `json:"id"`
			Content string `json:"content"`
		}
		status, raw, _ = c.DoJSON("POST",
			"/api/projects/"+pid+"/files/"+f.ID+"/restore/"+targetID,
			nil, owner.AccessToken, &restoredFile)
		if s.Status("POST restore target", status, 200, raw) {
			s.Equal("restored file content == contents[3]", restoredFile.Content, target)
		}

		// The restore itself records a new revision row sourced 'restore'.
		var restoreSrc string
		if err := env.Pool.QueryRow(ctx, `
			select source from file_revisions
			 where file_id = $1
			 order by created_at desc
			 limit 1
		`, f.ID).Scan(&restoreSrc); s.NoError("read latest src", err) {
			s.Equal("latest revision source=restore", restoreSrc, "restore")
		}
	}

	// --- Compression sanity: total stored compressed bytes for this
	// file should be a tiny fraction of the cumulative plaintext we'd
	// have written without diffs. We assert at least 5× shrink versus
	// "naive plaintext per-rev sum"; the actual ratio is much higher
	// (~50×+ on typical text), but we keep the bar low so noisy
	// content patterns don't false-fail. ---
	var (
		totalGz    int
		totalPlain int
	)
	if err := env.Pool.QueryRow(ctx, `
		select coalesce(sum(octet_length(content_gz)), 0) from file_revisions
		 where file_id = $1
	`, f.ID).Scan(&totalGz); !s.NoError("sum gz bytes", err) {
		return
	}
	// Simulate plaintext-per-rev sum: sum of plaintext lengths for each
	// revision, recovered by reconstructing each row.
	rows, err := env.Pool.Query(ctx, `
		select id from file_revisions where file_id = $1 order by created_at asc
	`, f.ID)
	if !s.NoError("scan rev ids", err) {
		return
	}
	defer rows.Close()
	var ids []string
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			s.Fail("scan id", err.Error())
			return
		}
		ids = append(ids, id)
	}
	for _, id := range ids {
		txt, err := tools.ReconstructRevision(ctx, env.Pool, id)
		if !s.NoError("reconstruct "+id, err) {
			return
		}
		totalPlain += len(txt)
	}
	if totalPlain > 0 && totalGz > 0 {
		ratio := float64(totalPlain) / float64(totalGz)
		s.True("compressed total < plaintext / 5", ratio >= 5.0,
			"plain=%d gz=%d ratio=%.2fx", totalPlain, totalGz, ratio)
	}
}
