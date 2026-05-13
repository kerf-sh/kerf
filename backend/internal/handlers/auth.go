package handlers

import (
	"context"
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
	googleoauth "golang.org/x/oauth2/google"

	"github.com/imranp/kerf/backend/internal/middleware"
	"github.com/imranp/kerf/backend/internal/models"
)

type authResponse struct {
	AccessToken      string            `json:"access_token"`
	RefreshToken     string            `json:"refresh_token"`
	User             models.User       `json:"user"`
	DefaultWorkspace *models.Workspace `json:"default_workspace,omitempty"`
}

// OnUserRegistered is an OSS-side hook the cloud build assigns to send the
// welcome email after a successful registration. The OSS build leaves it nil
// (no email plumbing), so callers must nil-check before invoking. Kept in the
// OSS package so handlers/* never imports backend/cloud/*.
var OnUserRegistered func(ctx context.Context, userID, email, name string)

type registerReq struct {
	Email    string `json:"email"`
	Password string `json:"password"`
	Name     string `json:"name"`
}

// BootstrapLocal is the local-mode-only auto-account endpoint. When
// `[server].local_mode = true` (the OSS default), the frontend hits this
// on first paint and gets back a fully-authed bundle without ever
// rendering /login.
//
// Behavior:
//
//   - Cloud build / local_mode=false → 404. The endpoint simply isn't
//     wired into the cloud router, but we also gate here in defense in
//     depth so a misconfigured proxy can't accidentally expose it.
//   - First call (zero users): create the singleton user (email +
//     name come from [system_user] when set, falling back to
//     "local@kerf.local" / "Local"), attach a personal workspace,
//     mint tokens, return.
//   - Subsequent calls: look up the same email and re-mint tokens.
//     The user, workspace, and projects all persist across restarts.
//
// Idempotent — safe to hammer from a flaky frontend boot path.
func (d *Deps) BootstrapLocal(w http.ResponseWriter, r *http.Request) {
	if !d.Cfg.LocalMode {
		writeError(w, http.StatusNotFound, "not found")
		return
	}
	email := strings.TrimSpace(strings.ToLower(d.Cfg.SystemUserEmail))
	if email == "" {
		email = "local@kerf.local"
	}
	name := strings.TrimSpace(d.Cfg.SystemUserName)
	if name == "" {
		name = "Local"
	}

	ctx := r.Context()
	var u models.User
	err := d.Pool.QueryRow(ctx,
		`select id, email, name, avatar_url, account_role, is_system, created_at
		   from users where email = $1`,
		email).Scan(&u.ID, &u.Email, &u.Name, &u.AvatarURL, &u.AccountRole, &u.IsSystem, &u.CreatedAt)
	if err != nil {
		if !errors.Is(err, pgx.ErrNoRows) {
			genericServerError(w, err)
			return
		}
		// First boot: create the singleton user. We deliberately leave
		// password_hash NULL — the local-mode user authenticates only
		// via this endpoint + the issued refresh token. There's no
		// /auth/login path against this account.
		err = d.Pool.QueryRow(ctx, `
			insert into users(email, name, account_role, is_system)
			values ($1, $2, 'system', true)
			returning id, email, name, avatar_url, account_role, is_system, created_at
		`, email, name).Scan(&u.ID, &u.Email, &u.Name, &u.AvatarURL, &u.AccountRole, &u.IsSystem, &u.CreatedAt)
		if err != nil {
			if isUniqueViolation(err) {
				// Race: another concurrent bootstrap-local won. Re-read.
				err = d.Pool.QueryRow(ctx,
					`select id, email, name, avatar_url, account_role, is_system, created_at
					   from users where email = $1`,
					email).Scan(&u.ID, &u.Email, &u.Name, &u.AvatarURL, &u.AccountRole, &u.IsSystem, &u.CreatedAt)
			}
			if err != nil {
				genericServerError(w, err)
				return
			}
		}
	}
	d.issueAndRespond(w, r, u, http.StatusOK)
}

