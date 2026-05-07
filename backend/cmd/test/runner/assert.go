package runner

import (
	"fmt"
	"reflect"
	"strings"
	"time"
)

// Suite is the per-scenario assertion accumulator. It holds the scenario
// name, an Env reference, the count of assertions performed, and any
// failures recorded. Scenarios call its helpers to record PASS/FAIL.
type Suite struct {
	Name       string
	Env        *Env
	Assertions int
	Failures   []Failure
	StartTime  time.Time
}

// Failure is one assertion failure with enough context to debug.
type Failure struct {
	Step    string
	Message string
}

// NewSuite constructs a Suite tied to the given env.
func NewSuite(name string, env *Env) *Suite {
	return &Suite{Name: name, Env: env, StartTime: time.Now()}
}

// Failed reports whether any assertion failed.
func (s *Suite) Failed() bool { return len(s.Failures) > 0 }

// Elapsed returns the wall time since NewSuite was called.
func (s *Suite) Elapsed() time.Duration { return time.Since(s.StartTime) }

// fail records a failure with the given step + message. Returns false so
// callers can `if !s.Equal(...) { return }` to early-exit dependent steps.
func (s *Suite) fail(step, msg string) bool {
	s.Failures = append(s.Failures, Failure{Step: step, Message: msg})
	return false
}

// Fail is the exported direct-failure helper, for cases where a scenario
// can detect a problem without going through Equal/True/etc. Always returns
// false so it can be used in `if !s.Fail(...)` chains.
func (s *Suite) Fail(step, msg string) bool {
	s.Assertions++
	return s.fail(step, msg)
}

// pass increments the assertion counter (used internally when an assertion
// succeeds).
func (s *Suite) pass() bool {
	s.Assertions++
	return true
}

// Equal asserts deep equality between got and want.
func (s *Suite) Equal(step string, got, want any) bool {
	s.Assertions++
	if !reflect.DeepEqual(got, want) {
		return s.fail(step, fmt.Sprintf("got %v, want %v", got, want))
	}
	return true
}

// True asserts that cond is true.
func (s *Suite) True(step string, cond bool, msgAndArgs ...any) bool {
	s.Assertions++
	if !cond {
		msg := "expected true"
		if len(msgAndArgs) > 0 {
			if f, ok := msgAndArgs[0].(string); ok {
				msg = fmt.Sprintf(f, msgAndArgs[1:]...)
			}
		}
		return s.fail(step, msg)
	}
	return true
}

// False asserts that cond is false.
func (s *Suite) False(step string, cond bool, msgAndArgs ...any) bool {
	return s.True(step, !cond, msgAndArgs...)
}

// Contains asserts that haystack contains needle (substring).
func (s *Suite) Contains(step, haystack, needle string) bool {
	s.Assertions++
	if !strings.Contains(haystack, needle) {
		return s.fail(step, fmt.Sprintf("expected to contain %q, got %q", needle, truncate(haystack, 200)))
	}
	return true
}

// Status asserts that an HTTP status matches. Body is included in failure
// messages so the cause is visible on the first run.
func (s *Suite) Status(step string, gotStatus, wantStatus int, body []byte) bool {
	s.Assertions++
	if gotStatus != wantStatus {
		return s.fail(step,
			fmt.Sprintf("expected status %d, got %d\n    body: %s",
				wantStatus, gotStatus, truncate(string(body), 400)))
	}
	return true
}

// NotEmpty asserts that a string is non-empty.
func (s *Suite) NotEmpty(step, value string) bool {
	s.Assertions++
	if value == "" {
		return s.fail(step, "expected non-empty string")
	}
	return true
}

// NoError asserts err is nil.
func (s *Suite) NoError(step string, err error) bool {
	s.Assertions++
	if err != nil {
		return s.fail(step, fmt.Sprintf("unexpected error: %v", err))
	}
	return true
}
