//go:build cloud
// +build cloud

// Package fx provides USD↔ZAR (and other-pair) FX rates with a simple
// daily refresh + in-memory cache.
//
// Why a spread? The fetched rate is a mid-market quote, but settlement
// goes through Paystack which charges in ZAR and the bank's ZAR→USD
// reconciliation happens later at a less favorable rate. The configurable
// spread (cloud.fx.spread_pct) absorbs that variance plus a small margin.
package fx

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"sync"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/internal/config"
)

// Fetcher pulls FX rates and stores them in cloud_fx_rates. It also keeps
// a small in-memory cache so the per-request hot path doesn't re-hit the
// DB on every transaction initialize.
type Fetcher struct {
	pool *pgxpool.Pool
	cfg  *config.Config
	http *http.Client

	mu    sync.RWMutex
	cache map[string]cachedRate // key = base+"/"+target
}

type cachedRate struct {
	rate     float64
	asOf     time.Time
	cachedAt time.Time
}

// cacheTTL is the in-process cache validity window. Short enough that an
// admin-triggered refresh is visible quickly; long enough to absorb bursts.
const cacheTTL = 1 * time.Minute

// New constructs a Fetcher and performs an initial Refresh so the first
// /api/billing/topup call has a rate available. Refresh failures are
// non-fatal: we log and continue, falling back to whatever is already in
// cloud_fx_rates from a previous run.
func New(ctx context.Context, cfg *config.Config, pool *pgxpool.Pool) (*Fetcher, error) {
	f := &Fetcher{
		pool:  pool,
		cfg:   cfg,
		http:  &http.Client{Timeout: 10 * time.Second},
		cache: make(map[string]cachedRate),
	}
	// Best-effort initial refresh.
	if err := f.Refresh(ctx); err != nil {
		// Don't fail boot on this — older rates in the DB are still usable.
		fmt.Printf("fx: initial refresh failed: %v (will rely on cached DB rates)\n", err)
	}
	return f, nil
}

// Start runs a 24h ticker until ctx is cancelled. Caller is expected to
// kick this off in a goroutine.
func (f *Fetcher) Start(ctx context.Context) {
	t := time.NewTicker(24 * time.Hour)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			if err := f.Refresh(ctx); err != nil {
				fmt.Printf("fx: scheduled refresh failed: %v\n", err)
			}
		}
	}
}

// fxResponse mirrors the exchangerate.host /latest payload shape.
// Other free providers (e.g. open.er-api.com) return the same {rates: {...}}
// envelope, so this struct works against multiple sources interchangeably.
type fxResponse struct {
	Base    string             `json:"base"`
	Date    string             `json:"date"`
	Rates   map[string]float64 `json:"rates"`
	Success *bool              `json:"success,omitempty"`
}

// Refresh fetches the latest rate from cfg.Cloud.FX.RefreshURL and inserts
// it into cloud_fx_rates. We always insert (never UPDATE) so the table
// retains a history — needed for at-time-of-charge audit and refunds.
func (f *Fetcher) Refresh(ctx context.Context) error {
	url := f.cfg.Cloud.FX.RefreshURL
	if url == "" {
		return errors.New("fx: refresh url not configured")
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return err
	}
	resp, err := f.http.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("fx: provider returned %d", resp.StatusCode)
	}
	var body fxResponse
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return fmt.Errorf("fx: decode: %w", err)
	}
	if body.Success != nil && !*body.Success {
		return errors.New("fx: provider reported success=false")
	}
	base := body.Base
	if base == "" {
		base = f.cfg.Cloud.FX.BaseCurrency
	}
	target := f.cfg.Cloud.FX.SettlementCurrency
	rate, ok := body.Rates[target]
	if !ok || rate <= 0 {
		return fmt.Errorf("fx: no %s rate in response", target)
	}

	_, err = f.pool.Exec(ctx, `
        insert into cloud_fx_rates(base_currency, target_currency, rate)
        values ($1, $2, $3)
    `, base, target, rate)
	if err != nil {
		return fmt.Errorf("fx: insert: %w", err)
	}

	// Prime the in-memory cache.
	f.mu.Lock()
	f.cache[cacheKey(base, target)] = cachedRate{
		rate:     rate,
		asOf:     time.Now(),
		cachedAt: time.Now(),
	}
	f.mu.Unlock()
	return nil
}

// Rate returns the most recent stored rate for (base, target). Cached for
// 1 minute in process to avoid hammering the DB during burst traffic.
func (f *Fetcher) Rate(base, target string) (rate float64, asOf time.Time, ok bool) {
	key := cacheKey(base, target)
	f.mu.RLock()
	if c, hit := f.cache[key]; hit && time.Since(c.cachedAt) < cacheTTL {
		f.mu.RUnlock()
		return c.rate, c.asOf, true
	}
	f.mu.RUnlock()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	var r float64
	var fetched time.Time
	err := f.pool.QueryRow(ctx, `
        select rate, fetched_at from cloud_fx_rates
        where base_currency = $1 and target_currency = $2
        order by fetched_at desc limit 1
    `, base, target).Scan(&r, &fetched)
	if err != nil {
		return 0, time.Time{}, false
	}
	f.mu.Lock()
	f.cache[key] = cachedRate{rate: r, asOf: fetched, cachedAt: time.Now()}
	f.mu.Unlock()
	return r, fetched, true
}

// RateWithSpread returns the configured-spread-adjusted rate. Charge-time
// invoices should always use this, never the bare Rate, so the captured
// fx_rate column on cloud_invoices reflects what the user actually paid.
func (f *Fetcher) RateWithSpread(base, target string, spreadPct float64) (rate float64, asOf time.Time, ok bool) {
	r, asOf, ok := f.Rate(base, target)
	if !ok {
		return 0, asOf, false
	}
	return r * (1.0 + spreadPct/100.0), asOf, true
}

func cacheKey(base, target string) string { return base + "/" + target }
