//go:build cloud
// +build cloud

package main

import (
	"context"

	cloudfx "github.com/imranp/kerf/backend/cloud/fx"
)

// runFXRefresh exercises the FX fetcher end-to-end against the in-memory
// mock. It walks through:
//
//  1. SetRate on the mock, Refresh the fetcher → cloud_fx_rates row exists
//     with the rate we served.
//  2. Rate("USD","ZAR") returns the served rate.
//  3. RateWithSpread applies the configured spread_pct (1.5% default →
//     18.55 → 18.83).
//  4. Calling Rate twice in a row hits the in-process cache: the mock
//     should NOT see another /latest request after Refresh primed the
//     cache.
func runFXRefresh(ctx context.Context, env *testEnv, suite *Suite) {
	const sc = "fx_refresh"

	// Set the mock to a known value before we trigger refresh. Note that
	// ResetState already constructed a fresh fetcher (which Refresh'd once
	// against the mock's default of 18.55) — we override and re-Refresh to
	// pin the value tightly to this test.
	env.FXMock.SetRate(18.55)

	// Construct a brand-new fetcher so we know the cache starts cold.
	f, err := cloudfx.New(ctx, env.Cfg, env.Pool)
	if !suite.AssertNoError(sc, "construct fetcher", err) {
		return
	}
	hitsBefore := env.FXMock.HitCount()

	if !suite.AssertNoError(sc, "explicit Refresh", f.Refresh(ctx)) {
		return
	}

	// Verify a row was inserted into cloud_fx_rates by Refresh.
	var n int
	if err := env.Pool.QueryRow(ctx,
		`select count(*) from cloud_fx_rates where base_currency='USD' and target_currency='ZAR'`).Scan(&n); err != nil {
		suite.Failf(sc, "count fx rows: %v", err)
		return
	}
	suite.Assert(sc, "cloud_fx_rates row exists", n >= 1, "expected ≥1 row after Refresh")

	rate, _, ok := f.Rate("USD", "ZAR")
	if !suite.Assert(sc, "Rate ok", ok, "Rate returned ok=false after Refresh") {
		return
	}
	suite.AssertFloatNear(sc, "Rate = 18.55", 18.55, rate, 0.0001)

	// 18.55 * (1 + 1.5/100) = 18.55 * 1.015 = 18.82825
	withSpread, _, ok := f.RateWithSpread("USD", "ZAR", 1.5)
	suite.Assert(sc, "RateWithSpread ok", ok, "RateWithSpread returned ok=false")
	suite.AssertFloatNear(sc, "RateWithSpread = 18.83", 18.83, withSpread, 0.005)

	// Second Rate call must hit the in-memory cache, NOT re-fetch from
	// the provider. The mock counts /latest hits — Refresh touched it
	// once (above) plus whatever cloudfx.New did internally before the
	// HitCount snapshot. After Rate, the count must NOT increase further.
	hitsAfterRefresh := env.FXMock.HitCount()
	_, _, _ = f.Rate("USD", "ZAR")
	hitsAfterCacheRead := env.FXMock.HitCount()
	suite.AssertEqual(sc, "second Rate is cached (no new /latest hit)",
		hitsAfterRefresh, hitsAfterCacheRead)

	// Sanity: the explicit Refresh did at least one hit since hitsBefore.
	suite.Assert(sc, "Refresh hit the provider", hitsAfterRefresh > hitsBefore,
		"Refresh did not increase mock hit count")
}
