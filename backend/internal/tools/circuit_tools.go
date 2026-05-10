package tools

// Circuit scaffolding — create_circuit only.
//
// Per-element tools (add_component, connect, set_component_prop) were
// removed when the LLM tool surface was consolidated. The model now
// authors / mutates `.circuit.tsx` files by editing the TSX source via
// write_file / edit_file after consulting docs/llm/circuit.md.

import (
	"context"
	"encoding/json"
	"fmt"
	"regexp"
	"strings"

	"github.com/google/uuid"

	"github.com/imranp/kerf/backend/internal/llm"
)

// Default seed for a new .circuit.tsx file. Mirrors src/lib/circuitRunner.js
// DEFAULT_CIRCUIT so create_circuit + the frontend's "New Circuit" produce
// identical starting points.
const defaultCircuitSeed = `import { Circuit } from "tscircuit"

// Kerf: default export is a JSX element OR a Circuit instance. The editor
// renders the schematic, PCB, and 3D views in their respective tabs.
export default (
  <board width="20mm" height="20mm">
  </board>
)
`

// ---------------------------------------------------------------------------
// create_circuit

var createCircuitSpec = llm.ToolSpec{
	Name: "create_circuit",
	Description: "Create a new tscircuit electronics-design file (`.circuit.tsx`). The user authors components + traces in JSX; the editor compiles to schematic, PCB, and 3D views via tscircuit. After creation, edit the TSX source via write_file / edit_file (see docs/llm/circuit.md for component vocabulary).",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"path": map[string]any{
				"type":        "string",
				"description": "Absolute path of the new circuit file. Should end with .circuit.tsx; the suffix is appended if absent.",
			},
			"name": map[string]any{
				"type":        "string",
				"description": "Optional human-readable name (currently unused at the file level — kept for parity with other create_* tools).",
			},
			"width_mm": map[string]any{
				"type":        "number",
				"description": "Initial board width in millimetres. Defaults to 20mm.",
			},
			"height_mm": map[string]any{
				"type":        "number",
				"description": "Initial board height in millimetres. Defaults to 20mm.",
			},
		},
		"required": []string{"path"},
	},
}

type createCircuitArgs struct {
	Path     string  `json:"path"`
	Name     string  `json:"name"`
	WidthMM  float64 `json:"width_mm"`
	HeightMM float64 `json:"height_mm"`
}

func runCreateCircuit(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a createCircuitArgs
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
	if !strings.HasSuffix(strings.ToLower(clean), ".circuit.tsx") {
		// Append the canonical suffix. The frontend's fileKindFor uses the
		// `.circuit.tsx` extension to route to the CircuitEditor.
		clean = clean + ".circuit.tsx"
		parts = splitPath(clean)
	}
	if rp, _ := resolvePath(ctx, pc, clean); rp.Exists {
		return errPayload("path already exists", "EXISTS"), nil
	}

	w := a.WidthMM
	h := a.HeightMM
	if w <= 0 {
		w = 20
	}
	if h <= 0 {
		h = 20
	}
	body := fmt.Sprintf(`import { Circuit } from "tscircuit"

// Kerf: default export is a JSX element OR a Circuit instance. The editor
// renders the schematic, PCB, and 3D views in their respective tabs.
export default (
  <board width="%gmm" height="%gmm">
  </board>
)
`, w, h)
	// Tolerate the unused defaultCircuitSeed for symmetry with the runner —
	// it's the same template, but lets the LLM observe the file shape via the
	// constant if we ever expose it.
	_ = defaultCircuitSeed

	parent, err := ensureFolders(ctx, pc, parts[:len(parts)-1])
	if err != nil {
		return "", err
	}
	leaf := parts[len(parts)-1]
	var newID uuid.UUID
	err = pc.Pool.QueryRow(ctx,
		`insert into files(project_id, parent_id, name, kind, content)
		 values ($1,$2,$3,'circuit',$4)
		 returning id`,
		pc.ProjectID, parent, leaf, body).Scan(&newID)
	if err != nil {
		return "", err
	}
	_ = recordRevisionForFile(ctx, pc, newID, body, "tool")
	return okPayload(map[string]any{
		"path":      clean,
		"id":        newID.String(),
		"width_mm":  w,
		"height_mm": h,
	}), nil
}

// ---------------------------------------------------------------------------
// add_probe
//
// Splices a `// @kerf-probe NAME=<n> KIND=<V|I> PORT=<id>` source-comment
// line into a `.circuit.tsx` file just before the closing `</board>` tag.
// Mirrors the `appendProbe` helper in `src/lib/circuitTSX.js` so the LLM
// tool side matches the schematic Probe button's on-disk format byte-for-
// byte; the frontend's `circuitProbes.injectProbeRecords` then synthesizes
// `simulation_probe` records into the compiled CircuitJSON for
// `circuitToSpice` to emit `.print` directives.

