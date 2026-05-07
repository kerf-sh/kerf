//go:build cloud
// +build cloud

// Package billing wraps Paystack and exposes the cloud HTTP routes for
// top-ups, balance lookup, usage history, and webhook ingestion.
//
// Paystack quirks worth knowing:
//   - Paystack ZA only settles in ZAR. We collect ZAR amounts but track
//     credit in USD because that's the user-facing display currency.
//   - All currency amounts on the Paystack API are integer minor units
//     (kobo / cents). We multiply by 100 going out and divide by 100 on
//     the way back.
//   - Webhook signatures are HMAC-SHA512 of the raw request body using
//     the secret key (NOT a separate webhook secret on Paystack — though
//     they let you set webhook_secret as the same value, which is what
//     this package expects via cfg.Cloud.Paystack.WebhookSecret).
package billing

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha512"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"
)

// defaultPaystackBaseURL is the production Paystack REST endpoint. The
// PAYSTACK_BASE_URL env var overrides this and is intended exclusively for
// the cloud test runner (see backend/cloud/cmd/test) which spins up an
// httptest mock server.
const defaultPaystackBaseURL = "https://api.paystack.co"

// Client is a thin Paystack REST client.
type Client struct {
	secretKey     string
	publicKey     string
	webhookSecret string
	baseURL       string
	http          *http.Client
}

// NewClient constructs a client. webhookSecret is used solely for HMAC
// verification of incoming webhooks; on Paystack South Africa this is
// usually configured to be the same value as the secretKey.
//
// If the PAYSTACK_BASE_URL environment variable is set, requests target it
// instead of api.paystack.co — used by the cloud test runner to point the
// client at an httptest server. In production, leave it unset.
func NewClient(secretKey, publicKey, webhookSecret string) *Client {
	if webhookSecret == "" {
		webhookSecret = secretKey
	}
	base := defaultPaystackBaseURL
	if v := strings.TrimRight(os.Getenv("PAYSTACK_BASE_URL"), "/"); v != "" {
		base = v
	}
	return &Client{
		secretKey:     secretKey,
		publicKey:     publicKey,
		webhookSecret: webhookSecret,
		baseURL:       base,
		http:          &http.Client{Timeout: 15 * time.Second},
	}
}

// SecretKey is exported so handlers can include it in test fixtures.
// (Don't ever log the value at runtime.)
func (c *Client) SecretKey() string { return c.secretKey }

// initRequest is the body sent to /transaction/initialize.
type initRequest struct {
	Email       string `json:"email"`
	Amount      int    `json:"amount"`   // ZAR cents
	Currency    string `json:"currency"` // "ZAR"
	Reference   string `json:"reference"`
	CallbackURL string `json:"callback_url,omitempty"`
}

type initResponse struct {
	Status  bool   `json:"status"`
	Message string `json:"message"`
	Data    struct {
		AuthorizationURL string `json:"authorization_url"`
		AccessCode       string `json:"access_code"`
		Reference        string `json:"reference"`
	} `json:"data"`
}

