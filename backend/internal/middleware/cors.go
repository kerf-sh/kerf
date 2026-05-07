package middleware

import (
	"net/http"
	"strings"
)

// CORS allows one or more origins (comma-separated). When the request's Origin
// header matches one of them, that exact origin is reflected back so credentialed
// requests work (Access-Control-Allow-Origin: * is invalid with credentials).
//
// `*` is supported: it reflects whatever Origin was sent. Useful in dev when
// Vite picks an unpredictable port (5173, 5174, 5175…). Not recommended in prod.
func CORS(allowed string) func(http.Handler) http.Handler {
	origins := splitAndTrim(allowed)
	wildcard := false
	for _, o := range origins {
		if o == "*" {
			wildcard = true
			break
		}
	}

	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			h := w.Header()
			origin := r.Header.Get("Origin")

			if origin != "" && (wildcard || contains(origins, origin)) {
				h.Set("Access-Control-Allow-Origin", origin)
				h.Set("Vary", "Origin")
			}
			h.Set("Access-Control-Allow-Credentials", "true")
			h.Set("Access-Control-Allow-Methods", "GET, POST, PATCH, PUT, DELETE, OPTIONS")
			h.Set("Access-Control-Allow-Headers", "Authorization, Content-Type")
			h.Set("Access-Control-Max-Age", "600")

			if r.Method == http.MethodOptions {
				w.WriteHeader(http.StatusNoContent)
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

func splitAndTrim(s string) []string {
	parts := strings.Split(s, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		if p = strings.TrimSpace(p); p != "" {
			out = append(out, p)
		}
	}
	return out
}

func contains(list []string, v string) bool {
	for _, x := range list {
		if x == v {
			return true
		}
	}
	return false
}
