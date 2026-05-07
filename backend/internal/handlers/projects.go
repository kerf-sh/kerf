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

// ListProjects returns every project the caller owns or is a member of.
func (d *Deps) ListProjects(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	rows, err := d.Pool.Query(r.Context(), `
		select p.id, p.owner_id, p.name, p.description, p.visibility,
		       p.created_at, p.updated_at,
		       case when p.owner_id = $1 then 'owner' else m.role end as my_role
		from projects p
		left join project_members m on m.project_id = p.id and m.user_id = $1
		where p.owner_id = $1 or m.user_id = $1
		order by p.updated_at desc
	`, uid)
	if err != nil {
		genericServerError(w, err)
		return
	}
	defer rows.Close()
	out := []models.Project{}
	for rows.Next() {
		var p models.Project
		if err := rows.Scan(&p.ID, &p.OwnerID, &p.Name, &p.Description, &p.Visibility, &p.CreatedAt, &p.UpdatedAt, &p.MyRole); err != nil {
			genericServerError(w, err)
			return
		}
		out = append(out, p)
	}
	writeJSON(w, http.StatusOK, out)
}

type createProjectReq struct {
	Name        string `json:"name"`
	Description string `json:"description"`
}

// CreateProject inserts a project, the owner project_member row, and a starter file.
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
	tx, err := d.Pool.Begin(r.Context())
	if err != nil {
		genericServerError(w, err)
		return
	}
	defer tx.Rollback(r.Context())

	var p models.Project
	err = tx.QueryRow(r.Context(), `
		insert into projects(owner_id, name, description)
		values ($1,$2,$3)
		returning id, owner_id, name, description, visibility, created_at, updated_at
	`, uid, body.Name, body.Description).Scan(&p.ID, &p.OwnerID, &p.Name, &p.Description, &p.Visibility, &p.CreatedAt, &p.UpdatedAt)
	if err != nil {
		genericServerError(w, err)
		return
	}
	if _, err := tx.Exec(r.Context(),
		`insert into project_members(project_id, user_id, role) values ($1,$2,'owner')`,
		p.ID, uid); err != nil {
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
	p.MyRole = "owner"
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
		select id, owner_id, name, description, visibility, created_at, updated_at
		from projects where id = $1
	`, pid).Scan(&p.ID, &p.OwnerID, &p.Name, &p.Description, &p.Visibility, &p.CreatedAt, &p.UpdatedAt)
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

// UpdateProject patches the project (owner or editor).
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
		returning id, owner_id, name, description, visibility, created_at, updated_at
	`, pid, body.Name, body.Description, body.Visibility).Scan(
		&p.ID, &p.OwnerID, &p.Name, &p.Description, &p.Visibility, &p.CreatedAt, &p.UpdatedAt)
	if err != nil {
		genericServerError(w, err)
		return
	}
	p.MyRole = role
	writeJSON(w, http.StatusOK, p)
}

// DeleteProject removes the project (owner only).
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
