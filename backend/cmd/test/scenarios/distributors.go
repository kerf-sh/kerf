package scenarios

// Distributors / Library Phase 2 scenario.
//
// Exercises the distributor-API integration end-to-end with mocked HTTP
// transports — no live traffic leaves the test process. The flow:
//
//   1. Register an admin user (account_role = 'admin' set via direct DB
//      UPDATE since there's no admin-bootstrap scenario today).
//   2. Create a project + a kind='part' file via the create_part tool,
//      with `distributors[]` entries for digikey, mouser, and lcsc.
//   3. Construct a *distributors.Registry pointing at the same DB, swap
//      its HTTP client for one whose RoundTripper returns canned
//      provider responses.
//   4. Persist credentials for each provider via Registry.Upsert (which
//      goes through the same admin-handler-equivalent code path —
//      validate → encrypt → INSERT).
//   5. Reload + invoke distributors.RefreshPart on the Part's content.
//      Assert the on-disk Part JSON gains populated price/stock fields
//      for each distributor.
//
// We bypass the HTTP route for the refresh because the test runner
// doesn't currently mount /api/projects/.../distributors/refresh. The
// underlying RefreshPart package function is what the handler invokes
// after permission checks — calling it directly exercises 100% of the
// distributor logic with one fewer indirection.
//
// McMaster gets a separate sub-assertion: its Service.Lookup returns
// ErrNotSupported and the entry must be left untouched.

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"net/http"
	"strings"

	"github.com/google/uuid"

	"github.com/imranp/kerf/backend/cmd/test/runner"
	"github.com/imranp/kerf/backend/internal/distributors"
	"github.com/imranp/kerf/backend/internal/tools"
)

