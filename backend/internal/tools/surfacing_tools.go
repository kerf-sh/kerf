package tools

// Phase 4a — jewelry-priority surfacing LLM tools.
//
// `feature_sweep2`, `feature_network_srf`, and `feature_blend_srf` each
// append one node to a `.feature` file's `features` array. The model would
// otherwise have to author the JSON via write_file/edit_file; these tools
// give it a typed entry point so it can compose ring-shanks, prong-baskets,
// and bezels from a few sentences of intent.
//
// Mirrors the shape that `add_configuration` uses to round-trip the host
// JSON: read the row, splice the array, re-emit, record a revision.
//
// All three are write tools (editor+ only).

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/google/uuid"

	"github.com/imranp/kerf/backend/internal/llm"
)

// appendFeatureNode loads a kind='feature' file by id, parses its JSON,
// appends `node` to the `features` array, and persists the result. Returns
// (file_name, node_id, error) — node_id is the value of node["id"] (caller
// is responsible for setting it before calling).
func appendFeatureNode(ctx context.Context, pc ProjectCtx, fileID uuid.UUID, node map[string]any) (string, string, error) {
	var name, kind, content string
	err := pc.Pool.QueryRow(ctx,
		`select name, kind, content from files
		 where id = $1 and project_id = $2 and deleted_at is null`,
		fileID, pc.ProjectID).Scan(&name, &kind, &content)
	if err != nil {
		return "", "", fmt.Errorf("file not found: %w", err)
	}
	if kind != "feature" {
		return "", "", fmt.Errorf("file kind %q is not 'feature'", kind)
	}
	var doc map[string]any
	if strings.TrimSpace(content) != "" {
		if err := json.Unmarshal([]byte(content), &doc); err != nil {
			return "", "", fmt.Errorf("file is not valid JSON: %w", err)
		}
	}
	if doc == nil {
		doc = map[string]any{"version": 1, "features": []any{}}
	}
	if _, has := doc["version"]; !has {
		doc["version"] = 1
	}
	var existing []any
	if raw, ok := doc["features"]; ok {
		if arr, ok := raw.([]any); ok {
			existing = arr
		}
	}
	existing = append(existing, node)
	doc["features"] = existing

	body, err := json.MarshalIndent(doc, "", "  ")
	if err != nil {
		return "", "", fmt.Errorf("encode: %w", err)
	}
	if _, err := pc.Pool.Exec(ctx,
		`update files set content = $1, updated_at = now()
		 where id = $2 and project_id = $3`,
		string(body), fileID, pc.ProjectID); err != nil {
		return "", "", err
	}
	_ = recordRevisionForFile(ctx, pc, fileID, string(body), "tool")

	id, _ := node["id"].(string)
	return name, id, nil
}

// nextNodeID picks "<op>-<n>" where n is one greater than the highest
// existing index for that op in the file's features array, or 1 if none.
// Best-effort: on parse failure we return "<op>-1".
func nextNodeID(content string, op string) string {
	if strings.TrimSpace(content) == "" {
		return op + "-1"
	}
	var doc map[string]any
	if err := json.Unmarshal([]byte(content), &doc); err != nil {
		return op + "-1"
	}
	arr, _ := doc["features"].([]any)
	maxN := 0
	prefix := op + "-"
	for _, item := range arr {
		m, ok := item.(map[string]any)
		if !ok {
			continue
		}
		id, _ := m["id"].(string)
		if !strings.HasPrefix(id, prefix) {
			continue
		}
		var n int
		if _, err := fmt.Sscanf(strings.TrimPrefix(id, prefix), "%d", &n); err == nil {
			if n > maxN {
				maxN = n
			}
		}
	}
	return fmt.Sprintf("%s-%d", op, maxN+1)
}

