package scenarios

// add_probe / remove_probe / rename_probe LLM tools — exercises the
// SPICE-probe splice path end-to-end.
//
// The schematic Probe button (shipped earlier) and the LLM tools all write
// the same `// @kerf-probe NAME=… KIND=V|I PORT=…` source-comment line into
// `.circuit.tsx`. The tool side ports `appendProbe`, `removeProbe`, and
// `renameProbe` from src/lib/circuitTSX.js to Go (see `spliceProbeComment`,
// `removeProbeComment`, `renameProbeComment` in
// backend/internal/tools/circuit_tools.go). This scenario asserts:
//
//   - Valid V probe → 200, comment line appears in source.
//   - Valid I probe → 200, comment line appears with KIND=I.
//   - Bad name (spaces) → BAD_ARGS.
//   - Bad kind ("X") → BAD_ARGS.
//   - Wrong file kind (sketch) → BAD_ARGS.
//   - Bogus file id → NOT_FOUND.
//   - remove_probe excises the matching @kerf-probe line.
//   - remove_probe of an already-absent probe is a 200 no-op.
//   - rename_probe rewrites the NAME field, preserving KIND/PORT.
//   - rename_probe of a missing probe is a 200 no-op.
//   - remove/rename_probe with bad name regex → BAD_ARGS.
//   - rename_probe with old==new → BAD_ARGS.

import (
	"context"
	"strings"

	"github.com/google/uuid"

	"github.com/imranp/kerf/backend/cmd/test/runner"
	"github.com/imranp/kerf/backend/internal/tools"
)

