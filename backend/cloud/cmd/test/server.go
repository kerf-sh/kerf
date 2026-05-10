//go:build cloud
// +build cloud

package main

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/cloud/billing"
	cloudfx "github.com/imranp/kerf/backend/cloud/fx"
	"github.com/imranp/kerf/backend/cloud/library"
	"github.com/imranp/kerf/backend/cloud/workshop"
	"github.com/imranp/kerf/backend/internal/auth"
	"github.com/imranp/kerf/backend/internal/config"
	"github.com/imranp/kerf/backend/internal/db"
	kmw "github.com/imranp/kerf/backend/internal/middleware"
)

// CloudTestUserID is the fixed UUID of the test-only user the cloud
// scenarios drive. We seed one user per ResetState rather than minting
// JWTs, since the routes under test (billing, quota) only need a valid
// user id stamped into request context — not a fully-fledged auth flow.
const (
	CloudTestUserID    = "00000000-0000-0000-0000-000000000001"
	CloudTestUserEmail = "cloud-test@kerf.local"
)

// ensureCloudTestUser idempotently seeds the test user.
func ensureCloudTestUser(ctx context.Context, pool *pgxpool.Pool) error {
	_, err := pool.Exec(ctx, `
		insert into users(id, email, name, avatar_url, account_role, is_system, password_hash)
		values ($1, $2, 'Cloud Test', '', 'user', false, null)
		on conflict (id) do nothing
	`, CloudTestUserID, CloudTestUserEmail)
	return err
}

