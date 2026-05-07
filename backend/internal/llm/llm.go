package llm

import (
	"context"
	"fmt"
	"strings"
)

// SystemPrompt is the default system prompt sent with every LLM call.
const SystemPrompt = "You are an expert JSCAD (@jscad/modeling) author helping a user iterate on a CAD model. " +
	"You have file tools. Use them eagerly to inspect and modify the user's CAD files. " +
	"Always read a file before editing it. After making changes, briefly summarize what you did. " +
	"Don't quote the full file back unless asked. " +
	"When asked to modify a part, prefer surgical edits via edit_file; only fall back to write_file if a wholesale rewrite is required. " +
	"Reference parts by their `id`."

// ToolCall is a single tool invocation requested by the assistant.
type ToolCall struct {
	ID            string // provider-issued (or synthesized) id
	Name          string
	ArgumentsJSON string // raw JSON object string
}

// ToolSpec describes a tool the model may call.
type ToolSpec struct {
	Name        string
	Description string
	InputSchema map[string]any // JSON Schema (object)
}

// Message is a single chat message in a Complete request.
type Message struct {
	Role       string     // "user" | "assistant" | "system" | "tool"
	Content    string     // for user/assistant/system; result JSON for "tool"
	ToolCalls  []ToolCall // for assistant-with-tools
	ToolCallID string     // for role="tool", the tool_use id this responds to
}

// CompleteRequest is the provider-agnostic request shape.
type CompleteRequest struct {
	Model       string
	System      string
	Messages    []Message
	MaxTokens   int     // default 4096
	Temperature float64 // default 0.7
	Tools       []ToolSpec
	ToolChoice  string // "auto" | "none" | a specific tool name; default "auto" when Tools non-empty
}

// CompleteResponse is the provider-agnostic response shape.
type CompleteResponse struct {
	Content      string
	ToolCalls    []ToolCall
	StopReason   string // "stop" | "tool_use" | "length" | ...
	ModelUsed    string
	InputTokens  int
	OutputTokens int
}

// Provider is the interface every LLM backend implements.
type Provider interface {
	Complete(ctx context.Context, req CompleteRequest) (CompleteResponse, error)
	Name() string
}

// PartContext is a single referenced part (file path + part id + file contents).
type PartContext struct {
	FilePath string
	PartID   string
	Content  string
}

// HistoryMessage is a prior chat message in the thread.
type HistoryMessage struct {
	Role    string // "user" or "assistant"
	Content string
}

// BuildUserMessage formats the user's message together with any referenced
// part contexts. Exported so handlers can reuse the same wrapping.
func BuildUserMessage(userContent string, parts []PartContext) string {
	if len(parts) == 0 {
		return userContent
	}
	var sb strings.Builder
	sb.WriteString(userContent)
	sb.WriteString("\n\n<context>\n")
	for _, p := range parts {
		sb.WriteString(fmt.Sprintf("<file path=%q part_id=%q>\n", p.FilePath, p.PartID))
		sb.WriteString(p.Content)
		if !strings.HasSuffix(p.Content, "\n") {
			sb.WriteString("\n")
		}
		sb.WriteString("</file>\n")
	}
	sb.WriteString("</context>\n")
	return sb.String()
}