// ProbeTool drives the add_probe LLM tool end-to-end.
func ProbeTool(s *runner.Suite, env *runner.Env) {
	c := env.Client
	ctx := context.Background()

	owner, status, raw := registerWS(c, "probe-owner@example.com", "probepass1", "Probe Owner")
	if !s.Status("register probe owner", status, 201, raw) {
		return
	}
	if !s.True("probe owner default_workspace present", owner.DefaultWorkspace != nil,
		"expected default_workspace on register response") {
		return
	}
	var proj struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects",
		map[string]string{
			"name":         "Probe project",
			"workspace_id": owner.DefaultWorkspace.ID,
		}, owner.AccessToken, &proj)
	if !s.Status("create probe project", status, 201, raw) {
		return
	}
	pid := proj.ID
	pc := tools.ProjectCtx{
		Pool:      env.Pool,
		ProjectID: uuid.MustParse(pid),
		UserID:    uuid.MustParse(owner.User.ID),
		Role:      "owner",
	}

	// --- Seed a .circuit.tsx file with a sample <board>…</board> body. ---
	co := runTool(s, ctx, pc, "create_circuit", map[string]any{
		"path":      "/electronics/probe-board",
		"width_mm":  20,
		"height_mm": 20,
	})
	circuitID, _ := co["id"].(string)
	if !s.NotEmpty("create_circuit id", circuitID) {
		return
	}

	// --- 1. Valid V probe → 200, comment with KIND=V appears. ---
	vOut := runTool(s, ctx, pc, "add_probe", map[string]any{
		"circuit_file_id": circuitID,
		"name":            "VOUT",
		"kind":            "V",
		"target_id":       "src_port_xyz",
	})
	if _, isErr := vOut["code"]; isErr {
		s.Fail("add_probe V valid",
			"expected success, got code="+asString(vOut["code"])+
				" error="+asString(vOut["error"]))
	} else {
		s.True("add_probe V ok flag", vOut["ok"] == true)
		s.Equal("add_probe V echoes name", vOut["name"], "VOUT")
	}
	var contentAfterV string
	if err := env.Pool.QueryRow(ctx,
		`select content from files where id = $1`, circuitID).Scan(&contentAfterV); s.NoError("read circuit after V probe", err) {
		s.Contains("V probe comment in source",
			contentAfterV, "// @kerf-probe NAME=VOUT KIND=V PORT=src_port_xyz")
		s.True("V probe inserted before </board>",
			strings.Index(contentAfterV, "// @kerf-probe NAME=VOUT") <
				strings.LastIndex(contentAfterV, "</board>"),
			"comment must precede the closing </board>")
	}

	// --- 2. Valid I probe → 200, comment with KIND=I appears. ---
	iOut := runTool(s, ctx, pc, "add_probe", map[string]any{
		"circuit_file_id": circuitID,
		"name":            "IR1",
		"kind":            "I",
		"target_id":       "R1",
	})
	if _, isErr := iOut["code"]; isErr {
		s.Fail("add_probe I valid",
			"expected success, got code="+asString(iOut["code"])+
				" error="+asString(iOut["error"]))
	} else {
		s.Equal("add_probe I echoes kind", iOut["kind"], "I")
	}
	var contentAfterI string
	if err := env.Pool.QueryRow(ctx,
		`select content from files where id = $1`, circuitID).Scan(&contentAfterI); s.NoError("read circuit after I probe", err) {
		s.Contains("I probe comment in source",
			contentAfterI, "// @kerf-probe NAME=IR1 KIND=I PORT=R1")
		// V probe still present after a second splice (idempotent — V is preserved).
		s.Contains("V probe still present after I splice",
			contentAfterI, "NAME=VOUT KIND=V")
	}

	// --- 3. Bad name (spaces) → BAD_ARGS. ---
	badName := runTool(s, ctx, pc, "add_probe", map[string]any{
		"circuit_file_id": circuitID,
		"name":            "bad name",
		"kind":            "V",
		"target_id":       "src_port_xyz",
	})
	s.Equal("add_probe bad name → BAD_ARGS", badName["code"], "BAD_ARGS")

	// --- 4. Bad kind 'X' → BAD_ARGS. ---
	badKind := runTool(s, ctx, pc, "add_probe", map[string]any{
		"circuit_file_id": circuitID,
		"name":            "PX",
		"kind":            "X",
		"target_id":       "src_port_xyz",
	})
	s.Equal("add_probe bad kind → BAD_ARGS", badKind["code"], "BAD_ARGS")

	// --- 5. Wrong file kind (sketch) → BAD_ARGS. ---
	var sketchRow struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{
			"name":    "not-a-circuit.sketch",
			"kind":    "sketch",
			"content": `{"entities":[]}`,
		}, owner.AccessToken, &sketchRow)
	if !s.Status("create wrong-kind sketch via API", status, 201, raw) {
		return
	}
	wrongKind := runTool(s, ctx, pc, "add_probe", map[string]any{
		"circuit_file_id": sketchRow.ID,
		"name":            "PSKETCH",
		"kind":            "V",
		"target_id":       "anything",
	})
	s.Equal("add_probe on sketch kind → BAD_ARGS", wrongKind["code"], "BAD_ARGS")

	// --- 6. Bogus file id (well-formed UUID, not present) → NOT_FOUND. ---
	bogus := runTool(s, ctx, pc, "add_probe", map[string]any{
		"circuit_file_id": "00000000-0000-0000-0000-000000000000",
		"name":            "PGHOST",
		"kind":            "V",
		"target_id":       "anything",
	})
	s.Equal("add_probe missing file → NOT_FOUND", bogus["code"], "NOT_FOUND")

	// --- 7. Malformed UUID also rejected as BAD_ARGS. ---
	badUUID := runTool(s, ctx, pc, "add_probe", map[string]any{
		"circuit_file_id": "not-a-uuid",
		"name":            "PBAD",
		"kind":            "V",
		"target_id":       "anything",
	})
	s.Equal("add_probe malformed uuid → BAD_ARGS", badUUID["code"], "BAD_ARGS")

	// --- 8. remove_probe excises the matching @kerf-probe NAME=VOUT line. ---
	rmOut := runTool(s, ctx, pc, "remove_probe", map[string]any{
		"circuit_file_id": circuitID,
		"name":            "VOUT",
	})
	if _, isErr := rmOut["code"]; isErr {
		s.Fail("remove_probe VOUT",
			"expected success, got code="+asString(rmOut["code"])+
				" error="+asString(rmOut["error"]))
	} else {
		s.True("remove_probe removed flag", rmOut["removed"] == true)
	}
	var contentAfterRm string
	if err := env.Pool.QueryRow(ctx,
		`select content from files where id = $1`, circuitID).Scan(&contentAfterRm); s.NoError("read circuit after remove", err) {
		s.True("VOUT probe line gone from source",
			!strings.Contains(contentAfterRm, "NAME=VOUT"),
			"expected the @kerf-probe NAME=VOUT line to be excised")
		// I probe (IR1) untouched.
		s.Contains("IR1 probe still present after VOUT removal",
			contentAfterRm, "NAME=IR1 KIND=I")
	}

	// --- 9. Re-add VOUT so we can rename it next. ---
	readd := runTool(s, ctx, pc, "add_probe", map[string]any{
		"circuit_file_id": circuitID,
		"name":            "VOUT",
		"kind":            "V",
		"target_id":       "src_port_xyz",
	})
	s.True("re-add VOUT ok", readd["ok"] == true)

	// --- 10. rename_probe VOUT → VRESULT rewrites NAME, preserves KIND/PORT. ---
	rnOut := runTool(s, ctx, pc, "rename_probe", map[string]any{
		"circuit_file_id": circuitID,
		"old_name":        "VOUT",
		"new_name":        "VRESULT",
	})
	if _, isErr := rnOut["code"]; isErr {
		s.Fail("rename_probe VOUT→VRESULT",
			"expected success, got code="+asString(rnOut["code"])+
				" error="+asString(rnOut["error"]))
	} else {
		s.True("rename_probe renamed flag", rnOut["renamed"] == true)
	}
	var contentAfterRename string
	if err := env.Pool.QueryRow(ctx,
		`select content from files where id = $1`, circuitID).Scan(&contentAfterRename); s.NoError("read circuit after rename", err) {
		s.Contains("VRESULT probe line in source",
			contentAfterRename, "NAME=VRESULT KIND=V PORT=src_port_xyz")
		s.True("VOUT name absent after rename",
			!strings.Contains(contentAfterRename, "NAME=VOUT"),
			"expected old NAME=VOUT to be gone")
	}

	// --- 11. remove_probe with bad name regex → BAD_ARGS. ---
	rmBad := runTool(s, ctx, pc, "remove_probe", map[string]any{
		"circuit_file_id": circuitID,
		"name":            "bad name",
	})
	s.Equal("remove_probe bad name → BAD_ARGS", rmBad["code"], "BAD_ARGS")

	// --- 12. remove_probe of nonexistent probe → 200 (no-op succeeds). ---
	rmNoop := runTool(s, ctx, pc, "remove_probe", map[string]any{
		"circuit_file_id": circuitID,
		"name":            "GHOST",
	})
	if _, isErr := rmNoop["code"]; isErr {
		s.Fail("remove_probe missing → expected 200",
			"got code="+asString(rmNoop["code"])+" error="+asString(rmNoop["error"]))
	} else {
		s.True("remove_probe missing removed=false", rmNoop["removed"] == false)
	}

	// --- 13. rename_probe with old==new → BAD_ARGS. ---
	rnSame := runTool(s, ctx, pc, "rename_probe", map[string]any{
		"circuit_file_id": circuitID,
		"old_name":        "VRESULT",
		"new_name":        "VRESULT",
	})
	s.Equal("rename_probe old==new → BAD_ARGS", rnSame["code"], "BAD_ARGS")

	// --- 14. rename_probe of nonexistent probe → 200 (no-op). ---
	rnNoop := runTool(s, ctx, pc, "rename_probe", map[string]any{
		"circuit_file_id": circuitID,
		"old_name":        "GHOST",
		"new_name":        "GHOST2",
	})
	if _, isErr := rnNoop["code"]; isErr {
		s.Fail("rename_probe missing → expected 200",
			"got code="+asString(rnNoop["code"])+" error="+asString(rnNoop["error"]))
	} else {
		s.True("rename_probe missing renamed=false", rnNoop["renamed"] == false)
	}

	// --- 15. rename_probe with bad new_name → BAD_ARGS. ---
	rnBadNew := runTool(s, ctx, pc, "rename_probe", map[string]any{
		"circuit_file_id": circuitID,
		"old_name":        "VRESULT",
		"new_name":        "bad name",
	})
	s.Equal("rename_probe bad new_name → BAD_ARGS", rnBadNew["code"], "BAD_ARGS")
}
