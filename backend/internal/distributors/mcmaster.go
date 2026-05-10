package distributors

import (
	"context"
	"net/http"
)

// McMaster integration. McMaster-Carr does NOT publish a programmatic
// API for their catalog — every part page is rendered server-side and
// pricing/stock isn't exposed via a stable endpoint. This file ships
// only as a stub so:
//
//   - The provider name appears in AllProviders() / the admin UI for
//     symmetry with the other distributors.
//   - The `distributors[*].name = "mcmaster"` entries in Part files
//     don't poison the refresh loop with "unknown distributor" errors.
//
// Both Lookup and Search return ErrNotSupported; the refresh loop
// treats that as a soft skip and leaves the entry's URL/price untouched.
//
// If McMaster ever exposes a public API (or an operator wants to wire
// an internal scraper), the place to fill in is `mcmasterService.lookup`.

type mcmasterService struct {
	// client is unused in the stub but kept for parity with the other
	// services — when McMaster eventually exposes an API the same
	// mocked-transport test pattern will work.
	client *http.Client
}

func newMcMaster(c *http.Client, _ Credentials) Service {
	return &mcmasterService{client: c}
}

func (m *mcmasterService) Name() string { return ProviderMcMaster }

func (m *mcmasterService) Lookup(ctx context.Context, sku string) (*DistributorPart, error) {
	// ErrNotSupported is sticky: the refresh loop must NOT keep
	// retrying the same SKU on every sweep. The sync.RefreshPart
	// helper logs and continues, which is the correct behaviour here.
	return nil, ErrNotSupported
}

func (m *mcmasterService) Search(ctx context.Context, query string, limit int) ([]*DistributorPart, error) {
	return nil, ErrNotSupported
}
