package handlers

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/internal/auth"
	"github.com/imranp/kerf/backend/internal/middleware"
	"github.com/imranp/kerf/backend/internal/models"
)

// Workspace avatar upload caps.
const (
	maxWorkspaceAvatarBytes = 5 * 1024 * 1024 // 5 MB
)

// slugRe enforces 3-32 chars, lowercase + digits + hyphens, no leading/trailing hyphen.
var slugRe = regexp.MustCompile(`^[a-z0-9](?:[a-z0-9-]{1,30}[a-z0-9])?$`)

// slugFromName produces a best-effort slug from a free-form name.
func slugFromName(name string) string {
	lower := strings.ToLower(strings.TrimSpace(name))
	var b strings.Builder
	prevDash := false
	for _, r := range lower {
		switch {
		case r >= 'a' && r <= 'z', r >= '0' && r <= '9':
			b.WriteRune(r)
			prevDash = false
		case r == ' ' || r == '_' || r == '-':
			if !prevDash && b.Len() > 0 {
				b.WriteByte('-')
				prevDash = true
			}
		}
	}
	out := strings.Trim(b.String(), "-")
	if len(out) > 32 {
		out = out[:32]
	}
	if len(out) < 3 {
		out = out + strings.Repeat("x", 3-len(out))
	}
	return out
}

// workspaceRoleByID returns the caller's role on a workspace, or "" if not a member.
func workspaceRoleByID(ctx context.Context, pool *pgxpool.Pool, workspaceID, userID string) (role string, exists bool, err error) {
	var got string
	err = pool.QueryRow(ctx, `select 1 from workspaces where id = $1`, workspaceID).Scan(new(int))
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return "", false, nil
		}
		return "", false, err
	}
	exists = true
	err = pool.QueryRow(ctx,
		`select role from workspace_members where workspace_id = $1 and user_id = $2`,
		workspaceID, userID).Scan(&got)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return "", true, nil
		}
		return "", true, err
	}
	return got, true, nil
}

// resolveWorkspaceBySlug returns the workspace id for a slug, or "" if not found.
func resolveWorkspaceBySlug(ctx context.Context, pool *pgxpool.Pool, slug string) (string, error) {
	var id string
	err := pool.QueryRow(ctx, `select id from workspaces where slug = $1`, slug).Scan(&id)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return "", nil
		}
		return "", err
	}
	return id, nil
}

// requireWorkspaceMember writes 404/403 and returns "" if not authorized.
func requireWorkspaceMember(w http.ResponseWriter, r *http.Request, pool *pgxpool.Pool, workspaceID, userID string) string {
	role, exists, err := workspaceRoleByID(r.Context(), pool, workspaceID, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return ""
	}
	if !exists {
		writeError(w, http.StatusNotFound, "workspace not found")
		return ""
	}
	if role == "" {
		writeError(w, http.StatusForbidden, "forbidden")
		return ""
	}
	return role
}

// requireWorkspaceAdmin allows owner/admin only.
func requireWorkspaceAdmin(w http.ResponseWriter, r *http.Request, pool *pgxpool.Pool, workspaceID, userID string) string {
	role := requireWorkspaceMember(w, r, pool, workspaceID, userID)
	if role == "" {
		return ""
	}
	if role != "owner" && role != "admin" {
		writeError(w, http.StatusForbidden, "owner or admin required")
		return ""
	}
	return role
}

// resolveWorkspaceFromURL pulls :slug, looks up the workspace, ensures membership,
// and returns (workspaceID, role). On any failure it writes the response and
// returns ("", "").
func (d *Deps) resolveWorkspaceFromURL(w http.ResponseWriter, r *http.Request) (string, string) {
	uid := middleware.UserID(r.Context())
	slug := chi.URLParam(r, "slug")
	if slug == "" {
		writeError(w, http.StatusBadRequest, "missing slug")
		return "", ""
	}
	id, err := resolveWorkspaceBySlug(r.Context(), d.Pool, slug)
	if err != nil {
		genericServerError(w, err)
		return "", ""
	}
	if id == "" {
		writeError(w, http.StatusNotFound, "workspace not found")
		return "", ""
	}
	role := requireWorkspaceMember(w, r, d.Pool, id, uid)
	if role == "" {
		return "", ""
	}
	return id, role
}

