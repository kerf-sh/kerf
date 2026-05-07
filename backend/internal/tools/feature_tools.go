package tools

// Feature scaffolding — create_feature only.
//
// Per-operation tools (feature_pad, feature_pocket, feature_revolve,
// feature_fillet, feature_chamfer, feature_shell, feature_hole) were
// removed when the LLM tool surface was consolidated. The model now
// authors / mutates the feature tree by editing the JSON via
// write_file / edit_file after consulting docs/llm/feature.md.
//
// Schema (mirrors src/lib/occtRunner.js DEFAULT_FEATURE):
//
//   {
//     "version": 1,
//     "name": "...",
//     "features": [
//       { "id": "feat-abcd", "op": "pad", "sketch_path": "/foo.sketch",
//         "height": 10, "direction": "up" },
//       { "id": "feat-xyz",  "op": "fillet", "target_id": "feat-abcd",
//         "edge_filter": "all", "radius": 1 },
//       ...
//     ]
//   }

import (
	"context"
	"encoding/json"
	"strings"

	"github.com/google/uuid"

	"github.com/imranp/kerf/backend/internal/llm"
)

// featureNode / featureDoc are the feature-tree shapes. Kept as types
// (rather than `any`) so create_feature can serialize a canonical seed
// the OCCT worker accepts on first load.

type featureNode struct {
	ID         string  `json:"id"`
	Op         string  `json:"op"`
	SketchPath string  `json:"sketch_path,omitempty"`
	TargetID   string  `json:"target_id,omitempty"`
	Height     float64 `json:"height,omitempty"`
	Depth      float64 `json:"depth,omitempty"`
	Direction  string  `json:"direction,omitempty"`
	Axis       string  `json:"axis,omitempty"`
	AngleDeg   float64 `json:"angle_deg,omitempty"`
	EdgeFilter string  `json:"edge_filter,omitempty"`
	EdgeIDs    []int   `json:"edge_ids,omitempty"`
	FaceIDs    []int   `json:"face_ids,omitempty"`
	Radius     float64 `json:"radius,omitempty"`
	Distance   float64 `json:"distance,omitempty"`
	Thickness  float64 `json:"thickness,omitempty"`
	Diameter   float64 `json:"diameter,omitempty"`
}

type featureDoc struct {
	Version  int            `json:"version"`
	Name     string         `json:"name,omitempty"`
	Features []featureNode  `json:"features"`
	Metadata map[string]any `json:"metadata,omitempty"`
}

func serializeFeatureContent(d featureDoc) (string, error) {
	if d.Features == nil {
		d.Features = []featureNode{}
	}
	if d.Version == 0 {
		d.Version = 1
	}
	b, err := json.MarshalIndent(d, "", "  ")
	if err != nil {
		return "", err
	}
	return string(b), nil
}

// ---------------------------------------------------------------------------
// create_feature

var createFeatureSpec = llm.ToolSpec{
	Name:        "create_feature",
	Description: "Create a new empty .feature file (OCCT B-rep timeline). After creation, append operations by editing the JSON via write_file / edit_file. Consult docs/llm/feature.md for the node-type vocabulary (pad / pocket / revolve / fillet / chamfer / shell / hole). Refuses .sketch / .assembly / .drawing / .part paths.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"path": map[string]any{
				"type":        "string",
				"description": "Absolute path of the new feature file. Should end with .feature.",
			},
			"name": map[string]any{
				"type":        "string",
				"description": "Optional human-readable name persisted into the JSON.",
			},
		},
		"required": []string{"path"},
	},
}

type createFeatureArgs struct {
	Path string `json:"path"`
	Name string `json:"name"`
}

func runCreateFeature(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a createFeatureArgs
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
	low := strings.ToLower(clean)
	for _, ext := range []string{".sketch", ".assembly", ".drawing", ".part"} {
		if strings.HasSuffix(low, ext) {
			return errPayload("path has reserved extension "+ext, "BAD_KIND"), nil
		}
	}
	if !strings.HasSuffix(low, ".feature") {
		clean += ".feature"
		parts = splitPath(clean)
	}
	if rp, _ := resolvePath(ctx, pc, clean); rp.Exists {
		return errPayload("path already exists", "EXISTS"), nil
	}
	parent, err := ensureFolders(ctx, pc, parts[:len(parts)-1])
	if err != nil {
		return "", err
	}
	leaf := parts[len(parts)-1]
	doc := featureDoc{
		Version:  1,
		Name:     a.Name,
		Features: []featureNode{},
	}
	body, err := serializeFeatureContent(doc)
	if err != nil {
		return errPayload("encode: "+err.Error(), "ERROR"), nil
	}
	var newID uuid.UUID
	err = pc.Pool.QueryRow(ctx,
		`insert into files(project_id, parent_id, name, kind, content)
		 values ($1,$2,$3,'feature',$4)
		 returning id`,
		pc.ProjectID, parent, leaf, body).Scan(&newID)
	if err != nil {
		return "", err
	}
	_ = recordRevisionForFile(ctx, pc, newID, body, "tool")
	return okPayload(map[string]any{
		"path": clean,
		"id":   newID.String(),
	}), nil
}
