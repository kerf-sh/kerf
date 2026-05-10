package scenarios

// Materials scenario — exercises the `.material` file kind end-to-end:
//   - kind='material' is accepted by POST /files (added in
//     1746577700000_kind_material migration + the handlers.CreateFile
//     validator).
//   - kind='not-a-real-kind' is rejected (validator regression).
//   - GET round-trips the JSON content verbatim.
//   - The LLM `read_material` tool returns the parsed JSON shape with
//     mechanical / thermal / physical groups.
//   - The LLM `find_material_by_name` tool fuzzy-matches by name + by
//     common_names, ranking exact hits first.
//   - The LLM `set_part_material` tool attaches a material_path to a
//     `.part` file's JSON; a follow-up GET reflects the change.
//   - set_part_material rejects a non-existent material path.
//
// Mirrors the user-facing flow: material files live in the standard
// files table with no special server-side validation of the JSON shape
// (the contract is "the editor + consumers read it"). The kind validator
// and the LLM tools are the only pieces of server logic specific to
// materials.

import (
	"context"
	"encoding/json"
	"strings"

	"github.com/google/uuid"

	"github.com/imranp/kerf/backend/cmd/test/runner"
	"github.com/imranp/kerf/backend/internal/tools"
)

// Materials drives the .material file kind. Registered in main.go's
// allScenarios.
func Materials(s *runner.Suite, env *runner.Env) {
	c := env.Client
	ctx := context.Background()

	owner, status, raw := registerWS(c, "materials-owner@example.com", "matpass99hunter", "Materials Owner")
	if !s.Status("register materials owner", status, 201, raw) {
		return
	}
	if !s.True("materials owner default_workspace present", owner.DefaultWorkspace != nil,
		"expected default_workspace on register response") {
		return
	}

	// Create a holding project.
	var proj struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects", map[string]any{
		"workspace_id": owner.DefaultWorkspace.ID,
		"name":         "Materials project",
		"tags":         []string{"mechanical"},
	}, owner.AccessToken, &proj)
	if !s.Status("create materials project", status, 201, raw) {
		return
	}
	pid := proj.ID

	pc := tools.ProjectCtx{
		Pool:      env.Pool,
		ProjectID: uuid.MustParse(pid),
		UserID:    uuid.MustParse(owner.User.ID),
		Role:      "owner",
	}

	// --- 1. kind validator: 'material' is accepted ---
	steelJSON := `{
  "version": 1,
  "name": "AISI 1018 Steel",
  "category": "metal/steel/carbon",
  "common_names": ["mild steel", "1018"],
  "color_hex": "#7d8088",
  "mechanical": {
    "E_GPa": 205, "G_GPa": 80, "nu": 0.29,
    "yield_MPa": 370, "ultimate_MPa": 440, "elongation_pct": 15
  },
  "thermal": {
    "alpha_per_K": 1.17e-5, "k_W_mK": 51.9, "cp_J_kgK": 486,
    "T_min_C": -40, "T_max_C": 250
  },
  "physical": { "rho_kg_m3": 7870 },
  "callout": "AISI 1018",
  "notes": "Test fixture."
}`
	var steelRow struct {
		ID   string `json:"id"`
		Kind string `json:"kind"`
		Name string `json:"name"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{
			"name":      "aisi-1018.material",
			"kind":      "material",
			"parent_id": nil,
			"content":   steelJSON,
		}, owner.AccessToken, &steelRow)
	if !s.Status("create material file", status, 201, raw) {
		return
	}
	s.Equal("material.kind echoed", steelRow.Kind, "material")
	s.Equal("material.name echoed", steelRow.Name, "aisi-1018.material")
	s.NotEmpty("material.id", steelRow.ID)

	// --- 2. kind validator rejects garbage ---
	var badRow struct {
		ID   string `json:"id"`
		Kind string `json:"kind"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{
			"name":      "wat.junk",
			"kind":      "not-a-real-kind",
			"parent_id": nil,
			"content":   "",
		}, owner.AccessToken, &badRow)
	s.Status("invalid kind rejected", status, 400, raw)

	// --- 3. GET round-trips the JSON content verbatim ---
	var matGet struct {
		Kind    string `json:"kind"`
		Content string `json:"content"`
	}
	status, raw, _ = c.DoJSON("GET", "/api/projects/"+pid+"/files/"+steelRow.ID, nil,
		owner.AccessToken, &matGet)
	if s.Status("get material file", status, 200, raw) {
		s.Equal("material.kind round-trip", matGet.Kind, "material")
		s.Equal("material.content round-trip", matGet.Content, steelJSON)
	}

	// --- 4. read_material LLM tool returns the parsed shape ---
	readOut := runTool(s, ctx, pc, "read_material", map[string]any{
		"path": "/aisi-1018.material",
	})
	s.NotEmpty("read_material path", asString(readOut["path"]))
	s.NotEmpty("read_material id", asString(readOut["id"]))
	mat, _ := readOut["material"].(map[string]any)
	if s.True("read_material has material map", mat != nil,
		"expected material map; got %T", readOut["material"]) {
		s.Equal("read_material name", mat["name"], "AISI 1018 Steel")
		s.Equal("read_material category", mat["category"], "metal/steel/carbon")
		// JSON decodes numbers as float64.
		mech, _ := mat["mechanical"].(map[string]any)
		if s.True("read_material has mechanical group", mech != nil, "missing mechanical") {
			s.Equal("E_GPa", mech["E_GPa"], float64(205))
			s.Equal("nu", mech["nu"], 0.29)
		}
		phys, _ := mat["physical"].(map[string]any)
		if s.True("read_material has physical group", phys != nil, "missing physical") {
			s.Equal("rho_kg_m3", phys["rho_kg_m3"], float64(7870))
		}
	}

	// read_material on a wrong-kind file → BAD_KIND.
	// First, create a non-material file to point at.
	var dummy struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{
			"name": "notes.txt", "kind": "file", "parent_id": nil, "content": "hello",
		}, owner.AccessToken, &dummy)
	if s.Status("create plain-file decoy", status, 201, raw) {
		bad := runTool(s, ctx, pc, "read_material", map[string]any{"path": "/notes.txt"})
		s.Equal("read_material wrong kind → BAD_KIND", bad["code"], "BAD_KIND")
	}

	// read_material on missing path → NOT_FOUND.
	miss := runTool(s, ctx, pc, "read_material", map[string]any{
		"path": "/does-not-exist.material",
	})
	s.Equal("read_material missing → NOT_FOUND", miss["code"], "NOT_FOUND")

	// --- 5. find_material_by_name fuzzy search ---
	// Add a second material so we can test ranking.
	alJSON := `{
  "version": 1,
  "name": "Aluminum 6061-T6",
  "category": "metal/aluminum/wrought",
  "common_names": ["6061", "aircraft aluminum"],
  "mechanical": { "E_GPa": 68.9, "yield_MPa": 276 },
  "thermal":    { "alpha_per_K": 2.36e-5, "k_W_mK": 167 },
  "physical":   { "rho_kg_m3": 2700 }
}`
	var alRow struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{
			"name": "aluminum-6061-t6.material", "kind": "material",
			"parent_id": nil, "content": alJSON,
		}, owner.AccessToken, &alRow)
	s.Status("create al-6061 material", status, 201, raw)

	// Exact-name match → returns the steel.
	findExact := runTool(s, ctx, pc, "find_material_by_name", map[string]any{
		"query": "AISI 1018 Steel",
	})
	matches, _ := findExact["matches"].([]any)
	if s.True("find_material_by_name returned ≥1 match", len(matches) >= 1,
		"got %d matches", len(matches)) {
		first, _ := matches[0].(map[string]any)
		s.Equal("first match is the exact-name steel", first["name"], "AISI 1018 Steel")
		// Score for an exact name match should be the maximum 1000.
		s.Equal("exact-name score", first["score"], float64(1000))
	}

	// Common-name match: "mild steel" → AISI 1018 (in common_names).
	findCommon := runTool(s, ctx, pc, "find_material_by_name", map[string]any{
		"query": "mild steel",
	})
	cm, _ := findCommon["matches"].([]any)
	if s.True("find_material_by_name common-name returned ≥1 match", len(cm) >= 1,
		"got %d matches", len(cm)) {
		first, _ := cm[0].(map[string]any)
		s.Equal("common-name match resolves to steel", first["name"], "AISI 1018 Steel")
	}

	// Substring match: "alum" → 6061.
	findSub := runTool(s, ctx, pc, "find_material_by_name", map[string]any{
		"query": "alum",
	})
	sm, _ := findSub["matches"].([]any)
	if s.True("find_material_by_name substring returned ≥1 match", len(sm) >= 1,
		"got %d matches", len(sm)) {
		first, _ := sm[0].(map[string]any)
		s.Equal("substring match resolves to 6061", first["name"], "Aluminum 6061-T6")
	}

	// Empty / whitespace query → BAD_ARGS.
	bad := runTool(s, ctx, pc, "find_material_by_name", map[string]any{"query": "   "})
	s.Equal("find_material_by_name empty → BAD_ARGS", bad["code"], "BAD_ARGS")

	// --- 6. set_part_material LLM tool ---
	// Create a Part to attach a material to.
	createPart := runTool(s, ctx, pc, "create_part", map[string]any{
		"path": "/library/bracket.part",
		"metadata": map[string]any{
			"name":     "Bracket, M3 mounting",
			"category": "bracket",
			"mpn":      "BRK-M3-AL",
		},
	})
	partID, _ := createPart["id"].(string)
	if !s.NotEmpty("create_part returned id", partID) {
		return
	}

	// Attach the 6061 material.
	setOut := runTool(s, ctx, pc, "set_part_material", map[string]any{
		"part_path":     "/library/bracket.part",
		"material_path": "/aluminum-6061-t6.material",
	})
	if _, isErr := setOut["code"]; isErr {
		s.Fail("set_part_material", "expected success, got code="+asString(setOut["code"])+
			" error="+asString(setOut["error"]))
	} else {
		s.Equal("set_part_material echoes part_path", setOut["part_path"], "/library/bracket.part")
		s.Equal("set_part_material echoes material_path", setOut["material_path"], "/aluminum-6061-t6.material")
		s.Equal("set_part_material cleared=false", setOut["cleared"], false)
	}

	// Confirm the Part file content reflects.
	var partGet struct {
		Content string `json:"content"`
	}
	status, raw, _ = c.DoJSON("GET", "/api/projects/"+pid+"/files/"+partID, nil,
		owner.AccessToken, &partGet)
	if s.Status("get part after set_part_material", status, 200, raw) {
		s.Contains("part content has material_path", partGet.Content, "material_path")
		s.Contains("part content has the material file path", partGet.Content,
			"/aluminum-6061-t6.material")
		// Decoded JSON must still be valid (catches "we wrote garbage" bugs).
		var doc map[string]any
		err := json.Unmarshal([]byte(partGet.Content), &doc)
		s.NoError("part content is still valid JSON", err)
		s.Equal("part doc material_path field", doc["material_path"],
			"/aluminum-6061-t6.material")
		// Existing Part metadata must be preserved.
		s.Equal("part doc still has mpn", doc["mpn"], "BRK-M3-AL")
	}

	// set_part_material with an empty material_path clears the field.
	clearOut := runTool(s, ctx, pc, "set_part_material", map[string]any{
		"part_path":     "/library/bracket.part",
		"material_path": "",
	})
	s.Equal("set_part_material clear → cleared=true", clearOut["cleared"], true)
	status, raw, _ = c.DoJSON("GET", "/api/projects/"+pid+"/files/"+partID, nil,
		owner.AccessToken, &partGet)
	if s.Status("get part after clear", status, 200, raw) {
		s.True("part content no longer has material_path",
			!strings.Contains(partGet.Content, `"material_path"`),
			"expected material_path removed; content=%s", partGet.Content)
	}

	// set_part_material rejects a non-existent material path.
	missMat := runTool(s, ctx, pc, "set_part_material", map[string]any{
		"part_path":     "/library/bracket.part",
		"material_path": "/library/materials/unobtanium.material",
	})
	s.Equal("set_part_material missing material → NOT_FOUND",
		missMat["code"], "NOT_FOUND")

	// set_part_material rejects a non-Part part_path.
	notAPart := runTool(s, ctx, pc, "set_part_material", map[string]any{
		"part_path":     "/aisi-1018.material",
		"material_path": "/aluminum-6061-t6.material",
	})
	s.Equal("set_part_material non-part target → BAD_KIND",
		notAPart["code"], "BAD_KIND")
}
