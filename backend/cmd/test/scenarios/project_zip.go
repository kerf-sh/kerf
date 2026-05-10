package scenarios

// project_zip exercises the GET /api/projects/:pid/export and
// POST /api/projects/import roundtrip.
//
// Coverage:
//   - export returns 200, a Content-Disposition attachment header, and a
//     valid zip payload that contains manifest.json + files/<path>
//   - import (re-uploading the same zip) creates a new project and
//     materializes the same files (count, kinds, content)
//   - manifest path traversal is rejected (../etc/passwd)
//   - duplicate manifest paths are rejected

import (
	"archive/zip"
	"bytes"
	"encoding/json"
	"io"
	"mime/multipart"
	"net/http"
	"net/textproto"
	"strings"

	"github.com/imranp/kerf/backend/cmd/test/runner"
)

// ProjectZip is the scenario entry point registered in cmd/test/main.go.
func ProjectZip(s *runner.Suite, env *runner.Env) {
	c := env.Client

	owner, status, raw := register(c, "zip-owner@example.com", "ziphunter22pw", "Zip Owner")
	if !s.Status("register owner", status, 201, raw) {
		return
	}
	if owner.DefaultWorkspace == nil {
		s.Fail("owner.default_workspace", "register did not return a default workspace")
		return
	}
	wsID := owner.DefaultWorkspace.ID

	// --- Create a project with a couple of text-bearing files. ----------
	var proj struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects", map[string]any{
		"name":         "Zip Source",
		"description":  "fixture for zip export/import scenario",
		"workspace_id": wsID,
		"tags":         []string{"mechanical"},
		"starter":      "blank",
	}, owner.AccessToken, &proj)
	if !s.Status("create source project", status, 201, raw) {
		return
	}

	// Three files, three different kinds.
	type createdFile struct {
		ID      string `json:"id"`
		Name    string `json:"name"`
		Kind    string `json:"kind"`
		Content string `json:"content"`
	}
	mkFile := func(name, kind, content string) createdFile {
		var got createdFile
		st, body, _ := c.DoJSON("POST", "/api/projects/"+proj.ID+"/files",
			map[string]any{
				"name":    name,
				"kind":    kind,
				"content": content,
			}, owner.AccessToken, &got)
		if !s.Status("create "+name, st, 201, body) {
			return createdFile{}
		}
		return got
	}
	f1 := mkFile("design.jscad", "file", "// jscad source\nexport default () => {}\n")
	f2 := mkFile("profile.sketch", "sketch", `{"version":1,"entities":[]}`)
	f3 := mkFile("params.equations", "equations", `{"version":1,"params":[{"name":"h","expr":"10"}]}`)
	if f1.ID == "" || f2.ID == "" || f3.ID == "" {
		return
	}

	// --- GET /api/projects/:pid/export → 200 + valid zip. ---------------
	req, _ := http.NewRequest("GET", c.BaseURL+"/api/projects/"+proj.ID+"/export", nil)
	req.Header.Set("Authorization", "Bearer "+owner.AccessToken)
	resp, err := c.HTTP.Do(req)
	if !s.NoError("export request", err) {
		return
	}
	zipBytes, _ := io.ReadAll(resp.Body)
	resp.Body.Close()
	if !s.Status("export status", resp.StatusCode, 200, zipBytes) {
		return
	}
	cd := resp.Header.Get("Content-Disposition")
	s.True("export Content-Disposition is attachment",
		strings.HasPrefix(cd, "attachment;"),
		"got %q", cd)
	s.True("export body looks like zip",
		len(zipBytes) > 4 && string(zipBytes[:2]) == "PK",
		"first bytes: %q", string(zipBytes[:min(4, len(zipBytes))]))

	zr, err := zip.NewReader(bytes.NewReader(zipBytes), int64(len(zipBytes)))
	if !s.NoError("zip parses", err) {
		return
	}
	zipNames := map[string]bool{}
	for _, e := range zr.File {
		zipNames[e.Name] = true
	}
	s.True("zip has manifest.json", zipNames["manifest.json"], "names: %v", zipNames)
	s.True("zip has files/design.jscad", zipNames["files/design.jscad"], "")
	s.True("zip has files/profile.sketch", zipNames["files/profile.sketch"], "")
	s.True("zip has files/params.equations", zipNames["files/params.equations"], "")

	// Parse manifest to confirm shape.
	manBytes := readZipMember(zr, "manifest.json")
	var man struct {
		Version int      `json:"version"`
		Name    string   `json:"name"`
		Tags    []string `json:"tags"`
		Files   []struct {
			Path    string  `json:"path"`
			Kind    string  `json:"kind"`
			Content *string `json:"content,omitempty"`
		} `json:"files"`
	}
	if !s.NoError("manifest unmarshal", json.Unmarshal(manBytes, &man)) {
		return
	}
	s.Equal("manifest version", man.Version, 1)
	s.Equal("manifest name", man.Name, "Zip Source")
	s.Equal("manifest file count", len(man.Files), 3)

	// --- POST /api/projects/import → 201 + new project. -----------------
	importedID := postImport(s, c, owner.AccessToken, wsID, zipBytes)
	if importedID == "" {
		return
	}
	s.True("imported project id differs", importedID != proj.ID,
		"got identical id %s", importedID)

	// New project's files must match (count, kinds, content).
	var newFiles []struct {
		ID      string `json:"id"`
		Name    string `json:"name"`
		Kind    string `json:"kind"`
		Content string `json:"content"`
	}
	st, body, _ := c.DoJSON("GET", "/api/projects/"+importedID+"/files", nil,
		owner.AccessToken, &newFiles)
	if !s.Status("list imported files", st, 200, body) {
		return
	}
	s.Equal("imported file count", len(newFiles), 3)

	// Compare per-file: fetch each from imported project and assert
	// content round-trip.
	wantByName := map[string]createdFile{
		f1.Name: f1, f2.Name: f2, f3.Name: f3,
	}
	for _, nf := range newFiles {
		want, ok := wantByName[nf.Name]
		if !ok {
			s.Fail("imported file unexpected", "name="+nf.Name)
			continue
		}
		s.Equal("imported "+nf.Name+".kind", nf.Kind, want.Kind)
		// Need a content read — the list endpoint omits it.
		var full struct {
			Content string `json:"content"`
		}
		st2, body2, _ := c.DoJSON("GET",
			"/api/projects/"+importedID+"/files/"+nf.ID, nil,
			owner.AccessToken, &full)
		if s.Status("get imported "+nf.Name, st2, 200, body2) {
			s.Equal("imported "+nf.Name+".content", full.Content, want.Content)
		}
	}

	// --- Reject path traversal. -----------------------------------------
	traverseZip := buildMaliciousZip(s, "../etc/passwd", "file")
	if traverseZip != nil {
		st, body := postImportRaw(c, owner.AccessToken, wsID, traverseZip)
		s.Status("traversal path → 400", st, 400, body)
	}

	// --- Reject duplicate manifest paths. -------------------------------
	dupZip := buildDuplicatePathZip(s)
	if dupZip != nil {
		st, body := postImportRaw(c, owner.AccessToken, wsID, dupZip)
		s.Status("duplicate path → 400", st, 400, body)
	}
}

