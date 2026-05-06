package middleware

import (
	"context"
	"net/http"
	"strings"

	"github.com/imranp/kerf/backend/internal/auth"
)

type ctxKey string

const userIDKey ctxKey = "userID"

// RequireAuth validates the bearer token and sets the user id in the request
// context. It rejects with 401 if no/invalid token is supplied.
func RequireAuth(svc *auth.Service) func(http.Handler) http.Handler {
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
			ctx := context.WithValue(r.Context(), userIDKey, uid)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

// OptionalAuth attaches a user id if present, but does not reject unauthenticated requests.
func OptionalAuth(svc *auth.Service) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			h := r.Header.Get("Authorization")
			if strings.HasPrefix(h, "Bearer ") {
				tok := strings.TrimSpace(strings.TrimPrefix(h, "Bearer "))
				if uid, err := svc.ParseAccessToken(tok); err == nil {
					ctx := context.WithValue(r.Context(), userIDKey, uid)
					r = r.WithContext(ctx)
				}
			}
			next.ServeHTTP(w, r)
		})
	}
}

// UserID returns the authenticated user id from context (empty string if absent).
func UserID(ctx context.Context) string {
	v, _ := ctx.Value(userIDKey).(string)
	return v
}