// attachWorkspaceAvatar populates ws.AvatarURL from the storage key.
func (d *Deps) attachWorkspaceAvatar(ws *models.Workspace, key *string) {
	if key == nil || *key == "" {
		return
	}
	if d.Storage != nil {
		ws.AvatarURL = d.Storage.PublicURL(*key)
	}
}

// uniqueSlug returns a slug that's not yet taken, appending -2, -3, …
func uniqueSlug(ctx context.Context, pool *pgxpool.Pool, base string) (string, error) {
	candidate := base
	for i := 1; i < 100; i++ {
		var id string
		err := pool.QueryRow(ctx, `select id from workspaces where slug = $1`, candidate).Scan(&id)
		if errors.Is(err, pgx.ErrNoRows) {
			return candidate, nil
		}
		if err != nil {
			return "", err
		}
		i++
		candidate = fmt.Sprintf("%s-%d", base, i)
	}
	return "", fmt.Errorf("could not derive unique slug from %q", base)
}

// createPersonalWorkspace inserts a default workspace for a freshly-created user.
// It is best-effort: failures are returned to the caller but the user row is
// already committed by the time we get here.
func createPersonalWorkspace(ctx context.Context, pool *pgxpool.Pool, userID, displayName string) (models.Workspace, error) {
	if displayName == "" {
		displayName = "My"
	}
	first := strings.Fields(displayName)[0]
	wsName := first + "'s workspace"
	base := slugFromName(first)
	if !slugRe.MatchString(base) {
		base = "workspace"
	}
	slug, err := uniqueSlug(ctx, pool, base)
	if err != nil {
		return models.Workspace{}, err
	}
	tx, err := pool.Begin(ctx)
	if err != nil {
		return models.Workspace{}, err
	}
	defer tx.Rollback(ctx)
	var ws models.Workspace
	err = tx.QueryRow(ctx, `
		insert into workspaces(slug, name, created_by)
		values ($1, $2, $3)
		returning id, slug, name, created_by, created_at, updated_at
	`, slug, wsName, userID).Scan(&ws.ID, &ws.Slug, &ws.Name, &ws.CreatedBy, &ws.CreatedAt, &ws.UpdatedAt)
	if err != nil {
		return models.Workspace{}, err
	}
	if _, err := tx.Exec(ctx,
		`insert into workspace_members(workspace_id, user_id, role) values ($1, $2, 'owner')`,
		ws.ID, userID); err != nil {
		return models.Workspace{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return models.Workspace{}, err
	}
	ws.MyRole = "owner"
	ws.MemberCount = 1
	return ws, nil
}

// ListWorkspaces returns workspaces the caller is a member of.
func (d *Deps) ListWorkspaces(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	rows, err := d.Pool.Query(r.Context(), `
		select w.id, w.slug, w.name, w.avatar_storage_key, w.created_by,
		       w.created_at, w.updated_at, m.role,
		       (select count(*) from workspace_members wm where wm.workspace_id = w.id) as member_count,
		       (select count(*) from projects p where p.workspace_id = w.id) as project_count
		from workspaces w
		join workspace_members m on m.workspace_id = w.id
		where m.user_id = $1
		order by w.created_at asc
	`, uid)
	if err != nil {
		genericServerError(w, err)
		return
	}
	defer rows.Close()
	out := []models.Workspace{}
	for rows.Next() {
		var (
			ws  models.Workspace
			key *string
		)
		if err := rows.Scan(&ws.ID, &ws.Slug, &ws.Name, &key, &ws.CreatedBy,
			&ws.CreatedAt, &ws.UpdatedAt, &ws.MyRole, &ws.MemberCount, &ws.ProjectCount); err != nil {
			genericServerError(w, err)
			return
		}
		d.attachWorkspaceAvatar(&ws, key)
		out = append(out, ws)
	}
	writeJSON(w, http.StatusOK, out)
}

type createWorkspaceReq struct {
	Name string `json:"name"`
	Slug string `json:"slug"`
}

// CreateWorkspace inserts a workspace, makes the caller the owner, and returns it.
func (d *Deps) CreateWorkspace(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	var body createWorkspaceReq
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	body.Name = strings.TrimSpace(body.Name)
	body.Slug = strings.ToLower(strings.TrimSpace(body.Slug))
	if body.Name == "" {
		writeError(w, http.StatusBadRequest, "name is required")
		return
	}
	if body.Slug == "" {
		body.Slug = slugFromName(body.Name)
	}
	if !slugRe.MatchString(body.Slug) {
		writeError(w, http.StatusBadRequest, "invalid slug (3-32 chars, lowercase a-z 0-9 and hyphens)")
		return
	}

	tx, err := d.Pool.Begin(r.Context())
	if err != nil {
		genericServerError(w, err)
		return
	}
	defer tx.Rollback(r.Context())

	var ws models.Workspace
	err = tx.QueryRow(r.Context(), `
		insert into workspaces(slug, name, created_by)
		values ($1, $2, $3)
		returning id, slug, name, created_by, created_at, updated_at
	`, body.Slug, body.Name, uid).Scan(&ws.ID, &ws.Slug, &ws.Name, &ws.CreatedBy, &ws.CreatedAt, &ws.UpdatedAt)
	if err != nil {
		if isUniqueViolation(err) {
			writeError(w, http.StatusConflict, "slug already in use")
			return
		}
		genericServerError(w, err)
		return
	}
	if _, err := tx.Exec(r.Context(),
		`insert into workspace_members(workspace_id, user_id, role) values ($1, $2, 'owner')`,
		ws.ID, uid); err != nil {
		genericServerError(w, err)
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		genericServerError(w, err)
		return
	}
	ws.MyRole = "owner"
	ws.MemberCount = 1
	writeJSON(w, http.StatusCreated, ws)
}

type workspaceDetailResp struct {
	models.Workspace
	Members []models.WorkspaceMember `json:"members"`
}

// GetWorkspace returns workspace details + members.
func (d *Deps) GetWorkspace(w http.ResponseWriter, r *http.Request) {
	id, role := d.resolveWorkspaceFromURL(w, r)
	if id == "" {
		return
	}
	var (
		ws  models.Workspace
		key *string
	)
	err := d.Pool.QueryRow(r.Context(), `
		select id, slug, name, avatar_storage_key, created_by, created_at, updated_at
		from workspaces where id = $1
	`, id).Scan(&ws.ID, &ws.Slug, &ws.Name, &key, &ws.CreatedBy, &ws.CreatedAt, &ws.UpdatedAt)
	if err != nil {
		genericServerError(w, err)
		return
	}
	d.attachWorkspaceAvatar(&ws, key)
	ws.MyRole = role

	members, err := d.loadWorkspaceMembers(r.Context(), id)
	if err != nil {
		genericServerError(w, err)
		return
	}
	ws.MemberCount = len(members)
	resp := workspaceDetailResp{Workspace: ws, Members: members}
	writeJSON(w, http.StatusOK, resp)
}

func (d *Deps) loadWorkspaceMembers(ctx context.Context, workspaceID string) ([]models.WorkspaceMember, error) {
	rows, err := d.Pool.Query(ctx, `
		select m.workspace_id, m.user_id, m.role, m.created_at,
		       u.id, u.email, u.name, u.avatar_url, u.account_role, u.is_system, u.created_at
		from workspace_members m
		join users u on u.id = m.user_id
		where m.workspace_id = $1
		order by m.created_at asc
	`, workspaceID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []models.WorkspaceMember{}
	for rows.Next() {
		var m models.WorkspaceMember
		if err := rows.Scan(&m.WorkspaceID, &m.UserID, &m.Role, &m.CreatedAt,
			&m.User.ID, &m.User.Email, &m.User.Name, &m.User.AvatarURL,
			&m.User.AccountRole, &m.User.IsSystem, &m.User.CreatedAt); err != nil {
			return nil, err
		}
		out = append(out, m)
	}
	return out, nil
}

type updateWorkspaceReq struct {
	Name *string `json:"name"`
	Slug *string `json:"slug"`
}

// UpdateWorkspace edits name/slug. Owner or admin.
func (d *Deps) UpdateWorkspace(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	id, _ := d.resolveWorkspaceFromURL(w, r)
	if id == "" {
		return
	}
	if requireWorkspaceAdmin(w, r, d.Pool, id, uid) == "" {
		return
	}
	var body updateWorkspaceReq
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if body.Slug != nil {
		s := strings.ToLower(strings.TrimSpace(*body.Slug))
		if !slugRe.MatchString(s) {
			writeError(w, http.StatusBadRequest, "invalid slug")
			return
		}
		body.Slug = &s
	}
	if body.Name != nil {
		n := strings.TrimSpace(*body.Name)
		if n == "" {
			writeError(w, http.StatusBadRequest, "name cannot be empty")
			return
		}
		body.Name = &n
	}
	var (
		ws  models.Workspace
		key *string
	)
	err := d.Pool.QueryRow(r.Context(), `
		update workspaces set
			name = coalesce($2, name),
			slug = coalesce($3, slug),
			updated_at = now()
		where id = $1
		returning id, slug, name, avatar_storage_key, created_by, created_at, updated_at
	`, id, body.Name, body.Slug).Scan(&ws.ID, &ws.Slug, &ws.Name, &key,
		&ws.CreatedBy, &ws.CreatedAt, &ws.UpdatedAt)
	if err != nil {
		if isUniqueViolation(err) {
			writeError(w, http.StatusConflict, "slug already in use")
			return
		}
		genericServerError(w, err)
		return
	}
	d.attachWorkspaceAvatar(&ws, key)
	writeJSON(w, http.StatusOK, ws)
}

// DeleteWorkspace removes a workspace (owner only). 204.
func (d *Deps) DeleteWorkspace(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	id, role := d.resolveWorkspaceFromURL(w, r)
	if id == "" {
		return
	}
	if role != "owner" {
		writeError(w, http.StatusForbidden, "owner only")
		return
	}
	_ = uid
	if _, err := d.Pool.Exec(r.Context(), `delete from workspaces where id = $1`, id); err != nil {
		genericServerError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

type inviteMemberReq struct {
	Email string `json:"email"`
	Role  string `json:"role"`
}

type inviteMemberResp struct {
	Added  *models.WorkspaceMember `json:"added,omitempty"`
	Invite *models.WorkspaceInvite `json:"invite,omitempty"`
}

// InviteWorkspaceMember adds a user (or creates an invite token if they don't
// have an account yet). Owner / admin only.
func (d *Deps) InviteWorkspaceMember(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	id, _ := d.resolveWorkspaceFromURL(w, r)
	if id == "" {
		return
	}
	if requireWorkspaceAdmin(w, r, d.Pool, id, uid) == "" {
		return
	}
	d.inviteIntoWorkspace(w, r, id)
}

// inviteIntoWorkspace is the shared implementation for the workspace and the
// legacy /api/projects/:pid/members invite paths.
func (d *Deps) inviteIntoWorkspace(w http.ResponseWriter, r *http.Request, workspaceID string) {
	uid := middleware.UserID(r.Context())
	var body inviteMemberReq
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	body.Email = strings.TrimSpace(strings.ToLower(body.Email))
	if body.Email == "" {
		writeError(w, http.StatusBadRequest, "email is required")
		return
	}
	if body.Role == "" {
		body.Role = "member"
	}
	// Accept the legacy project-member roles by mapping them onto workspace roles.
	switch body.Role {
	case "owner", "admin", "member":
		// ok
	case "editor", "viewer":
		body.Role = "member"
	default:
		writeError(w, http.StatusBadRequest, "invalid role")
		return
	}

	// Existing user?
	var u models.User
	err := d.Pool.QueryRow(r.Context(),
		`select id, email, name, avatar_url, account_role, is_system, created_at from users where email = $1`,
		body.Email).Scan(&u.ID, &u.Email, &u.Name, &u.AvatarURL, &u.AccountRole, &u.IsSystem, &u.CreatedAt)
	if err == nil {
		var m models.WorkspaceMember
		err = d.Pool.QueryRow(r.Context(), `
			insert into workspace_members(workspace_id, user_id, role)
			values ($1, $2, $3)
			on conflict (workspace_id, user_id) do update set role = excluded.role
			returning workspace_id, user_id, role, created_at
		`, workspaceID, u.ID, body.Role).Scan(&m.WorkspaceID, &m.UserID, &m.Role, &m.CreatedAt)
		if err != nil {
			genericServerError(w, err)
			return
		}
		m.User = u
		writeJSON(w, http.StatusCreated, inviteMemberResp{Added: &m})
		return
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		genericServerError(w, err)
		return
	}

	// No account — issue invite token.
	token, err := auth.IssueShareToken()
	if err != nil {
		genericServerError(w, err)
		return
	}
	var inv models.WorkspaceInvite
	err = d.Pool.QueryRow(r.Context(), `
		insert into workspace_invites(workspace_id, email, role, token, created_by)
		values ($1, $2, $3, $4, $5)
		returning id, workspace_id, email, role, token, created_by, created_at
	`, workspaceID, body.Email, body.Role, token, uid).Scan(
		&inv.ID, &inv.WorkspaceID, &inv.Email, &inv.Role, &inv.Token,
		&inv.CreatedBy, &inv.CreatedAt)
	if err != nil {
		genericServerError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, inviteMemberResp{Invite: &inv})
}

type changeRoleReq struct {
	Role string `json:"role"`
}

// ChangeWorkspaceMemberRole updates a member's role. Owner / admin only.
// Cannot demote the only remaining owner.
func (d *Deps) ChangeWorkspaceMemberRole(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	id, _ := d.resolveWorkspaceFromURL(w, r)
	if id == "" {
		return
	}
	if requireWorkspaceAdmin(w, r, d.Pool, id, uid) == "" {
		return
	}
	memberID := chi.URLParam(r, "user_id")
	d.changeRoleOnWorkspace(w, r, id, memberID)
}

// changeRoleOnWorkspace is shared by the workspace and project-member URL paths.
func (d *Deps) changeRoleOnWorkspace(w http.ResponseWriter, r *http.Request, id, memberID string) {
	var body changeRoleReq
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	switch body.Role {
	case "owner", "admin", "member":
		// ok
	case "editor", "viewer":
		body.Role = "member"
	default:
		writeError(w, http.StatusBadRequest, "invalid role")
		return
	}
	// Look up the existing role; refuse to demote the last owner.
	var current string
	err := d.Pool.QueryRow(r.Context(),
		`select role from workspace_members where workspace_id = $1 and user_id = $2`,
		id, memberID).Scan(&current)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "member not found")
			return
		}
		genericServerError(w, err)
		return
	}
	if current == "owner" && body.Role != "owner" {
		var owners int
		if err := d.Pool.QueryRow(r.Context(),
			`select count(*) from workspace_members where workspace_id = $1 and role = 'owner'`,
			id).Scan(&owners); err != nil {
			genericServerError(w, err)
			return
		}
		if owners <= 1 {
			writeError(w, http.StatusBadRequest, "cannot demote the only owner")
			return
		}
	}
	var m models.WorkspaceMember
	err = d.Pool.QueryRow(r.Context(), `
		update workspace_members set role = $3
		where workspace_id = $1 and user_id = $2
		returning workspace_id, user_id, role, created_at
	`, id, memberID, body.Role).Scan(&m.WorkspaceID, &m.UserID, &m.Role, &m.CreatedAt)
	if err != nil {
		genericServerError(w, err)
		return
	}
	if err := d.Pool.QueryRow(r.Context(),
		`select id, email, name, avatar_url, account_role, is_system, created_at from users where id = $1`,
		memberID).Scan(&m.User.ID, &m.User.Email, &m.User.Name, &m.User.AvatarURL,
		&m.User.AccountRole, &m.User.IsSystem, &m.User.CreatedAt); err != nil {
		genericServerError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, m)
}

// RemoveWorkspaceMember kicks a member. Owner / admin. Cannot remove the only owner.
func (d *Deps) RemoveWorkspaceMember(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	id, _ := d.resolveWorkspaceFromURL(w, r)
	if id == "" {
		return
	}
	if requireWorkspaceAdmin(w, r, d.Pool, id, uid) == "" {
		return
	}
	memberID := chi.URLParam(r, "user_id")
	d.removeFromWorkspace(w, r, id, memberID)
}

// removeFromWorkspace is shared by workspace and legacy project URL paths.
func (d *Deps) removeFromWorkspace(w http.ResponseWriter, r *http.Request, id, memberID string) {
	var current string
	err := d.Pool.QueryRow(r.Context(),
		`select role from workspace_members where workspace_id = $1 and user_id = $2`,
		id, memberID).Scan(&current)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "member not found")
			return
		}
		genericServerError(w, err)
		return
	}
	if current == "owner" {
		var owners int
		if err := d.Pool.QueryRow(r.Context(),
			`select count(*) from workspace_members where workspace_id = $1 and role = 'owner'`,
			id).Scan(&owners); err != nil {
			genericServerError(w, err)
			return
		}
		if owners <= 1 {
			writeError(w, http.StatusBadRequest, "cannot remove the only owner")
			return
		}
	}
	if _, err := d.Pool.Exec(r.Context(),
		`delete from workspace_members where workspace_id = $1 and user_id = $2`,
		id, memberID); err != nil {
		genericServerError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// UploadWorkspaceAvatar accepts multipart 'file', writes a blob, sets
// avatar_storage_key, returns updated workspace.
func (d *Deps) UploadWorkspaceAvatar(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	id, _ := d.resolveWorkspaceFromURL(w, r)
	if id == "" {
		return
	}
	if requireWorkspaceAdmin(w, r, d.Pool, id, uid) == "" {
		return
	}
	if d.Storage == nil {
		writeError(w, http.StatusServiceUnavailable, "storage not configured")
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, maxWorkspaceAvatarBytes)
	if err := r.ParseMultipartForm(maxWorkspaceAvatarBytes); err != nil {
		writeError(w, http.StatusBadRequest, "invalid multipart body: "+err.Error())
		return
	}
	file, fhdr, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, "missing 'file' field")
		return
	}
	defer file.Close()
	contentType := fhdr.Header.Get("Content-Type")
	ext := strings.ToLower(filepath.Ext(fhdr.Filename))
	switch ext {
	case ".png":
		if contentType == "" {
			contentType = "image/png"
		}
	case ".jpg", ".jpeg":
		if contentType == "" {
			contentType = "image/jpeg"
		}
	default:
		// allow image/* by content-type if extension is missing.
		if !strings.HasPrefix(contentType, "image/") {
			writeError(w, http.StatusBadRequest, "only PNG or JPEG allowed")
			return
		}
	}
	if !strings.HasPrefix(contentType, "image/") {
		writeError(w, http.StatusBadRequest, "only PNG or JPEG allowed")
		return
	}

	key := fmt.Sprintf("workspaces/%s/avatar-%s%s", id, uuid.New().String(), ext)
	if _, err := d.Storage.Put(r.Context(), key, file, contentType, fhdr.Size); err != nil {
		genericServerError(w, err)
		return
	}

	// Read previous key so we can clean it up.
	var prev *string
	_ = d.Pool.QueryRow(r.Context(),
		`select avatar_storage_key from workspaces where id = $1`, id).Scan(&prev)

	var (
		ws     models.Workspace
		newKey *string
	)
	err = d.Pool.QueryRow(r.Context(), `
		update workspaces set avatar_storage_key = $2, updated_at = now()
		where id = $1
		returning id, slug, name, avatar_storage_key, created_by, created_at, updated_at
	`, id, key).Scan(&ws.ID, &ws.Slug, &ws.Name, &newKey, &ws.CreatedBy, &ws.CreatedAt, &ws.UpdatedAt)
	if err != nil {
		_ = d.Storage.Delete(r.Context(), key)
		genericServerError(w, err)
		return
	}
	d.attachWorkspaceAvatar(&ws, newKey)
	if prev != nil && *prev != "" && *prev != key {
		_ = d.Storage.Delete(r.Context(), *prev)
	}
	writeJSON(w, http.StatusOK, ws)
}

