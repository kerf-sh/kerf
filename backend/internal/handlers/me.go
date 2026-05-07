package handlers

import (
	"errors"
	"net/http"

	"github.com/jackc/pgx/v5"

	"github.com/imranp/kerf/backend/internal/middleware"
	"github.com/imranp/kerf/backend/internal/models"
)

type meResponse struct {
	models.User
	DefaultWorkspace *models.Workspace `json:"default_workspace,omitempty"`
}

// Me returns the currently authenticated user, plus their default workspace
// (oldest workspace they're a member of) so the client can route home.
func (d *Deps) Me(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	var u models.User
	err := d.Pool.QueryRow(r.Context(),
		`select id, email, name, avatar_url, account_role, is_system, created_at from users where id = $1`,
		uid).Scan(&u.ID, &u.Email, &u.Name, &u.AvatarURL, &u.AccountRole, &u.IsSystem, &u.CreatedAt)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "user not found")
			return
		}
		genericServerError(w, err)
		return
	}
	resp := meResponse{User: u}
	if ws, ok, err := d.defaultWorkspaceForUser(r.Context(), uid); err == nil && ok {
		resp.DefaultWorkspace = &ws
	}
	writeJSON(w, http.StatusOK, resp)
}
