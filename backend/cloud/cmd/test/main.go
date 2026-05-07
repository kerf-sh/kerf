//go:build cloud
// +build cloud

// Command test is the cloud-only end-to-end test runner. It boots an
// in-process httptest server with both OSS and cloud routes mounted,
// applies the OSS + cloud SQL migrations against a real Postgres, and
// drives the billing/FX/quota scenarios end-to-end.
//
// Usage:
//
//	go run -tags=cloud ./cloud/cmd/test --scenario=all
//	go run -tags=cloud ./cloud/cmd/test --scenario=paystack_init
//
// The runner does NOT compile or link without -tags=cloud — every file in
// this package is gated by `//go:build cloud`. That mirrors the rest of
// backend/cloud and ensures the OSS binary stays free of paystack/fx code.
//
// Test database: $KERF_TEST_DATABASE_URL or
// postgres://postgres:postgres@localhost:5432/kerf_test_cloud?sslmode=disable.
// Distinct from the OSS test default (kerf_test) so the two suites can run
// in parallel without stepping on each other.
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"strings"
)

// scenarioFunc is the signature each scenario file exports. They take the
// boot result (httptest server URL, pool, deps) and a Suite to record
// PASS/FAIL into. They never call os.Exit themselves — main does that
// after summing across scenarios.
type scenarioFunc func(ctx context.Context, env *testEnv, suite *Suite)

// scenarios is the registry. Keys are the names accepted by --scenario.
// Add new files under this directory and register them here.
var scenarios = map[string]scenarioFunc{
	"paystack_init":     runPaystackInit,
	"paystack_webhook":  runPaystackWebhook,
	"fx_refresh":        runFXRefresh,
	"quota_gate":        runQuotaGate,
	"workshop_parts":    runWorkshopParts,
	"workshop_listings": runWorkshopListings,
}

func main() {
	scenarioFlag := flag.String("scenario", "all", "comma-separated list of scenarios, or 'all'")
	keepDBFlag := flag.Bool("keep-db", false, "leave the test database populated after run (default: drop schema on exit)")
	verboseFlag := flag.Bool("v", false, "verbose logging from server + scenarios")
	flag.Parse()

	if !*verboseFlag {
		// Quiet the chi/middleware log noise unless -v is passed.
		log.SetFlags(0)
		log.SetOutput(os.Stderr)
	}

	selected, err := selectScenarios(*scenarioFlag)
	if err != nil {
		fmt.Fprintf(os.Stderr, "scenario flag: %v\n", err)
		os.Exit(2)
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	env, err := bootTestEnv(ctx)
	if err != nil {
		fmt.Fprintf(os.Stderr, "boot: %v\n", err)
		os.Exit(2)
	}
	defer env.Close(*keepDBFlag)

	suite := NewSuite()

	for _, name := range selected {
		fn, ok := scenarios[name]
		if !ok {
			suite.Failf(name, "unknown scenario %q", name)
			continue
		}
		fmt.Printf("=== RUN  %s\n", name)
		// Truncate state between scenarios so they're independent. We keep
		// the schema (migrations applied) but wipe rows.
		if err := env.ResetState(ctx); err != nil {
			suite.Failf(name, "reset state: %v", err)
			continue
		}
		fn(ctx, env, suite)
	}

	suite.PrintSummary(os.Stdout)
	if suite.Failed() > 0 {
		os.Exit(1)
	}
}

// selectScenarios resolves the --scenario flag into an ordered slice.
// "all" expands to a deterministic ordering that matches the registry's
// natural test pyramid (FX → init → webhook → quota).
func selectScenarios(arg string) ([]string, error) {
	if arg == "" || arg == "all" {
		return []string{"fx_refresh", "paystack_init", "paystack_webhook", "quota_gate",
			"workshop_parts", "workshop_listings"}, nil
	}
	parts := strings.Split(arg, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p == "" {
			continue
		}
		if _, ok := scenarios[p]; !ok {
			names := make([]string, 0, len(scenarios))
			for k := range scenarios {
				names = append(names, k)
			}
			return nil, fmt.Errorf("unknown scenario %q (available: %s)", p, strings.Join(names, ", "))
		}
		out = append(out, p)
	}
	return out, nil
}
