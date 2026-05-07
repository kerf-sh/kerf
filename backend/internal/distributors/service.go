// Package distributors provides distributor-API integrations for the
// Library subsystem (DigiKey, Mouser, LCSC). Each Service exposes a
// uniform Lookup / Search shape so the Part-refresh handler can iterate
// over enabled services without distributor-specific branching.
//
// Operator-facing surface:
//
//   - Credentials are encrypted at rest via backend/internal/auth.
//     Plaintext is JSON-shaped (see Credentials docstring).
//   - Each row has a per-minute rate limit enforced in-process via
//     golang.org/x/time/rate.
//   - The Registry is loaded once at boot and reloaded whenever an
//     admin updates / deletes a row through the admin handler.
//
// What's deliberately NOT here:
//
//   - McMaster: no public API. Mech parts store a catalog URL only; the
//     manual-refresh path skips them (they never appear as keys in the
//     Registry's services map).
//   - Provider-specific Go SDKs: every distributor here is hand-rolled
//     net/http to keep the binary small and the dependency surface flat.
package distributors

import (
	"context"
	"encoding/json"
	"errors"
	"time"
)

// Provider names — single source of truth for what the system knows
// about. Adding a new distributor requires:
//   - registering it here,
//   - implementing the Service interface in a new file,
//   - extending Registry.buildService with a name-keyed branch,
//   - adding a payload validator in validateCredentials.
const (
	ProviderDigiKey = "digikey"
	ProviderMouser  = "mouser"
	ProviderLCSC    = "lcsc"
)

// AllProviders lists every supported distributor name. Used by the admin
// handler to render an empty row for distributors the operator hasn't
// configured yet.
func AllProviders() []string {
	return []string{ProviderDigiKey, ProviderMouser, ProviderLCSC}
}

// Credentials is the plaintext shape of the secret payload before
// encryption. Different distributors use different fields:
//
//   - DigiKey: ClientID + ClientSecret (OAuth2 client_credentials)
//   - Mouser:  APIKey
//   - LCSC:    APIKey
//
// The unmarshal is permissive — we only validate that the *required*
// fields for the named distributor are present (see validateCredentials).
type Credentials struct {
	ClientID     string `json:"client_id,omitempty"`
	ClientSecret string `json:"client_secret,omitempty"`
	APIKey       string `json:"api_key,omitempty"`
}

// DistributorPart is the normalized result returned by Lookup and
// Search. PriceUSD is always converted to USD by the implementation
// (LCSC, for instance, returns CNY and the implementation converts via
// the cloud FX cache when available).
//
// `Raw` carries the provider's raw response JSON so the caller can
// surface extra fields (lead time, packaging, etc.) without us having
// to encode every distributor-specific column up-front.
type DistributorPart struct {
	Name      string          `json:"name"`
	SKU       string          `json:"sku,omitempty"`
	URL       string          `json:"url"`
	PriceUSD  *float64        `json:"price_usd,omitempty"`
	Stock     *int            `json:"stock,omitempty"`
	FetchedAt time.Time       `json:"fetched_at"`
	Raw       json.RawMessage `json:"raw,omitempty"`
}

// Service is the per-distributor lookup interface. Implementations
// hold their credentials in memory after Registry.buildService
// decrypts them; they are NOT goroutine-safe per-instance — the
// Registry serializes calls through its rate limiter.
type Service interface {
	// Name returns the canonical distributor name (digikey, mouser, …).
	Name() string

	// Lookup returns metadata for an exact part-number match. When the
	// distributor has multiple matches it returns the first / canonical
	// one. Returns ErrNotFound when nothing matches.
	Lookup(ctx context.Context, sku string) (*DistributorPart, error)

	// Search returns up to `limit` candidate parts for a free-text
	// query. Used as a fallback when a Part has a manufacturer + MPN
	// but no SKU yet.
	Search(ctx context.Context, query string, limit int) ([]*DistributorPart, error)
}

// ErrNotFound is the sentinel for "no result for this SKU/query."
// Callers should treat this as a soft-miss — leave the existing
// price/stock untouched and bump fetched_at so the next sweep doesn't
// keep retrying immediately.
var ErrNotFound = errors.New("distributor: not found")

// ErrNotConfigured signals the Registry has no enabled service for a
// given distributor name. The refresh path uses this to decide whether
// to surface a friendly "ask the admin to configure DigiKey" hint to
// the LLM.
var ErrNotConfigured = errors.New("distributor: not configured or disabled")

// validateCredentials enforces the per-distributor required-fields rule
// before we encrypt and store. Returns a human-readable error so the
// admin handler can echo it verbatim.
func validateCredentials(name string, c Credentials) error {
	switch name {
	case ProviderDigiKey:
		if c.ClientID == "" || c.ClientSecret == "" {
			return errors.New("digikey requires client_id and client_secret")
		}
	case ProviderMouser, ProviderLCSC:
		if c.APIKey == "" {
			return errors.New(name + " requires api_key")
		}
	default:
		return errors.New("unknown distributor: " + name)
	}
	return nil
}
