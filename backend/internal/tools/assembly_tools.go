package tools

// Assembly-only LLM tool surface. Today it's a single tool —
// `assembly_add_external_component` — that appends a Component referencing
// geometry from a SIBLING project (PCB-as-part style cross-project ref).
//
// Why a dedicated tool instead of "let the LLM edit JSON":
//   - The cross-project ref shape is non-obvious (project_id + file_id +
//     kind + pin) and easy to mis-assemble. A typed tool surface gives the
//     model schema-level help.
//   - The tool validates that the referenced project + file actually exist
//     (and that the caller is a member of the source project's workspace)
//     before splicing the component in, so bad refs never land in saved
//     files.
//   - Same-project Components stay on the file_ops path — the model still
//     edits the assembly JSON directly via write_file / edit_file when the
//     ref is local. Cross-project is the surgical exception.
//
// Mirrors the surface of the (now-retired) `assembly_add` tool: name +
// description + an args struct. Records a file revision so Cmd-Z works.

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/google/uuid"

	"github.com/imranp/kerf/backend/internal/llm"
)

// ----------------------- assembly_add_external_component -------------------

var assemblyAddExternalComponentSpec = llm.ToolSpec{
	Name: "assembly_add_external_component",
	Description: "Append a Component to an Assembly file whose geometry is sourced from a DIFFERENT project (cross-project reference). Use this when the user wants a mechanical assembly to reference a PCB from an electronics project (board_3d / board_outline_2d) or any other project's geometry. The caller MUST be a member of the source project's workspace; the tool returns a permission error otherwise. The newly-added Component carries an `external_ref` field with `{project_id, file_id, kind, pin}` — same-project components keep using `file_id` and are added by editing the assembly JSON directly.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"assembly_file_id": map[string]any{
				"type":        "string",
				"description": "Target assembly file in the CURRENT project (kind='assembly').",
			},
			"external_project_id": map[string]any{
				"type":        "string",
				"description": "Source project's uuid — the OTHER project the geometry comes from.",
			},
			"external_file_id": map[string]any{
				"type":        "string",
				"description": "Source file's uuid INSIDE that project (typically a .circuit.tsx for board_3d/board_outline_2d, or a .feature/.step/.part for mesh).",
			},
			"kind": map[string]any{
				"type":        "string",
				"enum":        []string{"board_3d", "board_outline_2d", "mesh"},
				"description": "Which artifact to extract from the source. board_3d = assembled PCB cuboid mock; board_outline_2d = the board edge as a thin slab; mesh = direct geometry (loaded the same way a same-project component would).",
			},
			"pin": map[string]any{
				"type":        "string",
				"description": "Either 'tracking_latest' (default — always render HEAD of the source) or a revision id to pin against. Optional; defaults to tracking_latest.",
			},
			"component_id": map[string]any{
				"type":        "string",
				"description": "Optional id for the new component within the assembly. Auto-generated from the source file's name when omitted.",
			},
			"transform": map[string]any{
				"type":        "array",
				"description": "Optional row-major 4×4 transform (16 numbers). Defaults to identity.",
				"items":       map[string]any{"type": "number"},
			},
		},
		"required": []string{"assembly_file_id", "external_project_id", "external_file_id", "kind"},
	},
}

type assemblyAddExternalArgs struct {
	AssemblyFileID    string    `json:"assembly_file_id"`
	ExternalProjectID string    `json:"external_project_id"`
	ExternalFileID    string    `json:"external_file_id"`
	Kind              string    `json:"kind"`
	Pin               string    `json:"pin"`
	ComponentID       string    `json:"component_id"`
	Transform         []float64 `json:"transform"`
}

