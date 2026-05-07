//go:build cloud
// +build cloud

package main

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha512"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"

	"github.com/google/uuid"
)

// runPaystackWebhook covers the webhook ingestion path. It seeds a
// pending invoice directly via the pool, then drives /api/billing/webhook
// through several signed and unsigned variants to verify:
//
//  1. Valid signature + known reference → invoice flips to 'success',
//     paid_at populated, balance credited by amount_usd.
//  2. Replaying the same payload is idempotent: status stays 'success',
//     balance is NOT incremented a second time.
//  3. Bad signature → 401 (and no DB mutation).
//  4. Valid signature but unknown reference → 200 (acked, no mutation).
func runPaystackWebhook(ctx context.Context, env *testEnv, suite *Suite) {
	const sc = "paystack_webhook"

	uid := CloudTestUserID
	reference := uuid.NewString()
	const amountUSD = 7.5
	const amountZAR = 141.0
	const fxRate = 18.80

	if _, err := env.Pool.Exec(ctx, `
        insert into cloud_invoices(user_id, reference, status, amount_usd, amount_zar, fx_rate)
        values ($1, $2, 'pending', $3, $4, $5)
    `, uid, reference, amountUSD, amountZAR, fxRate); err != nil {
		suite.Failf(sc, "seed invoice: %v", err)
		return
	}

	// Build the webhook envelope the way Paystack would.
	envelope := map[string]interface{}{
		"event": "charge.success",
		"data": map[string]interface{}{
			"reference": reference,
			"status":    "success",
			"amount":    int(amountZAR * 100),
			"currency":  "ZAR",
			"customer": map[string]interface{}{
				"id":            int64(123456),
				"customer_code": "CUS_test_xxx",
				"email":         "test@example.com",
			},
		},
	}
	body, _ := json.Marshal(envelope)
	sig := hmacSHA512Hex(env.Cfg.Cloud.Paystack.WebhookSecret, body)

	// --- Case 1: bad signature is rejected. We do this BEFORE the success
	// path so we can be sure the invoice is still pending when we test it.
	{
		req, _ := http.NewRequest(http.MethodPost,
			env.HTTPServer.URL+"/api/billing/webhook", bytes.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("x-paystack-signature", "deadbeef")
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			suite.Failf(sc, "bad-sig do: %v", err)
			return
		}
		_ = resp.Body.Close()
		suite.AssertEqual(sc, "bad signature → 401", 401, resp.StatusCode)
	}

	// --- Case 2: success path.
	if !postWebhook(env.HTTPServer.URL, body, sig, suite, sc, "valid sig → 200", 200) {
		return
	}
	// Verify state transitions.
	{
		var (
			status   string
			paidAt   *string
			balance  float64
			balErr   error
		)
		err := env.Pool.QueryRow(ctx, `select status, paid_at::text from cloud_invoices where reference = $1`,
			reference).Scan(&status, &paidAt)
		suite.AssertNoError(sc, "load invoice after success", err)
		suite.AssertEqual(sc, "invoice status=success", "success", status)
		suite.Assert(sc, "paid_at set", paidAt != nil, "paid_at should be non-null after success")

		balErr = env.Pool.QueryRow(ctx, `select credits_usd from cloud_user_balances where user_id = $1`,
			uid).Scan(&balance)
		suite.AssertNoError(sc, "load balance after success", balErr)
		suite.AssertFloatNear(sc, "balance credited", amountUSD, balance, 0.0001)
	}

	// --- Case 3: replay the exact same body+signature. Should be ack'd
	// 200 but NOT credit the balance again.
	{
		if !postWebhook(env.HTTPServer.URL, body, sig, suite, sc, "replay → 200", 200) {
			return
		}
		var balance float64
		err := env.Pool.QueryRow(ctx, `select credits_usd from cloud_user_balances where user_id = $1`,
			uid).Scan(&balance)
		suite.AssertNoError(sc, "load balance after replay", err)
		suite.AssertFloatNear(sc, "balance NOT double-credited", amountUSD, balance, 0.0001)
	}

	// --- Case 4: unknown reference. Webhook should ack with 200 and NOT
	// touch any of our existing rows.
	{
		unknown := map[string]interface{}{
			"event": "charge.success",
			"data": map[string]interface{}{
				"reference": "unknown_ref_xyz",
				"status":    "success",
				"amount":    100,
				"currency":  "ZAR",
				"customer":  map[string]interface{}{"id": int64(0), "customer_code": "", "email": ""},
			},
		}
		ub, _ := json.Marshal(unknown)
		usig := hmacSHA512Hex(env.Cfg.Cloud.Paystack.WebhookSecret, ub)
		postWebhook(env.HTTPServer.URL, ub, usig, suite, sc, "unknown ref → 200", 200)

		// Confirm nothing accidentally got created.
		var n int
		_ = env.Pool.QueryRow(ctx, `select count(*) from cloud_invoices where reference = 'unknown_ref_xyz'`).Scan(&n)
		suite.AssertEqual(sc, "unknown ref did not create invoice", 0, n)
	}
}

// postWebhook is a small request helper. Returns true if the status
// matched expectations (so the caller can early-return on the
// "first webhook must succeed before we can test idempotency" precondition).
func postWebhook(baseURL string, body []byte, sig string, suite *Suite, sc, label string, wantStatus int) bool {
	req, _ := http.NewRequest(http.MethodPost, baseURL+"/api/billing/webhook", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("x-paystack-signature", sig)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		suite.Failf(sc, "%s: do: %v", label, err)
		return false
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != wantStatus {
		suite.Fail(sc, label, "status="+http.StatusText(resp.StatusCode)+" body="+string(raw))
		return false
	}
	suite.Pass(sc, label)
	return true
}

func hmacSHA512Hex(secret string, body []byte) string {
	mac := hmac.New(sha512.New, []byte(secret))
	mac.Write(body)
	return hex.EncodeToString(mac.Sum(nil))
}