// injectTestUser is a chi middleware shim that stamps CloudTestUserID
// into request context exactly the way RequireAuth would have. Used in
// place of real JWT auth so the cloud test scenarios stay short.
func injectTestUser(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ctx := kmw.WithUserID(r.Context(), CloudTestUserID)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// testEnv bundles every long-lived dependency a scenario might need. It's
// constructed once at runner start and shared across scenarios — between
// scenarios we ResetState() to wipe rows but keep the server up.
type testEnv struct {
	Cfg        *config.Config
	Pool       *pgxpool.Pool
	HTTPServer *httptest.Server
	FX         *cloudfx.Fetcher
	Paystack   *billing.Client

	// PaystackMock and FXMock are kept around so individual scenarios can
	// reconfigure their handlers (e.g. a different fake response per test)
	// before calling the cloud code under test.
	PaystackMock *paystackMock
	FXMock       *fxMock

	// h is the live billing.Handlers wired into the chi router. ResetState
	// mutates h.FX in place when it swaps fetchers, since the router holds
	// a closure over this pointer.
	h *billing.Handlers
}

// bootTestEnv connects to Postgres, applies all migrations, builds a
// minimal Config that points at our mock servers, and stands up a chi
// router with the cloud routes mounted.
//
// We seed a single test user (cloudTestUserID + cloudTestUserEmail) and
// stamp its id into request context via a shim middleware so the cloud
// handlers can read middleware.UserID(ctx) without us having to mint
// per-request JWTs. The routes that matter (billing/webhook) authenticate
// via HMAC, not JWT, and the topup/me/usage routes only need a valid
// user id in context — which the shim provides.
func bootTestEnv(ctx context.Context) (*testEnv, error) {
	pool, err := db.Connect(ctx, resolveTestDSN())
	if err != nil {
		return nil, fmt.Errorf("connect %s: %w", resolveTestDSN(), err)
	}

	if err := applyAllMigrations(ctx, pool); err != nil {
		pool.Close()
		return nil, fmt.Errorf("migrations: %w", err)
	}

	if err := ensureCloudTestUser(ctx, pool); err != nil {
		pool.Close()
		return nil, fmt.Errorf("ensure test user: %w", err)
	}

	// Mock Paystack first — we set PAYSTACK_BASE_URL before constructing
	// the billing.Client so its NewClient picks it up.
	paystackMock := newPaystackMock()
	if err := os.Setenv("PAYSTACK_BASE_URL", paystackMock.Server.URL); err != nil {
		pool.Close()
		return nil, fmt.Errorf("set PAYSTACK_BASE_URL: %w", err)
	}

	// Mock FX provider. We feed its URL into cfg.Cloud.FX.RefreshURL.
	fxMock := newFXMock()

	cfg := &config.Config{
		Env:           "test",
		Port:          "0", // unused — we use httptest.
		CORSOrigin:    "http://example.test",
		DatabaseURL:   resolveTestDSN(),
		JWTSecret:     "cloud-test-secret",
		JWTAccessTTL:  15 * time.Minute,
		JWTRefreshTTL: 24 * time.Hour,
		Cloud: config.CloudConfig{
			Enabled: true,
			Paystack: config.PaystackConfig{
				SecretKey:     "sk_test_xxx",
				PublicKey:     "pk_test_xxx",
				WebhookSecret: "sk_test_xxx", // Paystack convention: same as secret.
			},
			FX: config.FXConfig{
				BaseCurrency:       "USD",
				SettlementCurrency: "ZAR",
				RefreshURL:         fxMock.Server.URL + "/latest",
				SpreadPct:          1.5,
			},
			Pricing: config.PricingConfig{
				TokenMarkupPct:       20.0,
				StorageUSDPerGBMonth: 0.20,
				FreeStorageMB:        50,
			},
		},
	}

	_ = auth.New(cfg, pool) // kept around for future scenarios that mint real JWTs

	// FX fetcher: we deliberately call New (which does an initial Refresh).
	// For scenarios that want to reset rates, we expose the Fetcher and
	// let them re-trigger Refresh themselves.
	fxFetcher, err := cloudfx.New(ctx, cfg, pool)
	if err != nil {
		pool.Close()
		return nil, fmt.Errorf("fx fetcher: %w", err)
	}

	paystack := billing.NewClient(
		cfg.Cloud.Paystack.SecretKey,
		cfg.Cloud.Paystack.PublicKey,
		cfg.Cloud.Paystack.WebhookSecret,
	)

	h := &billing.Handlers{
		Pool:     pool,
		Cfg:      cfg,
		FX:       fxFetcher,
		Paystack: paystack,
	}

	wh := &workshop.Handlers{
		Pool: pool,
		Cfg:  cfg,
	}

	libH := &library.Handlers{
		Pool: pool,
		Cfg:  cfg,
	}

	r := chi.NewRouter()
	r.Route("/api/billing", func(api chi.Router) {
		api.Group(func(public chi.Router) { h.Mount(nil, public) })
		api.Group(func(authed chi.Router) {
			authed.Use(injectTestUser)
			h.Mount(authed, nil)
		})
	})
	r.Route("/api/workshop", func(api chi.Router) {
		api.Group(func(public chi.Router) { wh.Mount(nil, public) })
		api.Group(func(authed chi.Router) {
			authed.Use(injectTestUser)
			wh.Mount(authed, nil)
		})
	})
	// Mirror the cloud_enabled.go production wiring for /api/library so
	// scenarios can hit the canonical Library routes (Phase 2 + 4 of the
	// Library/Workshop split — ROADMAP row 74).
	r.Route("/api/library", func(api chi.Router) {
		api.Group(func(public chi.Router) {
			public.Get("/parts", wh.ListPartsAlias)
			public.Get("/parts/{slug}", wh.GetPart)
		})
		// Submission queue — Library Phase 3 (ROADMAP row 73). Auth
		// required; injectTestUser stands in for the bearer-token flow.
		api.Group(func(authed chi.Router) {
			authed.Use(injectTestUser)
			libH.MountSubmit(authed)
		})
	})
	r.Route("/api/admin/library", func(api chi.Router) {
		api.Use(injectTestUser)
		libH.MountAdmin(api)
	})

	srv := httptest.NewServer(r)

	// Sanity check: parsing the URL. Failing here means httptest is broken
	// — there's nothing useful we can do, so we surface it.
	if _, err := url.Parse(srv.URL); err != nil {
		srv.Close()
		pool.Close()
		return nil, fmt.Errorf("httptest url: %w", err)
	}

	return &testEnv{
		Cfg:          cfg,
		Pool:         pool,
		HTTPServer:   srv,
		FX:           fxFetcher,
		Paystack:     paystack,
		PaystackMock: paystackMock,
		FXMock:       fxMock,
		h:            h,
	}, nil
}

// ResetState wipes all rows between scenarios while keeping the schema
// and the running httptest server. The test user row is recreated so
// downstream INSERTs on tables that reference users(id) keep working.
func (e *testEnv) ResetState(ctx context.Context) error {
	if err := resetRows(ctx, e.Pool); err != nil {
		return err
	}
	if err := ensureCloudTestUser(ctx, e.Pool); err != nil {
		return err
	}
	// Reset the FX in-memory cache by constructing a fresh fetcher and
	// swapping it in. Calling New also primes the cache from the mock.
	fresh, err := cloudfx.New(ctx, e.Cfg, e.Pool)
	if err != nil {
		return fmt.Errorf("fx reset: %w", err)
	}
	e.FX = fresh
	// Rewire the handlers to point at the new fetcher. The chi router
	// holds a closure over the *billing.Handlers we built at boot, so
	// updating the field in place is enough.
	if e.h != nil {
		e.h.FX = fresh
	}
	// Reset mock state too.
	e.PaystackMock.Reset()
	e.FXMock.Reset()
	return nil
}

// Close shuts down the httptest server and the DB pool. If keepDB is
// false we also drop the schema so the next run starts clean.
func (e *testEnv) Close(keepDB bool) {
	if e.HTTPServer != nil {
		e.HTTPServer.Close()
	}
	if !keepDB && e.Pool != nil {
		_ = dropSchema(context.Background(), e.Pool)
	}
	if e.PaystackMock != nil {
		e.PaystackMock.Server.Close()
	}
	if e.FXMock != nil {
		e.FXMock.Server.Close()
	}
	if e.Pool != nil {
		e.Pool.Close()
	}
	_ = os.Unsetenv("PAYSTACK_BASE_URL")
}
