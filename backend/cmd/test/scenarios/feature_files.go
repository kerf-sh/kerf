package scenarios

// File-kind plumbing scenarios for the consolidated `.feature` and
// `.circuit.tsx` kinds.
//
//   - create_feature scaffolds a kind='feature' file (.feature suffix).
//   - create_circuit scaffolds a kind='circuit' file (.circuit.tsx).
//   - The kind row plumbing accepts both kinds via the API as well.
//
// The dedicated per-operation tools (feature_pad / pocket / fillet, plus
// add_component / connect / set_component_prop) were consolidated away.
// The model now mutates these files via write_file / edit_file directly
// after consulting docs/llm/feature.md and docs/llm/circuit.md.

import (
	"context"
	"encoding/json"
	"strings"

	"github.com/google/uuid"

	"github.com/imranp/kerf/backend/cmd/test/runner"
	"github.com/imranp/kerf/backend/internal/tools"
)

// FeatureFiles drives the feature + circuit kind plumbing.
func FeatureFiles(s *runner.Suite, env *runner.Env) {
	c := env.Client
	ctx := context.Background()

	owner, status, raw := registerWS(c, "feat-owner@example.com", "featpass1", "Feat Owner")
	if !s.Status("register feat owner", status, 201, raw) {
		return
	}
	if !s.True("feat owner default_workspace present", owner.DefaultWorkspace != nil,
		"expected default_workspace on register response") {
		return
	}
	var proj struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects",
		map[string]string{
			"name":         "Feature project",
			"workspace_id": owner.DefaultWorkspace.ID,
		}, owner.AccessToken, &proj)
	if !s.Status("create feat project", status, 201, raw) {
		return
	}
	pid := proj.ID
	pc := tools.ProjectCtx{
		Pool:      env.Pool,
		ProjectID: uuid.MustParse(pid),
		UserID:    uuid.MustParse(owner.User.ID),
		Role:      "owner",
	}

	// --- create_feature: appends .feature, kind='feature'. ---
	out := runTool(s, ctx, pc, "create_feature", map[string]any{
		"path": "/parts/widget.feature",
		"name": "Widget body",
	})
	featID, _ := out["id"].(string)
	if !s.NotEmpty("create_feature id", featID) {
		return
	}
	var kind string
	if err := env.Pool.QueryRow(ctx,
		`select kind from files where id = $1`, featID).Scan(&kind); s.NoError("kind lookup feature", err) {
		s.Equal("feature row kind=feature", kind, "feature")
	}

	// .feature suffix auto-appended.
	out2 := runTool(s, ctx, pc, "create_feature", map[string]any{
		"path": "/parts/auto-suffix",
	})
	pathOut, _ := out2["path"].(string)
	s.True("create_feature auto-suffix .feature",
		strings.HasSuffix(pathOut, ".feature"),
		"path=%q", pathOut)

	// Reserved-extension paths are rejected (.sketch / .assembly / .drawing / .part).
	for _, ext := range []string{".sketch", ".assembly", ".drawing", ".part"} {
		o := runTool(s, ctx, pc, "create_feature", map[string]any{
			"path": "/parts/reserved" + ext,
		})
		s.Equal("create_feature rejects "+ext, o["code"], "BAD_KIND")
	}

	// --- READONLY guards: write_file refuses to CREATE a .feature file
	// (steers to create_feature). create_file with kind='feature' or a
	// .feature suffix is similarly rejected. Editing an EXISTING .feature
	// via write_file IS allowed once the file has been scaffolded. ---
	wfFeat := runTool(s, ctx, pc, "write_file", map[string]any{
		"path":    "/parts/missing.feature",
		"content": "garbage",
	})
	s.Equal("write_file on missing .feature → READONLY_FEATURE",
		wfFeat["code"], "READONLY_FEATURE")
	cfFeat := runTool(s, ctx, pc, "create_file", map[string]any{
		"path": "/parts/foo.feature",
		"kind": "feature",
	})
	s.Equal("create_file kind=feature → READONLY_FEATURE", cfFeat["code"], "READONLY_FEATURE")
	cfFeatSuffix := runTool(s, ctx, pc, "create_file", map[string]any{
		"path": "/parts/bar.feature",
	})
	s.Equal("create_file .feature suffix → READONLY_FEATURE", cfFeatSuffix["code"], "READONLY_FEATURE")

	// --- create_circuit: appends .circuit.tsx, kind='circuit'. ---
	co := runTool(s, ctx, pc, "create_circuit", map[string]any{
		"path":      "/electronics/board",
		"width_mm":  25,
		"height_mm": 25,
	})
	circuitID, _ := co["id"].(string)
	circuitPath, _ := co["path"].(string)
	if !s.NotEmpty("create_circuit id", circuitID) {
		return
	}
	s.True("create_circuit appended .circuit.tsx",
		strings.HasSuffix(circuitPath, ".circuit.tsx"),
		"path=%q", circuitPath)
	if err := env.Pool.QueryRow(ctx,
		`select kind from files where id = $1`, circuitID).Scan(&kind); s.NoError("kind lookup circuit", err) {
		s.Equal("circuit row kind=circuit", kind, "circuit")
	}

	// --- write_file ON .circuit.tsx works (text is canonical TSX, not JSON). ---
	wfCircuit := runTool(s, ctx, pc, "write_file", map[string]any{
		"path":    circuitPath,
		"content": "// hand-edited circuit file\nexport default null\n",
	})
	if _, isErr := wfCircuit["code"]; isErr {
		s.Fail("write_file on .circuit.tsx",
			"expected success, got code="+asString(wfCircuit["code"])+
				" error="+asString(wfCircuit["error"]))
	} else {
		s.True("write_file on .circuit.tsx ok", wfCircuit["bytes"] != nil)
	}
	var content string
	if err := env.Pool.QueryRow(ctx,
		`select content from files where id = $1`, circuitID).Scan(&content); s.NoError("read circuit", err) {
		s.Contains("circuit content has hand-edited marker", content, "hand-edited circuit file")
	}

	// --- The API also accepts these kinds via POST /files (the create_file
	// LLM tool's enum is more restrictive: file|folder|assembly only). ---
	for _, k := range []string{"sketch", "feature", "drawing", "part", "circuit"} {
		var f struct {
			Kind string `json:"kind"`
		}
		status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
			map[string]any{"name": "via-api-" + k, "kind": k},
			owner.AccessToken, &f)
		if s.Status("POST /files kind="+k+" via API", status, 201, raw) {
			s.Equal("API row kind="+k, f.Kind, k)
		}
	}

	// --- "Use in feature" UI workflow: the SketchView toolbar creates a
	// .feature file seeded with a single pad referencing the originating
	// sketch's path. Mirror the createFeatureFromSketch store action with
	// raw API calls and assert the sketch + feature plumbing round-trips. ---
	var sketchRow struct {
		ID   string `json:"id"`
		Kind string `json:"kind"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{
			"name":    "profile.sketch",
			"kind":    "sketch",
			"content": `{"entities":[]}`,
		}, owner.AccessToken, &sketchRow)
	if s.Status("create sketch via API", status, 201, raw) {
		s.Equal("sketch.kind", sketchRow.Kind, "sketch")
		s.NotEmpty("sketch.id", sketchRow.ID)
	}

	featureSeed := `{"features":[{"id":"f1","op":"pad","sketch_path":"/profile.sketch","height":5,"direction":"up"}]}`
	var featRow struct {
		ID   string `json:"id"`
		Kind string `json:"kind"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{
			"name":      "profile.feature",
			"kind":      "feature",
			"parent_id": nil,
			"content":   featureSeed,
		}, owner.AccessToken, &featRow)
	if s.Status("create feature-from-sketch via API", status, 201, raw) {
		s.Equal("feature.kind", featRow.Kind, "feature")
		s.NotEmpty("feature.id", featRow.ID)
	}

	// Round-trip the seeded content via GET /files/:id.
	var featGet struct {
		Kind    string `json:"kind"`
		Content string `json:"content"`
	}
	status, raw, _ = c.DoJSON("GET", "/api/projects/"+pid+"/files/"+featRow.ID, nil,
		owner.AccessToken, &featGet)
	if s.Status("get feature-from-sketch", status, 200, raw) {
		s.Equal("feature.kind round-trip", featGet.Kind, "feature")
		s.Equal("feature.content round-trip", featGet.Content, featureSeed)
	}

	// --- Phase 4a sweep2 (twin-rail sweep) plumbing.
	// Create profile + 2 rail sketches via create_sketch (returns paths),
	// pre-seed a .feature with an explicit sweep2 node, GET round-trip it,
	// then exercise the feature_sweep2 LLM tool which should auto-id its
	// appended node `sweep2-2`. Also verify BAD_ARGS guards. ---
	profileOut := runTool(s, ctx, pc, "create_sketch", map[string]any{
		"path": "/sw2-profile.sketch", "plane": "XY",
	})
	rail1Out := runTool(s, ctx, pc, "create_sketch", map[string]any{
		"path": "/sw2-rail1.sketch", "plane": "XY",
	})
	rail2Out := runTool(s, ctx, pc, "create_sketch", map[string]any{
		"path": "/sw2-rail2.sketch", "plane": "XY",
	})
	profilePath, _ := profileOut["path"].(string)
	rail1Path, _ := rail1Out["path"].(string)
	rail2Path, _ := rail2Out["path"].(string)
	s.NotEmpty("sweep2 profile path", profilePath)
	s.NotEmpty("sweep2 rail1 path", rail1Path)
	s.NotEmpty("sweep2 rail2 path", rail2Path)

	sweep2Seed := `{"version":1,"features":[{"id":"sweep2-1","op":"sweep2","profile_sketch_path":"` + profilePath + `","rail1_sketch_path":"` + rail1Path + `","rail2_sketch_path":"` + rail2Path + `","twist_deg":0,"scale_end":1,"mode":"auto"}]}`
	var sweep2Row struct {
		ID   string `json:"id"`
		Kind string `json:"kind"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{
			"name":    "ringshank.feature",
			"kind":    "feature",
			"content": sweep2Seed,
		}, owner.AccessToken, &sweep2Row)
	s.Status("create sweep2-seeded feature", status, 201, raw)
	s.NotEmpty("sweep2 feature id", sweep2Row.ID)
	s.Equal("sweep2 feature kind", sweep2Row.Kind, "feature")

	// GET round-trips the seeded sweep2 node verbatim.
	var sw2Get struct {
		Content string `json:"content"`
	}
	status, raw, _ = c.DoJSON("GET", "/api/projects/"+pid+"/files/"+sweep2Row.ID, nil,
		owner.AccessToken, &sw2Get)
	if s.Status("get sweep2 feature", status, 200, raw) {
		s.Equal("sweep2 seed round-trip", sw2Get.Content, sweep2Seed)
	}

	// feature_sweep2 LLM tool appends a second sweep2 node — auto-id 'sweep2-2'.
	sw2Out := runTool(s, ctx, pc, "feature_sweep2", map[string]any{
		"file_id":             sweep2Row.ID,
		"profile_sketch_path": profilePath,
		"rail1_sketch_path":   rail1Path,
		"rail2_sketch_path":   rail2Path,
		"twist_deg":           15,
		"scale_end":           0.9,
		"mode":                "frenet",
	})
	s.Equal("feature_sweep2 op", sw2Out["op"], "sweep2")
	s.Equal("feature_sweep2 auto-id sweep2-2", sw2Out["id"], "sweep2-2")

	// Inspect the row payload — must now hold 2 sweep2 nodes with intact fields.
	var sw2Content string
	if err := env.Pool.QueryRow(ctx,
		`select content from files where id = $1`, sweep2Row.ID).Scan(&sw2Content); s.NoError("read sweep2 content", err) {
		var doc map[string]any
		if err := json.Unmarshal([]byte(sw2Content), &doc); s.NoError("decode sweep2 content", err) {
			feats, _ := doc["features"].([]any)
			s.True("sweep2 features len=2", len(feats) == 2, "got %d", len(feats))
			if len(feats) == 2 {
				second, _ := feats[1].(map[string]any)
				s.Equal("sweep2-2 op", second["op"], "sweep2")
				s.Equal("sweep2-2 profile path", second["profile_sketch_path"], profilePath)
				s.Equal("sweep2-2 rail1 path", second["rail1_sketch_path"], rail1Path)
				s.Equal("sweep2-2 rail2 path", second["rail2_sketch_path"], rail2Path)
				s.Equal("sweep2-2 mode", second["mode"], "frenet")
			}
		}
	}

	// BAD_ARGS guards: missing profile_sketch_path.
	missingProfile := runTool(s, ctx, pc, "feature_sweep2", map[string]any{
		"file_id":           sweep2Row.ID,
		"rail1_sketch_path": rail1Path,
		"rail2_sketch_path": rail2Path,
	})
	s.Equal("feature_sweep2 missing profile → BAD_ARGS", missingProfile["code"], "BAD_ARGS")

	// BAD_ARGS guards: missing rail1_sketch_path.
	missingRail1 := runTool(s, ctx, pc, "feature_sweep2", map[string]any{
		"file_id":             sweep2Row.ID,
		"profile_sketch_path": profilePath,
		"rail2_sketch_path":   rail2Path,
	})
	s.Equal("feature_sweep2 missing rail1 → BAD_ARGS", missingRail1["code"], "BAD_ARGS")

	// --- Phase 4a network_srf (NURBS surface fit through a U/V grid) plumbing.
	// Seed 4 sketches (2 U + 2 V), seed a .feature with a network_srf node,
	// GET round-trip it, then exercise the feature_network_srf LLM tool.
	u1Out := runTool(s, ctx, pc, "create_sketch", map[string]any{"path": "/net-u1.sketch", "plane": "XY"})
	u2Out := runTool(s, ctx, pc, "create_sketch", map[string]any{"path": "/net-u2.sketch", "plane": "XY"})
	v1Out := runTool(s, ctx, pc, "create_sketch", map[string]any{"path": "/net-v1.sketch", "plane": "XY"})
	v2Out := runTool(s, ctx, pc, "create_sketch", map[string]any{"path": "/net-v2.sketch", "plane": "XY"})
	u1Path, _ := u1Out["path"].(string)
	u2Path, _ := u2Out["path"].(string)
	v1Path, _ := v1Out["path"].(string)
	v2Path, _ := v2Out["path"].(string)
	s.NotEmpty("network_srf u1 path", u1Path)
	s.NotEmpty("network_srf v1 path", v1Path)

	netSeed := `{"version":1,"features":[{"id":"network_srf-1","op":"network_srf","u_curves":["` + u1Path + `","` + u2Path + `"],"v_curves":["` + v1Path + `","` + v2Path + `"],"continuity":"C1"}]}`
	var netRow struct {
		ID   string `json:"id"`
		Kind string `json:"kind"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{"name": "cap.feature", "kind": "feature", "content": netSeed},
		owner.AccessToken, &netRow)
	s.Status("create network_srf-seeded feature", status, 201, raw)
	s.NotEmpty("network_srf feature id", netRow.ID)

	// GET round-trip.
	var netGet struct {
		Content string `json:"content"`
	}
	status, raw, _ = c.DoJSON("GET", "/api/projects/"+pid+"/files/"+netRow.ID, nil,
		owner.AccessToken, &netGet)
	if s.Status("get network_srf feature", status, 200, raw) {
		s.Equal("network_srf seed round-trip", netGet.Content, netSeed)
	}

	// LLM tool appends a second network_srf node — auto-id 'network_srf-2'.
	netOut := runTool(s, ctx, pc, "feature_network_srf", map[string]any{
		"file_id": netRow.ID,
		"u_paths": []string{u1Path, u2Path},
		"v_paths": []string{v1Path, v2Path},
		"options": map[string]any{"continuity": "C2"},
	})
	s.Equal("feature_network_srf op", netOut["op"], "network_srf")
	s.Equal("feature_network_srf auto-id", netOut["id"], "network_srf-2")

	var netContent string
	if err := env.Pool.QueryRow(ctx,
		`select content from files where id = $1`, netRow.ID).Scan(&netContent); s.NoError("read network_srf content", err) {
		var doc map[string]any
		if err := json.Unmarshal([]byte(netContent), &doc); s.NoError("decode network_srf content", err) {
			feats, _ := doc["features"].([]any)
			s.True("network_srf features len=2", len(feats) == 2, "got %d", len(feats))
			if len(feats) == 2 {
				second, _ := feats[1].(map[string]any)
				s.Equal("network_srf-2 op", second["op"], "network_srf")
				s.Equal("network_srf-2 continuity", second["continuity"], "C2")
			}
		}
	}

	// BAD_ARGS guard: u_paths < 2.
	netBadU := runTool(s, ctx, pc, "feature_network_srf", map[string]any{
		"file_id": netRow.ID,
		"u_paths": []string{u1Path},
		"v_paths": []string{v1Path, v2Path},
	})
	s.Equal("feature_network_srf missing u_paths → BAD_ARGS", netBadU["code"], "BAD_ARGS")

	// BAD_ARGS guard: v_paths < 2.
	netBadV := runTool(s, ctx, pc, "feature_network_srf", map[string]any{
		"file_id": netRow.ID,
		"u_paths": []string{u1Path, u2Path},
		"v_paths": []string{v1Path},
	})
	s.Equal("feature_network_srf missing v_paths → BAD_ARGS", netBadV["code"], "BAD_ARGS")

	// --- Phase 4a blend_srf (G0/G1/G2 blend between two body edges) plumbing.
	// Seed a .feature with a pad + blend_srf node, GET round-trip, then
	// exercise the feature_blend_srf LLM tool.
	blendSeed := `{"version":1,"features":[{"id":"pad-1","op":"pad","sketch_path":"` + profilePath + `","height":5,"direction":"up"},{"id":"blend_srf-1","op":"blend_srf","target_id":"pad-1","edge1_id":1,"edge2_id":3,"continuity":"G1"}]}`
	var blendRow struct {
		ID   string `json:"id"`
		Kind string `json:"kind"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{"name": "bezel.feature", "kind": "feature", "content": blendSeed},
		owner.AccessToken, &blendRow)
	s.Status("create blend_srf-seeded feature", status, 201, raw)
	s.NotEmpty("blend_srf feature id", blendRow.ID)

	var blendGet struct {
		Content string `json:"content"`
	}
	status, raw, _ = c.DoJSON("GET", "/api/projects/"+pid+"/files/"+blendRow.ID, nil,
		owner.AccessToken, &blendGet)
	if s.Status("get blend_srf feature", status, 200, raw) {
		s.Equal("blend_srf seed round-trip", blendGet.Content, blendSeed)
	}

	// LLM tool appends a second blend_srf node — auto-id 'blend_srf-2'.
	blendOut := runTool(s, ctx, pc, "feature_blend_srf", map[string]any{
		"file_id":   blendRow.ID,
		"target_id": "pad-1",
		"edge1_id":  2,
		"edge2_id":  4,
		"options":   map[string]any{"continuity": "G2"},
	})
	s.Equal("feature_blend_srf op", blendOut["op"], "blend_srf")
	s.Equal("feature_blend_srf auto-id", blendOut["id"], "blend_srf-2")

	var blendContent string
	if err := env.Pool.QueryRow(ctx,
		`select content from files where id = $1`, blendRow.ID).Scan(&blendContent); s.NoError("read blend_srf content", err) {
		var doc map[string]any
		if err := json.Unmarshal([]byte(blendContent), &doc); s.NoError("decode blend_srf content", err) {
			feats, _ := doc["features"].([]any)
			s.True("blend_srf features len=3", len(feats) == 3, "got %d", len(feats))
			if len(feats) == 3 {
				third, _ := feats[2].(map[string]any)
				s.Equal("blend_srf-2 op", third["op"], "blend_srf")
				s.Equal("blend_srf-2 continuity", third["continuity"], "G2")
				s.Equal("blend_srf-2 target", third["target_id"], "pad-1")
			}
		}
	}

	// BAD_ARGS guard: missing target_id.
	blendBadTarget := runTool(s, ctx, pc, "feature_blend_srf", map[string]any{
		"file_id":  blendRow.ID,
		"edge1_id": 1,
		"edge2_id": 2,
	})
	s.Equal("feature_blend_srf missing target_id → BAD_ARGS", blendBadTarget["code"], "BAD_ARGS")

	// BAD_ARGS guard: missing file_id.
	blendBadFile := runTool(s, ctx, pc, "feature_blend_srf", map[string]any{
		"target_id": "pad-1",
		"edge1_id":  1,
		"edge2_id":  2,
	})
	s.Equal("feature_blend_srf missing file_id → BAD_ARGS", blendBadFile["code"], "BAD_ARGS")
}

// asString safely converts an interface{} to string ("" on miss).
func asString(v any) string {
	s, _ := v.(string)
	return s
}