// DeleteWorkspaceAvatar clears the avatar.
func (d *Deps) DeleteWorkspaceAvatar(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	id, _ := d.resolveWorkspaceFromURL(w, r)
	if id == "" {
		return
	}
	if requireWorkspaceAdmin(w, r, d.Pool, id, uid) == "" {
		return
	}
	var prev *string
	if err := d.Pool.QueryRow(r.Context(),
		`update workspaces set avatar_storage_key = null, updated_at = now()
		 where id = $1 returning avatar_storage_key`, id).Scan(&prev); err != nil {
		genericServerError(w, err)
		return
	}
	// best-effort cleanup
	if prev != nil && *prev != "" && d.Storage != nil {
		_ = d.Storage.Delete(r.Context(), *prev)
	}
	w.WriteHeader(http.StatusNoContent)
}

// ServeWorkspaceAvatar streams a workspace avatar to authed callers (any user).
// This avoids exposing arbitrary blobs through /api/blobs/*.
func (d *Deps) ServeWorkspaceAvatar(w http.ResponseWriter, r *http.Request) {
	if d.Storage == nil {
		writeError(w, http.StatusServiceUnavailable, "storage not configured")
		return
	}
	id := chi.URLParam(r, "id")
	if id == "" {
		writeError(w, http.StatusBadRequest, "missing id")
		return
	}
	var key *string
	err := d.Pool.QueryRow(r.Context(),
		`select avatar_storage_key from workspaces where id = $1`, id).Scan(&key)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "workspace not found")
			return
		}
		genericServerError(w, err)
		return
	}
	if key == nil || *key == "" {
		writeError(w, http.StatusNotFound, "no avatar")
		return
	}
	rc, ct, err := d.Storage.Get(r.Context(), *key)
	if err != nil {
		writeError(w, http.StatusNotFound, "blob not found")
		return
	}
	defer rc.Close()
	w.Header().Set("Content-Type", ct)
	w.Header().Set("Cache-Control", "private, max-age=300")
	_, _ = io.Copy(w, rc)
}

