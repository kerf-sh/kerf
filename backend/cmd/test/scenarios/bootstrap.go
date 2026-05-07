package scenarios

// Bootstrap-extension scenarios. The base flow is covered in with_auth.go's
// bootstrapTest; this file adds:
//
//   - File mode 0600 / dir mode 0700 of the on-disk state.
//   - Skipped path when [system_user].password is empty.
//   - Re-boot at the same statePath: state.json is preserved on disk and
//     /api/bootstrap still returns has_state=true for the same email.

import (
	"context"
	"os"
	"path/filepath"
	"runtime"
	"strings"

	"github.com/imranp/kerf/backend/cmd/test/runner"
)

// Bootstrap drives the bootstrap-extension cases.
func Bootstrap(s *runner.Suite, _ *runner.Env) {
	ctx := context.Background()

	tmp, err := os.MkdirTemp("", "kerf-bootstrap-ext-*")
	if !s.NoError("mkdir bootstrap tmp", err) {
		return
	}
	defer os.RemoveAll(tmp)
	statePath := filepath.Join(tmp, "kerf", "state.json")

	// --- Skipped path: [system_user].password empty. ---
	skipState := filepath.Join(tmp, "skip", "state.json")
	envEmpty, err := runner.Boot(ctx, runner.BootOptions{
		SystemUserEmail: "ignored@kerf.local",
		// Password deliberately empty.
		StatePath: skipState,
	})
	if !s.NoError("boot skipped env", err) {
		return
	}

	c := envEmpty.Client
	var skipBoot struct {
		HasState bool `json:"has_state"`
	}
	status, raw, _ := c.DoJSON("GET", "/api/bootstrap", nil, "", &skipBoot)
	if s.Status("GET /api/bootstrap (no password)", status, 200, raw) {
		s.False("has_state false when password empty", skipBoot.HasState)
	}
	// state.json should NOT exist.
	if _, err := os.Stat(skipState); err == nil {
		s.Fail("state.json present when skipped", "expected no state.json when password unset")
	} else if !os.IsNotExist(err) {
		s.Fail("stat skipped state", err.Error())
	} else {
		s.True("state.json absent when skipped", true)
	}
	envEmpty.Cleanup(ctx, true)

	// --- Real bootstrap: produce state.json. ---
	env1, err := runner.Boot(ctx, runner.BootOptions{
		SystemUserEmail:    "shared@kerf.local",
		SystemUserPassword: "passwordfourtytwo",
		SystemUserName:     "Shared",
		StatePath:          statePath,
	})
	if !s.NoError("boot env1", err) {
		return
	}

	// File mode + dir mode checks (POSIX only).
	if runtime.GOOS != "windows" {
		if fi, err := os.Stat(statePath); s.NoError("stat state.json", err) {
			s.Equal("state.json mode 0600", fi.Mode().Perm(), os.FileMode(0o600))
		}
		if fi, err := os.Stat(filepath.Dir(statePath)); s.NoError("stat state dir", err) {
			s.Equal("state dir mode 0700", fi.Mode().Perm(), os.FileMode(0o700))
		}
	}

	// First /api/bootstrap returns the initial refresh token.
	var b1 struct {
		HasState     bool   `json:"has_state"`
		RefreshToken string `json:"refresh_token"`
		User         struct {
			Email string `json:"email"`
		} `json:"user"`
	}
	status, raw, _ = env1.Client.DoJSON("GET", "/api/bootstrap", nil, "", &b1)
	if !s.Status("GET /api/bootstrap env1", status, 200, raw) {
		env1.Cleanup(ctx, true)
		return
	}
	s.True("env1 has_state", b1.HasState)
	s.NotEmpty("env1 refresh_token", b1.RefreshToken)
	s.Equal("env1 user email", b1.User.Email, "shared@kerf.local")

	// state.json content is human-readable and contains the email.
	rawState, err := os.ReadFile(statePath)
	if !s.NoError("read state.json post-env1", err) {
		env1.Cleanup(ctx, true)
		return
	}
	s.True("state.json contains refresh_token field",
		strings.Contains(string(rawState), `"refresh_token"`),
		"state.json missing refresh_token field")
	s.True("state.json contains user email",
		strings.Contains(string(rawState), "shared@kerf.local"),
		"state.json missing email")

	// Tear down env1 (drops schema). state.json stays on disk.
	env1.Cleanup(ctx, true)

	// --- Second boot at the same statePath. The runner's ResetSchema
	// clears refresh_tokens, so the existing token is invalid; the
	// bootstrap path silently re-mints. /api/bootstrap should still
	// return a usable has_state=true bundle for the same email. ---
	env2, err := runner.Boot(ctx, runner.BootOptions{
		SystemUserEmail:    "shared@kerf.local",
		SystemUserPassword: "passwordfourtytwo",
		SystemUserName:     "Shared",
		StatePath:          statePath,
	})
	if !s.NoError("boot env2 (same state path)", err) {
		return
	}
	defer env2.Cleanup(ctx, true)

	var b2 struct {
		HasState bool `json:"has_state"`
		User     struct {
			Email string `json:"email"`
		} `json:"user"`
	}
	status, raw, _ = env2.Client.DoJSON("GET", "/api/bootstrap", nil, "", &b2)
	if s.Status("GET /api/bootstrap env2", status, 200, raw) {
		s.True("env2 has_state", b2.HasState)
		s.Equal("env2 user email matches", b2.User.Email, "shared@kerf.local")
	}

	// Mode + dir mode again, post-restart.
	if runtime.GOOS != "windows" {
		if fi, err := os.Stat(statePath); s.NoError("stat state.json env2", err) {
			s.Equal("state.json still 0600", fi.Mode().Perm(), os.FileMode(0o600))
		}
	}

	_ = os.Unsetenv("KERF_STATE_PATH")
}