// Register creates a new email/password user and issues tokens.
func (d *Deps) Register(w http.ResponseWriter, r *http.Request) {
	var body registerReq
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	body.Email = strings.TrimSpace(strings.ToLower(body.Email))
	if body.Email == "" || body.Password == "" {
		writeError(w, http.StatusBadRequest, "email and password are required")
		return
	}
	if len(body.Password) < 8 {
		writeError(w, http.StatusBadRequest, "password must be at least 8 characters")
		return
	}
	hash, err := d.Auth.HashPassword(body.Password)
	if err != nil {
		genericServerError(w, err)
		return
	}
	var u models.User
	err = d.Pool.QueryRow(r.Context(), `
		insert into users(email, password_hash, name)
		values ($1, $2, $3)
		returning id, email, name, avatar_url, account_role, is_system, created_at
	`, body.Email, hash, body.Name).Scan(&u.ID, &u.Email, &u.Name, &u.AvatarURL, &u.AccountRole, &u.IsSystem, &u.CreatedAt)
	if err != nil {
		if isUniqueViolation(err) {
			writeError(w, http.StatusConflict, "email already registered")
			return
		}
		genericServerError(w, err)
		return
	}
	// Bootstrap a personal workspace so the user has somewhere to go.
	displayName := body.Name
	if displayName == "" {
		// fall back to the local-part of their email.
		if at := strings.Index(body.Email, "@"); at > 0 {
			displayName = body.Email[:at]
		} else {
			displayName = "My"
		}
	}
	if _, err := createPersonalWorkspace(r.Context(), d.Pool, u.ID, displayName); err != nil {
		// Non-fatal: log and proceed without a workspace; the client can
		// still create one later.
		// Use a simple stderr-style write via the JSON error path on demand.
		// (Don't fail registration just because workspace creation hiccupped.)
	}
	d.issueAndRespond(w, r, u, http.StatusCreated)
}

type loginReq struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

// Login verifies the password and issues new tokens.
func (d *Deps) Login(w http.ResponseWriter, r *http.Request) {
	var body loginReq
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	body.Email = strings.TrimSpace(strings.ToLower(body.Email))
	var (
		u    models.User
		hash *string
	)
	err := d.Pool.QueryRow(r.Context(), `
		select id, email, name, avatar_url, account_role, is_system, created_at, password_hash
		from users where email = $1
	`, body.Email).Scan(&u.ID, &u.Email, &u.Name, &u.AvatarURL, &u.AccountRole, &u.IsSystem, &u.CreatedAt, &hash)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusUnauthorized, "invalid credentials")
			return
		}
		genericServerError(w, err)
		return
	}
	if hash == nil || *hash == "" || !d.Auth.CheckPassword(*hash, body.Password) {
		writeError(w, http.StatusUnauthorized, "invalid credentials")
		return
	}
	d.issueAndRespond(w, r, u, http.StatusOK)
}

type refreshReq struct {
	RefreshToken string `json:"refresh_token"`
}

