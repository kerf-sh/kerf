//go:build cloud
// +build cloud

package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync"
)

// paystackMock stands in for the Paystack REST API. It only implements
// the endpoints we drive in the test scenarios: /transaction/initialize
// (used by Topup) and /transaction/verify/{ref} (used by VerifyTransaction
// — currently unused by the runner but wired up for completeness).
//
// Behavior is configurable per-test via the public fields. Default
// behavior is to return a synthetic 200 success response so the happy
// path "just works" without per-scenario setup.
type paystackMock struct {
	Server *httptest.Server

	mu sync.Mutex

	// InitFn lets a scenario customize the response. nil → default ok.
	InitFn   func(w http.ResponseWriter, r *http.Request)
	VerifyFn func(w http.ResponseWriter, r *http.Request)

	// LastInit captures the last decoded /transaction/initialize body so
	// scenarios can assert on what we sent (amount, currency, reference).
	LastInit map[string]interface{}
}

// newPaystackMock constructs the mock and starts an httptest server.
func newPaystackMock() *paystackMock {
	m := &paystackMock{}
	mux := http.NewServeMux()
	mux.HandleFunc("/transaction/initialize", func(w http.ResponseWriter, r *http.Request) {
		// Always decode the body so LastInit reflects reality even when
		// the scenario overrides the response handler.
		var body map[string]interface{}
		_ = json.NewDecoder(r.Body).Decode(&body)
		m.mu.Lock()
		m.LastInit = body
		fn := m.InitFn
		m.mu.Unlock()
		if fn != nil {
			fn(w, r)
			return
		}
		ref, _ := body["reference"].(string)
		writeJSONResponse(w, 200, map[string]interface{}{
			"status":  true,
			"message": "Authorization URL created",
			"data": map[string]interface{}{
				"authorization_url": "https://checkout.paystack.com/test/" + ref,
				"access_code":       "ac_" + ref,
				"reference":         ref,
			},
		})
	})
	mux.HandleFunc("/transaction/verify/", func(w http.ResponseWriter, r *http.Request) {
		m.mu.Lock()
		fn := m.VerifyFn
		m.mu.Unlock()
		if fn != nil {
			fn(w, r)
			return
		}
		writeJSONResponse(w, 200, map[string]interface{}{
			"status":  true,
			"message": "Verification successful",
			"data": map[string]interface{}{
				"reference": "",
				"status":    "success",
				"amount":    0,
				"currency":  "ZAR",
			},
		})
	})
	m.Server = httptest.NewServer(mux)
	return m
}

// Reset clears the per-test overrides and recorded state.
func (m *paystackMock) Reset() {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.InitFn = nil
	m.VerifyFn = nil
	m.LastInit = nil
}

// fxMock stands in for an exchangerate.host-style provider. The default
// /latest response is a 200 with {base:"USD", rates:{ZAR: rate}}; tests
// override Rate or Handler to model failure modes.
type fxMock struct {
	Server *httptest.Server

	mu      sync.Mutex
	Rate    float64 // ZAR per USD; default 18.55
	Handler func(w http.ResponseWriter, r *http.Request)

	// Hits is incremented on every /latest call so tests can verify the
	// in-memory cache is doing its job (i.e. NOT incrementing).
	Hits int
}

func newFXMock() *fxMock {
	m := &fxMock{Rate: 18.55}
	mux := http.NewServeMux()
	mux.HandleFunc("/latest", func(w http.ResponseWriter, r *http.Request) {
		m.mu.Lock()
		m.Hits++
		fn := m.Handler
		rate := m.Rate
		m.mu.Unlock()
		if fn != nil {
			fn(w, r)
			return
		}
		writeJSONResponse(w, 200, map[string]interface{}{
			"base":  "USD",
			"date":  "2026-01-01",
			"rates": map[string]float64{"ZAR": rate},
		})
	})
	m.Server = httptest.NewServer(mux)
	return m
}

// Reset clears overrides and counters. We deliberately keep Rate so a
// scenario that doesn't change rates still gets the default 18.55.
func (m *fxMock) Reset() {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.Handler = nil
	m.Hits = 0
	m.Rate = 18.55
}

// SetRate updates the rate served by /latest atomically.
func (m *fxMock) SetRate(r float64) {
	m.mu.Lock()
	m.Rate = r
	m.mu.Unlock()
}

// HitCount returns the snapshot of /latest hits since the last Reset.
func (m *fxMock) HitCount() int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.Hits
}

// writeJSONResponse is a tiny local helper. We don't import the cloud
// billing package's writeJSON because that's an unexported test concern
// and we want this file freestanding.
func writeJSONResponse(w http.ResponseWriter, status int, body interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}
