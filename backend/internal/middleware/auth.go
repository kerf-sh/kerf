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

// RequireAuth validates the bearer token, confirms the user still exists in
// the DB (so a JWT issued for a since-deleted user is rejected — this would
// otherwise surface much later as a foreign-key error), and sets the user id
// in the request context. Rejects with 401 on any of: missing token, invalid
// signature, expired token, user no longer exists.
func RequireAuth(svc *auth.Service, pool *pgxpool.Pool) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			h := r.Header.Get("Authorization")
			if !strings.HasPrefix(h, "Bearer ") {
				http.Error(w, "unauthorized", http.StatusUnauthorized)
				return
			}
			tok := strings.TrimSpace(strings.TrimPrefix(h, "Bearer "))
			uid, err := svc.ParseAccessToken(tok)
			if err != nil {
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