type acceptInviteReq struct {
	Token string `json:"token"`
}

// AcceptWorkspaceInvite consumes a token, adds the caller as a member, deletes the invite.
func (d *Deps) AcceptWorkspaceInvite(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	var body acceptInviteReq
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	body.Token = strings.TrimSpace(body.Token)
	if body.Token == "" {
		writeError(w, http.StatusBadRequest, "token is required")
		return
	}
	tx, err := d.Pool.Begin(r.Context())
	if err != nil {
		genericServerError(w, err)
		return
	}
	defer tx.Rollback(r.Context())
	var (
		inviteID    string
		workspaceID string
		role        string
	)
	err = tx.QueryRow(r.Context(),
		`select id, workspace_id, role from workspace_invites where token = $1`,
		body.Token).Scan(&inviteID, &workspaceID, &role)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "invite not found")
			return
		}
		genericServerError(w, err)
		return
	}
	if _, err := tx.Exec(r.Context(), `
		insert into workspace_members(workspace_id, user_id, role)
		values ($1, $2, $3)
		on conflict (workspace_id, user_id) do update set role = excluded.role
	`, workspaceID, uid, role); err != nil {
		genericServerError(w, err)
		return
	}
	if _, err := tx.Exec(r.Context(),
		`delete from workspace_invites where id = $1`, inviteID); err != nil {
		genericServerError(w, err)
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		genericServerError(w, err)
		return
	}
	// Return workspace summary so the client can route into it.
	var (
		ws  models.Workspace
		key *string
	)
	if err := d.Pool.QueryRow(r.Context(), `
		select id, slug, name, avatar_storage_key, created_by, created_at, updated_at
		from workspaces where id = $1
	`, workspaceID).Scan(&ws.ID, &ws.Slug, &ws.Name, &key,
		&ws.CreatedBy, &ws.CreatedAt, &ws.UpdatedAt); err != nil {
		genericServerError(w, err)
		return
	}
	d.attachWorkspaceAvatar(&ws, key)
	ws.MyRole = role
	writeJSON(w, http.StatusOK, ws)
}

// defaultWorkspaceForUser returns the user's earliest workspace (by creation),
// or zero value if they have none.
func (d *Deps) defaultWorkspaceForUser(ctx context.Context, userID string) (models.Workspace, bool, error) {
	var (
		ws  models.Workspace
		key *string
	)
	err := d.Pool.QueryRow(ctx, `
		select w.id, w.slug, w.name, w.avatar_storage_key, w.created_by,
		       w.created_at, w.updated_at, m.role
		from workspaces w
		join workspace_members m on m.workspace_id = w.id
		where m.user_id = $1
		order by w.created_at asc
		limit 1
	`, userID).Scan(&ws.ID, &ws.Slug, &ws.Name, &key, &ws.CreatedBy,
		&ws.CreatedAt, &ws.UpdatedAt, &ws.MyRole)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return models.Workspace{}, false, nil
		}
		return models.Workspace{}, false, err
	}
	d.attachWorkspaceAvatar(&ws, key)
	return ws, true, nil
}

// strconv import retained for potential count parsing in future routes.
var _ = strconv.Atoi
