package handlers

import (
	"errors"
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"

	"github.com/imranp/kerf/backend/internal/middleware"
	"github.com/imranp/kerf/backend/internal/models"
)

// Mirrors src/lib/jscadRunner.js DEFAULT_JSCAD. The runner calls the default
// export with the @jscad/modeling namespace, so the function destructures
// what it needs from the argument — top-level imports are unnecessary
// (and would be stripped by the runner anyway).
const defaultJSCAD = `// Kerf: default export receives the @jscad/modeling module and returns parts.
export default function ({ primitives, transforms, booleans }) {
  const base = primitives.cuboid({ size: [40, 40, 10] })
  const peg  = transforms.translate([0, 0, 10], primitives.cylinder({ radius: 6, height: 20 }))
  return [
    { id: 'base', geom: base },
    { id: 'peg',  geom: peg  },
  ]
}
`

// ListProjects returns every project visible to the caller through workspace
// membership. Optionally filtered to ?workspace_id=… or ?workspace_slug=….
func (d *Deps) ListProjects(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	wsID := strings.TrimSpace(r.URL.Query().Get("workspace_id"))
	wsSlug := strings.TrimSpace(r.URL.Query().Get("workspace_slug"))
	if wsID == "" && wsSlug != "" {
		id, err := resolveWorkspaceBySlug(r.Context(), d.Pool, wsSlug)
		if err != nil {
			genericServerError(w, err)
			return
		}
		if id == "" {
			writeError(w, http.StatusNotFound, "workspace not found")
			return
		}
		wsID = id
	}
	if wsID != "" {
		// Ensure the caller is actually a member of the requested workspace.
		role := requireWorkspaceMember(w, r, d.Pool, wsID, uid)
		if role == "" {
			return
		}
	}

	rows, err := d.Pool.Query(r.Context(), `
		select p.id, p.workspace_id, p.name, p.description, p.visibility,
		       p.created_at, p.updated_at, m.role
		from projects p
		join workspace_members m on m.workspace_id = p.workspace_id
		where m.user_id = $1
		  and ($2::uuid is null or p.workspace_id = $2)
		order by p.updated_at desc
	`, uid, nullableUUID(wsID))
	if err != nil {
		genericServerError(w, err)
		return
	}
	defer rows.Close()
	out := []models.Project{}
	for rows.Next() {
		var (
			p    models.Project
			role string
		)
		if err := rows.Scan(&p.ID, &p.WorkspaceID, &p.Name, &p.Description, &p.Visibility,
			&p.CreatedAt, &p.UpdatedAt, &role); err != nil {
			genericServerError(w, err)
			return
		}
		switch role {
		case "owner":
			p.MyRole = "owner"
		default:
			p.MyRole = "editor"
		}
		out = append(out, p)
	}
	writeJSON(w, http.StatusOK, out)
}

// nullableUUID returns nil for an empty string, else the string itself, for
// use with `$2::uuid is null or …` patterns in optional filters.
func nullableUUID(s string) any {
	if s == "" {
		return nil
	}
	return s
}

type createProjectReq struct {
	WorkspaceID   string `json:"workspace_id"`
	WorkspaceSlug string `json:"workspace_slug"`
	Name          string `json:"name"`
	Description   string `json:"description"`
}

// CreateProject inserts a project under a workspace and seeds a starter file.
func (d *Deps) CreateProject(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	var body createProjectReq
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	body.Name = strings.TrimSpace(body.Name)
	if body.Name == "" {
		writeError(w, http.StatusBadRequest, "name is required")
		return
	}
	wsID := strings.TrimSpace(body.WorkspaceID)
	if wsID == "" && body.WorkspaceSlug != "" {
		id, err := resolveWorkspaceBySlug(r.Context(), d.Pool, body.WorkspaceSlug)
		if err != nil {
			genericServerError(w, err)
			return
		}
		if id == "" {
			writeError(w, http.StatusNotFound, "workspace not found")
			return
		}
		wsID = id
	}
	if wsID == "" {
		writeError(w, http.StatusBadRequest, "workspace_id (or workspace_slug) is required")
		return
	}
	role := requireWorkspaceMember(w, r, d.Pool, wsID, uid)
	if role == "" {
		return
	}

	tx, err := d.Pool.Begin(r.Context())
	if err != nil {
		genericServerError(w, err)
		return
	}
	defer tx.Rollback(r.Context())

	var p models.Project
	err = tx.QueryRow(r.Context(), `
		insert into projects(workspace_id, name, description)
		values ($1,$2,$3)
		returning id, workspace_id, name, description, visibility, created_at, updated_at
	`, wsID, body.Name, body.Description).Scan(
		&p.ID, &p.WorkspaceID, &p.Name, &p.Description, &p.Visibility, &p.CreatedAt, &p.UpdatedAt)
	if err != nil {
		genericServerError(w, err)
		return
	}
	if _, err := tx.Exec(r.Context(),
		`insert into files(project_id, name, kind, content) values ($1,'main.jscad','file',$2)`,
		p.ID, defaultJSCAD); err != nil {
		genericServerError(w, err)
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		genericServerError(w, err)
		return
	}
	if role == "owner" {
		p.MyRole = "owner"
	} else {
		p.MyRole = "editor"
	}
	writeJSON(w, http.StatusCreated, p)
}

// GetProject returns a single project with the caller's role.
func (d *Deps) GetProject(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	role := requireMember(w, r, d.Pool, pid, uid)
	if role == "" {
		return
	}
	var p models.Project
	err := d.Pool.QueryRow(r.Context(), `
		select id, workspace_id, name, description, visibility, created_at, updated_at
		from projects where id = $1
	`, pid).Scan(&p.ID, &p.WorkspaceID, &p.Name, &p.Description, &p.Visibility, &p.CreatedAt, &p.UpdatedAt)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "project not found")
			return
		}
		genericServerError(w, err)
		return
	}
	p.MyRole = role
	writeJSON(w, http.StatusOK, p)
}

type updateProjectReq struct {
	Name        *string `json:"name"`
	Description *string `json:"description"`
	Visibility  *string `json:"visibility"`
}

// UpdateProject patches the project (any workspace member can edit in v1).
func (d *Deps) UpdateProject(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	role := requireMember(w, r, d.Pool, pid, uid)
	if role == "" {
		return
	}
	if role == "viewer" {
		writeError(w, http.StatusForbidden, "viewer cannot edit project")
		return
	}
	var body updateProjectReq
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if body.Visibility != nil {
		v := *body.Visibility
		if v != "private" && v != "unlisted" && v != "public" {
			writeError(w, http.StatusBadRequest, "invalid visibility")
			return
		}
	}
	var p models.Project
	err := d.Pool.QueryRow(r.Context(), `
		update projects set
			name        = coalesce($2, name),
			description = coalesce($3, description),
			visibility  = coalesce($4, visibility),
			updated_at  = now()
		where id = $1
		returning id, workspace_id, name, description, visibility, created_at, updated_at
	`, pid, body.Name, body.Description, body.Visibility).Scan(
		&p.ID, &p.WorkspaceID, &p.Name, &p.Description, &p.Visibility, &p.CreatedAt, &p.UpdatedAt)
	if err != nil {
		genericServerError(w, err)
		return
	}
	p.MyRole = role
	writeJSON(w, http.StatusOK, p)
}

// DeleteProject removes the project (workspace owner only).
func (d *Deps) DeleteProject(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	if !requireOwner(w, r, d.Pool, pid, uid) {
		return
	}
	if _, err := d.Pool.Exec(r.Context(), `delete from projects where id = $1`, pid); err != nil {
		genericServerError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
