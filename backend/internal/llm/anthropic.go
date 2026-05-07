package llm

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// Anthropic is a Provider implementation backed by api.anthropic.com.
type Anthropic struct {
	apiKey string
	http   *http.Client
}

// NewAnthropic returns a Provider that talks to the Anthropic Messages API.
func NewAnthropic(apiKey string) *Anthropic {
	return &Anthropic{
		apiKey: apiKey,
		http:   &http.Client{Timeout: 120 * time.Second},
	}
}

// Name returns "anthropic".
func (a *Anthropic) Name() string { return "anthropic" }

// Anthropic content blocks (request side).
type anthropicContentBlock struct {
	Type string `json:"type"`
	// text
	Text string `json:"text,omitempty"`
	// tool_use
	ID    string          `json:"id,omitempty"`
	Name  string          `json:"name,omitempty"`
	Input json.RawMessage `json:"input,omitempty"`
	// tool_result
	ToolUseID string `json:"tool_use_id,omitempty"`
	Content   string `json:"content,omitempty"`
	IsError   bool   `json:"is_error,omitempty"`
}

type anthropicMessage struct {
	Role    string                  `json:"role"`
	Content []anthropicContentBlock `json:"content"`
}

type anthropicTool struct {
	Name        string         `json:"name"`
	Description string         `json:"description,omitempty"`
	InputSchema map[string]any `json:"input_schema"`
}

type anthropicToolChoice struct {
	Type string `json:"type"` // "auto" | "any" | "tool" | "none"
	Name string `json:"name,omitempty"`
}

type anthropicRequest struct {
	Model       string               `json:"model"`
	System      string               `json:"system,omitempty"`
	MaxTokens   int                  `json:"max_tokens"`
	Temperature float64              `json:"temperature,omitempty"`
	Messages    []anthropicMessage   `json:"messages"`
	Tools       []anthropicTool      `json:"tools,omitempty"`
	ToolChoice  *anthropicToolChoice `json:"tool_choice,omitempty"`
}

type anthropicResponseBlock struct {
	Type  string          `json:"type"`
	Text  string          `json:"text,omitempty"`
	ID    string          `json:"id,omitempty"`
	Name  string          `json:"name,omitempty"`
	Input json.RawMessage `json:"input,omitempty"`
}

type anthropicResponse struct {
	Content    []anthropicResponseBlock `json:"content"`
	StopReason string                   `json:"stop_reason"`
	Usage      struct {
		InputTokens  int `json:"input_tokens"`
		OutputTokens int `json:"output_tokens"`
	} `json:"usage"`
	Error *struct {
		Type    string `json:"type"`
		Message string `json:"message"`
	} `json:"error"`
}

// buildAnthropicMessages converts our generic messages into Anthropic's
// content-block-flavored shape, batching consecutive tool result messages
// into a single user message of tool_result blocks (as Anthropic requires).
func buildAnthropicMessages(in []Message) []anthropicMessage {
	out := make([]anthropicMessage, 0, len(in))
	i := 0
	for i < len(in) {
		m := in[i]
		switch m.Role {
		case "user":
			out = append(out, anthropicMessage{
				Role:    "user",
				Content: []anthropicContentBlock{{Type: "text", Text: m.Content}},
			})
			i++
		case "assistant":
			blocks := make([]anthropicContentBlock, 0, 1+len(m.ToolCalls))
			if strings.TrimSpace(m.Content) != "" {
				blocks = append(blocks, anthropicContentBlock{Type: "text", Text: m.Content})
			}
			for _, tc := range m.ToolCalls {
				input := json.RawMessage(tc.ArgumentsJSON)
				if len(input) == 0 {
					input = json.RawMessage("{}")
				}
				blocks = append(blocks, anthropicContentBlock{
					Type:  "tool_use",
					ID:    tc.ID,
					Name:  tc.Name,
					Input: input,
				})
			}
			if len(blocks) == 0 {
				// Anthropic forbids empty content; emit a noop text block.
				blocks = append(blocks, anthropicContentBlock{Type: "text", Text: ""})
			}
			out = append(out, anthropicMessage{Role: "assistant", Content: blocks})
			i++
		case "tool":
			// Batch all consecutive tool messages into one user message.
			blocks := []anthropicContentBlock{}
			for i < len(in) && in[i].Role == "tool" {
				blocks = append(blocks, anthropicContentBlock{
					Type:      "tool_result",
					ToolUseID: in[i].ToolCallID,
					Content:   in[i].Content,
				})
				i++
			}
			out = append(out, anthropicMessage{Role: "user", Content: blocks})
		default:
			// system/unknown roles handled outside (system) or skipped.
			i++
		}
	}
	return out
}

