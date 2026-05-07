package tools

// Sketch tools — let the LLM scaffold parametric 2D sketch files. The actual
// geometry/constraint authoring happens in the dedicated sketch UI on the
// frontend (it integrates planegcs for solving). LLM tools intentionally
// cannot mutate sketch JSON beyond creation; write_file/edit_file/delete_file
// reject `.sketch` paths with a READONLY_SKETCH code.
//
// Sketches compile to a JSCAD Geom2 at JSCAD-import time so they can be
// extruded / lofted from `.jscad` files without round-tripping through code.

import (
	"context"
	"encoding/json"
	"strings"

	"github.com/google/uuid"

	"github.com/imranp/kerf/backend/internal/llm"
)

// ---------------------------------------------------------------------------
// Sketch JSON shape (mirrors the TS Sketch type in the contract).
//
// Only the fields the backend cares about are typed here; the sketch UI is
// the source of truth for the schema and we tolerate unknown keys via the
// raw JSON path on read. The seed produced by `create_sketch` populates the
// minimum the UI expects: version, plane, an origin point, empty arrays for
// constraints/visible_3d/solved, and a metadata block for name/description.

type sketchPlane struct {
	Type    string `json:"type"`              // "base" | "face"
	Name    string `json:"name,omitempty"`    // "XY" | "XZ" | "YZ" for base planes
	FileID  string `json:"file_id,omitempty"` // future v2: face-anchored sketches
	FaceID  string `json:"face_id,omitempty"`
}

type sketchEntity struct {
	ID           string  `json:"id"`
	Type         string  `json:"type"` // "point" | "line" | "arc" | "circle"
	X            float64 `json:"x,omitempty"`
	Y            float64 `json:"y,omitempty"`
	P1           string  `json:"p1,omitempty"`
	P2           string  `json:"p2,omitempty"`
	Center       string  `json:"center,omitempty"`
	Start        string  `json:"start,omitempty"`
	End          string  `json:"end,omitempty"`
	SweepCCW     bool    `json:"sweep_ccw,omitempty"`
	Radius       float64 `json:"radius,omitempty"`
	Construction bool    `json:"construction,omitempty"`
}

type sketchMetadata struct {
	Name        string `json:"name,omitempty"`
	Description string `json:"description,omitempty"`
}

type sketchDoc struct {
	Version     int             `json:"version"`
	Plane       sketchPlane     `json:"plane"`
	Entities    []sketchEntity  `json:"entities"`
	Constraints []any           `json:"constraints"`
	Visible3D   []string        `json:"visible_3d"`
	Solved      map[string]any  `json:"solved"`
	Metadata    sketchMetadata  `json:"metadata"`
}

func validBasePlane(p string) bool {
	switch p {
	case "XY", "XZ", "YZ":
		return true
	}
	return false
}

// ---------------------------------------------------------------------------
// create_sketch

var createSketchSpec = llm.ToolSpec{
	Name: "create_sketch",
	Description: "Create a new parametric 2D sketch file. The user authors geometry + dimensional/geometric constraints in the sketch UI; LLM tools cannot mutate sketches beyond creation. Sketches compile to a JSCAD Geom2 and can be imported by `.jscad` files via `import profile from '/path.sketch'`.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"path": map[string]any{
				"type":        "string",
				"description": "Absolute path of the new sketch file. Should end with .sketch.",
			},
			"plane": map[string]any{
				"type":        "string",
				"enum":        []string{"XY", "XZ", "YZ"},
				"description": "Base plane the sketch lives on. Defaults to XY.",
			},
			"name": map[string]any{
				"type":        "string",
				"description": "Optional human-readable name persisted into metadata.",
			},
			"description": map[string]any{
				"type":        "string",
				"description": "Optional one-line description.",
			},
		},
		"required": []string{"path"},
	},
}

type createSketchArgs struct {
	Path        string `json:"path"`
	Plane       string `json:"plane"`
	Name        string `json:"name"`
	Description string `json:"description"`
}

func runCreateSketch(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a createSketchArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	clean, err := normalizePath(a.Path)
	if err != nil {
		return errPayload(err.Error(), "BAD_ARGS"), nil
	}
	parts := splitPath(clean)
	if len(parts) == 0 {
		return errPayload("cannot create the root", "BAD_ARGS"), nil
	}
	if !strings.HasSuffix(strings.ToLower(clean), ".sketch") {
		// Append the extension if the user/LLM omitted it.
		clean = clean + ".sketch"
		parts = splitPath(clean)
	}
	if rp, _ := resolvePath(ctx, pc, clean); rp.Exists {
		return errPayload("path already exists", "EXISTS"), nil
	}
	plane := strings.ToUpper(a.Plane)
	if plane == "" {
		plane = "XY"
	}
	if !validBasePlane(plane) {
		return errPayload("plane must be XY|XZ|YZ", "BAD_ARGS"), nil
	}

	// Default seed: one origin point at (0,0). Editor renders this so the
	// canvas has something to anchor against; users typically pin it with a
	// distance_x/distance_y or coincident constraint.
	doc := sketchDoc{
		Version: 1,
		Plane:   sketchPlane{Type: "base", Name: plane},
		Entities: []sketchEntity{
			{ID: "origin", Type: "point", X: 0, Y: 0},
		},
		Constraints: []any{},
		Visible3D:   []string{},
		Solved:      map[string]any{},
		Metadata: sketchMetadata{
			Name:        a.Name,
			Description: a.Description,
		},
	}

	parent, err := ensureFolders(ctx, pc, parts[:len(parts)-1])
	if err != nil {
		return "", err
	}
	leaf := parts[len(parts)-1]

	body, err := json.MarshalIndent(doc, "", "  ")
	if err != nil {
		return errPayload("encode sketch: "+err.Error(), "ERROR"), nil
	}
	var newID uuid.UUID
	err = pc.Pool.QueryRow(ctx,
		`insert into files(project_id, parent_id, name, kind, content)
		 values ($1,$2,$3,'sketch',$4)
		 returning id`,
		pc.ProjectID, parent, leaf, string(body)).Scan(&newID)
	if err != nil {
		return "", err
	}
	_ = recordRevisionForFile(ctx, pc, newID, string(body), "tool")
	return okPayload(map[string]any{
		"path":  clean,
		"id":    newID.String(),
		"plane": plane,
	}), nil
}