// readZipMember extracts the bytes of one zip entry by name. Returns nil
// if the member is missing or unreadable; tests should already have
// asserted presence first.
func readZipMember(zr *zip.Reader, name string) []byte {
	for _, e := range zr.File {
		if e.Name != name {
			continue
		}
		rc, err := e.Open()
		if err != nil {
			return nil
		}
		defer rc.Close()
		buf, _ := io.ReadAll(rc)
		return buf
	}
	return nil
}

// postImport uploads zipBytes to /api/projects/import and asserts a 201,
// returning the new project id (empty on failure).
func postImport(s *runner.Suite, c *runner.Client, token, wsID string, zipBytes []byte) string {
	st, body := postImportRaw(c, token, wsID, zipBytes)
	if !s.Status("import status", st, 201, body) {
		return ""
	}
	var created struct {
		ID string `json:"id"`
	}
	if err := json.Unmarshal(body, &created); err != nil {
		s.Fail("import response decode", err.Error())
		return ""
	}
	s.NotEmpty("import.id", created.ID)
	return created.ID
}

// postImportRaw issues the multipart POST and returns (status, body).
func postImportRaw(c *runner.Client, token, wsID string, zipBytes []byte) (int, []byte) {
	body := &bytes.Buffer{}
	mw := multipart.NewWriter(body)
	hdr := textproto.MIMEHeader{}
	hdr.Set("Content-Disposition", `form-data; name="file"; filename="project.zip"`)
	hdr.Set("Content-Type", "application/zip")
	pw, _ := mw.CreatePart(hdr)
	_, _ = pw.Write(zipBytes)
	mw.Close()

	req, _ := http.NewRequest("POST",
		c.BaseURL+"/api/projects/import?workspace_id="+wsID, body)
	req.Header.Set("Content-Type", mw.FormDataContentType())
	req.Header.Set("Authorization", "Bearer "+token)
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return 0, []byte(err.Error())
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	return resp.StatusCode, raw
}

// buildMaliciousZip emits a minimal zip whose manifest.json names a
// traversal path. Used by the path-traversal rejection assertion.
func buildMaliciousZip(s *runner.Suite, badPath, kind string) []byte {
	manifest := map[string]any{
		"version":     1,
		"name":        "Bad",
		"description": "",
		"tags":        []string{},
		"created_at":  "2026-01-01T00:00:00Z",
		"files": []map[string]any{
			{"path": badPath, "kind": kind, "content": "owned"},
		},
	}
	manBytes, err := json.Marshal(manifest)
	if !s.NoError("malicious manifest marshal", err) {
		return nil
	}
	var buf bytes.Buffer
	zw := zip.NewWriter(&buf)
	w, _ := zw.Create("manifest.json")
	_, _ = w.Write(manBytes)
	zw.Close()
	return buf.Bytes()
}

// buildDuplicatePathZip produces a manifest with two entries at the same
// path. Used by the duplicate-path rejection assertion.
func buildDuplicatePathZip(s *runner.Suite) []byte {
	manifest := map[string]any{
		"version":     1,
		"name":        "Dup",
		"description": "",
		"tags":        []string{},
		"created_at":  "2026-01-01T00:00:00Z",
		"files": []map[string]any{
			{"path": "a.txt", "kind": "file", "content": "one"},
			{"path": "a.txt", "kind": "file", "content": "two"},
		},
	}
	manBytes, err := json.Marshal(manifest)
	if !s.NoError("duplicate manifest marshal", err) {
		return nil
	}
	var buf bytes.Buffer
	zw := zip.NewWriter(&buf)
	w, _ := zw.Create("manifest.json")
	_, _ = w.Write(manBytes)
	// Need at least one files/ entry to satisfy our expectation, but
	// even without it the duplicate-path check fires earlier.
	zw.Close()
	return buf.Bytes()
}

// min keeps the file dependency-free against Go versions that ship
// builtin min — duplicates the polyfill used in a few other scenarios.
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
