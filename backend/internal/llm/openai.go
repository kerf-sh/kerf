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

// OpenAICompatible is a Provider implementation for any service that speaks
// the OpenAI /chat/completions wire format (currently OpenAI itself and
// Moonshot).
type OpenAICompatible struct {
	name    string
	baseURL string
	apiKey  string
	http    *http.Client
}

// NewOpenAICompatible returns a Provider for any OpenAI-compatible endpoint.
func NewOpenAICompatible(name, baseURL, apiKey string) *OpenAICompatible {
	return &OpenAICompatible{
		name:    name,
		baseURL: strings.TrimRight(baseURL, "/"),
		apiKey:  apiKey,
		http:    &http.Client{Timeout: 120 * time.Second},
	}
}

// NewOpenAI returns a Provider for api.openai.com.
func NewOpenAI(apiKey string) *OpenAICompatible {
	return NewOpenAICompatible("openai", "https://api.openai.com/v1", apiKey)
}

// NewMoonshot returns a Provider for api.moonshot.ai.
func NewMoonshot(apiKey string) *OpenAICompatible {
	return NewOpenAICompatible("moonshot", "https://api.moonshot.ai/v1", apiKey)
}

// Name returns the provider name passed at construction.
func (o *OpenAICompatible) Name() string { return o.name }

type openaiToolFunctionCall struct {
	Name      string `json:"name"`
	Arguments string `json:"arguments"`
}

type openaiToolCall struct {
	ID       string                 `json:"id"`
	Type     string                 `json:"type"`
	Function openaiToolFunctionCall `json:"function"`
}

type openaiMessage struct {
	Role       string           `json:"role"`
	Content    string           `json:"content"`
	ToolCalls  []openaiToolCall `json:"tool_calls,omitempty"`
	ToolCallID string           `json:"tool_call_id,omitempty"`
	Name       string           `json:"name,omitempty"`
}

type openaiToolFunctionDecl struct {
	Name        string         `json:"name"`
	Description string         `json:"description,omitempty"`
	Parameters  map[string]any `json:"parameters"`
}

type openaiTool struct {
	Type     string                 `json:"type"`
	Function openaiToolFunctionDecl `json:"function"`
}

type openaiRequest struct {
	Model       string          `json:"model"`
	Messages    []openaiMessage `json:"messages"`
	MaxTokens   int             `json:"max_tokens,omitempty"`
	Temperature float64         `json:"temperature,omitempty"`
	Tools       []openaiTool    `json:"tools,omitempty"`
	ToolChoice  any             `json:"tool_choice,omitempty"`
}

type openaiResponse struct {
	Choices []struct {
		FinishReason string `json:"finish_reason"`
		Message      struct {
			Role      string           `json:"role"`
			Content   string           `json:"content"`
			ToolCalls []openaiToolCall `json:"tool_calls"`
		} `json:"message"`
	} `json:"choices"`
	Usage struct {
		PromptTokens     int `json:"prompt_tokens"`
		CompletionTokens int `json:"completion_tokens"`
	} `json:"usage"`
	Error *struct {
		Message string `json:"message"`
		Type    string `json:"type"`
	} `json:"error"`
}

func buildOpenAIMessages(system string, in []Message) []openaiMessage {
	out := make([]openaiMessage, 0, len(in)+1)
	if system != "" {
		out = append(out, openaiMessage{Role: "system", Content: system})
	}
	for _, m := range in {
		switch m.Role {
		case "user":
			out = append(out, openaiMessage{Role: "user", Content: m.Content})
		case "system":
			out = append(out, openaiMessage{Role: "system", Content: m.Content})
		case "assistant":
			oc := make([]openaiToolCall, 0, len(m.ToolCalls))
			for _, tc := range m.ToolCalls {
				args := tc.ArgumentsJSON
				if strings.TrimSpace(args) == "" {
					args = "{}"
				}
				oc = append(oc, openaiToolCall{
					ID:   tc.ID,
					Type: "function",
					Function: openaiToolFunctionCall{
						Name:      tc.Name,
						Arguments: args,
					},
				})
			}
			out = append(out, openaiMessage{
				Role:      "assistant",
				Content:   m.Content,
				ToolCalls: oc,
			})
		case "tool":
			out = append(out, openaiMessage{
				Role:       "tool",
				Content:    m.Content,
				ToolCallID: m.ToolCallID,
			})
		}
	}
	return out
}

