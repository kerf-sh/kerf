package llm

// ModelInfo describes a single model in the built-in catalog.
type ModelInfo struct {
	ID            string `json:"id"`
	Provider      string `json:"provider"`
	Label         string `json:"label"`
	ContextWindow int    `json:"context_window,omitempty"`
}

// Catalog is the built-in list of models we know how to route. The provider
// field maps each entry to one of the four Provider implementations.
var Catalog = []ModelInfo{
	// Anthropic
	{ID: "claude-opus-4-7", Provider: "anthropic", Label: "Claude Opus 4.7", ContextWindow: 200_000},
	{ID: "claude-sonnet-4-6", Provider: "anthropic", Label: "Claude Sonnet 4.6", ContextWindow: 200_000},
	{ID: "claude-haiku-4-5", Provider: "anthropic", Label: "Claude Haiku 4.5", ContextWindow: 200_000},

	// OpenAI
	{ID: "gpt-4o", Provider: "openai", Label: "GPT-4o", ContextWindow: 128_000},
	{ID: "gpt-4o-mini", Provider: "openai", Label: "GPT-4o mini", ContextWindow: 128_000},
	{ID: "o3-mini", Provider: "openai", Label: "o3-mini", ContextWindow: 200_000},

	// Moonshot
	{ID: "kimi-k2-0905-preview", Provider: "moonshot", Label: "Kimi K2", ContextWindow: 256_000},
	{ID: "moonshot-v1-128k", Provider: "moonshot", Label: "Moonshot v1 128k", ContextWindow: 128_000},
	{ID: "moonshot-v1-32k", Provider: "moonshot", Label: "Moonshot v1 32k", ContextWindow: 32_000},

	// Gemini
	{ID: "gemini-2.5-pro", Provider: "gemini", Label: "Gemini 2.5 Pro", ContextWindow: 2_000_000},
	{ID: "gemini-2.5-flash", Provider: "gemini", Label: "Gemini 2.5 Flash", ContextWindow: 1_000_000},
}

// LookupModel returns the catalog entry for a given model ID, or nil if not
// found.
func LookupModel(id string) *ModelInfo {
	for i := range Catalog {
		if Catalog[i].ID == id {
			return &Catalog[i]
		}
	}
	return nil
}