// readFeatureContent loads a feature row's content (used by nextNodeID
// callers that need to inspect existing ids before appending).
func readFeatureContent(ctx context.Context, pc ProjectCtx, fileID uuid.UUID) (string, error) {
	var content, kind string
	err := pc.Pool.QueryRow(ctx,
		`select content, kind from files
		 where id = $1 and project_id = $2 and deleted_at is null`,
		fileID, pc.ProjectID).Scan(&content, &kind)
	if err != nil {
		return "", err
	}
	if kind != "feature" {
		return "", fmt.Errorf("file kind %q is not 'feature'", kind)
	}
	return content, nil
}

// ---------------------------------------------------------------------------
// feature_sweep2

var featureSweep2Spec = llm.ToolSpec{
	Name: "feature_sweep2",
	Description: "Append a `sweep2` node to a `.feature` file. Sweep2 sweeps a closed profile sketch along TWO open-curve rails — the canonical move for ring shanks (oval profile twin-railed along inside + outside curves of the band), bracelets, and any tube whose cross-section needs to track two curves rather than one. Profile must be a closed wire (sketch enforces); rails must be open. The worker wires rail1 as the spine and rail2 as the auxiliary spine via BRepOffsetAPI_MakePipeShell.SetMode_3.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"file_id": map[string]any{
				"type":        "string",
				"description": "Target .feature file id.",
			},
			"profile_sketch_path": map[string]any{
				"type":        "string",
				"description": "Absolute path of the profile .sketch (closed wire).",
			},
			"rail1_sketch_path": map[string]any{
				"type":        "string",
				"description": "Absolute path of the first rail .sketch (open curve).",
			},
			"rail2_sketch_path": map[string]any{
				"type":        "string",
				"description": "Absolute path of the second rail .sketch (open curve).",
			},
			"twist_deg": map[string]any{"type": "number", "description": "Twist along the sweep, degrees."},
			"scale_end": map[string]any{"type": "number", "description": "End-section scale, default 1."},
			"mode":      map[string]any{"type": "string", "enum": []string{"auto", "frenet", "corrected_frenet"}, "description": "Frame mode for the sweep; default auto."},
			"id":        map[string]any{"type": "string", "description": "Optional explicit node id (default: sweep2-N)."},
		},
		"required": []string{"file_id", "profile_sketch_path", "rail1_sketch_path", "rail2_sketch_path"},
	},
}

type featureSweep2Args struct {
	FileID            string  `json:"file_id"`
	ProfileSketchPath string  `json:"profile_sketch_path"`
	Rail1SketchPath   string  `json:"rail1_sketch_path"`
	Rail2SketchPath   string  `json:"rail2_sketch_path"`
	TwistDeg          float64 `json:"twist_deg"`
	ScaleEnd          float64 `json:"scale_end"`
	Mode              string  `json:"mode"`
	ID                string  `json:"id"`
}

func runFeatureSweep2(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a featureSweep2Args
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	a.FileID = strings.TrimSpace(a.FileID)
	a.ProfileSketchPath = strings.TrimSpace(a.ProfileSketchPath)
	a.Rail1SketchPath = strings.TrimSpace(a.Rail1SketchPath)
	a.Rail2SketchPath = strings.TrimSpace(a.Rail2SketchPath)
	if a.FileID == "" {
		return errPayload("file_id is required", "BAD_ARGS"), nil
	}
	if a.ProfileSketchPath == "" {
		return errPayload("profile_sketch_path is required", "BAD_ARGS"), nil
	}
	if a.Rail1SketchPath == "" {
		return errPayload("rail1_sketch_path is required", "BAD_ARGS"), nil
	}
	if a.Rail2SketchPath == "" {
		return errPayload("rail2_sketch_path is required", "BAD_ARGS"), nil
	}
	fid, err := uuid.Parse(a.FileID)
	if err != nil {
		return errPayload("file_id must be a uuid: "+err.Error(), "BAD_ARGS"), nil
	}
	content, err := readFeatureContent(ctx, pc, fid)
	if err != nil {
		return errPayload(err.Error(), "NOT_FOUND"), nil
	}
	id := strings.TrimSpace(a.ID)
	if id == "" {
		id = nextNodeID(content, "sweep2")
	}
	mode := strings.TrimSpace(a.Mode)
	if mode == "" {
		mode = "auto"
	}
	scaleEnd := a.ScaleEnd
	if scaleEnd == 0 {
		scaleEnd = 1
	}
	node := map[string]any{
		"id":                  id,
		"op":                  "sweep2",
		"profile_sketch_path": a.ProfileSketchPath,
		"rail1_sketch_path":   a.Rail1SketchPath,
		"rail2_sketch_path":   a.Rail2SketchPath,
		"twist_deg":           a.TwistDeg,
		"scale_end":           scaleEnd,
		"mode":                mode,
	}
	name, nodeID, err := appendFeatureNode(ctx, pc, fid, node)
	if err != nil {
		return errPayload(err.Error(), "ERROR"), nil
	}
	return okPayload(map[string]any{
		"file_id": a.FileID,
		"name":    name,
		"id":      nodeID,
		"op":      "sweep2",
	}), nil
}

