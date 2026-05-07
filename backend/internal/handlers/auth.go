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

	"github.com/jackc/pgx/v5"
	"golang.org/x/oauth2"
	googleoauth "golang.org/x/oauth2/google"

	"github.com/imranp/kerf/backend/internal/models"
)

type authResponse struct {
	AccessToken      string            `json:"access_token"`
	RefreshToken     string            `json:"refresh_token"`
	User             models.User       `json:"user"`
	DefaultWorkspace *models.Workspace `json:"default_workspace,omitempty"`
}

type registerReq struct {
	Email    string `json:"email"`
	Password string `json:"password"`
	Name     string `json:"name"`
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
