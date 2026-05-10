package tools

// Material tools — consume `.material` engineering-property files and
// attach materials to Parts.
//
// Three tools live here:
//   - `read_material`: parse a .material file by absolute path and return
//     the structured JSON shape (mechanical / thermal / physical groups).
//   - `find_material_by_name`: fuzzy-search every .material file in the
//     project by name + common_names, returning the top-N matches.
//   - `set_part_material`: write a `material_path` field onto a Part
//     file's JSON so downstream consumers (FEM, drawing callouts, BOM)
//     can resolve the material.
//
// File shape mirrors src/lib/material.js — keep the two definitions in
// sync. See backend/internal/llm/docs/material.md for the full schema.

import (
	"context"
	"encoding/json"
	"fmt"
	"sort"
	"strings"

	"github.com/google/uuid"

	"github.com/imranp/kerf/backend/internal/llm"
)

// ----- material document type ----------------------------------------------

// materialDoc mirrors the on-disk JSON shape. We use *float64 rather than
// float64 + omitempty so `null` round-trips literally — the contract is
// "unknown values render as —"; encoding/json's default float zero would
// silently turn an unknown into 0 and bork downstream consumers (FEM
// using ρ=0 as a "real" density would be catastrophic).
type materialDoc struct {
	Version     int      `json:"version"`
	Name        string   `json:"name"`
	Category    string   `json:"category,omitempty"`
	CommonNames []string `json:"common_names,omitempty"`
	ColorHex    string   `json:"color_hex,omitempty"`

	Mechanical materialMechanical `json:"mechanical"`
	Thermal    materialThermal    `json:"thermal"`
	Physical   materialPhysical   `json:"physical"`

	Callout string `json:"callout,omitempty"`
	Notes   string `json:"notes,omitempty"`
}

type materialMechanical struct {
	EGPa          *float64 `json:"E_GPa"`
	GGPa          *float64 `json:"G_GPa"`
	Nu            *float64 `json:"nu"`
	YieldMPa      *float64 `json:"yield_MPa"`
	UltimateMPa   *float64 `json:"ultimate_MPa"`
	ElongationPct *float64 `json:"elongation_pct"`
}

type materialThermal struct {
	AlphaPerK *float64 `json:"alpha_per_K"`
	KWmK      *float64 `json:"k_W_mK"`
	CpJkgK    *float64 `json:"cp_J_kgK"`
	TMinC     *float64 `json:"T_min_C"`
	TMaxC     *float64 `json:"T_max_C"`
}

type materialPhysical struct {
	RhoKgM3 *float64 `json:"rho_kg_m3"`
}

// parseMaterialContent is tolerant: missing / malformed JSON falls back
// to a defaulted doc with version=1.
func parseMaterialContent(s string) materialDoc {
	var d materialDoc
	if strings.TrimSpace(s) != "" {
		_ = json.Unmarshal([]byte(s), &d)
	}
	if d.Version == 0 {
		d.Version = 1
	}
	if d.CommonNames == nil {
		d.CommonNames = []string{}
	}
	return d
}

// ----- read_material -------------------------------------------------------

var readMaterialSpec = llm.ToolSpec{
	Name: "read_material",
	Description: "Read a .material engineering-property file by absolute path. Returns the parsed JSON shape with mechanical / thermal / physical groups (E, G, ν, yield, ultimate, elongation; α, k, cₚ, T_min, T_max; ρ). Unknown numeric values come back as null. See docs/llm/material.md for the full schema.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"path": map[string]any{
				"type":        "string",
				"description": "Absolute path of the .material file.",
			},
		},
		"required": []string{"path"},
	},
}

type readMaterialArgs struct {
	Path string `json:"path"`
}

func runReadMaterial(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a readMaterialArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	rp, err := resolvePath(ctx, pc, a.Path)
	if err != nil || !rp.Exists {
		return errPayload("file not found: "+a.Path, "NOT_FOUND"), nil
	}
	if rp.Kind != "material" && !strings.HasSuffix(strings.ToLower(rp.Name), ".material") {
		return errPayload("path is not a .material file (kind="+rp.Kind+")", "BAD_KIND"), nil
	}
	var content string
	if err := pc.Pool.QueryRow(ctx,
		`select content from files where id = $1 and project_id = $2`,
		rp.ID, pc.ProjectID).Scan(&content); err != nil {
		return "", err
	}
	doc := parseMaterialContent(content)
	return okPayload(map[string]any{
		"path":     a.Path,
		"id":       rp.ID.String(),
		"material": doc,
	}), nil
}