// ---------------------------------------------------------------------------
// feature_network_srf

var featureNetworkSrfSpec = llm.ToolSpec{
	Name: "feature_network_srf",
	Description: "Append a `network_srf` node to a `.feature` file. NetworkSrf fits a NURBS surface to a U/V grid of edges (≥2 curves in each direction). The right tool for organic settings, prong baskets, double-curvature jewelry caps, or any patch you'd reach for in Rhino's NetworkSrf. Pass arrays of sketch paths for U and V; continuity defaults to C1.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"file_id": map[string]any{"type": "string", "description": "Target .feature file id."},
			"u_paths": map[string]any{
				"type":        "array",
				"items":       map[string]any{"type": "string"},
				"description": "Absolute paths of the U-direction .sketch files (≥2).",
			},
			"v_paths": map[string]any{
				"type":        "array",
				"items":       map[string]any{"type": "string"},
				"description": "Absolute paths of the V-direction .sketch files (≥2).",
			},
			"options": map[string]any{
				"type": "object",
				"properties": map[string]any{
					"continuity": map[string]any{"type": "string", "enum": []string{"C0", "C1", "C2"}},
					"id":         map[string]any{"type": "string"},
				},
			},
		},
		"required": []string{"file_id", "u_paths", "v_paths"},
	},
}

type featureNetworkSrfArgs struct {
	FileID  string   `json:"file_id"`
	UPaths  []string `json:"u_paths"`
	VPaths  []string `json:"v_paths"`
	Options struct {
		Continuity string `json:"continuity"`
		ID         string `json:"id"`
	} `json:"options"`
}

func runFeatureNetworkSrf(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a featureNetworkSrfArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	a.FileID = strings.TrimSpace(a.FileID)
	if a.FileID == "" {
		return errPayload("file_id is required", "BAD_ARGS"), nil
	}
	if len(a.UPaths) < 2 {
		return errPayload("u_paths needs ≥2 entries", "BAD_ARGS"), nil
	}
	if len(a.VPaths) < 2 {
		return errPayload("v_paths needs ≥2 entries", "BAD_ARGS"), nil
	}
	fid, err := uuid.Parse(a.FileID)
	if err != nil {
		return errPayload("file_id must be a uuid: "+err.Error(), "BAD_ARGS"), nil
	}
	content, err := readFeatureContent(ctx, pc, fid)
	if err != nil {
		return errPayload(err.Error(), "NOT_FOUND"), nil
	}
	id := strings.TrimSpace(a.Options.ID)
	if id == "" {
		id = nextNodeID(content, "network_srf")
	}
	cont := strings.ToUpper(a.Options.Continuity)
	if cont != "C0" && cont != "C1" && cont != "C2" {
		cont = "C1"
	}
	uAny := make([]any, len(a.UPaths))
	for i, p := range a.UPaths {
		uAny[i] = p
	}
	vAny := make([]any, len(a.VPaths))
	for i, p := range a.VPaths {
		vAny[i] = p
	}
	node := map[string]any{
		"id":         id,
		"op":         "network_srf",
		"u_curves":   uAny,
		"v_curves":   vAny,
		"continuity": cont,
	}
	name, nodeID, err := appendFeatureNode(ctx, pc, fid, node)
	if err != nil {
		return errPayload(err.Error(), "ERROR"), nil
	}
	return okPayload(map[string]any{
		"file_id": a.FileID,
		"name":    name,
		"id":      nodeID,
		"op":      "network_srf",
	}), nil
}

