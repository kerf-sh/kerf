package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/imranp/kerf/backend/internal/assembly"
	"github.com/imranp/kerf/backend/internal/llm"
)

// ----------------------- add_mate ---------------------------------

var addMateSpec = llm.ToolSpec{
	Name:        "add_mate",
	Description: "Add a geometric mate constraint to an assembly file. A mate connects two component entities (face/edge/vertex/axis) with a constraint type. Use this when the user wants to constrain two components together — e.g. \"mate these two faces coincident\", \"make these axes parallel\", \"set this distance to 10mm\". Mates are used by the SolveSpace solver to position components correctly in 3D space.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"assembly_file_id": map[string]any{
				"type":        "string",
				"description": "Target assembly file's uuid (kind='assembly').",
			},
			"mate": map[string]any{
				"type":        "object",
				"description": "The mate to add.",
				"properties": map[string]any{
					"id": map[string]any{
						"type":        "string",
						"description": "Unique identifier for this mate within the assembly.",
					},
					"type": map[string]any{
						"type": "string",
						"enum": []string{"coincident", "concentric", "parallel", "perpendicular", "distance", "angle", "tangent"},
						"description": "Geometric constraint type.",
					},
					"a": map[string]any{
						"type": "object",
						"description": "First entity reference.",
						"properties": map[string]any{
							"component_id": map[string]any{"type": "string", "description": "Component id from the assembly."},
							"feature":      map[string]any{"type": "string", "enum": []string{"face", "edge", "vertex", "axis"}},
							"feature_id":   map[string]any{"type": "string", "description": "Identifier of the specific face/edge/vertex/axis on the component."},
						},
						"required": []string{"component_id", "feature", "feature_id"},
					},
					"b": map[string]any{
						"type": "object",
						"description": "Second entity reference.",
						"properties": map[string]any{
							"component_id": map[string]any{"type": "string", "description": "Component id from the assembly."},
							"feature":      map[string]any{"type": "string", "enum": []string{"face", "edge", "vertex", "axis"}},
							"feature_id":   map[string]any{"type": "string", "description": "Identifier of the specific face/edge/vertex/axis on the component."},
						},
						"required": []string{"component_id", "feature", "feature_id"},
					},
					"value": map[string]any{
						"type":        "number",
						"description": "Numeric value for distance or angle mates. Required for distance/angle, omitted for other types.",
					},
					"unit": map[string]any{
						"type":        "string",
						"description": "Unit for distance (mm/cm/inch) or angle (deg/rad). Required for distance/angle mates.",
					},
				},
				"required": []string{"type", "a", "b"},
			},
		},
		"required": []string{"assembly_file_id", "mate"},
	},
}

type addMateArgs struct {
	AssemblyFileID string          `json:"assembly_file_id"`
	Mate          json.RawMessage  `json:"mate"`
}

func runAddMate(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a addMateArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	a.AssemblyFileID = strings.TrimSpace(a.AssemblyFileID)
	if a.AssemblyFileID == "" {
		return errPayload("assembly_file_id is required", "BAD_ARGS"), nil
	}

	asmFid, err := parseUUID(a.AssemblyFileID)
	if err != nil {
		return errPayload("assembly_file_id must be a uuid: "+err.Error(), "BAD_ARGS"), nil
	}

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

	doc, err := assembly.ParseDoc(content)
	if err != nil {
		return errPayload("failed to parse assembly: "+err.Error(), "BAD_FILE"), nil
	}

	var mateRaw map[string]any
	if err := json.Unmarshal(a.Mate, &mateRaw); err != nil {
		return errPayload("mate must be a valid JSON object: "+err.Error(), "BAD_ARGS"), nil
	}

	parsed := assembly.ParseMate(mateRaw)
	if parsed == nil {
		return errPayload("mate is missing type/a/b or has invalid values", "BAD_MATE"), nil
	}

	if err := parsed.Validate(); err != nil {
		return errPayload(err.Error(), "BAD_MATE"), nil
	}

	existingIDs := make(map[string]bool)
	for _, m := range doc.Mates {
		if m.ID != "" {
			existingIDs[m.ID] = true
		}
	}
	id := parsed.ID
	if id == "" {
		id = generateMateID(parsed.Type, existingIDs)
	} else if existingIDs[id] {
		id = generateMateID(parsed.Type, existingIDs)
	}
	parsed.ID = id

	doc.Mates = append(doc.Mates, parsed)

	jsonOut, err := assembly.SerializeDoc(doc)
	if err != nil {
		return errPayload("serialize failed: "+err.Error(), "ERROR"), nil
	}

	if _, err := pc.Pool.Exec(ctx,
		`update files set content = $1, updated_at = now()
		 where id = $2 and project_id = $3`,
		jsonOut, asmFid, pc.ProjectID); err != nil {
		return "", err
	}
	_ = recordRevisionForFile(ctx, pc, asmFid, jsonOut, "tool")

	return okPayload(map[string]any{
		"assembly_file_id": a.AssemblyFileID,
		"mate_id":         parsed.ID,
		"type":            parsed.Type,
	}), nil
}

