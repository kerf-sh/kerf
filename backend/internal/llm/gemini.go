package llm

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// Gemini is a Provider implementation backed by Google's Generative Language
// API (`generativelanguage.googleapis.com`).
type Gemini struct {
	apiKey string
	http   *http.Client
}

// NewGemini returns a Provider for the Gemini API.
func NewGemini(apiKey string) *Gemini {
	return &Gemini{
		apiKey: apiKey,
		http:   &http.Client{Timeout: 60 * time.Second},
	}
}

// Name returns "gemini".
func (g *Gemini) Name() string { return "gemini" }

type geminiPart struct {
	Text string `json:"text"`
}

type geminiContent struct {
	Role  string       `json:"role,omitempty"`
	Parts []geminiPart `json:"parts"`
}

type geminiGenerationConfig struct {
	MaxOutputTokens int     `json:"maxOutputTokens,omitempty"`
	Temperature     float64 `json:"temperature,omitempty"`
}

type geminiRequest struct {
	Contents          []geminiContent         `json:"contents"`
	SystemInstruction *geminiContent          `json:"systemInstruction,omitempty"`
	GenerationConfig  *geminiGenerationConfig `json:"generationConfig,omitempty"`
}

type geminiResponse struct {
	Candidates []struct {
		Content struct {
			Role  string       `json:"role"`
			Parts []geminiPart `json:"parts"`
		} `json:"content"`
	} `json:"candidates"`
	UsageMetadata struct {
		PromptTokenCount     int `json:"promptTokenCount"`
		CandidatesTokenCount int `json:"candidatesTokenCount"`
	} `json:"usageMetadata"`
	Error *struct {
		Code    int    `json:"code"`
		Message string `json:"message"`
		Status  string `json:"status"`
	} `json:"error"`
}

// Complete posts to /v1beta/models/{model}:generateContent.
func (g *Gemini) Complete(ctx context.Context, req CompleteRequest) (CompleteResponse, error) {
	maxTokens := req.MaxTokens
	if maxTokens <= 0 {
		maxTokens = 4096
	}
	temperature := req.Temperature

	contents := make([]geminiContent, 0, len(req.Messages))
	for _, m := range req.Messages {
		role := m.Role
		switch role {
		case "user":
			role = "user"
		case "assistant":
			role = "model"
		default:
			// skip system / unknown — system goes via systemInstruction.
			continue
		}
		contents = append(contents, geminiContent{
			Role:  role,
			Parts: []geminiPart{{Text: m.Content}},
		})
	}

	body := geminiRequest{
		Contents: contents,
		GenerationConfig: &geminiGenerationConfig{
			MaxOutputTokens: maxTokens,
			Temperature:     temperature,
		},
	}
	if req.System != "" {
		body.SystemInstruction = &geminiContent{
			Parts: []geminiPart{{Text: req.System}},
		}
	}

	raw, err := json.Marshal(body)
	if err != nil {
		return CompleteResponse{}, err
	}

	endpoint := fmt.Sprintf("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s",
		url.PathEscape(req.Model), url.QueryEscape(g.apiKey))

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(raw))
	if err != nil {
		return CompleteResponse{}, err
	}
	httpReq.Header.Set("content-type", "application/json")

	resp, err := g.http.Do(httpReq)
	if err != nil {
		return CompleteResponse{}, fmt.Errorf("gemini call: %w", err)
	}
	defer resp.Body.Close()
	respBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return CompleteResponse{}, err
	}
	if resp.StatusCode >= 400 {
		return CompleteResponse{}, fmt.Errorf("gemini %d: %s", resp.StatusCode, strings.TrimSpace(string(respBytes)))
	}
	var parsed geminiResponse
	if err := json.Unmarshal(respBytes, &parsed); err != nil {
		return CompleteResponse{}, fmt.Errorf("decode gemini response: %w", err)
	}
	if parsed.Error != nil {
		return CompleteResponse{}, fmt.Errorf("gemini error: %s", parsed.Error.Message)
	}
	if len(parsed.Candidates) == 0 {
		return CompleteResponse{}, fmt.Errorf("gemini: no candidates in response")
	}
	var sb strings.Builder
	for _, p := range parsed.Candidates[0].Content.Parts {
		sb.WriteString(p.Text)
	}
	out := sb.String()
	if out == "" {
		out = "(empty response)"
	}
	return CompleteResponse{
		Content:      out,
		ModelUsed:    req.Model,
		InputTokens:  parsed.UsageMetadata.PromptTokenCount,
		OutputTokens: parsed.UsageMetadata.CandidatesTokenCount,
	}, nil
}
