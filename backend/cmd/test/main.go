// Package main is the kerf integration-test CLI.
//
// It boots an in-process kerf HTTP server using net/http/httptest against
// a real Postgres test DB (KERF_TEST_DATABASE_URL or the documented
// fallback) and runs scenarios that drive the public API.
//
// Usage:
//
//	go run ./cmd/test --scenario=all
//	go run ./cmd/test --scenario=with_auth
//	go run ./cmd/test --scenario=with_auth,features
//
// Exits non-zero if any scenario records a failure.
package main

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/imranp/kerf/backend/cmd/test/runner"
	"github.com/imranp/kerf/backend/cmd/test/scenarios"
)

// scenarioFn is the signature each scenario file exposes.
type scenarioFn func(*runner.Suite, *runner.Env)

// scenarioDef bundles a scenario's name, its boot options, and its body.
type scenarioDef struct {
	Name string
	Opts runner.BootOptions
	Run  scenarioFn
}

// allScenarios is the dispatch table. Listed in the order they should run.
var allScenarios = []scenarioDef{
	{Name: "with_auth", Opts: runner.BootOptions{}, Run: scenarios.WithAuth},
	{Name: "features", Opts: runner.BootOptions{}, Run: scenarios.Features},
	{Name: "pentest", Opts: runner.BootOptions{}, Run: scenarios.Pentest},
	{Name: "library", Opts: runner.BootOptions{}, Run: scenarios.Library},
	{Name: "sketcher", Opts: runner.BootOptions{}, Run: scenarios.Sketcher},
	{Name: "drawings", Opts: runner.BootOptions{}, Run: scenarios.Drawings},
	{Name: "feature_files", Opts: runner.BootOptions{}, Run: scenarios.FeatureFiles},
	{Name: "activity", Opts: runner.BootOptions{}, Run: scenarios.Activity},
	{Name: "avatars", Opts: runner.BootOptions{}, Run: scenarios.Avatars},
	{Name: "bootstrap", Opts: runner.BootOptions{}, Run: scenarios.Bootstrap},
}

func main() {
	scenarioFlag := "all"
	verbose := false
	for i := 1; i < len(os.Args); i++ {
		a := os.Args[i]
		switch {
		case a == "-v" || a == "--verbose":
			verbose = true
		case strings.HasPrefix(a, "--scenario="):
			scenarioFlag = strings.TrimPrefix(a, "--scenario=")
		case a == "--scenario":
			if i+1 < len(os.Args) {
				scenarioFlag = os.Args[i+1]
				i++
			}
		case a == "-h" || a == "--help":
			printHelp()
			return
		}
	}

	selected := selectScenarios(scenarioFlag)
	if len(selected) == 0 {
		fmt.Fprintf(os.Stderr, "no scenarios match %q\n", scenarioFlag)
		fmt.Fprintf(os.Stderr, "available: %s, all\n", strings.Join(scenarioNames(), ", "))
		os.Exit(2)
	}

	fmt.Println("[scenarios] running...")

	overallStart := time.Now()
	totalAssertions := 0
	failedScenarios := 0
	suites := make([]*runner.Suite, 0, len(selected))

	for _, def := range selected {
		suite, ok := runScenario(def, verbose)
		suites = append(suites, suite)
		totalAssertions += suite.Assertions
		if !ok {
			failedScenarios++
		}
	}

	// Summary line.
	totalElapsed := time.Since(overallStart)
	passed := len(selected) - failedScenarios
	fmt.Println()
	fmt.Printf("%d passed, %d failed (%d scenarios, %d assertions, %s)\n",
		passed, failedScenarios, len(selected), totalAssertions, totalElapsed.Round(time.Millisecond))

	if failedScenarios > 0 {
		os.Exit(1)
	}
}

// runScenario boots an env, runs the scenario, prints PASS/FAIL, and tears
// the env down. Returns the populated Suite + a bool indicating success.
func runScenario(def scenarioDef, verbose bool) (*runner.Suite, bool) {
	ctx := context.Background()
	env, err := runner.Boot(ctx, def.Opts)
	if err != nil {
		fmt.Printf("  [FAIL] %s (boot): %v\n", def.Name, err)
		// Synthesize a suite so the summary counter still works.
		s := runner.NewSuite(def.Name, nil)
		s.Fail("boot", err.Error())
		return s, false
	}
	defer env.Cleanup(ctx, true)

	s := runner.NewSuite(def.Name, env)
	defer func() {
		if r := recover(); r != nil {
			s.Fail("panic", fmt.Sprintf("scenario panicked: %v", r))
		}
	}()
	def.Run(s, env)

	if s.Failed() {
		fmt.Printf("  [FAIL] %s (%s, %d assertions):\n", s.Name,
			s.Elapsed().Round(time.Millisecond), s.Assertions)
		for _, f := range s.Failures {
			fmt.Printf("    - %s: %s\n", f.Step, indentLines(f.Message, "        "))
		}
		return s, false
	}
	fmt.Printf("  [PASS] %s (%s, %d assertions)\n",
		s.Name, s.Elapsed().Round(time.Millisecond), s.Assertions)
	if verbose {
		fmt.Printf("         server=%s\n", env.Server.URL)
	}
	return s, true
}

// selectScenarios resolves a comma-separated list (or "all") to the
// matching scenarioDef entries, preserving allScenarios order.
func selectScenarios(spec string) []scenarioDef {
	spec = strings.TrimSpace(spec)
	if spec == "" || spec == "all" {
		return allScenarios
	}
	wanted := map[string]bool{}
	for _, p := range strings.Split(spec, ",") {
		wanted[strings.TrimSpace(p)] = true
	}
	out := []scenarioDef{}
	for _, d := range allScenarios {
		if wanted[d.Name] {
			out = append(out, d)
		}
	}
	return out
}

func scenarioNames() []string {
	out := make([]string, 0, len(allScenarios))
	for _, d := range allScenarios {
		out = append(out, d.Name)
	}
	return out
}

// indentLines prefixes every line after the first with prefix. Keeps the
// first line raw so it follows the "- step:" anchor cleanly.
func indentLines(s, prefix string) string {
	lines := strings.Split(s, "\n")
	if len(lines) <= 1 {
		return s
	}
	for i := 1; i < len(lines); i++ {
		lines[i] = prefix + lines[i]
	}
	return strings.Join(lines, "\n")
}

func printHelp() {
	fmt.Println(`kerf integration test runner

Usage:
  go run ./cmd/test [--scenario=<name|all>] [-v]

Scenarios:
  ` + strings.Join(scenarioNames(), "\n  ") + `
  all (default)

Environment:
  KERF_TEST_DATABASE_URL — Postgres URL for the test DB.
                           Default: postgres://postgres:postgres@localhost:5432/kerf_test?sslmode=disable

The DB must already exist (createdb kerf_test) and be reachable.`)
}
