package scenarios

// Drawing scenarios — kind='drawing' file plumbing.
//
// The dedicated drawing-authoring LLM tools were consolidated away when
// the tool surface was trimmed; the model now writes drawing JSON directly
// via write_file / edit_file after consulting docs/llm/drawing.md. This
// scenario verifies the drawing-kind plumbing:
//
//   - kind='drawing' is creatable via POST /files (the API still accepts
//     all canonical kinds; the LLM's create_file tool is more restrictive).
//   - The file persists multi-sheet drawing JSON and round-trips cleanly
//     through GET /files/{fid}.
//   - Legacy single-sheet JSON (no `sheets[]` field) is still readable.

import (
	"encoding/json"

	"github.com/imranp/kerf/backend/cmd/test/runner"
)

// Drawings runs the drawing-kind plumbing scenario.
func Drawings(s *runner.Suite, env *runner.Env) {
	c := env.Client
	_ = env

	owner, status, raw := register(c, "draw-owner@example.com", "drawpass1", "Draw Owner")
	if !s.Status("register draw owner", status, 201, raw) {
		return
	}
	var proj struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects",
		map[string]string{"name": "Drawing project"}, owner.AccessToken, &proj)
	if !s.Status("create draw project", status, 201, raw) {
		return
	}
	pid := proj.ID

	// --- Source file the drawing references. ---
	var src struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{
			"name":    "widget.jscad",
			"kind":    "file",
			"content": "module.exports.main = () => cube({size: 10})",
		}, owner.AccessToken, &src)
	if !s.Status("create source jscad", status, 201, raw) {
		return
	}

	// --- Multi-sheet drawing JSON. ---
	doc := map[string]any{
		"sheets": []map[string]any{
			{
				"id": "sh-1",
				"frame": map[string]any{
					"size":         "A3",
					"orientation":  "landscape",
					"title":        "Widget",
					"sheet_number": "1/2",
					"template":     "default",
				},
				"views": []map[string]any{
					{
						"id":              "v-front",
						"source_file_id":  src.ID,
						"part_id":         "*",
						"projection":      "front",
						"scale":           1.0,
						"position":        []float64{50, 50},
						"show_hidden":     true,
						"show_silhouette": true,
						"label":           "Front",
					},
				},
				"dimensions":  []any{},
				"annotations": []any{},
				"centerlines": []any{},
				"breaks":      []any{},
				"symbols":     []any{},
			},
			{
				"id": "sh-2",
				"frame": map[string]any{
					"size":         "A4",
					"orientation":  "portrait",
					"title":        "Widget Detail",
					"sheet_number": "2/2",
				},
				"views":       []any{},
				"dimensions":  []any{},
				"annotations": []any{},
				"centerlines": []any{},
				"breaks":      []any{},
				"symbols":     []any{},
			},
		},
	}
	docJSON, _ := json.Marshal(doc)

	// --- POST /files with kind=drawing ---
	var drawing struct {
		ID   string `json:"id"`
		Kind string `json:"kind"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{
			"name":    "widget.drawing",
			"kind":    "drawing",
			"content": string(docJSON),
		}, owner.AccessToken, &drawing)
	if !s.Status("create drawing", status, 201, raw) {
		return
	}
	s.Equal("drawing kind=drawing", drawing.Kind, "drawing")

	// --- GET round-trips the JSON shape. ---
	var got struct {
		Content *string `json:"content"`
	}
	status, raw, _ = c.DoJSON("GET", "/api/projects/"+pid+"/files/"+drawing.ID,
		nil, owner.AccessToken, &got)
	if s.Status("GET drawing", status, 200, raw) {
		if s.True("drawing has content", got.Content != nil) {
			var roundTrip map[string]any
			if err := json.Unmarshal([]byte(*got.Content), &roundTrip); s.NoError("decode round-trip", err) {
				sheets, _ := roundTrip["sheets"].([]any)
				s.Equal("round-trip sheets=2", len(sheets), 2)
				if len(sheets) == 2 {
					sh1, _ := sheets[0].(map[string]any)
					views, _ := sh1["views"].([]any)
					s.Equal("sheet1 views=1", len(views), 1)
				}
			}
		}
	}

	// --- Legacy single-sheet JSON (no sheets[] field) is also accepted. ---
	legacy := `{
		"frame": {"size":"A3","orientation":"landscape","title":"Legacy"},
		"views": [],
		"dimensions": [],
		"annotations": []
	}`
	var legacyDoc struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{
			"name":    "legacy.drawing",
			"kind":    "drawing",
			"content": legacy,
		}, owner.AccessToken, &legacyDoc)
	if s.Status("create legacy drawing", status, 201, raw) {
		// Read it back; we make no assumption about server-side normalization
		// — the contract says the FRONTEND wraps legacy → sheets[oldSheet] on
		// load. The server stores raw JSON.
		var got2 struct {
			Content *string `json:"content"`
		}
		status, raw, _ = c.DoJSON("GET", "/api/projects/"+pid+"/files/"+legacyDoc.ID,
			nil, owner.AccessToken, &got2)
		if s.Status("GET legacy drawing", status, 200, raw) && got2.Content != nil {
			s.Contains("legacy frame.title preserved", *got2.Content, "Legacy")
		}
	}
}
