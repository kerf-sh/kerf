package handlers

import (
	"net/http"

	"github.com/go-chi/chi/v5"

	"github.com/imranp/kerf/backend/internal/middleware"
)

// Project member endpoints are now thin proxies onto the project's workspace.
// We list / invite / change / remove against workspace_members for the
// workspace that owns the project. The legacy URL surface is preserved so
// existing project-level "Share" UIs keep working.

// projectWorkspaceID looks up the workspace that owns the given project.
func (d *Deps) projectWorkspaceID(w http.ResponseWriter, r *http.Request, pid string) string {
	var wsID string
	err := d.Pool.QueryRow(r.Context(),
		`select workspace_id from projects where id = $1`, pid).Scan(&wsID)
	if err != nil {
		writeError(w, http.StatusNotFound, "project not found")
		return ""
	}
	return wsID
}

// ListMembers returns members of the project's workspace.
func (d *Deps) ListMembers(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}
	wsID := d.projectWorkspaceID(w, r, pid)
	if wsID == "" {
		return
	}
	members, err := d.loadWorkspaceMembers(r.Context(), wsID)
	if err != nil {
		genericServerError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, members)
}

// AddMember invites a user to the project's workspace as a 'member'.
// Owner / admin only on the workspace.
func (d *Deps) AddMember(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}
	wsID := d.projectWorkspaceID(w, r, pid)
	if wsID == "" {
		return
	}
	if requireWorkspaceAdmin(w, r, d.Pool, wsID, uid) == "" {
		return
	}
	// Reuse the workspace-invite handler logic by writing the slug into the
	// URL via a synthetic chi context isn't worth it — call the underlying
	// invite path directly by re-decoding here.
	d.inviteIntoWorkspace(w, r, wsID)
}

// UpdateMember and RemoveMember are similar thin wrappers.
func (d *Deps) UpdateMember(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	memberID := chi.URLParam(r, "uid")
	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}
	wsID := d.projectWorkspaceID(w, r, pid)
	if wsID == "" {
		return
	}
	if requireWorkspaceAdmin(w, r, d.Pool, wsID, uid) == "" {
		return
	}
	d.changeRoleOnWorkspace(w, r, wsID, memberID)
}

func (d *Deps) RemoveMember(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	memberID := chi.URLParam(r, "uid")
	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}
	wsID := d.projectWorkspaceID(w, r, pid)
	if wsID == "" {
		return
	}
	if requireWorkspaceAdmin(w, r, d.Pool, wsID, uid) == "" {
		return
	}
	d.removeFromWorkspace(w, r, wsID, memberID)
}