var addProbeSpec = llm.ToolSpec{
	Name:        "add_probe",
	Description: "Add a SPICE simulation probe to a `.circuit.tsx` file. The probe references a schematic port (V) or component (I) and becomes a `.print` directive in the generated SPICE netlist.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"circuit_file_id": map[string]any{
				"type":        "string",
				"description": "UUID of the `.circuit.tsx` file (kind='circuit') to splice the probe into.",
			},
			"name": map[string]any{
				"type":        "string",
				"description": "Probe label (regex `[A-Za-z0-9_-]+`). Surfaces in plot legends + the SPICE `.print` directive.",
			},
			"kind": map[string]any{
				"type":        "string",
				"enum":        []string{"V", "I"},
				"description": "Probe kind. 'V' measures voltage at a schematic port (`target_id` = port id). 'I' measures current through a component (`target_id` = component id).",
			},
			"target_id": map[string]any{
				"type":        "string",
				"description": "Port id (for kind='V') or component id (for kind='I') that the probe attaches to.",
			},
		},
		"required": []string{"circuit_file_id", "name", "kind", "target_id"},
	},
}

type addProbeArgs struct {
	CircuitFileID string `json:"circuit_file_id"`
	Name          string `json:"name"`
	Kind          string `json:"kind"`
	TargetID      string `json:"target_id"`
}

// probeNameRe gates the NAME field. Mirrors the schematic Probe dialog's
// allowed-character set (alphanumeric + underscore + dash). Spaces are
// rejected here so the comment line stays single-token-parseable by
// `parseProbes`.
var probeNameRe = regexp.MustCompile(`^[A-Za-z0-9_-]+$`)

// spliceProbeComment ports `appendProbe` from src/lib/circuitTSX.js to Go.
// Inserts a `// @kerf-probe …` line just before the LAST `</board>` tag,
// preserving the indentation of that closing tag (mirrors
// `appendComponent`'s indent-detection logic).
//
// Returns ("", false) if no `</board>` tag is found — the caller surfaces a
// BAD_ARGS so the LLM doesn't silently no-op.
func spliceProbeComment(source, name, kind, targetID string) (string, bool) {
	close := strings.LastIndex(source, "</board>")
	if close < 0 {
		return "", false
	}
	// Indent of the `</board>` line (whitespace between the previous newline
	// and the closing tag) — mirrors the JS helper.
	prevNl := strings.LastIndex(source[:close], "\n")
	indent := "  "
	if prevNl >= 0 {
		raw := source[prevNl+1 : close]
		ws := strings.IndexFunc(raw, func(r rune) bool { return r != ' ' && r != '\t' })
		if ws == -1 {
			indent = raw
		} else {
			indent = raw[:ws]
		}
	}
	comment := fmt.Sprintf("// @kerf-probe NAME=%s KIND=%s PORT=%s", name, kind, targetID)
	insertion := indent + "  " + comment + "\n" + indent
	return source[:close] + insertion + source[close:], true
}

func runAddProbe(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a addProbeArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	if strings.TrimSpace(a.CircuitFileID) == "" {
		return errPayload("circuit_file_id is required", "BAD_ARGS"), nil
	}
	if strings.TrimSpace(a.Name) == "" {
		return errPayload("name is required", "BAD_ARGS"), nil
	}
	if !probeNameRe.MatchString(a.Name) {
		return errPayload("name must match [A-Za-z0-9_-]+ (no spaces or punctuation)", "BAD_ARGS"), nil
	}
	if a.Kind != "V" && a.Kind != "I" {
		return errPayload("kind must be 'V' (voltage at port) or 'I' (current through component)", "BAD_ARGS"), nil
	}
	if strings.TrimSpace(a.TargetID) == "" {
		return errPayload("target_id is required", "BAD_ARGS"), nil
	}
	fileID, err := uuid.Parse(a.CircuitFileID)
	if err != nil {
		return errPayload("circuit_file_id must be a uuid: "+err.Error(), "BAD_ARGS"), nil
	}

	var name, kind, content string
	err = pc.Pool.QueryRow(ctx,
		`select name, kind, content from files
		 where id = $1 and project_id = $2 and deleted_at is null`,
		fileID, pc.ProjectID).Scan(&name, &kind, &content)
	if err != nil {
		return errPayload("circuit file not found", "NOT_FOUND"), nil
	}
	if kind != "circuit" {
		return errPayload("file kind "+kind+" is not 'circuit' (expected a .circuit.tsx file)", "BAD_ARGS"), nil
	}

	updated, ok := spliceProbeComment(content, a.Name, a.Kind, a.TargetID)
	if !ok {
		return errPayload("circuit file has no </board> closer to splice the probe before", "BAD_ARGS"), nil
	}

	if _, err := pc.Pool.Exec(ctx,
		`update files set content = $1, updated_at = now()
		 where id = $2 and project_id = $3`,
		updated, fileID, pc.ProjectID); err != nil {
		return "", err
	}
	_ = recordRevisionForFile(ctx, pc, fileID, updated, "tool")

	return okPayload(map[string]any{
		"ok":      true,
		"name":    a.Name,
		"kind":    a.Kind,
		"port":    a.TargetID,
		"file_id": fileID.String(),
		"content": updated,
	}), nil
}

