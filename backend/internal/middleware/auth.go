package middleware

import (
	"context"
	"net/http"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/internal/auth"
)

type ctxKey string

const userIDKey ctxKey = "userID"
const workspaceIDKey ctxKey = "workspaceID"
const tokenScopeKey ctxKey = "tokenScope"

func RequireAuth(svc *auth.Service, pool *pgxpool.Pool) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			h := r.Header.Get("Authorization")
			var uid string
			var err error
			if strings.HasPrefix(h, "Bearer ") {
				tok := strings.TrimSpace(strings.TrimPrefix(h, "Bearer "))
				if strings.HasPrefix(tok, "kerf_sk_") {
					meta, err := svc.ValidateAPIToken(r.Context(), tok)
					if err != nil {
						http.Error(w, "unauthorized", http.StatusUnauthorized)
						return
					}
					uid = meta.UserID
					ctx := context.WithValue(r.Context(), userIDKey, uid)
					ctx = context.WithValue(ctx, workspaceIDKey, meta.WorkspaceID)
					ctx = context.WithValue(ctx, tokenScopeKey, meta.Scopes)
					next.ServeHTTP(w, r.WithContext(ctx))
					return
				}
				uid, err = svc.ParseAccessToken(tok)
				if err != nil {
					http.Error(w, "unauthorized", http.StatusUnauthorized)
					return
				}
			} else {
				http.Error(w, "unauthorized", http.StatusUnauthorized)
				return
			}
			if !userExists(r.Context(), pool, uid) {
				http.Error(w, "unauthorized", http.StatusUnauthorized)
				return
			}
			ctx := context.WithValue(r.Context(), userIDKey, uid)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

// OptionalAuth attaches a user id if present and the user still exists, but
// does not reject unauthenticated (or stale-user) requests.
func OptionalAuth(svc *auth.Service, pool *pgxpool.Pool) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			h := r.Header.Get("Authorization")
			if strings.HasPrefix(h, "Bearer ") {
				tok := strings.TrimSpace(strings.TrimPrefix(h, "Bearer "))
				if uid, err := svc.ParseAccessToken(tok); err == nil && userExists(r.Context(), pool, uid) {
					ctx := context.WithValue(r.Context(), userIDKey, uid)
					r = r.WithContext(ctx)
				}
			}
			next.ServeHTTP(w, r)
		})
	}
}

func userExists(ctx context.Context, pool *pgxpool.Pool, uid string) bool {
	var exists bool
	if err := pool.QueryRow(ctx, `select exists(select 1 from users where id = $1)`, uid).Scan(&exists); err != nil {
		return false
	}
	return exists
}

// UserID returns the authenticated user id from context (empty string if absent).
func UserID(ctx context.Context) string {
	v, _ := ctx.Value(userIDKey).(string)
	return v
}

// WithUserID returns a copy of ctx that carries uid as the authenticated
// user id. Exposed for tests (and any non-HTTP entry points like a
// background job) that need to populate the same context slot the auth
// middleware writes into. Production HTTP traffic should always go
// through RequireAuth or OptionalAuth.
func WithUserID(ctx context.Context, uid string) context.Context {
	return context.WithValue(ctx, userIDKey, uid)
}

func WorkspaceID(ctx context.Context) string {
	v, _ := ctx.Value(workspaceIDKey).(string)
	return v
}

func TokenScopes(ctx context.Context) []string {
	v, _ := ctx.Value(tokenScopeKey).([]string)
	return v
}

func HasScope(ctx context.Context, required string) bool {
	for _, s := range TokenScopes(ctx) {
		if s == required {
			return true
		}
	}
	return false
}
