//go:build cloud
// +build cloud

package main

import (
	"context"
	"log"

	"github.com/go-chi/chi/v5"

	"github.com/imranp/kerf/backend/cloud/billing"
	cloudemail "github.com/imranp/kerf/backend/cloud/email"
	"github.com/imranp/kerf/backend/cloud/fx"
	"github.com/imranp/kerf/backend/cloud/git"
	"github.com/imranp/kerf/backend/cloud/library"
	"github.com/imranp/kerf/backend/cloud/usage"
	"github.com/imranp/kerf/backend/cloud/workshop"
	"github.com/imranp/kerf/backend/internal/distributors"
	"github.com/imranp/kerf/backend/internal/handlers"
	kmw "github.com/imranp/kerf/backend/internal/middleware"
)

// fxAdapter bridges the cloud fx.Fetcher to the distributors package's
// FXConverter interface. The FX cache stores USD/<X> rates, so to
// convert from a foreign currency to USD we invert the stored rate.
type fxAdapter struct{ f *fx.Fetcher }

func (a fxAdapter) Convert(amount float64, from, to string) (float64, bool) {
	if from == to {
		return amount, true
	}
	// Look up <to>/<from> directly first (e.g. USD/CNY for the
	// CNY→USD conversion).
	if rate, _, ok := a.f.Rate(to, from); ok && rate > 0 {
		return amount / rate, true
	}
	// Fallback: stored as <from>/<to> directly.
	if rate, _, ok := a.f.Rate(from, to); ok && rate > 0 {
		return amount * rate, true
	}
	return 0, false
}

