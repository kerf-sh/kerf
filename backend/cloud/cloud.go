//go:build cloud
// +build cloud

// Package cloud is the entry point for the proprietary hosted-mode
// billing layer. Everything under backend/cloud is gated by the
// `cloud` build tag so OSS builds never compile or link this code.
//
// The OSS server in cmd/server/main.go calls into Register(...) only
// when cfg.Cloud.Enabled is true; even the call site is build-tagged so
// the OSS binary doesn't carry a dangling import.
package cloud

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/cloud/billing"
	cloudfx "github.com/imranp/kerf/backend/cloud/fx"
	"github.com/imranp/kerf/backend/cloud/usage"
	"github.com/imranp/kerf/backend/internal/config"
	"github.com/imranp/kerf/backend/internal/llm"
)

// Service holds the long-lived cloud-side dependencies. It owns the FX
// fetcher and the Paystack client, and it knows how to mount the billing
// HTTP routes. The OSS handlers package never imports this — to call into
// cloud functionality from OSS code, the OSS layer would have to expose
// hooks (it doesn't, today; usage is recorded directly via the usage
// package by cloud-tag'd shims when needed).
type Service struct {
	Cfg      *config.Config
	Pool     *pgxpool.Pool
	Registry *llm.Registry
	FX       *cloudfx.Fetcher
	Paystack *billing.Client

	// cancel stops the background goroutines spun up by New.
	cancel context.CancelFunc
}

// New boots the cloud service: constructs the Paystack client, fetches an
// initial FX rate, and spawns the daily refresh + monthly storage rollup
// goroutines. The returned Service must outlive the goroutines; call
// Service.Stop() on shutdown.
func New(cfg *config.Config, pool *pgxpool.Pool, registry *llm.Registry) (*Service, error) {
	if !cfg.Cloud.Enabled {
		// Defensive: this function should only be called from a
		// cloud-tagged build path that already checked Enabled.
		return nil, fmt.Errorf("cloud.New called with cloud.enabled=false")
	}

	bgCtx, cancel := context.WithCancel(context.Background())

	fxFetcher, err := cloudfx.New(bgCtx, cfg, pool)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("cloud: fx fetcher: %w", err)
	}

	pkey := cfg.Cloud.Paystack
	if pkey.SecretKey == "" {
		log.Printf("cloud: WARNING paystack.secret_key empty — billing endpoints will return 503")
	}
	paystack := billing.NewClient(pkey.SecretKey, pkey.PublicKey, pkey.WebhookSecret)

	svc := &Service{
		Cfg:      cfg,
		Pool:     pool,
		Registry: registry,
		FX:       fxFetcher,
		Paystack: paystack,
		cancel:   cancel,
	}

	// Daily FX refresh.
	go fxFetcher.Start(bgCtx)
	// Monthly storage rollup. The actual debit logic is unimplemented
	// (see usage.MonthlyStorageDebit) but the loop is wired up so when
	// the function lands, the schedule is already running.
	go svc.runMonthlyStorageLoop(bgCtx)

	return svc, nil
}

// Stop cancels background goroutines.
func (s *Service) Stop() {
	if s.cancel != nil {
		s.cancel()
	}
}

// Register mounts the billing routes onto the parent /api router. The
// caller (cmd/server/main.go in a cloud build) is expected to pass:
//   - `authed`: a chi.Router already wrapped in RequireAuth — the topup,
//     me, and usage endpoints attach here.
//   - `public`: a chi.Router that is publicly reachable — the Paystack
//     webhook attaches here. Auth comes from the HMAC signature, not the
//     auth middleware.
//
// Returning a function rather than taking the routers up front keeps the
// OSS main.go simpler and avoids leaking router structure into Service.
func (s *Service) Register(authed chi.Router, public chi.Router) {
	h := &billing.Handlers{
		Pool:     s.Pool,
		Cfg:      s.Cfg,
		FX:       s.FX,
		Paystack: s.Paystack,
	}
	h.Mount(authed, public)
}

// RecordTokenEvent is a thin re-export so OSS packages can call into
// usage recording through the cloud Service handle (when one exists)
// without importing the cloud/usage package directly.
func (s *Service) RecordTokenEvent(
	ctx context.Context,
	userID string,
	projectID *string,
	model string,
	in, out int,
	costUSD float64,
) error {
	return usage.RecordTokenEvent(ctx, s.Pool, userID, projectID, model, in, out, costUSD)
}

// runMonthlyStorageLoop sleeps until the first of the next month and
// invokes MonthlyStorageDebit. The function itself is currently a TODO,
// so this is effectively a no-op timer until that lands.
func (s *Service) runMonthlyStorageLoop(ctx context.Context) {
	for {
		next := nextMonthStart(time.Now().UTC())
		wait := time.Until(next)
		select {
		case <-ctx.Done():
			return
		case <-time.After(wait):
		}
		if err := usage.MonthlyStorageDebit(ctx, s.Pool); err != nil {
			// Expected today (TODO in usage package). Don't spam logs.
			log.Printf("cloud: monthly storage debit: %v", err)
		}
	}
}

func nextMonthStart(now time.Time) time.Time {
	y, m, _ := now.Date()
	return time.Date(y, m+1, 1, 0, 5, 0, 0, time.UTC)
}
