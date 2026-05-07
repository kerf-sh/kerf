// Bootstrap supplies the brew/curl-install "open browser, you're already
// logged in" experience without the legacy auth.optional sentinel-user
// kludge. On a fresh machine, the server reads [system_user] from kerf.toml,
// upserts a real account into the users table, mints a long-lived refresh
// token, and writes the token + user metadata to a small JSON state file
// next to the config. The frontend reads that file via /api/bootstrap on
// first load and silently signs the user in.
//
// All of it is single-machine-only by design — the state file lives where
// the backend runs. Multi-user deployments either skip [system_user] (the
// state file never appears, the regular signup screen is shown) or wire up
// proper auth flows on top of the same JWT path.
package auth

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/internal/config"
)

// BootstrapState is the on-disk shape of state.json. The frontend hits
// /api/bootstrap, which reads this file and returns it as JSON. Single
// source of truth for the auto-login UX.
type BootstrapState struct {
	RefreshToken string             `json:"refresh_token"`
	User         BootstrapStateUser `json:"user"`
	IssuedAt     time.Time          `json:"issued_at"`
}

// BootstrapStateUser is the minimal user payload the frontend needs to
// hydrate the auth store before its first /api/me request.
type BootstrapStateUser struct {
	ID    string `json:"id"`
	Email string `json:"email"`
	Name  string `json:"name"`
}

// EnsureSystemUserResult reports what the boot-time bootstrap actually
// did. The caller logs a one-line summary based on these fields.
type EnsureSystemUserResult struct {
	// Skipped is true when the password (or email) wasn't configured —
	// no user was created, no state file was written, the frontend will
	// see the regular signup screen.
	Skipped bool
	// CreatedUser is true when this run inserted the user (not just
	// re-discovered an existing row).
	CreatedUser bool
	// WroteState is true when this run produced or overwrote state.json.
	WroteState bool
	// StatePath is the absolute path the state file was written to (or
	// would have been, if WroteState is false because of an error). Empty
	// when Skipped is true.
	StatePath string
	// User is the upserted/existing system user.
	User BootstrapStateUser
}

// EnsureSystemUser is the auto-bootstrap entrypoint called once on server
// boot. It is idempotent: subsequent runs will re-issue a fresh refresh
// token only when the on-disk state file is missing or unreadable, so a
// running install with a valid state.json keeps the same token across
// restarts.
//
// Behavior:
//
//   - [system_user].password unset → log a warning, return Skipped=true.
//   - 0 users in DB → insert a system user from [system_user] (account_role
//     = 'system', is_system = true).
//   - users exist → look up the system_user email; if present, reuse it.
//     If the email doesn't match any row, return Skipped=true and let the
//     regular signup flow take over.
//   - State file exists and is valid → return without touching it.
//   - State file missing → mint a new refresh token and write it.
func EnsureSystemUser(ctx context.Context, cfg *config.Config, pool *pgxpool.Pool, svc *Service) (*EnsureSystemUserResult, error) {
	res := &EnsureSystemUserResult{}

	if strings.TrimSpace(cfg.SystemUserPassword) == "" || strings.TrimSpace(cfg.SystemUserEmail) == "" {
		res.Skipped = true
		return res, nil
	}

	statePath, err := DefaultStatePath()
	if err != nil {
		return nil, fmt.Errorf("resolve state path: %w", err)
	}
	res.StatePath = statePath

	email := strings.TrimSpace(strings.ToLower(cfg.SystemUserEmail))
	name := strings.TrimSpace(cfg.SystemUserName)
	if name == "" {
		name = "Kerf System"
	}

	// Are there any users? If not, this is a fresh DB and we own creation.
	// If there are, we look up by email; if it matches we reuse.
	var userCount int
	if err := pool.QueryRow(ctx, `select count(*) from users`).Scan(&userCount); err != nil {
		return nil, fmt.Errorf("count users: %w", err)
	}

	var user BootstrapStateUser
	switch {
	case userCount == 0:
		// Fresh install. Create the user with a hashed password so /auth/login
		// also works against the same account if the user ever wants it.
		hash, err := HashPassword(cfg.SystemUserPassword, cfg.PasswordPepper)
		if err != nil {
			return nil, fmt.Errorf("hash system password: %w", err)
		}
		err = pool.QueryRow(ctx, `
			insert into users(email, name, password_hash, account_role, is_system)
			values ($1, $2, $3, 'system', true)
			returning id, email, name
		`, email, name, hash).Scan(&user.ID, &user.Email, &user.Name)
		if err != nil {
			return nil, fmt.Errorf("insert system user: %w", err)
		}
		res.CreatedUser = true
	default:
		// Some users exist. Try to find the configured system_user by
		// email. If it isn't there, the operator already has a real user
		// and we step out of the way.
		err := pool.QueryRow(ctx, `select id, email, name from users where email = $1`, email).
			Scan(&user.ID, &user.Email, &user.Name)
		if err != nil {
			if errors.Is(err, pgx.ErrNoRows) {
				res.Skipped = true
				return res, nil
			}
			return nil, fmt.Errorf("lookup system user: %w", err)
		}
	}
	res.User = user

	// Is there already a usable state file? Reuse if so.
	if existing, err := ReadStateFile(statePath); err == nil && existing != nil &&
		existing.User.ID == user.ID && existing.RefreshToken != "" {
		// Sanity: confirm the refresh token still maps to a live row in
		// refresh_tokens (not revoked, not expired). If anything is off,
		// we silently re-mint.
		if tokenStillValid(ctx, pool, existing.RefreshToken) {
			return res, nil
		}
	}

	// (Re-)mint a refresh token and write the state file.
	refresh, err := svc.IssueRefreshToken(ctx, user.ID)
	if err != nil {
		return nil, fmt.Errorf("issue refresh token: %w", err)
	}
	state := &BootstrapState{
		RefreshToken: refresh,
		User:         user,
		IssuedAt:     time.Now().UTC(),
	}
	if err := WriteStateFile(statePath, state); err != nil {
		return nil, fmt.Errorf("write state: %w", err)
	}
	res.WroteState = true
	return res, nil
}