// ---------------------------------------------------------------------------
// feature_blend_srf

var featureBlendSrfSpec = llm.ToolSpec{
	Name: "feature_blend_srf",
	Description: "Append a `blend_srf` node to a `.feature` file. BlendSrf builds a smooth G0/G1/G2 surface that bridges two existing edges of a body (e.g. the top edge of a ring shank and the lower edge of a bezel). Reference the upstream feature node id (`target_id`) and the two numeric edge ids on its evaluated topology. Use the FeatureView 'Edges' pick mode to discover edge ids.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"file_id":   map[string]any{"type": "string", "description": "Target .feature file id."},
			"target_id": map[string]any{"type": "string", "description": "Existing feature node id whose edges these belong to."},
			"edge1_id":  map[string]any{"type": "integer", "description": "First edge id (post-evaluation)."},
			"edge2_id":  map[string]any{"type": "integer", "description": "Second edge id."},
			"options": map[string]any{
				"type": "object",
				"properties": map[string]any{
					"continuity": map[string]any{"type": "string", "enum": []string{"G0", "G1", "G2"}},
					"id":         map[string]any{"type": "string"},
				},
			},
		},
		"required": []string{"file_id", "target_id", "edge1_id", "edge2_id"},
	},
}

type featureBlendSrfArgs struct {
	FileID   string `json:"file_id"`
	TargetID string `json:"target_id"`
	Edge1ID  int    `json:"edge1_id"`
	Edge2ID  int    `json:"edge2_id"`
	Options  struct {
		Continuity string `json:"continuity"`
		ID         string `json:"id"`
	} `json:"options"`
}

func runFeatureBlendSrf(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a featureBlendSrfArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	a.FileID = strings.TrimSpace(a.FileID)
	a.TargetID = strings.TrimSpace(a.TargetID)
	if a.FileID == "" {
		return errPayload("file_id is required", "BAD_ARGS"), nil
	}
	if a.TargetID == "" {
		return errPayload("target_id is required", "BAD_ARGS"), nil
	}
	fid, err := uuid.Parse(a.FileID)
	if err != nil {
		return errPayload("file_id must be a uuid: "+err.Error(), "BAD_ARGS"), nil
	}
	content, err := readFeatureContent(ctx, pc, fid)
	if err != nil {
		return errPayload(err.Error(), "NOT_FOUND"), nil
	}
	id := strings.TrimSpace(a.Options.ID)
	if id == "" {
		id = nextNodeID(content, "blend_srf")
	}
	cont := strings.ToUpper(a.Options.Continuity)
	if cont != "G0" && cont != "G1" && cont != "G2" {
		cont = "G1"
	}
	node := map[string]any{
		"id":         id,
		"op":         "blend_srf",
		"target_id":  a.TargetID,
		"edge1_id":   a.Edge1ID,
		"edge2_id":   a.Edge2ID,
		"continuity": cont,
	}
	name, nodeID, err := appendFeatureNode(ctx, pc, fid, node)
	if err != nil {
		return errPayload(err.Error(), "ERROR"), nil
	}
	return okPayload(map[string]any{
		"file_id": a.FileID,
		"name":    name,
		"id":      nodeID,
		"op":      "blend_srf",
	}), nil
}