// Distributors is the entry point registered in cmd/test/main.go.
func Distributors(s *runner.Suite, env *runner.Env) {
	c := env.Client
	ctx := context.Background()

	owner, status, raw := register(c, "dist-owner@example.com", "distownerpass1", "Dist Owner")
	if !s.Status("register dist owner", status, 201, raw) {
		return
	}
	// Promote to admin so the Upsert path doesn't need the HTTP admin
	// handler to be wired into the test router. Mirrors how pentest sets
	// up its is_verified_publisher flag.
	if _, err := env.Pool.Exec(ctx,
		`update users set account_role = 'admin' where id = $1`,
		owner.User.ID); !s.NoError("promote to admin", err) {
		return
	}

	// Project + Part with a multi-distributor entry list.
	var proj struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects",
		map[string]string{"name": "Distributors test", "workspace_id": owner.DefaultWorkspace.ID},
		owner.AccessToken, &proj)
	if !s.Status("create dist project", status, 201, raw) {
		return
	}
	pid := proj.ID

	pc := tools.ProjectCtx{
		Pool:      env.Pool,
		ProjectID: uuid.MustParse(pid),
		UserID:    uuid.MustParse(owner.User.ID),
		Role:      "owner",
	}

	const targetMPN = "RC0402JR-071K"
	createOut := runTool(s, ctx, pc, "create_part", map[string]any{
		"path": "/library/r1k.part",
		"metadata": map[string]any{
			"name":         "1kΩ resistor 0402",
			"category":     "resistor",
			"manufacturer": "Yageo",
			"mpn":          targetMPN,
			"value":        "1kΩ",
			"distributors": []map[string]any{
				// Pre-seed each entry with a SKU + URL so the refresh
				// loop hits the Lookup branch (not the Search fallback).
				{"name": distributors.ProviderDigiKey, "sku": "311-1.00KCRCT-ND",
					"url": "https://www.digikey.com/r1k"},
				{"name": distributors.ProviderMouser, "sku": "603-RC0402JR-071KL",
					"url": "https://www.mouser.com/r1k"},
				{"name": distributors.ProviderLCSC, "sku": "C11702",
					"url": "https://www.lcsc.com/product-detail/C11702.html"},
				{"name": distributors.ProviderMcMaster, "sku": "",
					"url": "https://www.mcmaster.com/91290A115/"},
			},
		},
	})
	partID, _ := createOut["id"].(string)
	if !s.NotEmpty("create_part returned id", partID) {
		return
	}

	// --- Build a Registry with a mocked transport. -----------------------
	// The mock dispatches by host so a single client serves all four
	// providers. Each handler returns a canned 200 response that the
	// Service code can parse.
	mock := &mockTransport{handler: distributorMockHandler}
	mockClient := &http.Client{Transport: mock}

	reg := distributors.New(ctx, env.Cfg, env.Pool, nil)
	// Swap the client BEFORE Upsert so subsequent Reload() builds
	// services with the mocked transport.
	reg.SetHTTPClient(ctx, mockClient)

	// --- Upsert credentials for each real provider. ---------------------
	if _, err := reg.Upsert(ctx, distributors.ProviderDigiKey, true, 600,
		distributors.Credentials{ClientID: "test-digikey-id", ClientSecret: "test-digikey-secret"},
	); !s.NoError("upsert digikey creds", err) {
		return
	}
	if _, err := reg.Upsert(ctx, distributors.ProviderMouser, true, 600,
		distributors.Credentials{APIKey: "test-mouser-key"},
	); !s.NoError("upsert mouser creds", err) {
		return
	}
	if _, err := reg.Upsert(ctx, distributors.ProviderLCSC, true, 600,
		distributors.Credentials{APIKey: "test-lcsc-key"},
	); !s.NoError("upsert lcsc creds", err) {
		return
	}
	if _, err := reg.Upsert(ctx, distributors.ProviderMcMaster, true, 600,
		distributors.Credentials{},
	); !s.NoError("upsert mcmaster creds", err) {
		return
	}
	if err := reg.Reload(ctx); !s.NoError("registry reload after upsert", err) {
		return
	}

	// Sanity: every provider resolves to a live Service in the registry.
	for _, name := range []string{
		distributors.ProviderDigiKey,
		distributors.ProviderMouser,
		distributors.ProviderLCSC,
		distributors.ProviderMcMaster,
	} {
		s.True("registry has "+name, reg.Has(name), "expected %s to be live", name)
	}

	// --- Refresh the Part through the same code path the HTTP handler ---
	// invokes. The handler is a thin wrapper around RefreshPart + a DB
	// write; we replicate the DB write here so the assertions below can
	// read the Part content from the row.
	var partContent string
	if err := env.Pool.QueryRow(ctx,
		`select content from files where id = $1`, partID).Scan(&partContent); !s.NoError("load part content", err) {
		return
	}
	newContent, n, err := distributors.RefreshPart(ctx, reg, partContent)
	if !s.NoError("RefreshPart", err) {
		return
	}
	// 3 of 4 distributors return real data; McMaster returns
	// ErrNotSupported and is skipped → expected count = 3.
	s.Equal("RefreshPart updated count", n, 3)

	if newContent != partContent {
		if _, err := env.Pool.Exec(ctx,
			`update files set content = $2, updated_at = now() where id = $1`,
			partID, newContent); !s.NoError("write refreshed part", err) {
			return
		}
	}

	// --- Verify each distributor entry was populated correctly. ---------
	doc := loadPartContent(s, env, partID)
	if doc == nil {
		return
	}
	dists, _ := doc["distributors"].([]any)
	if !s.Equal("distributors len", len(dists), 4) {
		return
	}
	byName := map[string]map[string]any{}
	for _, d := range dists {
		dm, _ := d.(map[string]any)
		if dm == nil {
			continue
		}
		name, _ := dm["name"].(string)
		byName[name] = dm
	}

	// DigiKey: price 0.014, stock 5000.
	if dk := byName[distributors.ProviderDigiKey]; s.True("digikey entry present", dk != nil) {
		s.Equal("digikey price_usd", dk["price_usd"], 0.014)
		s.Equal("digikey stock", dk["stock"], float64(5000))
		s.NotEmpty("digikey fetched_at", asString(dk["fetched_at"]))
	}

	// Mouser: price 0.018, stock 12000.
	if mo := byName[distributors.ProviderMouser]; s.True("mouser entry present", mo != nil) {
		s.Equal("mouser price_usd", mo["price_usd"], 0.018)
		s.Equal("mouser stock", mo["stock"], float64(12000))
		s.NotEmpty("mouser fetched_at", asString(mo["fetched_at"]))
	}

	// LCSC: price returned in CNY, no FX adapter wired in this scenario,
	// so price_usd must be absent. Stock must still be populated.
	if lc := byName[distributors.ProviderLCSC]; s.True("lcsc entry present", lc != nil) {
		s.True("lcsc price_usd absent (no FX)",
			lc["price_usd"] == nil,
			"got price_usd=%v", lc["price_usd"])
		s.Equal("lcsc stock", lc["stock"], float64(99999))
		s.NotEmpty("lcsc fetched_at", asString(lc["fetched_at"]))
	}

	// McMaster: ErrNotSupported → entry left untouched (no fetched_at,
	// no price, no stock).
	if mc := byName[distributors.ProviderMcMaster]; s.True("mcmaster entry present", mc != nil) {
		s.True("mcmaster fetched_at absent", asString(mc["fetched_at"]) == "",
			"got fetched_at=%v", mc["fetched_at"])
		s.True("mcmaster price_usd absent", mc["price_usd"] == nil)
		s.True("mcmaster stock absent", mc["stock"] == nil)
	}

	// --- Smoke: each provider's mock was actually hit. ------------------
	hits := mock.Hits()
	s.True("digikey token endpoint hit",
		hits["api.digikey.com/v1/oauth2/token"] >= 1,
		"hits=%v", hits)
	s.True("digikey search endpoint hit",
		hits["api.digikey.com/products/v4/search/keyword"] >= 1,
		"hits=%v", hits)
	s.True("mouser endpoint hit",
		hits["api.mouser.com/api/v1/search/partnumber"] >= 1,
		"hits=%v", hits)
	s.True("lcsc endpoint hit",
		hits["wmsc.lcsc.com/wmsc/product/search"] >= 1,
		"hits=%v", hits)
	// McMaster is a stub — its mock should NOT have been touched.
	s.Equal("mcmaster received no http traffic", mockTotalHits(hits, "mcmaster"), 0)
}