// ----- find_material_by_name ----------------------------------------------

var findMaterialByNameSpec = llm.ToolSpec{
	Name: "find_material_by_name",
	Description: "Fuzzy-search every .material file in the project by name + common_names. Returns up to N matches (default 5) ranked by closeness. Use this before set_part_material when the user gives a colloquial name (\"6061 aluminum\", \"mild steel\") and you need the canonical /library/materials/<...>.material path.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"query": map[string]any{
				"type":        "string",
				"description": "Free-form material name to search for. Matches are case-insensitive substring + common-name lookups.",
			},
			"max": map[string]any{
				"type":        "integer",
				"description": "Max matches to return (default 5, capped at 25).",
			},
		},
		"required": []string{"query"},
	},
}

type findMaterialArgs struct {
	Query string `json:"query"`
	Max   int    `json:"max"`
}

type materialMatch struct {
	Path        string `json:"path"`
	ID          string `json:"id"`
	Name        string `json:"name"`
	Category    string `json:"category,omitempty"`
	Score       int    `json:"score"`
	MatchedName string `json:"matched_name,omitempty"`
}

// scoreMaterial returns a positive integer when q matches the candidate
// strings, with higher = better. Zero means "no match". Heuristic:
//   - exact (case-insensitive) name match → 1000
//   - exact common_name match              → 800
//   - name starts with q                   → 500
//   - common_name starts with q            → 400
//   - q is a substring of name             → 300 - len(name)/4
//   - q is a substring of any common_name  → 200 - len(cn)/4
// Tie-breaks favor shorter strings (more specific match).
func scoreMaterial(q string, doc materialDoc) (int, string) {
	q = strings.ToLower(strings.TrimSpace(q))
	if q == "" {
		return 0, ""
	}
	name := strings.ToLower(doc.Name)
	if name == q {
		return 1000, doc.Name
	}
	for _, cn := range doc.CommonNames {
		if strings.ToLower(cn) == q {
			return 800, cn
		}
	}
	if strings.HasPrefix(name, q) {
		return 500, doc.Name
	}
	for _, cn := range doc.CommonNames {
		if strings.HasPrefix(strings.ToLower(cn), q) {
			return 400, cn
		}
	}
	if strings.Contains(name, q) {
		s := 300 - len(name)/4
		if s < 1 {
			s = 1
		}
		return s, doc.Name
	}
	for _, cn := range doc.CommonNames {
		if strings.Contains(strings.ToLower(cn), q) {
			s := 200 - len(cn)/4
			if s < 1 {
				s = 1
			}
			return s, cn
		}
	}
	return 0, ""
}

func runFindMaterialByName(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a findMaterialArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	if strings.TrimSpace(a.Query) == "" {
		return errPayload("query is required", "BAD_ARGS"), nil
	}
	if a.Max <= 0 {
		a.Max = 5
	}
	if a.Max > 25 {
		a.Max = 25
	}

	rows, err := pc.Pool.Query(ctx,
		`select id, content from files
		 where project_id = $1 and kind = 'material' and deleted_at is null`,
		pc.ProjectID)
	if err != nil {
		return "", err
	}
	defer rows.Close()

	type cand struct {
		id      uuid.UUID
		content string
	}
	var cs []cand
	for rows.Next() {
		var c cand
		if err := rows.Scan(&c.id, &c.content); err != nil {
			return "", err
		}
		cs = append(cs, c)
	}

	matches := make([]materialMatch, 0, len(cs))
	for _, c := range cs {
		doc := parseMaterialContent(c.content)
		score, hit := scoreMaterial(a.Query, doc)
		if score == 0 {
			continue
		}
		path, err := pathFromFileID(ctx, pc, c.id)
		if err != nil {
			continue
		}
		matches = append(matches, materialMatch{
			Path:        path,
			ID:          c.id.String(),
			Name:        doc.Name,
			Category:    doc.Category,
			Score:       score,
			MatchedName: hit,
		})
	}

	sort.SliceStable(matches, func(i, j int) bool {
		if matches[i].Score != matches[j].Score {
			return matches[i].Score > matches[j].Score
		}
		return matches[i].Name < matches[j].Name
	})
	if len(matches) > a.Max {
		matches = matches[:a.Max]
	}
	return okPayload(map[string]any{
		"query":   a.Query,
		"matches": matches,
	}), nil
}