// ---------------------------------------------------------------------------
// remove_probe
//
// Inverse of add_probe: the `remove_probe` tool deletes the
// `// @kerf-probe NAME=<name> KIND=… PORT=…` comment line from a
// `.circuit.tsx` source. Mirrors `removeProbe` in src/lib/circuitTSX.js —
// tolerant on missing probe (returns source unchanged so the LLM can call
// `remove_probe` idempotently without driving a BAD_ARGS loop).

// removeProbeComment ports `removeProbe` from src/lib/circuitTSX.js to Go.
// Finds the line whose NAME field equals `name` (regex anchored on the NAME
// token, with regex meta-characters in `name` escaped) and excises the entire
// line including its trailing newline. If no such line exists, returns
// `source` unchanged — caller surfaces that as a non-error no-op.
func removeProbeComment(source, name string) string {
	if source == "" || name == "" {
		return source
	}
	safe := regexp.QuoteMeta(name)
	// Match: line-leading whitespace, `// @kerf-probe`, anything-but-newline,
	// `NAME=<safe>` as a whole token, anything-but-newline, optional CR/LF.
	re := regexp.MustCompile(`(?m)^[ \t]*//\s*@kerf-probe\s+[^\n\r]*\bNAME\s*=\s*` + safe + `\b[^\n\r]*(?:\r?\n)?`)
	return re.ReplaceAllString(source, "")
}

// renameProbeComment ports `renameProbe` from src/lib/circuitTSX.js to Go.
// Rewrites the NAME= field of the line whose current NAME matches `oldName`
// to `newName`, preserving KIND/PORT and surrounding whitespace. No-op on
// missing probe.
func renameProbeComment(source, oldName, newName string) string {
	if source == "" || oldName == "" || newName == "" {
		return source
	}
	safeOld := regexp.QuoteMeta(oldName)
	re := regexp.MustCompile(`(?m)(^[ \t]*//\s*@kerf-probe\s+[^\n\r]*\bNAME\s*=\s*)` + safeOld + `(\b[^\n\r]*)`)
	return re.ReplaceAllString(source, "${1}"+newName+"${2}")
}

var removeProbeSpec = llm.ToolSpec{
	Name:        "remove_probe",
	Description: "Remove a SPICE simulation probe from a `.circuit.tsx` file by name. The matching `// @kerf-probe NAME=<name> …` comment line is deleted. Tolerant: succeeds without error if no such probe exists.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"circuit_file_id": map[string]any{
				"type":        "string",
				"description": "UUID of the `.circuit.tsx` file (kind='circuit') to remove the probe from.",
			},
			"name": map[string]any{
				"type":        "string",
				"description": "Probe label to remove (regex `[A-Za-z0-9_-]+`). Must match the NAME field of an existing `// @kerf-probe` line for the removal to take effect.",
			},
		},
		"required": []string{"circuit_file_id", "name"},
	},
}

type removeProbeArgs struct {
	CircuitFileID string `json:"circuit_file_id"`
	Name          string `json:"name"`
}

