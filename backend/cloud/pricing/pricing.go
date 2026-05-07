//go:build cloud
// +build cloud

// Package pricing computes per-event USD costs for token and storage usage.
//
// Pricing is currently a hard-coded table of USD-per-million-token rates per
// model id, with a configurable markup applied on top. The markup is the
// company's margin over raw provider cost.
//
// IMPORTANT: provider list pricing changes frequently (Anthropic, OpenAI,
// Google all repriced multiple times in 2025). When you bump or downgrade a
// model anywhere in the codebase, update the matching row here as well.
// Mismatches surface as silent over/under-charging until someone notices.
package pricing

import "strings"

// rate is the USD-per-1M-token list price for a single model.
type rate struct {
	InputUSDPerMTok  float64
	OutputUSDPerMTok float64
}

// table maps model id (case-insensitive prefix match — see lookupRate) to
// rates. Numbers reflect public list pricing as of the 2026 cycle. Update
// whenever a provider repricing lands.
var table = map[string]rate{
	// Anthropic
	"claude-opus-4-7":   {InputUSDPerMTok: 15.0, OutputUSDPerMTok: 75.0},
	"claude-sonnet-4-6": {InputUSDPerMTok: 3.0, OutputUSDPerMTok: 15.0},
	"claude-haiku-4-5":  {InputUSDPerMTok: 1.0, OutputUSDPerMTok: 5.0},

	// OpenAI
	"gpt-4o":      {InputUSDPerMTok: 2.50, OutputUSDPerMTok: 10.0},
	"gpt-4o-mini": {InputUSDPerMTok: 0.15, OutputUSDPerMTok: 0.60},
	"o3-mini":     {InputUSDPerMTok: 1.10, OutputUSDPerMTok: 4.40},

	// Google Gemini
	"gemini-2.5-pro":   {InputUSDPerMTok: 1.25, OutputUSDPerMTok: 5.0},
	"gemini-2.5-flash": {InputUSDPerMTok: 0.075, OutputUSDPerMTok: 0.30},

	// Moonshot (Kimi)
	"kimi-k2-0905-preview": {InputUSDPerMTok: 0.60, OutputUSDPerMTok: 2.50},
	"moonshot-v1-128k":     {InputUSDPerMTok: 0.60, OutputUSDPerMTok: 2.50},
	"moonshot-v1-32k":      {InputUSDPerMTok: 0.30, OutputUSDPerMTok: 1.20},
}

// medianRate is the fallback used when an unknown model id is billed.
// Sonnet 4.6 sits in the middle of the spread and is a defensible default.
var medianRate = rate{InputUSDPerMTok: 3.0, OutputUSDPerMTok: 15.0}

// lookupRate finds a matching row in the table. Provider model ids vary in
// suffixes (date stamps, regions, "latest" aliases), so we accept either an
// exact match or the longest registered prefix.
func lookupRate(model string) rate {
	if model == "" {
		return medianRate
	}
	m := strings.ToLower(model)
	if r, ok := table[m]; ok {
		return r
	}
	// Longest-prefix match. Prevents "claude-opus-4-7-20260101" from
	// silently falling through to median.
	var best string
	for k := range table {
		if strings.HasPrefix(m, k) && len(k) > len(best) {
			best = k
		}
	}
	if best != "" {
		return table[best]
	}
	return medianRate
}

// TokenCost returns the USD cost (markup-inclusive) of a single LLM call.
// markupPct is expressed in percent — e.g. 20.0 means a 20% margin.
func TokenCost(model string, inputTokens, outputTokens int, markupPct float64) float64 {
	r := lookupRate(model)
	raw := (float64(inputTokens)/1_000_000.0)*r.InputUSDPerMTok +
		(float64(outputTokens)/1_000_000.0)*r.OutputUSDPerMTok
	return raw * (1.0 + markupPct/100.0)
}

// StorageCostPerGBMonth is a passthrough kept for symmetry with TokenCost
// and so call sites don't reach into config directly.
func StorageCostPerGBMonth(usdPerGBMonth float64) float64 {
	return usdPerGBMonth
}

// StorageDailyCost converts a byte count and a per-GB-month rate to a single
// day's worth of charge. Used by the monthly storage rollup which prorates
// based on observed daily peak usage.
func StorageDailyCost(bytes int64, usdPerGBMonth float64) float64 {
	const bytesPerGB = 1024.0 * 1024.0 * 1024.0
	gb := float64(bytes) / bytesPerGB
	return gb * (usdPerGBMonth / 30.0)
}
