package scenarios

// Sketcher scenarios — sketch authoring + cross-cutting Part →
// assembly model resolution.
//
// Sketches (`kind='sketch'`) are scaffolded via create_sketch. The LLM
// surface for editing them via dedicated tools has been consolidated
// away; the model now writes JSON directly via write_file / edit_file
// after consulting docs/llm/sketch.md.

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/google/uuid"

	"github.com/imranp/kerf/backend/cmd/test/runner"
	"github.com/imranp/kerf/backend/internal/tools"
)

// Sketcher tests create_sketch + the cross-cutting Part-model wiring.
func Sketcher(s *runner.Suite, env *runner.Env) {
	c := env.Client
	ctx := context.Background()

	owner, status, raw := register(c, "sketch-owner@example.com", "sketchpass1", "Sketch Owner")
	if !s.Status("register sketch owner", status, 201, raw) {
		return
	}
	var proj struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects",
		map[string]string{"name": "Sketcher project"}, owner.AccessToken, &proj)
	if !s.Status("create sketch project", status, 201, raw) {
		return
	}
	pid := proj.ID
	pc := tools.ProjectCtx{
		Pool:      env.Pool,
		ProjectID: uuid.MustParse(pid),
		UserID:    uuid.MustParse(owner.User.ID),
		Role:      "owner",
	}

	// --- create_sketch ---
	out := runTool(s, ctx, pc, "create_sketch", map[string]any{
		"path":  "/sketches/profile.sketch",
		"plane": "XZ",
		"name":  "Top profile",
	})
	sketchID, _ := out["id"].(string)
	if !s.NotEmpty("create_sketch id", sketchID) {
		return
	}
	s.Equal("create_sketch plane", out["plane"], "XZ")

	// File row exists with kind='sketch'.
	var kind string
	if err := env.Pool.QueryRow(ctx,
		`select kind from files where id = $1`, sketchID).Scan(&kind); s.NoError("kind lookup", err) {
		s.Equal("sketch row kind=sketch", kind, "sketch")
	}

	// .sketch suffix is auto-appended when missing.
	out2 := runTool(s, ctx, pc, "create_sketch", map[string]any{
		"path": "/sketches/no-suffix",
	})
	pathOut, _ := out2["path"].(string)
	s.True("create_sketch auto-appends .sketch",
		strings.HasSuffix(pathOut, ".sketch"),
		"path=%q does not end in .sketch", pathOut)

	// Re-create same path → EXISTS.
	dup := runTool(s, ctx, pc, "create_sketch", map[string]any{
		"path": "/sketches/profile.sketch",
	})
	s.Equal("create_sketch duplicate path → EXISTS", dup["code"], "EXISTS")

	// --- READONLY guards: write_file / create_file refuse to CREATE a
	// .sketch (they steer to create_sketch). Editing an EXISTING .sketch
	// via write_file IS allowed — that's the contract for in-place
	// authoring. ---
	wfNew := runTool(s, ctx, pc, "write_file", map[string]any{
		"path":    "/sketches/missing.sketch",
		"content": "garbage",
	})
	s.Equal("write_file on missing .sketch → READONLY_SKETCH",
		wfNew["code"], "READONLY_SKETCH")
	cfKind := runTool(s, ctx, pc, "create_file", map[string]any{
		"path": "/sketches/foo.sketch",
		"kind": "sketch",
	})
	s.Equal("create_file kind=sketch → READONLY_SKETCH", cfKind["code"], "READONLY_SKETCH")
	cfSuffix := runTool(s, ctx, pc, "create_file", map[string]any{
		"path": "/sketches/bar.sketch",
	})
	s.Equal("create_file .sketch suffix → READONLY_SKETCH", cfSuffix["code"], "READONLY_SKETCH")

	// Sketch content has the canonical seed (version=1, origin point).
	var content string
	if err := env.Pool.QueryRow(ctx,
		`select content from files where id = $1`, sketchID).Scan(&content); s.NoError("read sketch content", err) {
		s.True("sketch content non-empty", len(content) > 0)
		var doc map[string]any
		if err := json.Unmarshal([]byte(content), &doc); s.NoError("decode sketch json", err) {
			s.Equal("sketch.version=1", doc["version"], float64(1))
			plane, _ := doc["plane"].(map[string]any)
			s.Equal("sketch.plane.name=XZ", plane["name"], "XZ")
		}
	}

	// --- Part with model_storage_key referenced by an assembly: BOM
	// rollup must surface model_storage_key on the part row. ---
	storageKey := "projects/" + pid + "/assets/test-model.step"
	createPartOut := runTool(s, ctx, pc, "create_part", map[string]any{
		"path": "/library/widget.part",
		"metadata": map[string]any{
			"name":              "Widget",
			"mpn":               "W-001",
			"model_storage_key": storageKey,
			"model_mime_type":   "model/step",
		},
	})
	partID, _ := createPartOut["id"].(string)
	if !s.NotEmpty("create part with model_storage_key", partID) {
		return
	}

	assyContent := fmt.Sprintf(`{"version":1,"components":[{"file_id":%q,"object_id":""}]}`, partID)
	var assy struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{"name": "main.assembly", "kind": "assembly", "content": assyContent},
		owner.AccessToken, &assy)
	if !s.Status("create assembly with widget part", status, 201, raw) {
		return
	}

	// BOM rollup carries through model_storage_key on the row's Part.
	var bom struct {
		Rows []struct {
			Part struct {
				ModelStorageKey string `json:"model_storage_key"`
				Name            string `json:"name"`
			} `json:"part"`
			Count int `json:"count"`
		} `json:"rows"`
	}
	status, raw, _ = c.DoJSON("GET", "/api/projects/"+pid+"/bom",
		nil, owner.AccessToken, &bom)
	if s.Status("GET /bom widget", status, 200, raw) {
		if s.Equal("bom rows for widget", len(bom.Rows), 1) && len(bom.Rows) == 1 {
			s.Equal("bom row.Part.model_storage_key passed through",
				bom.Rows[0].Part.ModelStorageKey, storageKey)
			s.Equal("bom row.Part.Name", bom.Rows[0].Part.Name, "Widget")
		}
	}
}
