//go:build cloud
// +build cloud

package git

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"
	"golang.org/x/oauth2"
	githuboauth "golang.org/x/oauth2/github"

	kmw "github.com/imranp/kerf/backend/internal/middleware"
)

// MountOAuthRoutes mounts the GitHub OAuth handlers. The caller passes
// two routers:
//   - `authed` — already wrapped in RequireAuth. Receives /start and
//     DELETE /, both of which need the caller's user_id.
//   - `public` — no auth required. Receives /callback (GitHub itself
//     hits this URL with no Authorization header; we recover the user
//     from the signed state cookie).
//
// Either router may be nil to skip that subset, mirroring the pattern
// used by billing/handlers.go.
func (s *Service) MountOAuthRoutes(authed chi.Router, public chi.Router) {
	if authed != nil {
		authed.Get("/start", s.OAuthStart)
		authed.Delete("/", s.OAuthDisconnect)
	}
	if public != nil {
		public.Get("/callback", s.OAuthCallback)
	}
}

// OAuthStart, OAuthCallback, OAuthDisconnect are exported so cloud-tag
// callers can mount them with custom auth wrappers if needed. Most
// callers should use MountOAuthRoutes instead.
func (s *Service) OAuthStart(w http.ResponseWriter, r *http.Request)      { s.oauthStart(w, r) }
func (s *Service) OAuthCallback(w http.ResponseWriter, r *http.Request)   { s.oauthCallback(w, r) }
func (s *Service) OAuthDisconnect(w http.ResponseWriter, r *http.Request) { s.oauthDisconnect(w, r) }

func (s *Service) githubConfig() *oauth2.Config {
	return &oauth2.Config{
		ClientID:     s.Cfg.Cloud.Git.GitHub.ClientID,
		ClientSecret: s.Cfg.Cloud.Git.GitHub.ClientSecret,
		RedirectURL:  s.Cfg.Cloud.Git.GitHub.RedirectURL,
		// `repo` covers both public and private repo read+write. We
		// take the wider scope deliberately: users link to push their
		// changes back to private repos.
		Scopes:   []string{"repo"},
		Endpoint: githuboauth.Endpoint,
	}
}

// oauthStart kicks off the GitHub OAuth flow. The user must already be
// authenticated to Kerf (the route is wrapped in RequireAuth by the
// caller in cloud_enabled.go). The state cookie carries a CSRF nonce
// and the user_id so the callback — which GitHub hits without an
// Authorization header — can pin the token back to the right account.
func (s *Service) oauthStart(w http.ResponseWriter, r *http.Request) {
	if s.Cfg.Cloud.Git.GitHub.ClientID == "" || s.Cfg.Cloud.Git.GitHub.ClientSecret == "" {
		writeError(w, http.StatusServiceUnavailable, "github oauth not configured")
		return
	}
	uid := kmw.UserID(r.Context())
	if uid == "" {
		writeError(w, http.StatusUnauthorized, "must be authenticated to link github")
		return
	}

	redirect := r.URL.Query().Get("redirect")
	st := oauthState{Nonce: randomNonce(), UserID: uid, Redirect: redirect}
	raw, _ := json.Marshal(st)
	encoded := base64.RawURLEncoding.EncodeToString(raw)

	http.SetCookie(w, &http.Cookie{
		Name:     "kerf_github_oauth_state",
		Value:    encoded,
		Path:     "/",
		HttpOnly: true,
		Secure:   r.TLS != nil,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   600,
	})

	cfg := s.githubConfig()
	loginURL := cfg.AuthCodeURL(encoded, oauth2.AccessTypeOnline)
	http.Redirect(w, r, loginURL, http.StatusFound)
}

