package handlers

// Project-type registry: single source of truth for the type → file-kinds
// mapping. Mirrored on the frontend in src/lib/projectTypes.js.
//
// v1 is intentionally **permissive** on the API surface: KindAllowedFor is
// only consulted by FileTree's "+ New" dropdown to decide which entries to
// render — the CreateFile handler still accepts any kind in any project so
// the rare cross-domain case (a quick mechanical bracket inside an
// electronics project, or vice versa) doesn't 400. This avoids surprising
// users while keeping the LLM prompt + UI defaults narrow per type.

// ProjectTypes is the authoritative list of valid project_type values.
// Order matches the picker in the New Project modal.
var ProjectTypes = []string{
	"mechanical",
	"electronics",
	"architecture",
}

// DefaultProjectType is used when an old client omits project_type.
const DefaultProjectType = "mechanical"

// ProjectTypeKinds maps each project_type to the file kinds the UI should
// surface as primary "New …" options. Folder is intentionally common across
// every type. Kinds outside this list are still creatable via the API
// (permissive model) but won't appear in the type's default create menu.
var ProjectTypeKinds = map[string][]string{
	"mechanical":   {"file", "folder", "sketch", "assembly", "drawing", "step", "feature", "part"},
	"electronics":  {"folder", "circuit", "part", "drawing", "step"},
	"architecture": {"file", "folder", "sketch", "drawing", "jscad"},
}

// ProjectTypeStarter describes the seed file the CreateProject handler emits
// for a fresh project of this type. The starter goes through the same files
// table + filesystem mirror path as any other create.
type ProjectTypeStarter struct {
	Name string // e.g. "main.jscad", "main.circuit.tsx"
	Kind string // e.g. "file", "circuit"
	// Body is the file's initial content; empty string for "create empty".
	Body string
}

// IsValidProjectType returns true for any value in the ProjectTypes slice.
// Mirrors the CHECK constraint in the SQL migration.
func IsValidProjectType(t string) bool {
	for _, v := range ProjectTypes {
		if v == t {
			return true
		}
	}
	return false
}

// KindAllowedFor reports whether the kind is in the project type's default
// allow-list. Currently only consulted by the FileTree menu via the JS
// constant; backend handlers stay permissive. Exposed so future strict-mode
// gating can flip a single switch.
func KindAllowedFor(projectType, kind string) bool {
	kinds, ok := ProjectTypeKinds[projectType]
	if !ok {
		return false
	}
	for _, k := range kinds {
		if k == kind {
			return true
		}
	}
	return false
}

// StarterFor returns the seed file for a given project type. Mechanical and
// architecture default to a JSCAD starter; electronics gets a minimal
// tscircuit starter.
func StarterFor(projectType string) ProjectTypeStarter {
	switch projectType {
	case "electronics":
		return ProjectTypeStarter{
			Name: "main.circuit.tsx",
			Kind: "circuit",
			Body: defaultCircuitTSX,
		}
	default:
		// mechanical, architecture, or any unknown fall back to the JSCAD
		// starter we've shipped from day one.
		return ProjectTypeStarter{
			Name: "main.jscad",
			Kind: "file",
			Body: defaultJSCAD,
		}
	}
}

// defaultCircuitTSX is the starter for an electronics project. Mirrors the
// minimal tscircuit "hello-world" so the user can see something render
// before the dedicated electronics editor lands.
const defaultCircuitTSX = `// Kerf: tscircuit starter. Default export is a <board /> component.
// See /docs/llm/circuit.md once the docs corpus ships an electronics page.
export default () => (
  <board width="20mm" height="20mm">
    <resistor name="R1" resistance="1k" footprint="0402" />
    <capacitor name="C1" capacitance="100nF" footprint="0402" />
    <trace from=".R1 .pin1" to=".C1 .pin1" />
  </board>
)
`