// DefaultStatePath returns the canonical location of the bootstrap state
// file: $XDG_CONFIG_HOME/kerf/state.json, or ~/.config/kerf/state.json
// when XDG_CONFIG_HOME is unset.
func DefaultStatePath() (string, error) {
	if v := strings.TrimSpace(os.Getenv("KERF_STATE_PATH")); v != "" {
		return v, nil
	}
	xdg := strings.TrimSpace(os.Getenv("XDG_CONFIG_HOME"))
	if xdg == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return "", err
		}
		xdg = filepath.Join(home, ".config")
	}
	return filepath.Join(xdg, "kerf", "state.json"), nil
}

// WriteStateFile atomically writes the bootstrap state to disk with 0600
// permissions. The directory is created if missing. Best-effort sync —
// we treat a write error as fatal at boot, since the whole point of
// bootstrap is to leave a usable artifact.
func WriteStateFile(path string, state *BootstrapState) error {
	if path == "" {
		return errors.New("empty state path")
	}
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return fmt.Errorf("mkdir %s: %w", dir, err)
	}
	raw, err := json.MarshalIndent(state, "", "  ")
	if err != nil {
		return err
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, raw, 0o600); err != nil {
		return err
	}
	if err := os.Rename(tmp, path); err != nil {
		return err
	}
	return nil
}

// ReadStateFile loads and parses the bootstrap state file. Returns
// (nil, nil) if the file doesn't exist; otherwise (state, nil) on
// success, or a parse / IO error.
func ReadStateFile(path string) (*BootstrapState, error) {
	if path == "" {
		return nil, errors.New("empty state path")
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil, nil
		}
		return nil, err
	}
	var state BootstrapState
	if err := json.Unmarshal(raw, &state); err != nil {
		return nil, err
	}
	return &state, nil
}

// tokenStillValid is a private helper: returns true if the supplied
// refresh token resolves to a non-revoked, non-expired row in refresh_tokens.
// Used by EnsureSystemUser to decide whether to reuse an on-disk state
// file or re-mint a fresh token.
func tokenStillValid(ctx context.Context, pool *pgxpool.Pool, token string) bool {
	hash := HashToken(token)
	var (
		expires   time.Time
		revokedAt *time.Time
	)
	err := pool.QueryRow(ctx,
		`select expires_at, revoked_at from refresh_tokens where token_hash = $1`,
		hash).Scan(&expires, &revokedAt)
	if err != nil {
		return false
	}
	if revokedAt != nil {
		return false
	}
	if time.Now().After(expires) {
		return false
	}
	return true
}
