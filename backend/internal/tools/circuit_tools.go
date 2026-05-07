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