// oauthCallback handles the GitHub redirect with ?code=...&state=...
// Validates the state cookie, exchanges the code for a token, fetches
// the user's GitHub profile, encrypts and stores the token, and
// redirects back to the frontend.
func (s *Service) oauthCallback(w http.ResponseWriter, r *http.Request) {
	if s.Cfg.Cloud.Git.GitHub.ClientID == "" || s.Cfg.Cloud.Git.GitHub.ClientSecret == "" {
		writeError(w, http.StatusServiceUnavailable, "github oauth not configured")
		return
	}
	cookie, err := r.Cookie("kerf_github_oauth_state")
	if err != nil {
		writeError(w, http.StatusBadRequest, "missing oauth state cookie")
		return
	}
	state := r.URL.Query().Get("state")
	if state == "" || state != cookie.Value {
		writeError(w, http.StatusBadRequest, "state mismatch")
		return
	}
	// Decode state to recover the user_id.
	raw, err := base64.RawURLEncoding.DecodeString(state)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid state encoding")
		return
	}
	var st oauthState
	if err := json.Unmarshal(raw, &st); err != nil {
		writeError(w, http.StatusBadRequest, "invalid state payload")
		return
	}
	if st.UserID == "" {
		writeError(w, http.StatusBadRequest, "state missing user_id")
		return
	}

	http.SetCookie(w, &http.Cookie{
		Name:     "kerf_github_oauth_state",
		Value:    "",
		Path:     "/",
		HttpOnly: true,
		MaxAge:   -1,
	})

	code := r.URL.Query().Get("code")
	if code == "" {
		writeError(w, http.StatusBadRequest, "missing code")
		return
	}

	cfg := s.githubConfig()
	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()

	tok, err := cfg.Exchange(ctx, code)
	if err != nil {
		writeError(w, http.StatusBadGateway, "oauth exchange failed: "+err.Error())
		return
	}
	scope := tok.Extra("scope")
	scopeStr, _ := scope.(string)

	// Fetch the user's GitHub profile so we can store login + id.
	client := cfg.Client(ctx, tok)
	resp, err := client.Get("https://api.github.com/user")
	if err != nil {
		writeError(w, http.StatusBadGateway, "github profile fetch failed")
		return
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		writeError(w, http.StatusBadGateway, "github profile failed: "+string(body))
		return
	}
	var profile struct {
		ID    int64  `json:"id"`
		Login string `json:"login"`
	}
	if err := json.Unmarshal(body, &profile); err != nil {
		writeError(w, http.StatusBadGateway, "decode github profile: "+err.Error())
		return
	}

	if err := s.saveGithubToken(r.Context(), st.UserID, tok.AccessToken, scopeStr, profile.ID, profile.Login); err != nil {
		writeError(w, http.StatusInternalServerError, "store token: "+err.Error())
		return
	}

	// Confirmation email — fire-and-forget. We pull the user's email
	// inside the same connection rather than passing it through the
	// state cookie because the cookie payload is signed-not-encrypted
	// and emitting an email address into a query-string-bound state
	// blob feels wrong. Failure here is logged inside the mailer and
	// must not break the OAuth completion flow.
	if s.Mailer != nil {
		var recipient string
		if err := s.Pool.QueryRow(r.Context(),
			`select email from users where id = $1`, st.UserID,
		).Scan(&recipient); err == nil && recipient != "" {
			_ = s.Mailer.SendTemplate(r.Context(), "github_linked", recipient, st.UserID, map[string]any{
				"GithubLogin": profile.Login,
				"AppURL":      s.Cfg.CORSOrigin,
			})
		}
	}

	frontend := s.Cfg.CORSOrigin
	dest, _ := url.Parse(frontend)
	if dest == nil || dest.Scheme == "" {
		dest, _ = url.Parse("http://localhost:5173")
	}
	dest.Path = "/auth/callback"
	q := dest.Query()
	q.Set("provider", "github")
	if st.Redirect != "" {
		q.Set("redirect", st.Redirect)
	}
	dest.RawQuery = q.Encode()
	http.Redirect(w, r, dest.String(), http.StatusFound)
}

// oauthDisconnect deletes the user's stored GitHub token. Idempotent.
func (s *Service) oauthDisconnect(w http.ResponseWriter, r *http.Request) {
	uid := kmw.UserID(r.Context())
	if uid == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return
	}
	if err := s.deleteGithubToken(r.Context(), uid); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// oauthState carries the CSRF nonce + the user id (so the callback can
// re-bind the token without depending on session cookies).
type oauthState struct {
	Nonce    string `json:"n"`
	UserID   string `json:"u"`
	Redirect string `json:"r,omitempty"`
}

// randomNonce generates a 16-byte URL-safe random string.
func randomNonce() string {
	raw := make([]byte, 16)
	_, _ = io.ReadFull(rand.Reader, raw)
	return base64.RawURLEncoding.EncodeToString(raw)
}

// errMissingToken is sentinel for "user hasn't linked github yet".
var errMissingToken = errors.New("github not linked")

// requireToken loads + decrypts the user's token, mapping pgx.ErrNoRows
// to errMissingToken so handlers can branch cleanly.
func (s *Service) requireToken(ctx context.Context, userID string) (string, error) {
	tok, err := s.loadGithubToken(ctx, userID)
	if err != nil {
		// pgx.ErrNoRows is returned verbatim by loadGithubToken when no
		// row exists; some pgx wrappers stringify it. Cover both.
		if errors.Is(err, pgx.ErrNoRows) || strings.Contains(err.Error(), "no rows") {
			return "", errMissingToken
		}
		return "", err
	}
	if tok == "" {
		return "", errMissingToken
	}
	return tok, nil
}
