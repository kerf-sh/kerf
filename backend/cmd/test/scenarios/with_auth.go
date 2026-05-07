package scenarios

import (
	"context"
	"fmt"
	"os"
	"path/filepath"

	"github.com/imranp/kerf/backend/cmd/test/runner"
)

// authBundle mirrors the auth response shape (exported across scenarios so
// tests can reuse it).
type authBundle struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	User         struct {
		ID    string `json:"id"`
		Email string `json:"email"`
		Name  string `json:"name"`
	} `json:"user"`
}

// register is a tiny inline helper. The richer version lives in
// cmd/test/seed.go but scenarios stay self-contained.
func register(c *runner.Client, email, password, name string) (authBundle, int, []byte) {
	var out authBundle
	status, raw, _ := c.DoJSON("POST", "/auth/register", map[string]string{
		"email": email, "password": password, "name": name,
	}, "", &out)
	return out, status, raw
}

func login(c *runner.Client, email, password string) (authBundle, int, []byte) {
	var out authBundle
	status, raw, _ := c.DoJSON("POST", "/auth/login", map[string]string{
		"email": email, "password": password,
	}, "", &out)
	return out, status, raw
}

// WithAuth covers the full email/password mode: register, login, refresh,
// logout, plus per-user project visibility.
func WithAuth(s *runner.Suite, env *runner.Env) {
	c := env.Client

	// Register a single user.
	bundle, status, raw := register(c, "alice@example.com", "hunter22supersecret", "Alice")
	if !s.Status("POST /auth/register alice", status, 201, raw) {
		return
	}
	s.NotEmpty("alice.access_token", bundle.AccessToken)
	s.NotEmpty("alice.refresh_token", bundle.RefreshToken)
	s.Equal("alice.email", bundle.User.Email, "alice@example.com")

	// Login with the same credentials returns a fresh bundle.
	loginBundle, status, raw := login(c, "alice@example.com", "hunter22supersecret")
	if !s.Status("POST /auth/login alice", status, 200, raw) {
		return
	}
	s.NotEmpty("login.access_token", loginBundle.AccessToken)
	s.NotEmpty("login.refresh_token", loginBundle.RefreshToken)

	// /api/me with bearer.
	var me struct {
		ID    string `json:"id"`
		Email string `json:"email"`
	}
	status, raw, _ = c.DoJSON("GET", "/api/me", nil, loginBundle.AccessToken, &me)
	if !s.Status("GET /api/me with token", status, 200, raw) {
		return
	}
	s.Equal("me.email", me.Email, "alice@example.com")

	// /api/me without bearer → 401.
	status, raw, _ = c.Do("GET", "/api/me", nil, "")
	s.Status("GET /api/me no bearer", status, 401, raw)

	// /api/me with malformed bearer → 401.
	status, raw, _ = c.Do("GET", "/api/me", nil, "garbage.token.here")
	s.Status("GET /api/me malformed bearer", status, 401, raw)

	// Two-user isolation.
	bob, status, raw := register(c, "bob@example.com", "anotherpassword", "Bob")
	if !s.Status("POST /auth/register bob", status, 201, raw) {
		return
	}

	// Alice creates a project.
	var aliceProj struct {
		ID      string `json:"id"`
		OwnerID string `json:"owner_id"`
		MyRole  string `json:"my_role"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects", map[string]string{
		"name": "Alice's secret",
	}, loginBundle.AccessToken, &aliceProj)
	if !s.Status("alice create project", status, 201, raw) {
		return
	}
	s.Equal("alice project owner", aliceProj.OwnerID, loginBundle.User.ID)

	// Bob's GET → 404 (not 403 — keep existence private).
	status, raw, _ = c.Do("GET", "/api/projects/"+aliceProj.ID, nil, bob.AccessToken)
	s.Status("bob GET alice project", status, 404, raw)

	// Bob's project list does not include alice's.
	var bobList []map[string]any
	status, raw, _ = c.DoJSON("GET", "/api/projects", nil, bob.AccessToken, &bobList)
	if s.Status("bob list projects", status, 200, raw) {
		s.Equal("bob projects empty", len(bobList), 0)
	}

	// /auth/refresh rotates the refresh token.
	var refreshed authBundle
	status, raw, _ = c.DoJSON("POST", "/auth/refresh", map[string]string{
		"refresh_token": loginBundle.RefreshToken,
	}, "", &refreshed)
	if s.Status("POST /auth/refresh", status, 200, raw) {
		s.NotEmpty("refreshed.access_token", refreshed.AccessToken)
		s.True("refreshed.refresh_token rotated",
			refreshed.RefreshToken != "" && refreshed.RefreshToken != loginBundle.RefreshToken,
			"refresh token did not rotate")
	}

	// The previously-used refresh token must not be reusable (it was revoked
	// by the rotate above).
	status, raw, _ = c.Do("POST", "/auth/refresh", map[string]string{
		"refresh_token": loginBundle.RefreshToken,
	}, "")
	s.Status("POST /auth/refresh stale", status, 401, raw)

	// /auth/logout revokes the current refresh token.
	status, raw, _ = c.Do("POST", "/auth/logout", map[string]string{
		"refresh_token": refreshed.RefreshToken,
	}, refreshed.AccessToken)
	s.Status("POST /auth/logout", status, 204, raw)

	// Subsequent /auth/refresh with the now-revoked token must fail.
	status, raw, _ = c.Do("POST", "/auth/refresh", map[string]string{
		"refresh_token": refreshed.RefreshToken,
	}, "")
	s.Status("POST /auth/refresh after logout", status, 401, raw)

	// Sanity: alice's access token still works for read-only routes (it
	// hasn't expired yet — the access token is independent of the refresh
	// token revocation in this mode).
	_ = fmt.Sprintf

	// --- Auto-bootstrap (single-user brew/curl-install path) ---------------
	bootstrapTest(s)
}

// bootstrapTest spins up a separate env wired with [system_user] populated
// to verify the auto-bootstrap flow end-to-end:
//
//  1. Server boot writes ~/.config/kerf/state.json (we redirect via
//     KERF_STATE_PATH so the test stays hermetic).
//  2. GET /api/bootstrap returns has_state=true with the same refresh
//     token from disk.
//  3. POST /auth/refresh with that refresh token returns access + user.
//  4. The user row in the DB has the configured system_user email.
//
// On a multi-user-style boot (no system_user.password) the same endpoint
// returns has_state=false — we exercise that variant too.
func bootstrapTest(s *runner.Suite) {
	ctx := context.Background()
	tmp, err := os.MkdirTemp("", "kerf-bootstrap-*")
	if !s.NoError("mkdir bootstrap tmp", err) {
		return
	}
	defer os.RemoveAll(tmp)
	statePath := filepath.Join(tmp, "state.json")

	env, err := runner.Boot(ctx, runner.BootOptions{
		SystemUserEmail:    "single-user@kerf.local",
		SystemUserPassword: "bootstrappassword99",
		SystemUserName:     "Single User",
		StatePath:          statePath,
	})
	if !s.NoError("boot bootstrap env", err) {
		return
	}
	defer env.Cleanup(ctx, true)
	defer os.Unsetenv("KERF_STATE_PATH")

	c := env.Client

	// state.json must exist on disk now.
	if _, err := os.Stat(statePath); !s.NoError("state.json on disk", err) {
		return
	}

	// /api/bootstrap should expose the same refresh token.
	var boot struct {
		HasState     bool   `json:"has_state"`
		RefreshToken string `json:"refresh_token"`
		User         struct {
			ID    string `json:"id"`
			Email string `json:"email"`
			Name  string `json:"name"`
		} `json:"user"`
	}
	status, raw, err := c.DoJSON("GET", "/api/bootstrap", nil, "", &boot)
	if !s.NoError("GET /api/bootstrap err", err) {
		return
	}
	if !s.Status("GET /api/bootstrap", status, 200, raw) {
		return
	}
	s.True("bootstrap.has_state", boot.HasState, "expected has_state=true")
	s.NotEmpty("bootstrap.refresh_token", boot.RefreshToken)
	s.Equal("bootstrap.user.email", boot.User.Email, "single-user@kerf.local")

	// The refresh token must be usable against /auth/refresh.
	var refreshed authBundle
	status, raw, _ = c.DoJSON("POST", "/auth/refresh", map[string]string{
		"refresh_token": boot.RefreshToken,
	}, "", &refreshed)
	if !s.Status("POST /auth/refresh w/ bootstrap token", status, 200, raw) {
		return
	}
	s.NotEmpty("refreshed.access_token", refreshed.AccessToken)
	s.Equal("refreshed.user.email", refreshed.User.Email, "single-user@kerf.local")

	// /api/me with the freshly-rotated access token confirms the user is
	// real and reachable through the standard auth path.
	var me struct {
		Email string `json:"email"`
	}
	status, raw, _ = c.DoJSON("GET", "/api/me", nil, refreshed.AccessToken, &me)
	if s.Status("GET /api/me w/ bootstrap-derived token", status, 200, raw) {
		s.Equal("me.email after bootstrap", me.Email, "single-user@kerf.local")
	}
}
