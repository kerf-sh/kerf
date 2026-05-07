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
var Registry = []Tool{
	{Spec: listFilesSpec, Run: runListFiles},
	{Spec: readFileSpec, Run: runReadFile},
	{Spec: writeFileSpec, Write: true, Run: runWriteFile},
	{Spec: editFileSpec, Write: true, Run: runEditFile},
	{Spec: createFileSpec, Write: true, Run: runCreateFile},
	{Spec: deleteFileSpec, Write: true, Run: runDeleteFile},
	{Spec: searchCodeSpec, Run: runSearchCode},
	{Spec: importStepSpec, Write: true, Run: runImportStep},
	{Spec: validateJSCADSpec, Run: runValidateJSCAD},
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
