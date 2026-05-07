package llm

import "fmt"

// Config bundles the per-provider API keys plus the default model ID. A
// blank API key disables that provider.
type Config struct {
	AnthropicAPIKey string
	OpenAIAPIKey    string
	MoonshotAPIKey  string
	GeminiAPIKey    string
	DefaultModel    string
}

// Registry routes catalog model IDs to their concrete Provider, gated by
// whether the corresponding API key is configured.
type Registry struct {
	providers    map[string]Provider // keyed by provider name
	defaultModel string
}

// NewRegistry constructs a Registry from the given Config. Providers without
// an API key are simply omitted from the map so Resolve can return a
// targeted error.
func NewRegistry(cfg Config) *Registry {
	providers := map[string]Provider{}
	if cfg.AnthropicAPIKey != "" {
		providers["anthropic"] = NewAnthropic(cfg.AnthropicAPIKey)
	}
	if cfg.OpenAIAPIKey != "" {
		providers["openai"] = NewOpenAI(cfg.OpenAIAPIKey)
	}
	if cfg.MoonshotAPIKey != "" {
		providers["moonshot"] = NewMoonshot(cfg.MoonshotAPIKey)
	}
	if cfg.GeminiAPIKey != "" {
		providers["gemini"] = NewGemini(cfg.GeminiAPIKey)
	}
	defaultModel := cfg.DefaultModel
	if defaultModel == "" {
		defaultModel = "claude-opus-4-7"
	}
	return &Registry{
		providers:    providers,
		defaultModel: defaultModel,
	}
}

// Available returns the catalog filtered to models whose provider has an
// API key. The returned slice preserves catalog order.
func (r *Registry) Available() []ModelInfo {
	out := make([]ModelInfo, 0, len(Catalog))
	for _, m := range Catalog {
		if _, ok := r.providers[m.Provider]; ok {
			out = append(out, m)
		}
	}
	return out
}

// Default returns the default model ID.
func (r *Registry) Default() string { return r.defaultModel }

// HasAny returns true if at least one provider is configured.
func (r *Registry) HasAny() bool { return len(r.providers) > 0 }

// Resolve looks up a catalog entry by model ID, finds the provider, and
// returns it along with the canonical model ID to send upstream. Returns an
// error if the model isn't in the catalog or its provider has no API key.
func (r *Registry) Resolve(modelID string) (Provider, string, error) {
	info := LookupModel(modelID)
	if info == nil {
		return nil, "", fmt.Errorf("unknown model %q", modelID)
	}
	p, ok := r.providers[info.Provider]
	if !ok {
		return nil, "", fmt.Errorf("provider %q for model %q is not configured", info.Provider, modelID)
	}
	return p, info.ID, nil
}
