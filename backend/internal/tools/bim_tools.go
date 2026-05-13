package tools

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"

	"github.com/google/uuid"

	"github.com/imranp/kerf/backend/internal/llm"
)

type bimDoc struct {
	Version   int               `json:"version"`
	Name      string            `json:"name,omitempty"`
	Site      *bimSite          `json:"site,omitempty"`
	Buildings []bimBuilding     `json:"buildings,omitempty"`
	Zones     []bimZone         `json:"zones,omitempty"`
	Metadata  map[string]any   `json:"metadata,omitempty"`
}

type bimSite struct {
	Name        string    `json:"name,omitempty"`
	Latitude    float64   `json:"latitude,omitempty"`
	Longitude   float64   `json:"longitude,omitempty"`
	Elevation   float64   `json:"elevation,omitempty"`
}

type bimBuilding struct {
	Name        string        `json:"name,omitempty"`
	Levels      []bimLevel    `json:"levels,omitempty"`
}

type bimLevel struct {
	Name    string  `json:"name,omitempty"`
	Elevation float64 `json:"elevation,omitempty"`
	Height  float64 `json:"height,omitempty"`
	Walls   []bimWall   `json:"walls,omitempty"`
	Slabs   []bimSlab   `json:"slabs,omitempty"`
	Openings []bimOpening `json:"openings,omitempty"`
	Spaces  []bimSpace  `json:"spaces,omitempty"`
}

type bimWall struct {
	ID       string  `json:"id"`
	Name     string  `json:"name,omitempty"`
	FromX    float64 `json:"from_x"`
	FromY    float64 `json:"from_y"`
	ToX      float64 `json:"to_x"`
	ToY      float64 `json:"to_y"`
	Height   float64 `json:"height"`
	ThickX   float64 `json:"thickness_x,omitempty"`
	ThickY   float64 `json:"thickness_y,omitempty"`
	LevelRef string  `json:"level_ref,omitempty"`
}

type bimSlab struct {
	ID        string        `json:"id"`
	Name      string        `json:"name,omitempty"`
	Polygon   []bimPoint2D  `json:"polygon"`
	Thickness float64       `json:"thickness"`
	LevelRef  string        `json:"level_ref,omitempty"`
}

type bimPoint2D struct {
	X float64 `json:"x"`
	Y float64 `json:"y"`
}

type bimOpening struct {
	ID       string  `json:"id"`
	Type     string  `json:"type"`
	FromX    float64 `json:"from_x"`
	FromY    float64 `json:"from_y"`
	ToX      float64 `json:"to_x"`
	ToY      float64 `json:"to_y"`
	Height   float64 `json:"height,omitempty"`
	Width    float64 `json:"width,omitempty"`
	LevelRef string  `json:"level_ref,omitempty"`
}

type bimSpace struct {
	ID        string   `json:"id"`
	Name      string   `json:"name,omitempty"`
	Polygon   []bimPoint2D `json:"polygon,omitempty"`
	ZoneRef   string   `json:"zone_ref,omitempty"`
	LevelRef  string   `json:"level_ref,omitempty"`
}

type bimZone struct {
	ID    string `json:"id"`
	Name  string `json:"name,omitempty"`
	Color string `json:"color,omitempty"`
}

func serializeBIM(d bimDoc) (string, error) {
	if d.Version == 0 {
		d.Version = 1
	}
	b, err := json.MarshalIndent(d, "", "  ")
	if err != nil {
		return "", err
	}
	return string(b), nil
}

var createBIMSpec = llm.ToolSpec{
	Name:        "create_bim",
	Description: "Create a new empty .bim architecture file (IFC4 BIM model). After creation, populate by editing the JSON via write_file / edit_file. Consult docs/llm/bim.md for the vocabulary. Refuses non-.bim paths.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"path": map[string]any{
				"type":        "string",
				"description": "Absolute path of the new .bim file.",
			},
			"name": map[string]any{
				"type":        "string",
				"description": "Optional human-readable name.",
			},
			"site": map[string]any{
				"type":        "object",
				"description": "Optional site object { name, latitude, longitude, elevation }.",
			},
		},
		"required": []string{"path"},
	},
}

type createBIMArgs struct {
	Path string     `json:"path"`
	Name string     `json:"name"`
	Site *bimSite   `json:"site"`
}

