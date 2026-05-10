package scenarios

// Preferences exercises the /api/me/preferences surface end-to-end:
//
//   1. Register a fresh user.
//   2. GET /api/me/preferences → 200 + empty object.
//   3. PUT a valid object → 200 + same shape echoed back.
//   4. GET → returns the saved object.
//   5. PUT with an unknown key → 400.
//   6. PUT with an out-of-range autosave_delay_ms → 400.

import (
	"encoding/json"

	"github.com/imranp/kerf/backend/cmd/test/runner"
)

func Preferences(s *runner.Suite, env *runner.Env) {
	c := env.Client

	user, status, raw := register(c, "prefs-user@example.com", "prefspassword99", "Prefs User")
	if !s.Status("register prefs user", status, 201, raw) {
		return
	}

	// 1. Fresh user has empty preferences object.
	status, raw, _ = c.Do("GET", "/api/me/preferences", nil, user.AccessToken)
	if !s.Status("GET /api/me/preferences fresh", status, 200, raw) {
		return
	}
	var initial map[string]any
	_ = json.Unmarshal(raw, &initial)
	s.Equal("preferences fresh empty", len(initial), 0)

	// 2. PUT a valid set.
	want := map[string]any{
		"default_model": "claude-haiku-4-5",
		"units":         "inches",
	}
	status, raw, _ = c.Do("PUT", "/api/me/preferences", want, user.AccessToken)
	if !s.Status("PUT /api/me/preferences valid", status, 200, raw) {
		return
	}
	var saved map[string]any
	_ = json.Unmarshal(raw, &saved)
	s.Equal("saved.default_model", saved["default_model"], "claude-haiku-4-5")
	s.Equal("saved.units", saved["units"], "inches")

	// 3. GET round-trips.
	status, raw, _ = c.Do("GET", "/api/me/preferences", nil, user.AccessToken)
	if !s.Status("GET /api/me/preferences after PUT", status, 200, raw) {
		return
	}
	var got map[string]any
	_ = json.Unmarshal(raw, &got)
	s.Equal("got.default_model", got["default_model"], "claude-haiku-4-5")
	s.Equal("got.units", got["units"], "inches")

	// 4. Unknown key → 400.
	bad := map[string]any{"garbage_key": "value"}
	status, raw, _ = c.Do("PUT", "/api/me/preferences", bad, user.AccessToken)
	s.Status("PUT garbage key → 400", status, 400, raw)

	// 5. Out-of-range int → 400.
	oob := map[string]any{"autosave_delay_ms": 50}
	status, raw, _ = c.Do("PUT", "/api/me/preferences", oob, user.AccessToken)
	s.Status("PUT autosave OOB → 400", status, 400, raw)

	// 6. Wrong type for theme → 400.
	wrong := map[string]any{"theme": "neon"}
	status, raw, _ = c.Do("PUT", "/api/me/preferences", wrong, user.AccessToken)
	s.Status("PUT bad theme → 400", status, 400, raw)
}