// registerCloud is the cloud-build implementation. It boots the FX
// fetcher (daily refresh of USD→ZAR), wires the Paystack client, and
// mounts /api/billing/* routes — the authenticated subset behind
// RequireAuth, the webhook public.
func registerCloud(ctx context.Context, r chi.Router, deps *handlers.Deps) {
	fxFetcher, err := fx.New(ctx, deps.Cfg, deps.Pool)
	if err != nil {
		log.Fatalf("cloud fx init: %v", err)
	}
	fxFetcher.Start(ctx)

	// Plug the FX fetcher into the distributors registry so LCSC's
	// CNY-priced results convert to USD. Best-effort: the OSS path
	// already works without this; SetFX just upgrades the LCSC entry.
	if reg, ok := deps.Distributors.(*distributors.Registry); ok && reg != nil {
		reg.SetFX(ctx, fxAdapter{f: fxFetcher})
	}

	// Transactional email subsystem. Boot reads cloud_email_credentials
	// and starts the drain goroutine; SendTemplate calls from billing,
	// usage, git, workshop dispatch through this single Mailer instance.
	// We boot it BEFORE the billing handlers are constructed so the
	// post-charge receipt hook can reference it.
	mailer := cloudemail.Boot(ctx, deps.Pool, deps.Cfg)

	// Wire the OSS-side post-register hook to the mailer. This is the
	// one place the OSS handlers package's `OnUserRegistered` function
	// pointer gets populated; the OSS build leaves it nil. Keeping the
	// hook in the OSS package (and assigning here from cloud) preserves
	// the build-tag isolation: handlers/* never imports backend/cloud/*.
	handlers.OnUserRegistered = func(ctx context.Context, userID, email, name string) {
		appURL := deps.Cfg.CORSOrigin
		_ = mailer.SendTemplate(ctx, "welcome", email, userID, map[string]any{
			"Name":   name,
			"AppURL": appURL,
		})
	}

	// Plug the mailer into the usage package so token-debit hooks can
	// fire low-balance notifications. The usage package can't import
	// the email package directly (cyclic — billing depends on usage),
	// so it accepts an interface and we hand it the concrete *Mailer.
	usage.SetMailer(mailer, deps.Cfg.CORSOrigin)

	paystack := billing.NewClient(
		deps.Cfg.Cloud.Paystack.SecretKey,
		deps.Cfg.Cloud.Paystack.PublicKey,
		deps.Cfg.Cloud.Paystack.WebhookSecret,
	)

	h := &billing.Handlers{
		Pool:     deps.Pool,
		Cfg:      deps.Cfg,
		FX:       fxFetcher,
		Paystack: paystack,
		Mailer:   mailer,
	}

	// /api/billing — authed routes for the user's own account, plus a
	// public /webhook for Paystack callbacks. The `Mount` helper takes
	// two routers so the caller controls auth wrapping; we hand it an
	// auth-wrapped sub-router and a plain one.
	r.Route("/api/billing", func(api chi.Router) {
		api.Group(func(public chi.Router) {
			h.Mount(nil, public) // mounts only the webhook
		})
		api.Group(func(authed chi.Router) {
			authed.Use(kmw.RequireAuth(deps.Auth, deps.Pool))
			h.Mount(authed, nil) // mounts the authed routes
		})
	})

	log.Printf("cloud: mounted /api/billing/{topup,me,usage,webhook}")

	// /api/workshop — same split-router pattern. Public routes use
	// OptionalAuth so an authenticated browser sees liked_by_me on the
	// returned listings, but unauthenticated visitors aren't gated out.
	mp := &workshop.Handlers{Pool: deps.Pool, Cfg: deps.Cfg, Mailer: mailer}
	r.Route("/api/workshop", func(api chi.Router) {
		api.Group(func(public chi.Router) {
			public.Use(kmw.OptionalAuth(deps.Auth, deps.Pool))
			mp.Mount(nil, public)
		})
		api.Group(func(authed chi.Router) {
			authed.Use(kmw.RequireAuth(deps.Auth, deps.Pool))
			mp.Mount(authed, nil)
		})
	})

	log.Printf("cloud: mounted /api/workshop/{list,detail,publish,like,fork}")

	// /api/library — canonical alias for the parts catalog. The Library
	// is the same data as /api/workshop/parts, but mounted under its own
	// top-level path so it can grow independently of the Workshop's
	// project-listing surface (see ROADMAP "Library / Workshop split").
	// /api/workshop/parts is kept as a deprecated alias.
	libHandlers := &library.Handlers{Pool: deps.Pool, Cfg: deps.Cfg}
	r.Route("/api/library", func(api chi.Router) {
		api.Group(func(public chi.Router) {
			public.Use(kmw.OptionalAuth(deps.Auth, deps.Pool))
			public.Get("/parts", mp.ListPartsAlias)
			public.Get("/parts/{slug}", mp.GetPart)
		})
		// /api/library/submissions — manufacturer-PR submission endpoint
		// (Library Phase 3, ROADMAP row 73). Auth required (any role); the
		// row lands in library_part_submissions.status='pending' until an
		// admin reviews it via /api/admin/library/submissions/{id}.
		api.Group(func(authed chi.Router) {
			authed.Use(kmw.RequireAuth(deps.Auth, deps.Pool))
			libHandlers.MountSubmit(authed)
		})
	})

	log.Printf("cloud: mounted /api/library/parts, /api/library/parts/{slug}, /api/library/submissions")

	// /api/admin/library — admin review queue. Admin role enforced
	// inside each handler (mirrors /api/admin/distributors).
	r.Route("/api/admin/library", func(api chi.Router) {
		api.Use(kmw.RequireAuth(deps.Auth, deps.Pool))
		libHandlers.MountAdmin(api)
	})
	log.Printf("cloud: mounted /api/admin/library/submissions[/{id}]")

	// Real-git integration. Bare repos live on disk under
	// cfg.Cloud.Git.Root; per-project routes mount under
	// /api/projects/{pid}/git/* (authed). The /auth/github/* OAuth
	// flow mounts at the top-level router — start/callback are public,
	// the DELETE is authed inline.
	gitSvc, err := git.New(deps.Cfg, deps.Pool, deps.Storage)
	if err != nil {
		log.Fatalf("cloud git init: %v", err)
	}
	gitSvc.Mailer = mailer
	r.Route("/api/projects/{pid}/git", func(api chi.Router) {
		api.Use(kmw.RequireAuth(deps.Auth, deps.Pool))
		gitSvc.MountProjectRoutes(api)
	})
	r.Route("/auth/github", func(sub chi.Router) {
		// /start needs the caller's identity to bind the token; we
		// require Bearer auth here too. The actual /callback is hit
		// by GitHub itself (no auth header) and pulls the user_id
		// out of the signed state cookie.
		sub.Group(func(public chi.Router) {
			gitSvc.MountOAuthRoutes(nil, public)
		})
		sub.Group(func(authed chi.Router) {
			authed.Use(kmw.RequireAuth(deps.Auth, deps.Pool))
			gitSvc.MountOAuthRoutes(authed, nil)
		})
	})
	log.Printf("cloud: mounted /api/projects/.../git/* and /auth/github/*")

	// Admin: transactional email provider config + log. Admin role is
	// enforced inside each handler (mirrors /api/admin/distributors).
	emailAdmin := &cloudemail.AdminHandlers{
		Pool:   deps.Pool,
		Cfg:    deps.Cfg,
		Mailer: mailer,
	}
	r.Route("/api/admin/email", func(api chi.Router) {
		api.Use(kmw.RequireAuth(deps.Auth, deps.Pool))
		emailAdmin.Mount(api)
	})
	log.Printf("cloud: mounted /api/admin/email/{providers,test,log}")
}