// --- mock transport ---------------------------------------------------------

// mockTransport is a tiny http.RoundTripper that delegates every request
// to a single handler func. It records per-(host+path) hit counts so the
// scenario can assert each provider's endpoint was actually exercised.
type mockTransport struct {
	handler func(req *http.Request) (*http.Response, error)
	hits    map[string]int
}

func (m *mockTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	if m.hits == nil {
		m.hits = map[string]int{}
	}
	key := req.URL.Host + req.URL.Path
	m.hits[key]++
	return m.handler(req)
}

func (m *mockTransport) Hits() map[string]int {
	out := map[string]int{}
	for k, v := range m.hits {
		out[k] = v
	}
	return out
}

func mockTotalHits(hits map[string]int, hostFragment string) int {
	n := 0
	for k, v := range hits {
		if strings.Contains(k, hostFragment) {
			n += v
		}
	}
	return n
}

// distributorMockHandler dispatches based on the request URL. Each
// branch returns the smallest valid payload the corresponding Service
// implementation will parse correctly.
func distributorMockHandler(req *http.Request) (*http.Response, error) {
	path := req.URL.Host + req.URL.Path
	switch path {
	case "api.digikey.com/v1/oauth2/token":
		return canned(http.StatusOK, `{
			"access_token": "fake-digikey-token",
			"expires_in": 1800,
			"token_type": "Bearer"
		}`), nil
	case "api.digikey.com/products/v4/search/keyword":
		return canned(http.StatusOK, `{
			"Products": [{
				"ManufacturerProductNumber": "RC0402JR-071K",
				"ProductUrl": "https://www.digikey.com/en/products/detail/yageo/RC0402JR-071K/727744",
				"UnitPrice": 0.014,
				"QuantityAvailable": 5000,
				"ProductVariations": [{
					"DigiKeyProductNumber": "311-1.00KCRCT-ND",
					"QuantityAvailableforPackageType": 5000,
					"UnitPrice": 0.014
				}]
			}]
		}`), nil
	case "api.mouser.com/api/v1/search/partnumber":
		return canned(http.StatusOK, `{
			"Errors": [],
			"SearchResults": {
				"NumberOfResult": 1,
				"Parts": [{
					"MouserPartNumber": "603-RC0402JR-071KL",
					"ProductDetailUrl": "https://www.mouser.com/ProductDetail/603-RC0402JR-071KL",
					"Availability": "12000",
					"PriceBreaks": [
						{"Quantity": 1, "Price": "$0.018", "Currency": "USD"}
					]
				}]
			}
		}`), nil
	case "wmsc.lcsc.com/wmsc/product/search":
		// /product/search returns a wrapper with `result.productCode` for
		// exact-MPN hits. Stock 99999, price 0.05 CNY (no FX adapter is
		// wired in this scenario so price_usd will end up nil — that's
		// the documented behaviour).
		return canned(http.StatusOK, `{
			"code": 200,
			"result": {
				"productCode": "C11702",
				"productUrl": "https://www.lcsc.com/product-detail/C11702.html",
				"stockNumber": 99999,
				"productPriceList": [
					{"ladderLevel": 1, "productPrice": 0.05}
				]
			}
		}`), nil
	}
	// Anything unexpected → 404 so the test fails loudly with a clear
	// "we forgot to mock this URL" signal.
	return canned(http.StatusNotFound,
		fmt.Sprintf(`{"error":"unmocked URL: %s"}`, path)), nil
}

func canned(status int, body string) *http.Response {
	return &http.Response{
		StatusCode: status,
		Status:     fmt.Sprintf("%d %s", status, http.StatusText(status)),
		Body:       io.NopCloser(bytes.NewReader([]byte(body))),
		Header: http.Header{
			"Content-Type": {"application/json"},
		},
	}
}

