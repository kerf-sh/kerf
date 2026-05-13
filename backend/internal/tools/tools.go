// Package tools implements the agent's file/project tools.
//
// Each tool is a Go function that runs synchronously inside the request
// handler. The agent loop calls Execute(toolCall) for every tool call the LLM
// emits, persists the result back as a `role='tool'` chat_message, then loops
// until the model returns no more tool calls (or hits the iteration cap).
package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/internal/llm"
	"github.com/imranp/kerf/backend/internal/storage"
)

// ProjectCtx is the request-scoped context every tool runs against.
type ProjectCtx struct {
	Pool       *pgxpool.Pool
	Storage    storage.Storage
	ProjectID  uuid.UUID
	UserID     uuid.UUID
	Role       string // "owner" | "editor" | "viewer"
	HTTPClient *http.Client
	// FileRevisionsMax bounds per-file revision retention; 0 → use default.
	FileRevisionsMax int
}

// Executor runs a single tool call. It returns a JSON string suitable to send
// back to the model as the tool result. Tool-level errors should be surfaced
// inside that JSON (with a "code" field) — the function-level error return is
// reserved for unexpected infrastructure failures.
type Executor func(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error)

// Tool ties a name + schema + handler + permission together.
type Tool struct {
	Spec      llm.ToolSpec
	Write     bool // true = editor+ only; false = viewer+ ok
	Run       Executor
}

// Registry is the static list of tools the agent loop can dispatch to.
//
// Following the LLM tool-surface consolidation, per-element drawing /
// assembly / feature / circuit / part-mutation tools are gone — the
// model edits those JSON / TSX files directly via write_file /
// edit_file after consulting the embedded authoring docs at
// /docs/llm/<kind>.md (search_kerf_docs → read_file).
var Registry = []Tool{
	// File ops.
	{Spec: listFilesSpec, Run: runListFiles},
	{Spec: readFileSpec, Run: runReadFile},
	{Spec: writeFileSpec, Write: true, Run: runWriteFile},
	{Spec: editFileSpec, Write: true, Run: runEditFile},
	{Spec: createFileSpec, Write: true, Run: runCreateFile},
	{Spec: deleteFileSpec, Write: true, Run: runDeleteFile},
	{Spec: searchCodeSpec, Run: runSearchCode},
	{Spec: importStepSpec, Write: true, Run: runImportStep},

	// Object ops (bracket-matched edits inside a JSCAD Part).
	{Spec: duplicateObjectSpec, Write: true, Run: runDuplicateObject},
	{Spec: deleteObjectSpec, Write: true, Run: runDeleteObject},

	// Validation + queries.
	{Spec: validateJSCADSpec, Run: runValidateJSCAD},
	{Spec: generateBOMSpec, Run: runGenerateBOM},

	// Scaffolding for kinds that need a canonical seed.
	{Spec: createSketchSpec, Write: true, Run: runCreateSketch},
	{Spec: createFeatureSpec, Write: true, Run: runCreateFeature},
	{Spec: createPartSpec, Write: true, Run: runCreatePart},
	{Spec: createCircuitSpec, Write: true, Run: runCreateCircuit},
	{Spec: addProbeSpec, Write: true, Run: runAddProbe},
	{Spec: removeProbeSpec, Write: true, Run: runRemoveProbe},
	{Spec: renameProbeSpec, Write: true, Run: runRenameProbe},

	// Equations: project-level named parameters.
	{Spec: readEquationsSpec, Run: runReadEquations},
	{Spec: setEquationSpec, Write: true, Run: runSetEquation},

	// Configurations: per-file parameter overrides (variants).
	{Spec: addConfigurationSpec, Write: true, Run: runAddConfiguration},
	{Spec: setActiveConfigSpec, Write: true, Run: runSetActiveConfig},

	// Authoring docs the LLM searches before editing non-.jscad kinds.
	{Spec: searchKerfDocsSpec, Run: runSearchKerfDocs},

	// Revisions / undo.
	{Spec: listRevisionsSpec, Run: runListRevisions},
	{Spec: restoreRevisionSpec, Write: true, Run: runRestoreRevision},

	// Phase 4a — surfacing feature ops the LLM can append to .feature files.
	{Spec: featureSweep2Spec, Write: true, Run: runFeatureSweep2},
	{Spec: featureNetworkSrfSpec, Write: true, Run: runFeatureNetworkSrf},
	{Spec: featureBlendSrfSpec, Write: true, Run: runFeatureBlendSrf},

	// FEM analysis.
	{Spec: femRunSpec, Write: true, Run: runFEMRun},
	{Spec: femJobStatusSpec, Run: runFEMJobStatus},

	// SPICE simulation.
	{Spec: runSimulationSpec, Write: true, Run: runSimulation},
	{Spec: simJobStatusSpec, Run: runSimJobStatus},

	// Topology optimization (SIMP via FEniCSx).
	{Spec: topoRunSpec, Write: true, Run: runTopoRun},

	// 3D assembly mates (SolveSpace solver).
	{Spec: addMateSpec, Write: true, Run: runAddMate},
	{Spec: deleteMateSpec, Write: true, Run: runDeleteMate},
	{Spec: listMatesSpec, Run: runListMates},

	// Tolerance stack-up (1D worst-case + RSS, Monte-Carlo).
	{Spec: toleranceStackSpec, Run: runToleranceStack},
	{Spec: toleranceMonteCarloSpec, Run: runToleranceMonteCarlo},
}

// Specs returns the JSON schemas of every tool a given role is allowed to use.
func Specs(role string) []llm.ToolSpec {
	out := make([]llm.ToolSpec, 0, len(Registry))
	for _, t := range Registry {
		if t.Write && role == "viewer" {
			continue
		}
		out = append(out, t.Spec)
	}
	return out
}

// Find returns the tool with a given name, or nil.
func Find(name string) *Tool {
	for i := range Registry {
		if Registry[i].Spec.Name == name {
			return &Registry[i]
		}
	}
	return nil
}

// Execute looks up a tool by name and runs it, enforcing role.
// On not-found / forbidden / handler error it returns a JSON-encoded error
// payload (so the model sees the failure cleanly) and a nil error.
func Execute(ctx context.Context, pc ProjectCtx, name string, args json.RawMessage) string {
	tool := Find(name)
	if tool == nil {
		return errPayload("unknown tool "+name, "UNKNOWN_TOOL")
	}
	if tool.Write && pc.Role == "viewer" {
		return errPayload("viewers cannot use "+name, "FORBIDDEN")
	}
	if len(args) == 0 {
		args = json.RawMessage("{}")
	}
	out, err := tool.Run(ctx, pc, args)
	if err != nil {
		return errPayload(err.Error(), "ERROR")
	}
	return out
}

// errPayload is the canonical JSON error result returned to the model.
func errPayload(msg, code string) string {
	b, _ := json.Marshal(map[string]string{"error": msg, "code": code})
	return string(b)
}

// okPayload marshals a result map; falls back to errPayload on encoding fail.
func okPayload(v any) string {
	b, err := json.Marshal(v)
	if err != nil {
		return errPayload(fmt.Sprintf("encode result: %v", err), "ERROR")
	}
	return string(b)
}