func runRemoveProbe(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a removeProbeArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	if strings.TrimSpace(a.CircuitFileID) == "" {
		return errPayload("circuit_file_id is required", "BAD_ARGS"), nil
	}
	if strings.TrimSpace(a.Name) == "" {
		return errPayload("name is required", "BAD_ARGS"), nil
	}
	if !probeNameRe.MatchString(a.Name) {
		return errPayload("name must match [A-Za-z0-9_-]+ (no spaces or punctuation)", "BAD_ARGS"), nil
	}
	fileID, err := uuid.Parse(a.CircuitFileID)
	if err != nil {
		return errPayload("circuit_file_id must be a uuid: "+err.Error(), "BAD_ARGS"), nil
	}

	var fname, kind, content string
	err = pc.Pool.QueryRow(ctx,
		`select name, kind, content from files
		 where id = $1 and project_id = $2 and deleted_at is null`,
		fileID, pc.ProjectID).Scan(&fname, &kind, &content)
	if err != nil {
		return errPayload("circuit file not found", "NOT_FOUND"), nil
	}
	if kind != "circuit" {
		return errPayload("file kind "+kind+" is not 'circuit' (expected a .circuit.tsx file)", "BAD_ARGS"), nil
	}

	updated := removeProbeComment(content, a.Name)
	changed := updated != content

	if changed {
		if _, err := pc.Pool.Exec(ctx,
			`update files set content = $1, updated_at = now()
			 where id = $2 and project_id = $3`,
			updated, fileID, pc.ProjectID); err != nil {
			return "", err
		}
		_ = recordRevisionForFile(ctx, pc, fileID, updated, "tool")
	}

	return okPayload(map[string]any{
		"ok":      true,
		"name":    a.Name,
		"file_id": fileID.String(),
		"removed": changed,
		"content": updated,
	}), nil
}

// ---------------------------------------------------------------------------
// rename_probe
//
// The `rename_probe` tool rewrites the NAME field on an existing
// `// @kerf-probe` line. Mirrors `renameProbe` in src/lib/circuitTSX.js.
// Tolerant on missing probe — `rename_probe` is a no-op then.

var renameProbeSpec = llm.ToolSpec{
	Name:        "rename_probe",
	Description: "Rename a SPICE simulation probe in a `.circuit.tsx` file. Rewrites the NAME field of the matching `// @kerf-probe` line, leaving KIND/PORT untouched. Tolerant: succeeds without error if no such probe exists.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"circuit_file_id": map[string]any{
				"type":        "string",
				"description": "UUID of the `.circuit.tsx` file (kind='circuit') containing the probe.",
			},
			"old_name": map[string]any{
				"type":        "string",
				"description": "Current probe label (regex `[A-Za-z0-9_-]+`).",
			},
			"new_name": map[string]any{
				"type":        "string",
				"description": "New probe label (regex `[A-Za-z0-9_-]+`). Must differ from old_name.",
			},
		},
		"required": []string{"circuit_file_id", "old_name", "new_name"},
	},
}

type renameProbeArgs struct {
	CircuitFileID string `json:"circuit_file_id"`
	OldName       string `json:"old_name"`
	NewName       string `json:"new_name"`
}

func runRenameProbe(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a renameProbeArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	if strings.TrimSpace(a.CircuitFileID) == "" {
		return errPayload("circuit_file_id is required", "BAD_ARGS"), nil
	}
	if strings.TrimSpace(a.OldName) == "" {
		return errPayload("old_name is required", "BAD_ARGS"), nil
	}
	if strings.TrimSpace(a.NewName) == "" {
		return errPayload("new_name is required", "BAD_ARGS"), nil
	}
	if !probeNameRe.MatchString(a.OldName) {
		return errPayload("old_name must match [A-Za-z0-9_-]+ (no spaces or punctuation)", "BAD_ARGS"), nil
	}
	if !probeNameRe.MatchString(a.NewName) {
		return errPayload("new_name must match [A-Za-z0-9_-]+ (no spaces or punctuation)", "BAD_ARGS"), nil
	}
	if a.OldName == a.NewName {
		return errPayload("old_name and new_name are identical (no-op rename)", "BAD_ARGS"), nil
	}
	fileID, err := uuid.Parse(a.CircuitFileID)
	if err != nil {
		return errPayload("circuit_file_id must be a uuid: "+err.Error(), "BAD_ARGS"), nil
	}

	var fname, kind, content string
	err = pc.Pool.QueryRow(ctx,
		`select name, kind, content from files
		 where id = $1 and project_id = $2 and deleted_at is null`,
		fileID, pc.ProjectID).Scan(&fname, &kind, &content)
	if err != nil {
		return errPayload("circuit file not found", "NOT_FOUND"), nil
	}
	if kind != "circuit" {
		return errPayload("file kind "+kind+" is not 'circuit' (expected a .circuit.tsx file)", "BAD_ARGS"), nil
	}

	updated := renameProbeComment(content, a.OldName, a.NewName)
	changed := updated != content

	if changed {
		if _, err := pc.Pool.Exec(ctx,
			`update files set content = $1, updated_at = now()
			 where id = $2 and project_id = $3`,
			updated, fileID, pc.ProjectID); err != nil {
			return "", err
		}
		_ = recordRevisionForFile(ctx, pc, fileID, updated, "tool")
	}

	return okPayload(map[string]any{
		"ok":       true,
		"old_name": a.OldName,
		"new_name": a.NewName,
		"file_id":  fileID.String(),
		"renamed":  changed,
		"content":  updated,
	}), nil
}