// InitializeTransaction creates a hosted-checkout link the frontend can
// redirect the user to. Returns the URL plus the access code (used for
// inline checkout if you want to embed instead of redirect).
func (c *Client) InitializeTransaction(
	ctx context.Context,
	email string,
	amountZARCents int,
	reference, callbackURL string,
) (authURL, accessCode string, err error) {
	body, err := json.Marshal(initRequest{
		Email:       email,
		Amount:      amountZARCents,
		Currency:    "ZAR",
		Reference:   reference,
		CallbackURL: callbackURL,
	})
	if err != nil {
		return "", "", err
	}
	req, err := http.NewRequestWithContext(ctx,
		http.MethodPost, c.baseURL+"/transaction/initialize",
		bytes.NewReader(body))
	if err != nil {
		return "", "", err
	}
	req.Header.Set("Authorization", "Bearer "+c.secretKey)
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.http.Do(req)
	if err != nil {
		return "", "", err
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	if resp.StatusCode/100 != 2 {
		return "", "", fmt.Errorf("paystack initialize: HTTP %d: %s", resp.StatusCode, string(raw))
	}
	var out initResponse
	if err := json.Unmarshal(raw, &out); err != nil {
		return "", "", fmt.Errorf("paystack initialize: decode: %w", err)
	}
	if !out.Status {
		return "", "", fmt.Errorf("paystack initialize: %s", out.Message)
	}
	return out.Data.AuthorizationURL, out.Data.AccessCode, nil
}

// VerifyResult is the trimmed-down view of a /transaction/verify response.
type VerifyResult struct {
	Reference     string          `json:"reference"`
	Status        string          `json:"status"`   // "success" | "failed" | "abandoned"
	AmountMinor   int             `json:"amount"`   // ZAR cents
	Currency      string          `json:"currency"` // "ZAR"
	PaidAt        *time.Time      `json:"paid_at,omitempty"`
	CustomerEmail string          `json:"customer_email,omitempty"`
	CustomerCode  string          `json:"customer_code,omitempty"`
	CustomerID    int64           `json:"customer_id,omitempty"`
	Raw           json.RawMessage `json:"-"`
}

// verifyResponse mirrors the Paystack envelope.
type verifyResponse struct {
	Status  bool   `json:"status"`
	Message string `json:"message"`
	Data    struct {
		Reference string  `json:"reference"`
		Status    string  `json:"status"`
		Amount    int     `json:"amount"`
		Currency  string  `json:"currency"`
		PaidAt    *string `json:"paid_at"`
		Customer  struct {
			ID            int64  `json:"id"`
			CustomerCode  string `json:"customer_code"`
			Email         string `json:"email"`
		} `json:"customer"`
	} `json:"data"`
}

// VerifyTransaction confirms the state of a transaction post-redirect.
// Always call this on webhook receipt OR on callback page load — never
// trust frontend-supplied success state.
func (c *Client) VerifyTransaction(ctx context.Context, reference string) (*VerifyResult, error) {
	url := c.baseURL + "/transaction/verify/" + reference
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+c.secretKey)

	resp, err := c.http.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	if resp.StatusCode/100 != 2 {
		return nil, fmt.Errorf("paystack verify: HTTP %d: %s", resp.StatusCode, string(raw))
	}
	var out verifyResponse
	if err := json.Unmarshal(raw, &out); err != nil {
		return nil, fmt.Errorf("paystack verify: decode: %w", err)
	}
	if !out.Status {
		return nil, fmt.Errorf("paystack verify: %s", out.Message)
	}
	r := &VerifyResult{
		Reference:     out.Data.Reference,
		Status:        out.Data.Status,
		AmountMinor:   out.Data.Amount,
		Currency:      out.Data.Currency,
		CustomerEmail: out.Data.Customer.Email,
		CustomerCode:  out.Data.Customer.CustomerCode,
		CustomerID:    out.Data.Customer.ID,
		Raw:           json.RawMessage(raw),
	}
	if out.Data.PaidAt != nil && *out.Data.PaidAt != "" {
		// Paystack sends RFC 3339 timestamps.
		if t, err := time.Parse(time.RFC3339, *out.Data.PaidAt); err == nil {
			r.PaidAt = &t
		}
	}
	return r, nil
}

// VerifyWebhookSignature validates the x-paystack-signature header.
// Paystack uses HMAC-SHA512 of the raw body with the secret key, hex
// encoded. Constant-time comparison prevents timing oracles.
func (c *Client) VerifyWebhookSignature(body []byte, signature string) bool {
	if signature == "" || c.webhookSecret == "" {
		return false
	}
	mac := hmac.New(sha512.New, []byte(c.webhookSecret))
	mac.Write(body)
	expected := hex.EncodeToString(mac.Sum(nil))
	return hmac.Equal([]byte(expected), []byte(signature))
}