// Complete posts to /v1/messages.
func (a *Anthropic) Complete(ctx context.Context, req CompleteRequest) (CompleteResponse, error) {
	maxTokens := req.MaxTokens
	if maxTokens <= 0 {
		maxTokens = 4096
	}
	// Don't send temperature unless the caller explicitly set it. Newer
	// Anthropic models (e.g. Opus 4.7) reject the field entirely with
	// "temperature is deprecated for this model".
	temperature := req.Temperature

	msgs := buildAnthropicMessages(req.Messages)

	tools := make([]anthropicTool, 0, len(req.Tools))
	for _, t := range req.Tools {
		schema := t.InputSchema
		if schema == nil {
			schema = map[string]any{"type": "object", "properties": map[string]any{}}
		}
		tools = append(tools, anthropicTool{
			Name:        t.Name,
			Description: t.Description,
			InputSchema: schema,
		})
	}

	var choice *anthropicToolChoice
	if len(tools) > 0 {
		switch req.ToolChoice {
		case "", "auto":
			choice = &anthropicToolChoice{Type: "auto"}
		case "none":
			choice = &anthropicToolChoice{Type: "none"}
		default:
			choice = &anthropicToolChoice{Type: "tool", Name: req.ToolChoice}
		}
	}

	body, err := json.Marshal(anthropicRequest{
		Model:       req.Model,
		System:      req.System,
		MaxTokens:   maxTokens,
		Temperature: temperature,
		Messages:    msgs,
		Tools:       tools,
		ToolChoice:  choice,
	})
	if err != nil {
		return CompleteResponse{}, err
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, "https://api.anthropic.com/v1/messages", bytes.NewReader(body))
	if err != nil {
		return CompleteResponse{}, err
	}
	httpReq.Header.Set("content-type", "application/json")
	httpReq.Header.Set("x-api-key", a.apiKey)
	httpReq.Header.Set("anthropic-version", "2023-06-01")

	resp, err := a.http.Do(httpReq)
	if err != nil {
		return CompleteResponse{}, fmt.Errorf("anthropic call: %w", err)
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return CompleteResponse{}, err
	}
	if resp.StatusCode >= 400 {
		return CompleteResponse{}, fmt.Errorf("anthropic %d: %s", resp.StatusCode, strings.TrimSpace(string(raw)))
	}
	var parsed anthropicResponse
	if err := json.Unmarshal(raw, &parsed); err != nil {
		return CompleteResponse{}, fmt.Errorf("decode anthropic response: %w", err)
	}
	if parsed.Error != nil {
		return CompleteResponse{}, fmt.Errorf("anthropic error: %s", parsed.Error.Message)
	}

	var sb strings.Builder
	var calls []ToolCall
	for _, blk := range parsed.Content {
		switch blk.Type {
		case "text":
			sb.WriteString(blk.Text)
		case "tool_use":
			args := string(blk.Input)
			if strings.TrimSpace(args) == "" {
				args = "{}"
			}
			calls = append(calls, ToolCall{
				ID:            blk.ID,
				Name:          blk.Name,
				ArgumentsJSON: args,
			})
		}
	}

	stopReason := "stop"
	switch parsed.StopReason {
	case "tool_use":
		stopReason = "tool_use"
	case "max_tokens":
		stopReason = "length"
	case "end_turn", "stop_sequence":
		stopReason = "stop"
	default:
		if parsed.StopReason != "" {
			stopReason = parsed.StopReason
		}
	}

	return CompleteResponse{
		Content:      sb.String(),
		ToolCalls:    calls,
		StopReason:   stopReason,
		ModelUsed:    req.Model,
		InputTokens:  parsed.Usage.InputTokens,
		OutputTokens: parsed.Usage.OutputTokens,
	}, nil
}
