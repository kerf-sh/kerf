package handlers

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/internal/auth"
	"github.com/imranp/kerf/backend/internal/config"
	"github.com/imranp/kerf/backend/internal/llm"
	"github.com/imranp/kerf/backend/internal/storage"
)

// Deps bundles everything handlers need.
type Deps struct {
	Cfg     *config.Config
	Pool    *pgxpool.Pool
	Auth    *auth.Service
	LLM     *llm.Registry
	Storage storage.Storage
}

func writeJSON(w http.ResponseWriter, status int, body interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if body == nil {
		return
	}
	_ = json.NewEncoder(w).Encode(body)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

func decodeJSON(r *http.Request, dst interface{}) error {
	dec := json.NewDecoder(r.Body)
	dec.DisallowUnknownFields()
	if err := dec.Decode(dst); err != nil {
		return err
	}
	return nil
}

// projectRole returns the caller's role on the project (or "" if none) and a
// boolean indicating whether the project exists. With workspaces, the role is
// the caller's role on the project's workspace, mapped:
//   - workspace owner → "owner"
//   - workspace admin → "editor"
//   - workspace member → "editor"
//
// (We collapse all members to edit access in v1; share_links still grant viewer.)
func projectRole(ctx context.Context, pool *pgxpool.Pool, projectID, userID string) (role string, exists bool, err error) {
	var workspaceID string
	err = pool.QueryRow(ctx, `select workspace_id from projects where id = $1`, projectID).Scan(&workspaceID)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return "", false, nil
		}
		return "", false, err
	}
	exists = true
	var wsRole string
	err = pool.QueryRow(ctx,
		`select role from workspace_members where workspace_id = $1 and user_id = $2`,
		workspaceID, userID).Scan(&wsRole)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return "", true, nil
		}
		return "", true, err
	}
	switch wsRole {
	case "owner":
		return "owner", true, nil
	case "admin", "member":
		return "editor", true, nil
	}
	return "", true, nil
}

// requireMember returns the caller's role; writes 404/403 and returns "" if not authorized.
func requireMember(w http.ResponseWriter, r *http.Request, pool *pgxpool.Pool, projectID, userID string) string {
	role, exists, err := projectRole(r.Context(), pool, projectID, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return ""
	}
	if !exists {
		writeError(w, http.StatusNotFound, "project not found")
		return ""
	}
	if role == "" {
		writeError(w, http.StatusForbidden, "forbidden")
		return ""
	}
	return role
}

// requireOwner ensures the caller is the project owner.
func requireOwner(w http.ResponseWriter, r *http.Request, pool *pgxpool.Pool, projectID, userID string) bool {
	role := requireMember(w, r, pool, projectID, userID)
	if role == "" {
		return false
	}
	if role != "owner" {
		writeError(w, http.StatusForbidden, "owner only")
		return false
	}
	return true
}

func notFound(err error) bool {
	return errors.Is(err, pgx.ErrNoRows)
}

// genericServerError sends a 500 with a sanitized message.
func genericServerError(w http.ResponseWriter, err error) {
	writeError(w, http.StatusInternalServerError, fmt.Sprintf("server error: %v", err))
}
