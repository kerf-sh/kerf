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

const SystemPrompt = "You are an expert JSCAD (@jscad/modeling) author helping a user iterate on a CAD model. When asked to modify a part, return the FULL updated file contents inside a ```jscad code block. Reference parts by their `id`."

// Client is a thin wrapper around the Anthropic Messages API. If APIKey is
// empty, calls return a stub message so the rest of the system can run.
type Client struct {
	APIKey string
	Model  string
	HTTP   *http.Client
}

func New(apiKey, model string) *Client {
	if model == "" {
		model = "claude-opus-4-7"
	}
	return &Client{
		APIKey: apiKey,
		Model:  model,
		HTTP:   &http.Client{Timeout: 60 * time.Second},
	}
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

type apiMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type apiRequest struct {
	Model     string       `json:"model"`
	System    string       `json:"system"`
	MaxTokens int          `json:"max_tokens"`
	Messages  []apiMessage `json:"messages"`
}

type apiResponse struct {
	Content []struct {
		Type string `json:"type"`
		Text string `json:"text"`
	} `json:"content"`
	Error *struct {
		Type    string `json:"type"`
		Message string `json:"message"`
	} `json:"error"`
}

// Complete asks the model to respond to the given user content + parts. The
// thread history (previous user/assistant turns, EXCLUDING the new user message)
// is provided so the model has context.
func (c *Client) Complete(ctx context.Context, history []HistoryMessage, userContent string, parts []PartContext) (string, error) {
	if c.APIKey == "" {
		return "LLM not configured — set ANTHROPIC_API_KEY", nil
	}

	final := buildUserMessage(userContent, parts)

	msgs := make([]apiMessage, 0, len(history)+1)
	for _, m := range history {
		role := m.Role
		if role != "user" && role != "assistant" {
			continue
		}
		msgs = append(msgs, apiMessage{Role: role, Content: m.Content})
	}
	msgs = append(msgs, apiMessage{Role: "user", Content: final})

	body, err := json.Marshal(apiRequest{
		Model:     c.Model,
		System:    SystemPrompt,
		MaxTokens: 4096,
		Messages:  msgs,
	})
	if err != nil {
		return "", err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, "https://api.anthropic.com/v1/messages", bytes.NewReader(body))
	if err != nil {
		return "", err
	}
	req.Header.Set("content-type", "application/json")
	req.Header.Set("x-api-key", c.APIKey)
	req.Header.Set("anthropic-version", "2023-06-01")

	resp, err := c.HTTP.Do(req)
	if err != nil {
		return "", fmt.Errorf("anthropic call: %w", err)
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}
	if resp.StatusCode >= 400 {
		return "", fmt.Errorf("anthropic %d: %s", resp.StatusCode, strings.TrimSpace(string(raw)))
	}
	var parsed apiResponse
	if err := json.Unmarshal(raw, &parsed); err != nil {
		return "", fmt.Errorf("decode anthropic response: %w", err)
	}
	if parsed.Error != nil {
		return "", fmt.Errorf("anthropic error: %s", parsed.Error.Message)
	}
	var sb strings.Builder
	for _, blk := range parsed.Content {
		if blk.Type == "text" {
			sb.WriteString(blk.Text)
		}
	}
	out := sb.String()
	if out == "" {
		out = "(empty response)"
	}
	return out, nil
}

func buildUserMessage(userContent string, parts []PartContext) string {
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