func runCreateBIM(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a createBIMArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	clean, err := normalizePath(a.Path)
	if err != nil {
		return errPayload(err.Error(), "BAD_ARGS"), nil
	}
	if !strings.HasSuffix(strings.ToLower(clean), ".bim") {
		return errPayload("path must end with .bim", "BAD_KIND"), nil
	}
	if rp, _ := resolvePath(ctx, pc, clean); rp.Exists {
		return errPayload("path already exists", "EXISTS"), nil
	}
	parts := splitPath(clean)
	parent, err := ensureFolders(ctx, pc, parts[:len(parts)-1])
	if err != nil {
		return "", err
	}
	leaf := parts[len(parts)-1]
	doc := bimDoc{
		Version: 1,
		Name:    a.Name,
		Site:    a.Site,
	}
	body, err := serializeBIM(doc)
	if err != nil {
		return errPayload("encode: "+err.Error(), "ERROR"), nil
	}
	var newID uuid.UUID
	err = pc.Pool.QueryRow(ctx,
		`insert into files(project_id, parent_id, name, kind, content)
		 values ($1,$2,$3,'bim',$4)
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

var readBIMSpec = llm.ToolSpec{
	Name:        "read_bim",
	Description: "Read a .bim architecture file and return its full JSON body. Use this before compile_bim_to_ifc or when editing.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"path": map[string]any{
				"type":        "string",
				"description": "Absolute path of the .bim file to read.",
			},
		},
		"required": []string{"path"},
	},
}

type readBIMArgs struct {
	Path string `json:"path"`
}

func runReadBIM(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a readBIMArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	clean, err := normalizePath(a.Path)
	if err != nil {
		return errPayload(err.Error(), "BAD_ARGS"), nil
	}
	row := pc.Pool.QueryRow(ctx,
		`select content from files
		 where project_id=$1 and path=$2 and kind='bim'`,
		pc.ProjectID, clean)
	var content []byte
	if err := row.Scan(&content); err != nil {
		return errPayload("file not found or not a .bim", "NOT_FOUND"), nil
	}
	return okPayload(map[string]any{
		"path":    clean,
		"content": string(content),
	}), nil
}

var compileBIMToIFCSpec = llm.ToolSpec{
	Name:        "compile_bim_to_ifc",
	Description: "Compile a .bim architecture file to an IFC4 .ifc binary using IfcOpenShell. The .ifc is stored in the same project and returned as a base64-encoded blob.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"bim_path": map[string]any{
				"type":        "string",
				"description": "Absolute path of the .bim source file.",
			},
		},
		"required": []string{"bim_path"},
	},
}

type compileBIMToIFCArgs struct {
	BIMPath string `json:"bim_path"`
}

func runCompileBIMToIFC(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a compileBIMToIFCArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	clean, err := normalizePath(a.BIMPath)
	if err != nil {
		return errPayload(err.Error(), "BAD_ARGS"), nil
	}

	var content []byte
	err = pc.Pool.QueryRow(ctx,
		`select content from files
		 where project_id=$1 and path=$2 and kind='bim'`,
		pc.ProjectID, clean).Scan(&content)
	if err != nil {
		return errPayload("bim file not found", "NOT_FOUND"), nil
	}

	pyworkerURL := getPyworkerURL() + "/compile-bim"
	reqBody := map[string]any{"bim_content": string(content)}
	reqBodyBytes, _ := json.Marshal(reqBody)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, pyworkerURL, bytes.NewReader(reqBodyBytes))
	if err != nil {
		return errPayload("build request failed: "+err.Error(), "ERROR"), nil
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := pc.HTTPClient.Do(req)
	if err != nil {
		return errPayload("compile worker unavailable: "+err.Error(), "WORKER_ERROR"), nil
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return errPayload(fmt.Sprintf("compile worker returned status %d", resp.StatusCode), "WORKER_ERROR"), nil
	}
	var result struct {
		IFCBase64 string `json:"ifc_base64"`
		IFCPath   string `json:"ifc_path"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return errPayload("invalid compile response: "+err.Error(), "ERROR"), nil
	}

	ifcLeaf := strings.TrimSuffix(clean, ".bim") + ".ifc"
	var newID uuid.UUID
	ifcBytes, err := base64.StdEncoding.DecodeString(result.IFCBase64)
	if err != nil {
		return errPayload("invalid ifc response", "ERROR"), nil
	}
	err = pc.Pool.QueryRow(ctx,
		`insert into files(project_id, parent_id, name, kind, content)
		 values ($1, $2, $3, 'ifc', $4)
		 returning id`,
		pc.ProjectID, splitPath(clean)[len(splitPath(clean))-1], ifcLeaf, ifcBytes).Scan(&newID)
	if err != nil {
		return "", err
	}

	return okPayload(map[string]any{
		"ifc_path": ifcLeaf,
		"ifc_id":   newID.String(),
	}), nil
}

var readIFCSpec = llm.ToolSpec{
	Name:        "read_ifc",
	Description: "Read the raw binary content of an existing .ifc file from the project, returned as base64. Use to inspect or re-export.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"path": map[string]any{
				"type":        "string",
				"description": "Absolute path of the .ifc file.",
			},
		},
		"required": []string{"path"},
	},
}

type readIFCArgs struct {
	Path string `json:"path"`
}

func runReadIFC(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a readIFCArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	clean, err := normalizePath(a.Path)
	if err != nil {
		return errPayload(err.Error(), "BAD_ARGS"), nil
	}
	var content []byte
	err = pc.Pool.QueryRow(ctx,
		`select content from files
		 where project_id=$1 and path=$2 and kind='ifc'`,
		pc.ProjectID, clean).Scan(&content)
	if err != nil {
		return errPayload("ifc file not found", "NOT_FOUND"), nil
	}
	return okPayload(map[string]any{
		"path":        clean,
		"ifc_base64":  base64.StdEncoding.EncodeToString(content),
	}), nil
}