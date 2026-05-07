//go:build cloud
// +build cloud

package main

import (
	"fmt"
	"io"
	"reflect"
	"strings"
	"sync"
	"time"
)

// Suite tracks pass/fail counts across scenarios and exposes assertion
// helpers that record into the suite without halting on first failure.
//
// We intentionally do not use the standard `testing` package — `go test`
// would force us to scaffold the whole runtime as a package test, which
// makes the build-tag fence harder to keep clean (test binaries pick up
// _test.go files regardless of tag for the host package). A custom runner
// keeps the boundary obvious: this is a cloud-tagged main, full stop.
type Suite struct {
	mu      sync.Mutex
	results []result
}

type result struct {
	scenario string
	name     string
	passed   bool
	message  string
	at       time.Time
}

// NewSuite constructs an empty suite.
func NewSuite() *Suite {
	return &Suite{results: make([]result, 0, 64)}
}

// Pass records a successful assertion under the given scenario.
func (s *Suite) Pass(scenario, name string) {
	s.record(scenario, name, true, "")
}

// Fail records a failed assertion. Scenarios call this directly when the
// failure message is already prepared.
func (s *Suite) Fail(scenario, name, message string) {
	s.record(scenario, name, false, message)
}

// Failf is the printf-style sibling of Fail.
func (s *Suite) Failf(scenario, format string, args ...interface{}) {
	s.record(scenario, "", false, fmt.Sprintf(format, args...))
}

func (s *Suite) record(scenario, name string, passed bool, message string) {
	s.mu.Lock()
	s.results = append(s.results, result{
		scenario: scenario,
		name:     name,
		passed:   passed,
		message:  message,
		at:       time.Now(),
	})
	s.mu.Unlock()
	prefix := "  PASS"
	if !passed {
		prefix = "  FAIL"
	}
	if name == "" {
		fmt.Printf("%s [%s] %s\n", prefix, scenario, message)
	} else if passed {
		fmt.Printf("%s [%s] %s\n", prefix, scenario, name)
	} else {
		fmt.Printf("%s [%s] %s: %s\n", prefix, scenario, name, message)
	}
}

// Failed returns how many assertions across all scenarios failed.
func (s *Suite) Failed() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	n := 0
	for _, r := range s.results {
		if !r.passed {
			n++
		}
	}
	return n
}

// PrintSummary writes a one-line-per-scenario summary plus a grand total.
func (s *Suite) PrintSummary(w io.Writer) {
	s.mu.Lock()
	defer s.mu.Unlock()
	byScenario := map[string]struct{ pass, fail int }{}
	order := []string{}
	for _, r := range s.results {
		c, ok := byScenario[r.scenario]
		if !ok {
			order = append(order, r.scenario)
		}
		if r.passed {
			c.pass++
		} else {
			c.fail++
		}
		byScenario[r.scenario] = c
	}
	fmt.Fprintln(w, "")
	fmt.Fprintln(w, "--- Summary ---")
	totalPass, totalFail := 0, 0
	for _, name := range order {
		c := byScenario[name]
		fmt.Fprintf(w, "  %-20s pass=%d fail=%d\n", name, c.pass, c.fail)
		totalPass += c.pass
		totalFail += c.fail
	}
	fmt.Fprintf(w, "  %-20s pass=%d fail=%d\n", "TOTAL", totalPass, totalFail)
}

// --- assertion helpers ---
//
// These mirror what `testing.T.Errorf` calls would look like, but record
// into the Suite. None of them halt — scenarios should `return` after a
// fatal precondition fails.

// Assert records a pass/fail named `name` under `scenario`. cond=true means pass.
func (s *Suite) Assert(scenario, name string, cond bool, failMsg string) bool {
	if cond {
		s.Pass(scenario, name)
		return true
	}
	s.Fail(scenario, name, failMsg)
	return false
}

// AssertEqual compares with reflect.DeepEqual.
func (s *Suite) AssertEqual(scenario, name string, want, got interface{}) bool {
	if reflect.DeepEqual(want, got) {
		s.Pass(scenario, name)
		return true
	}
	s.Fail(scenario, name, fmt.Sprintf("want %v, got %v", want, got))
	return false
}

// AssertNoError records pass when err is nil, fail (with message) otherwise.
func (s *Suite) AssertNoError(scenario, name string, err error) bool {
	if err == nil {
		s.Pass(scenario, name)
		return true
	}
	s.Fail(scenario, name, fmt.Sprintf("unexpected error: %v", err))
	return false
}

// AssertFloatNear checks that |want-got| <= eps. Used for FX math where a
// straight equality check would be brittle.
func (s *Suite) AssertFloatNear(scenario, name string, want, got, eps float64) bool {
	delta := want - got
	if delta < 0 {
		delta = -delta
	}
	if delta <= eps {
		s.Pass(scenario, name)
		return true
	}
	s.Fail(scenario, name, fmt.Sprintf("want %v ±%v, got %v (delta=%v)", want, eps, got, delta))
	return false
}

// AssertContains checks that `haystack` contains `needle`.
func (s *Suite) AssertContains(scenario, name, haystack, needle string) bool {
	if strings.Contains(haystack, needle) {
		s.Pass(scenario, name)
		return true
	}
	s.Fail(scenario, name, fmt.Sprintf("expected to contain %q, got %q", needle, haystack))
	return false
}