func generateMateID(mateType assembly.MateType, existing map[string]bool) string {
	base := string(mateType) + "-mate"
	if !existing[base] {
		return base
	}
	for i := 1; ; i++ {
		id := fmt.Sprintf("%s-%d", base, i)
		if !existing[id] {
			return id
		}
	}
}

// ----------------------- delete_mate ---------------------------------

var deleteMateSpec = llm.ToolSpec{
	Name:        "delete_mate",
	Description: "Remove a geometric mate constraint from an assembly file by its id.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"assembly_file_id": map[string]any{
				"type":        "string",
				"description": "Target assembly file's uuid.",
			},
			"mate_id": map[string]any{
				"type":        "string",
				"description": "The id of the mate to remove.",
			},
		},
		"required": []string{"assembly_file_id", "mate_id"},
	},
}

type deleteMateArgs struct {
	AssemblyFileID string `json:"assembly_file_id"`
	MateID        string `json:"mate_id"`
}

func runDeleteMate(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a deleteMateArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	a.AssemblyFileID = strings.TrimSpace(a.AssemblyFileID)
	a.MateID = strings.TrimSpace(a.MateID)
	if a.AssemblyFileID == "" || a.MateID == "" {
		return errPayload("assembly_file_id and mate_id are required", "BAD_ARGS"), nil
	}

	asmFid, err := parseUUID(a.AssemblyFileID)
	if err != nil {
		return errPayload("assembly_file_id must be a uuid: "+err.Error(), "BAD_ARGS"), nil
	}

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

	doc, err := assembly.ParseDoc(content)
	if err != nil {
		return errPayload("failed to parse assembly: "+err.Error(), "BAD_FILE"), nil
	}

	found := false
	newMates := make([]*assembly.Mate, 0, len(doc.Mates))
	for _, m := range doc.Mates {
		if m.ID != a.MateID {
			newMates = append(newMates, m)
		} else {
			found = true
		}
	}
	if !found {
		return errPayload("mate not found: "+a.MateID, "NOT_FOUND"), nil
	}

	doc.Mates = newMates

	jsonOut, err := assembly.SerializeDoc(doc)
	if err != nil {
		return errPayload("serialize failed: "+err.Error(), "ERROR"), nil
	}

	if _, err := pc.Pool.Exec(ctx,
		`update files set content = $1, updated_at = now()
		 where id = $2 and project_id = $3`,
		jsonOut, asmFid, pc.ProjectID); err != nil {
		return "", err
	}
	_ = recordRevisionForFile(ctx, pc, asmFid, jsonOut, "tool")

	return okPayload(map[string]any{
		"assembly_file_id": a.AssemblyFileID,
		"deleted_mate_id":  a.MateID,
	}), nil
}

// ----------------------- list_mates ---------------------------------

var listMatesSpec = llm.ToolSpec{
	Name:        "list_mates",
	Description: "List all mate constraints in an assembly file.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"assembly_file_id": map[string]any{
				"type":        "string",
				"description": "Target assembly file's uuid.",
			},
		},
		"required": []string{"assembly_file_id"},
	},
}

type listMatesArgs struct {
	AssemblyFileID string `json:"assembly_file_id"`
}

func runListMates(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a listMatesArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	a.AssemblyFileID = strings.TrimSpace(a.AssemblyFileID)
	if a.AssemblyFileID == "" {
		return errPayload("assembly_file_id is required", "BAD_ARGS"), nil
	}

	asmFid, err := parseUUID(a.AssemblyFileID)
	if err != nil {
		return errPayload("assembly_file_id must be a uuid: "+err.Error(), "BAD_ARGS"), nil
	}

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

	doc, err := assembly.ParseDoc(content)
	if err != nil {
		return errPayload("failed to parse assembly: "+err.Error(), "BAD_FILE"), nil
	}

	mates := make([]map[string]any, len(doc.Mates))
	for i, m := range doc.Mates {
		mates[i] = assembly.SerializeMate(m)
	}

	return okPayload(map[string]any{
		"assembly_file_id": a.AssemblyFileID,
		"mates":           mates,
		"count":           len(mates),
	}), nil
}

func parseUUID(s string) ([16]byte, error) {
	var u [16]byte
	_, err := fmt.Sscanf(s, "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
		&u[0], &u[1], &u[2], &u[3], &u[4], &u[5], &u[6], &u[7],
		&u[8], &u[9], &u[10], &u[11], &u[12], &u[13], &u[14], &u[15])
	if err != nil {
		return u, fmt.Errorf("invalid uuid: %s", s)
	}
	return u, nil
}