// ----- set_part_material ---------------------------------------------------

var setPartMaterialSpec = llm.ToolSpec{
	Name: "set_part_material",
	Description: "Attach a material to a Part by setting its `material_path` field. Both paths are absolute. Validates that material_path resolves to a kind='material' file before writing. Use find_material_by_name first if you only have a colloquial material name. Pass material_path=\"\" (empty) to clear the field.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"part_path": map[string]any{
				"type":        "string",
				"description": "Absolute path of the .part file to mutate.",
			},
			"material_path": map[string]any{
				"type":        "string",
				"description": "Absolute path of the .material file. Pass \"\" to clear an existing material_path.",
			},
		},
		"required": []string{"part_path", "material_path"},
	},
}

type setPartMaterialArgs struct {
	PartPath     string `json:"part_path"`
	MaterialPath string `json:"material_path"`
}

func runSetPartMaterial(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a setPartMaterialArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	if strings.TrimSpace(a.PartPath) == "" {
		return errPayload("part_path is required", "BAD_ARGS"), nil
	}

	// Resolve the Part.
	partRP, err := resolvePath(ctx, pc, a.PartPath)
	if err != nil || !partRP.Exists {
		return errPayload("part file not found: "+a.PartPath, "NOT_FOUND"), nil
	}
	if partRP.Kind != "part" {
		return errPayload("part_path is not a .part file (kind="+partRP.Kind+")", "BAD_KIND"), nil
	}

	// If a material_path is supplied, validate it resolves to a kind=material.
	cleanMaterialPath := strings.TrimSpace(a.MaterialPath)
	if cleanMaterialPath != "" {
		matRP, err := resolvePath(ctx, pc, cleanMaterialPath)
		if err != nil || !matRP.Exists {
			return errPayload("material file not found: "+cleanMaterialPath, "NOT_FOUND"), nil
		}
		if matRP.Kind != "material" {
			return errPayload("material_path is not a .material file (kind="+matRP.Kind+")", "BAD_KIND"), nil
		}
	}

	// Load the Part doc, mutate, write back. We round-trip through a
	// generic map[string]any rather than partDoc so any forward-compat
	// fields the user has on the Part survive verbatim — we only touch
	// the `material_path` field.
	var content string
	if err := pc.Pool.QueryRow(ctx,
		`select content from files where id = $1 and project_id = $2`,
		partRP.ID, pc.ProjectID).Scan(&content); err != nil {
		return "", err
	}
	var doc map[string]any
	if strings.TrimSpace(content) == "" {
		doc = map[string]any{"version": 1}
	} else if err := json.Unmarshal([]byte(content), &doc); err != nil {
		return errPayload("part file has invalid JSON: "+err.Error(), "BAD_PART"), nil
	}
	if doc == nil {
		doc = map[string]any{"version": 1}
	}
	if cleanMaterialPath == "" {
		delete(doc, "material_path")
	} else {
		doc["material_path"] = cleanMaterialPath
	}

	body, err := json.MarshalIndent(doc, "", "  ")
	if err != nil {
		return errPayload(fmt.Sprintf("encode part: %v", err), "ERROR"), nil
	}
	if _, err := pc.Pool.Exec(ctx,
		`update files set content = $1, updated_at = now() where id = $2 and project_id = $3`,
		string(body), partRP.ID, pc.ProjectID); err != nil {
		return "", err
	}
	_ = recordRevisionForFile(ctx, pc, partRP.ID, string(body), "tool")

	return okPayload(map[string]any{
		"part_path":     a.PartPath,
		"part_id":       partRP.ID.String(),
		"material_path": cleanMaterialPath,
		"cleared":       cleanMaterialPath == "",
	}), nil
}