func runAssemblyAddExternalComponent(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a assemblyAddExternalArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	a.AssemblyFileID = strings.TrimSpace(a.AssemblyFileID)
	a.ExternalProjectID = strings.TrimSpace(a.ExternalProjectID)
	a.ExternalFileID = strings.TrimSpace(a.ExternalFileID)
	a.Kind = strings.TrimSpace(a.Kind)
	a.Pin = strings.TrimSpace(a.Pin)
	a.ComponentID = strings.TrimSpace(a.ComponentID)
	if a.AssemblyFileID == "" || a.ExternalProjectID == "" || a.ExternalFileID == "" || a.Kind == "" {
		return errPayload("assembly_file_id, external_project_id, external_file_id, and kind are required", "BAD_ARGS"), nil
	}
	switch a.Kind {
	case "board_3d", "board_outline_2d", "mesh":
		// ok
	default:
		return errPayload("kind must be one of board_3d / board_outline_2d / mesh", "BAD_ARGS"), nil
	}
	if a.Pin == "" {
		a.Pin = "tracking_latest"
	}

	asmFid, err := uuid.Parse(a.AssemblyFileID)
	if err != nil {
		return errPayload("assembly_file_id must be a uuid: "+err.Error(), "BAD_ARGS"), nil
	}
	extPid, err := uuid.Parse(a.ExternalProjectID)
	if err != nil {
		return errPayload("external_project_id must be a uuid: "+err.Error(), "BAD_ARGS"), nil
	}
	extFid, err := uuid.Parse(a.ExternalFileID)
	if err != nil {
		return errPayload("external_file_id must be a uuid: "+err.Error(), "BAD_ARGS"), nil
	}

	// 1. Load the assembly file and verify it's an assembly.
	var kind, content string
	err = pc.Pool.QueryRow(ctx,
		`select kind, content from files
		 where id = $1 and project_id = $2 and deleted_at is null`,
		asmFid, pc.ProjectID).Scan(&kind, &content)
	if err != nil {
		return errPayload("assembly file not found: "+err.Error(), "NOT_FOUND"), nil
	}
	if kind != "assembly" {
		return errPayload(fmt.Sprintf("file kind %q is not an assembly", kind), "BAD_KIND"), nil
	}

	// 2. Verify the referenced project + file exist AND the caller has
	//    workspace-membership access to that source project. Same model the
	//    GET file endpoint enforces — we just inline it here so the tool
	//    rejects a bad ref before splicing it into JSON.
	var sourceFileExists bool
	err = pc.Pool.QueryRow(ctx, `
		select exists (
			select 1 from files f
			 where f.id = $1 and f.project_id = $2 and f.deleted_at is null
		)
	`, extFid, extPid).Scan(&sourceFileExists)
	if err != nil {
		return errPayload("source-file lookup failed: "+err.Error(), "ERROR"), nil
	}
	if !sourceFileExists {
		return errPayload("external_file_id not found in external_project_id", "NOT_FOUND"), nil
	}
	// Caller must be a member of the source project's workspace.
	var canAccess bool
	err = pc.Pool.QueryRow(ctx, `
		select exists (
			select 1
			  from projects p
			  join workspace_members wm on wm.workspace_id = p.workspace_id
			 where p.id = $1
			   and wm.user_id = $2
		)
	`, extPid, pc.UserID).Scan(&canAccess)
	if err != nil {
		return errPayload("permission lookup failed: "+err.Error(), "ERROR"), nil
	}
	if !canAccess {
		return errPayload("caller is not a member of the source project's workspace", "FORBIDDEN"), nil
	}

	// 3. Decode the assembly content (or seed an empty doc), append the new
	//    component, re-encode.
	var doc map[string]any
	if strings.TrimSpace(content) != "" {
		if err := json.Unmarshal([]byte(content), &doc); err != nil {
			return errPayload("assembly is not valid JSON: "+err.Error(), "BAD_FILE"), nil
		}
	}
	if doc == nil {
		doc = map[string]any{}
	}

	rawComponents, _ := doc["components"].([]any)
	if rawComponents == nil {
		// Tolerate the legacy `children` shape on read; we'll write
		// `components` regardless.
		if legacy, ok := doc["children"].([]any); ok {
			rawComponents = legacy
		}
	}

	// Pick a unique component id. If the caller supplied one, honour it but
	// suffix on collision.
	usedIds := map[string]bool{}
	for _, item := range rawComponents {
		if entry, ok := item.(map[string]any); ok {
			if id, ok2 := entry["id"].(string); ok2 && id != "" {
				usedIds[id] = true
			}
		}
	}
	base := a.ComponentID
	if base == "" {
		base = "ext-" + extFid.String()[:6]
	}
	id := base
	for n := 1; usedIds[id]; n++ {
		id = fmt.Sprintf("%s-%d", base, n)
	}

	// Identity transform if the caller didn't supply one.
	var transform []any
	if len(a.Transform) == 16 {
		transform = make([]any, 16)
		for i, v := range a.Transform {
			transform[i] = v
		}
	} else {
		transform = []any{
			float64(1), float64(0), float64(0), float64(0),
			float64(0), float64(1), float64(0), float64(0),
			float64(0), float64(0), float64(1), float64(0),
			float64(0), float64(0), float64(0), float64(1),
		}
	}

	newComp := map[string]any{
		"id":      id,
		"file_id": "", // empty when external_ref is the sole source
		"object_id": "",
		"transform": transform,
		"external_ref": map[string]any{
			"project_id": a.ExternalProjectID,
			"file_id":    a.ExternalFileID,
			"kind":       a.Kind,
			"pin":        a.Pin,
		},
	}
	rawComponents = append(rawComponents, newComp)
	doc["components"] = rawComponents
	delete(doc, "children")

	body, err := json.MarshalIndent(doc, "", "  ")
	if err != nil {
		return errPayload("encode failed: "+err.Error(), "ERROR"), nil
	}

	if _, err := pc.Pool.Exec(ctx,
		`update files set content = $1, updated_at = now()
		 where id = $2 and project_id = $3`,
		string(body), asmFid, pc.ProjectID); err != nil {
		return "", err
	}
	_ = recordRevisionForFile(ctx, pc, asmFid, string(body), "tool")
	return okPayload(map[string]any{
		"assembly_file_id":    a.AssemblyFileID,
		"component_id":        id,
		"external_project_id": a.ExternalProjectID,
		"external_file_id":    a.ExternalFileID,
		"kind":                a.Kind,
		"pin":                 a.Pin,
	}), nil
}
