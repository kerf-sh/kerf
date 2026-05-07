//go:build cloud
// +build cloud

package main

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
)

// runPaystackInit drives the topup flow up to (but not through) the
// Paystack-hosted redirect. It verifies:
//
//  1. POST /api/billing/topup with {amount_usd: 10} returns the expected
//     shape (auth URL, ZAR amount, FX rate populated).
//  2. A cloud_invoices row is written with status='pending' before the
//     mock Paystack call returns — the handler does this defensively so
//     a Paystack-side success but DB-side failure can't drop a charge.
//  3. The mock Paystack server saw a /transaction/initialize call with
//     the matching reference + currency=ZAR.
func runPaystackInit(ctx context.Context, env *testEnv, suite *Suite) {
	const sc = "paystack_init"

	body, _ := json.Marshal(map[string]interface{}{"amount_usd": 10.0})
	req, err := http.NewRequest(http.MethodPost, env.HTTPServer.URL+"/api/billing/topup", bytes.NewReader(body))
	if err != nil {
		suite.Failf(sc, "build request: %v", err)
		return
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		suite.Failf(sc, "do request: %v", err)
		return
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)

	if !suite.AssertEqual(sc, "topup status 200", 200, resp.StatusCode) {
		suite.Failf(sc, "topup body: %s", string(raw))
		return
	}

	var out struct {
		AuthorizationURL string  `json:"authorization_url"`
		Reference        string  `json:"reference"`
		AmountUSD        float64 `json:"amount_usd"`
		AmountZAR        float64 `json:"amount_zar"`
		FXRate           float64 `json:"fx_rate"`
	}
	if err := json.Unmarshal(raw, &out); err != nil {
		suite.Failf(sc, "decode topup response: %v (body=%s)", err, string(raw))
		return
	}

	suite.AssertContains(sc, "auth url has reference", out.AuthorizationURL, out.Reference)
	suite.AssertEqual(sc, "amount_usd echo", 10.0, out.AmountUSD)
	suite.Assert(sc, "amount_zar > 0", out.AmountZAR > 0,
		"amount_zar should be positive after FX conversion")
	suite.Assert(sc, "fx_rate > 0", out.FXRate > 0, "fx_rate should be populated")
	// 10 USD * (18.55 * 1.015) ≈ 188.28 ZAR. Allow ±0.5 for spread math drift.
	suite.AssertFloatNear(sc, "amount_zar ≈ 10 * rate-with-spread", 188.28, out.AmountZAR, 0.5)

	// Verify the mock Paystack server saw the right shape.
	env.PaystackMock.mu.Lock()
	last := env.PaystackMock.LastInit
	env.PaystackMock.mu.Unlock()
	if !suite.Assert(sc, "paystack mock saw initialize", last != nil, "no /transaction/initialize hit") {
		return
	}
	suite.AssertEqual(sc, "paystack currency=ZAR", "ZAR", last["currency"])
	if ref, _ := last["reference"].(string); ref != out.Reference {
		suite.Fail(sc, "paystack reference matches", "mock saw a different reference than handler returned")
	} else {
		suite.Pass(sc, "paystack reference matches")
	}

	// DB row check.
	var (
		invoiceStatus string
		invoiceUSD    float64
	)
	err = env.Pool.QueryRow(ctx, `select status, amount_usd from cloud_invoices where reference = $1`, out.Reference).Scan(&invoiceStatus, &invoiceUSD)
	if !suite.AssertNoError(sc, "load invoice", err) {
		return
	}
	suite.AssertEqual(sc, "invoice status=pending", "pending", invoiceStatus)
	suite.AssertEqual(sc, "invoice amount_usd=10", 10.0, invoiceUSD)
}