// Refresh rotates the refresh token and issues a new access token.
func (d *Deps) Refresh(w http.ResponseWriter, r *http.Request) {
	var body refreshReq
	if err := decodeJSON(r, &body); err != nil || body.RefreshToken == "" {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	uid, access, newRefresh, err := d.Auth.RotateRefreshToken(r.Context(), body.RefreshToken)
	if err != nil {
		writeError(w, http.StatusUnauthorized, err.Error())
		return
	}
	u, err := loadUser(r.Context(), d, uid)
	if err != nil {
		genericServerError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, authResponse{AccessToken: access, RefreshToken: newRefresh, User: u})
}

// Logout revokes a refresh token. Always 204 even if the token was unknown.
func (d *Deps) Logout(w http.ResponseWriter, r *http.Request) {
	var body refreshReq
	if err := decodeJSON(r, &body); err == nil && body.RefreshToken != "" {
		_ = d.Auth.RevokeRefreshToken(r.Context(), body.RefreshToken)
	}
	w.WriteHeader(http.StatusNoContent)
}

func (d *Deps) issueAndRespond(w http.ResponseWriter, r *http.Request, u models.User, status int) {
	access, err := d.Auth.IssueAccessToken(u.ID)
	if err != nil {
		genericServerError(w, err)
		return
	}
	refresh, err := d.Auth.IssueRefreshToken(r.Context(), u.ID)
	if err != nil {
		genericServerError(w, err)
		return
	}
	resp := authResponse{AccessToken: access, RefreshToken: refresh, User: u}
	if ws, ok, err := d.defaultWorkspaceForUser(r.Context(), u.ID); err == nil && ok {
		resp.DefaultWorkspace = &ws
	} else if err == nil && !ok {
		// Lazy bootstrap: any user without a workspace (seeded system user,
		// pre-workspaces account, failed register-time creation) gets one on
		// next sign-in. Non-fatal on error — the client can still create one.
		display := strings.TrimSpace(u.Name)
		if display == "" {
			if at := strings.Index(u.Email, "@"); at > 0 {
				display = u.Email[:at]
			} else {
				display = "My"
			}
		}
		if ws, err := createPersonalWorkspace(r.Context(), d.Pool, u.ID, display); err == nil {
			resp.DefaultWorkspace = &ws
		}
	}
	writeJSON(w, status, resp)
}

func loadUser(ctx context.Context, d *Deps, uid string) (models.User, error) {
	var u models.User
	err := d.Pool.QueryRow(ctx,
		`select id, email, name, avatar_url, account_role, is_system, created_at from users where id = $1`,
		uid).Scan(&u.ID, &u.Email, &u.Name, &u.AvatarURL, &u.AccountRole, &u.IsSystem, &u.CreatedAt)
	return u, err
}

func isUniqueViolation(err error) bool {
	return err != nil && strings.Contains(strings.ToLower(err.Error()), "unique")
}

// --- Google OAuth ---

func (d *Deps) googleConfig() *oauth2.Config {
	return &oauth2.Config{
		ClientID:     d.Cfg.GoogleClientID,
		ClientSecret: d.Cfg.GoogleClientSecret,
		RedirectURL:  d.Cfg.GoogleRedirectURL,
		Scopes:       []string{"openid", "email", "profile"},
		Endpoint:     googleoauth.Endpoint,
	}
}

type oauthState struct {
	Nonce    string `json:"n"`
	Redirect string `json:"r"`
}

func (d *Deps) GoogleStart(w http.ResponseWriter, r *http.Request) {
	if d.Cfg.GoogleClientID == "" || d.Cfg.GoogleClientSecret == "" {
		writeError(w, http.StatusServiceUnavailable, "google oauth not configured")
		return
	}
	redirect := r.URL.Query().Get("redirect")
	st := oauthState{Nonce: randomNonce(), Redirect: redirect}
	raw, _ := json.Marshal(st)
	encoded := base64.RawURLEncoding.EncodeToString(raw)

	http.SetCookie(w, &http.Cookie{
		Name:     "kerf_oauth_state",
		Value:    encoded,
		Path:     "/",
		HttpOnly: true,
		Secure:   r.TLS != nil,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   600,
	})

	cfg := d.googleConfig()
	url := cfg.AuthCodeURL(encoded, oauth2.AccessTypeOnline)
	http.Redirect(w, r, url, http.StatusFound)
}

func (d *Deps) GoogleCallback(w http.ResponseWriter, r *http.Request) {
	if d.Cfg.GoogleClientID == "" || d.Cfg.GoogleClientSecret == "" {
		writeError(w, http.StatusServiceUnavailable, "google oauth not configured")
		return
	}
	cookie, err := r.Cookie("kerf_oauth_state")
	if err != nil {
		writeError(w, http.StatusBadRequest, "missing oauth state cookie")
		return
	}
	state := r.URL.Query().Get("state")
	if state == "" || state != cookie.Value {
		writeError(w, http.StatusBadRequest, "state mismatch")
		return
	}
	http.SetCookie(w, &http.Cookie{
		Name:     "kerf_oauth_state",
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

	cfg := d.googleConfig()
	ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
	defer cancel()
	tok, err := cfg.Exchange(ctx, code)
	if err != nil {
		writeError(w, http.StatusBadGateway, "oauth exchange failed: "+err.Error())
		return
	}
	client := cfg.Client(ctx, tok)
	resp, err := client.Get("https://www.googleapis.com/oauth2/v3/userinfo")
	if err != nil {
		writeError(w, http.StatusBadGateway, "userinfo fetch failed")
		return
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		writeError(w, http.StatusBadGateway, "userinfo failed: "+string(raw))
		return
	}
	var info struct {
		Sub     string `json:"sub"`
		Email   string `json:"email"`
		Name    string `json:"name"`
		Picture string `json:"picture"`
	}
	if err := json.Unmarshal(raw, &info); err != nil {
		writeError(w, http.StatusBadGateway, "decode userinfo: "+err.Error())
		return
	}

	u, err := d.upsertGoogleUser(r.Context(), info.Sub, info.Email, info.Name, info.Picture)
	if err != nil {
		genericServerError(w, err)
		return
	}
	access, err := d.Auth.IssueAccessToken(u.ID)
	if err != nil {
		genericServerError(w, err)
		return
	}
	refresh, err := d.Auth.IssueRefreshToken(r.Context(), u.ID)
	if err != nil {
		genericServerError(w, err)
		return
	}

	frontend := d.Cfg.CORSOrigin
	dest, _ := url.Parse(frontend)
	if dest == nil || dest.Scheme == "" {
		dest, _ = url.Parse("http://localhost:5173")
	}
	dest.Path = "/auth/callback"
	q := dest.Query()
	q.Set("access_token", access)
	q.Set("refresh_token", refresh)
	dest.RawQuery = q.Encode()
	http.Redirect(w, r, dest.String(), http.StatusFound)
}

func (d *Deps) upsertGoogleUser(ctx context.Context, sub, email, name, picture string) (models.User, error) {
	email = strings.TrimSpace(strings.ToLower(email))
	var u models.User
	// On every successful path, mirror the Google avatar to our own storage so
	// we don't depend on Google's URL going forward. The helper short-circuits
	// when the user already has a storage-backed avatar.
	defer func() {
		if u.ID != "" && picture != "" {
			go d.pullGoogleAvatar(u.ID, picture)
		}
	}()
	// 1. By google_id.
	err := d.Pool.QueryRow(ctx, `
		update users set name = coalesce(nullif($2,''), name),
		                 avatar_url = coalesce(nullif($3,''), avatar_url)
		where google_id = $1
		returning id, email, name, avatar_url, account_role, is_system, created_at
	`, sub, name, picture).Scan(&u.ID, &u.Email, &u.Name, &u.AvatarURL, &u.AccountRole, &u.IsSystem, &u.CreatedAt)
	if err == nil {
		return u, nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return u, err
	}
	// 2. By email — link google_id.
	err = d.Pool.QueryRow(ctx, `
		update users set google_id = $1,
		                 name = coalesce(nullif($3,''), name),
		                 avatar_url = coalesce(nullif($4,''), avatar_url)
		where email = $2
		returning id, email, name, avatar_url, account_role, is_system, created_at
	`, sub, email, name, picture).Scan(&u.ID, &u.Email, &u.Name, &u.AvatarURL, &u.AccountRole, &u.IsSystem, &u.CreatedAt)
	if err == nil {
		return u, nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return u, err
	}
	// 3. Insert.
	err = d.Pool.QueryRow(ctx, `
		insert into users(email, google_id, name, avatar_url)
		values ($1,$2,$3,$4)
		returning id, email, name, avatar_url, account_role, is_system, created_at
	`, email, sub, name, picture).Scan(&u.ID, &u.Email, &u.Name, &u.AvatarURL, &u.AccountRole, &u.IsSystem, &u.CreatedAt)
	if err != nil {
		return u, err
	}
	// Bootstrap a personal workspace; non-fatal on failure.
	display := name
	if display == "" {
		if at := strings.Index(email, "@"); at > 0 {
			display = email[:at]
		} else {
			display = "My"
		}
	}
	_, _ = createPersonalWorkspace(ctx, d.Pool, u.ID, display)
	return u, nil
}

type apiTokenResponse struct {
	ID        string    `json:"id"`
	Name      string    `json:"name"`
	Token     string    `json:"token,omitempty"`
	Scopes    []string  `json:"scopes"`
	CreatedAt time.Time `json:"created_at"`
}

type createTokenReq struct {
	Name string `json:"name"`
}

func (d *Deps) CreateAPIToken(w http.ResponseWriter, r *http.Request) {
	var body createTokenReq
	if err := decodeJSON(r, &body); err != nil || body.Name == "" {
		writeError(w, http.StatusBadRequest, "name is required")
		return
	}
	ctx := r.Context()
	uid := middleware.UserID(ctx)
	wid := middleware.WorkspaceID(ctx)
	if wid == "" {
		writeError(w, http.StatusBadRequest, "workspace context required")
		return
	}
	token, err := d.Auth.CreateAPIToken(ctx, wid, uid, body.Name)
	if err != nil {
		genericServerError(w, err)
		return
	}
	meta, err := d.Auth.ValidateAPIToken(ctx, token)
	if err != nil {
		genericServerError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, apiTokenResponse{
		ID:        meta.ID,
		Name:      meta.Name,
		Token:     token,
		Scopes:    meta.Scopes,
		CreatedAt: meta.CreatedAt,
	})
}

func (d *Deps) ListAPITokens(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	uid := middleware.UserID(ctx)
	wid := middleware.WorkspaceID(ctx)
	if wid == "" {
		writeError(w, http.StatusBadRequest, "workspace context required")
		return
	}
	tokens, err := d.Auth.ListAPITokens(ctx, wid, uid)
	if err != nil {
		genericServerError(w, err)
		return
	}
	out := make([]apiTokenResponse, len(tokens))
	for i, t := range tokens {
		out[i] = apiTokenResponse{ID: t.ID, Name: t.Name, Scopes: t.Scopes, CreatedAt: t.CreatedAt}
	}
	writeJSON(w, http.StatusOK, out)
}

func (d *Deps) RevokeAPIToken(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	uid := middleware.UserID(ctx)
	wid := middleware.WorkspaceID(ctx)
	if wid == "" {
		writeError(w, http.StatusBadRequest, "workspace context required")
		return
	}
	tokenID := chi.URLParam(r, "token_id")
	if tokenID == "" {
		writeError(w, http.StatusBadRequest, "token_id required")
		return
	}
	if err := d.Auth.RevokeAPIToken(ctx, tokenID, wid, uid); err != nil {
		genericServerError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func randomNonce() string {
	raw := make([]byte, 16)
	_, _ = io.ReadFull(cryptoRand{}, raw)
	return base64.RawURLEncoding.EncodeToString(raw)
}

// cryptoRand wraps crypto/rand to avoid importing it twice in this file.
type cryptoRand struct{}

func (cryptoRand) Read(p []byte) (int, error) {
	return cryptoRandRead(p)
}
