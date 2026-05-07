package handlers

import (
	"net/http"

	"github.com/imranp/kerf/backend/internal/auth"
)

// Bootstrap is the public, no-auth handler that surfaces the on-disk
// bootstrap state file to the frontend. The frontend hits this on first
// load: when has_state is true it silently signs the user in with the
// returned refresh token. When false, the regular login screen renders.
//
// Rationale for the trust model: the state file lives on the same machine
// as the backend. Anyone who can reach /api/bootstrap and read state.json
// over the wire is trivially someone the operator already trusts (they
// have HTTP access to localhost on a single-machine install). For
// multi-user deploys, [system_user].password is left blank and
// EnsureSystemUser does nothing; this endpoint then returns has_state =
// false on every call.
func (d *Deps) Bootstrap(w http.ResponseWriter, r *http.Request) {
	path, err := auth.DefaultStatePath()
	if err != nil {
		writeJSON(w, http.StatusOK, map[string]any{"has_state": false})
		return
	}
	state, err := auth.ReadStateFile(path)
	if err != nil || state == nil || state.RefreshToken == "" {
		writeJSON(w, http.StatusOK, map[string]any{"has_state": false})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"has_state":     true,
		"refresh_token": state.RefreshToken,
		"user":          state.User,
	})
}