// Complete posts to ${baseURL}/chat/completions.
func (o *OpenAICompatible) Complete(ctx context.Context, req CompleteRequest) (CompleteResponse, error) {
	maxTokens := req.MaxTokens
	if maxTokens <= 0 {
		maxTokens = 4096
	}
	temperature := req.Temperature
	if temperature == 0 {
		temperature = 0.7
	}

	msgs := buildOpenAIMessages(req.System, req.Messages)

	tools := make([]openaiTool, 0, len(req.Tools))
	for _, t := range req.Tools {
		params := t.InputSchema
		if params == nil {
			params = map[string]any{"type": "object", "properties": map[string]any{}}
		}
		tools = append(tools, openaiTool{
			Type: "function",
			Function: openaiToolFunctionDecl{
				Name:        t.Name,
				Description: t.Description,
				Parameters:  params,
			},
		})
	}

	var toolChoice any
	if len(tools) > 0 {
		switch req.ToolChoice {
		case "", "auto":
			toolChoice = "auto"
		case "none":
			toolChoice = "none"
		default:
			toolChoice = map[string]any{
				"type":     "function",
				"function": map[string]any{"name": req.ToolChoice},
			}
		}
	}

	body, err := json.Marshal(openaiRequest{
		Model:       req.Model,
		Messages:    msgs,
		MaxTokens:   maxTokens,
		Temperature: temperature,
		Tools:       tools,
		ToolChoice:  toolChoice,
	})
	if err != nil {
		return CompleteResponse{}, err
	}

	url := o.baseURL + "/chat/completions"
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return CompleteResponse{}, err
	}
	httpReq.Header.Set("content-type", "application/json")
	httpReq.Header.Set("authorization", "Bearer "+o.apiKey)

	resp, err := o.http.Do(httpReq)
	if err != nil {
		return CompleteResponse{}, fmt.Errorf("%s call: %w", o.name, err)
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return CompleteResponse{}, err
	}
	if resp.StatusCode >= 400 {
		return CompleteResponse{}, fmt.Errorf("%s %d: %s", o.name, resp.StatusCode, strings.TrimSpace(string(raw)))
	}
	var parsed openaiResponse
	if err := json.Unmarshal(raw, &parsed); err != nil {
		return CompleteResponse{}, fmt.Errorf("decode %s response: %w", o.name, err)
	}
	if parsed.Error != nil {
		return CompleteResponse{}, fmt.Errorf("%s error: %s", o.name, parsed.Error.Message)
	}
	if len(parsed.Choices) == 0 {
		return CompleteResponse{}, fmt.Errorf("%s: no choices in response", o.name)
	}
	choice := parsed.Choices[0]

	var calls []ToolCall
	for _, tc := range choice.Message.ToolCalls {
		args := tc.Function.Arguments
		if strings.TrimSpace(args) == "" {
			args = "{}"
		}
		calls = append(calls, ToolCall{
			ID:            tc.ID,
			Name:          tc.Function.Name,
			ArgumentsJSON: args,
		})
	}

	stopReason := "stop"
	switch choice.FinishReason {
	case "tool_calls", "function_call":
		stopReason = "tool_use"
	case "length":
		stopReason = "length"
	case "stop", "":
		stopReason = "stop"
	default:
		stopReason = choice.FinishReason
	}

	return CompleteResponse{
		Content:      choice.Message.Content,
		ToolCalls:    calls,
		StopReason:   stopReason,
		ModelUsed:    req.Model,
		InputTokens:  parsed.Usage.PromptTokens,
		OutputTokens: parsed.Usage.CompletionTokens,
	}, nil
}
