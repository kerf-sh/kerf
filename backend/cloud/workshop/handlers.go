//go:build cloud
// +build cloud

// Package workshop implements the hosted-tier "Thingiverse-style"
// publish/browse/fork experience over the existing projects table.
//
// Every Go file here is gated by the `cloud` build tag — the OSS binary
// neither compiles nor links any of this. Cross-package boundary rule:
// this package never imports backend/internal/handlers (which would
// drag the cloud tag back into the OSS package). Tiny request helpers
// (writeJSON / writeError / decodeJSON) are duplicated locally,
// matching the pattern used by billing/handlers.go.
package workshop

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
	"unicode"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/cloud/email"
	"github.com/imranp/kerf/backend/internal/config"
	kmw "github.com/imranp/kerf/backend/internal/middleware"
)

// Hard cap on file rows copied per fork. Forking is meant for designs,
// not arbitrary file dumps; this bounds the txn so a single popular
// listing can't trigger an unbounded copy storm. Files past the cap are
// silently dropped — the handler returns a hint in the response so the
// caller can warn the user.
const maxForkFiles = 200

// Handlers wires the workshop endpoints. Constructed by the cloud
// build of cmd/server (see cloud_enabled.go) and mounted under
// /api/workshop by the same caller.
type Handlers struct {
	Pool *pgxpool.Pool
	Cfg  *config.Config
	// Mailer is non-nil in production cloud builds. Publish fires a
	// "workshop_published" notification on first publish via this
	// Mailer; nil disables that branch (test path).
	Mailer *email.Mailer
}

// Mount attaches workshop routes onto whichever routers are
// provided. The caller has already routed under /api/workshop and
// applied OptionalAuth to `public` / RequireAuth to `authed`. Either
// router may be nil to skip that subset.
//
// Public:
//
//	GET  /              — paginated listing index
//	GET  /{slug}        — listing detail
//
// Authenticated:
//
//	POST   /publish        — create or update a listing for a project
//	DELETE /{slug}         — unpublish (owner only)
//	POST   /{slug}/like    — toggle like (idempotent)
//	POST   /{slug}/fork    — clone the listing's project under the caller
func (h *Handlers) Mount(authed chi.Router, public chi.Router) {
	if public != nil {
		public.Get("/", h.List)
		// /parts must come before /{slug} so chi's pattern resolver doesn't
		// treat "parts" as a slug.
		public.Get("/parts", h.ListParts)
		public.Get("/{slug}", h.Get)
	}
	if authed != nil {
		authed.Post("/publish", h.Publish)
		authed.Delete("/{slug}", h.Unpublish)
		authed.Post("/{slug}/like", h.ToggleLike)
		authed.Post("/{slug}/fork", h.Fork)
	}
}

// --- request / response shapes ---

type authorView struct {
	ID        string `json:"id"`
	Name      string `json:"name"`
	AvatarURL string `json:"avatar_url"`
}

type listingView struct {
	ID           string     `json:"id"`
	Slug         string     `json:"slug"`
	Title        string     `json:"title"`
	Description  string     `json:"description"`
	ThumbnailURL *string    `json:"thumbnail_url,omitempty"`
	LikesCount   int        `json:"likes_count"`
	ForksCount   int        `json:"forks_count"`
	Author       authorView `json:"author"`
	PublishedAt  time.Time  `json:"published_at"`
	UpdatedAt    time.Time  `json:"updated_at"`
	LikedByMe    bool       `json:"liked_by_me"`
	// ProjectType ('mechanical' | 'electronics' | …) is denormalized from
	// the source project so the Workshop UI can render a per-type tab strip
	// + filter chip without a second join. See ROADMAP.md "Multi-domain
	// support: project types".
	ProjectType string `json:"project_type"`
}

type listingDetailView struct {
	listingView
	ProjectID  string    `json:"project_id"`
	FileCount  int       `json:"file_count"`
	TotalBytes int64     `json:"total_bytes"`
	LastEdited time.Time `json:"last_edited"`
}

type listResponse struct {
	Listings []listingView `json:"listings"`
	Page     int           `json:"page"`
	PageSize int           `json:"page_size"`
	HasMore  bool          `json:"has_more"`
}

type publishRequest struct {
	ProjectID   string `json:"project_id"`
	Title       string `json:"title"`
	Description string `json:"description"`
}

type publishResponse struct {
	Slug string `json:"slug"`
	ID   string `json:"id"`
}

type likeResponse struct {
	LikedByMe  bool `json:"liked_by_me"`
	LikesCount int  `json:"likes_count"`
}

type forkRequest struct {
	ProjectName string `json:"project_name"`
}

type forkResponse struct {
	ProjectID string `json:"project_id"`
	Truncated bool   `json:"truncated"`
}

// --- helpers ---

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
	return dec.Decode(dst)
}

// slugify produces a URL-safe slug from arbitrary input. Pure-Go: lower
// the case, ascii-only, swap runs of non-alnum for '-', trim. The
// migration deliberately does NOT depend on the unaccent extension —
// unicode characters are simply dropped here. A 4-byte hex suffix is
// added by the caller on collision.
func slugify(s string) string {
	s = strings.ToLower(strings.TrimSpace(s))
	var b strings.Builder
	b.Grow(len(s))
	prevDash := false
	for _, r := range s {
		if r > unicode.MaxASCII {
			// Skip non-ASCII to keep slugs portable.
			if !prevDash && b.Len() > 0 {
				b.WriteByte('-')
				prevDash = true
			}
			continue
		}
		if (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') {
			b.WriteRune(r)
			prevDash = false
			continue
		}
		if !prevDash && b.Len() > 0 {
			b.WriteByte('-')
			prevDash = true
		}
	}
	out := strings.Trim(b.String(), "-")
	if out == "" {
		out = "listing"
	}
	if len(out) > 60 {
		out = strings.TrimRight(out[:60], "-")
	}
	return out
}

func randomSuffix() string {
	var buf [2]byte
	_, _ = rand.Read(buf[:])
	return hex.EncodeToString(buf[:])
}

// uniqueSlug attempts the bare slug first, then appends -xxxx suffixes
// until a free row is found. We retry up to ~8 times; further conflicts
// fall back to a 6-byte suffix which is effectively never going to
// collide.
func uniqueSlug(ctx context.Context, q queryer, base string, excludeID string) (string, error) {
	candidate := base
	for attempt := 0; attempt < 8; attempt++ {
		var taken bool
		err := q.QueryRow(ctx,
			// Cast id to text so the `<> $2` comparison works regardless of
			// whether $2 is a UUID literal or empty string. The empty-string
			// branch is short-circuited to avoid the cast cost on the
			// publish-new path; the cast only matters when re-publishing.
			`select exists(select 1 from cloud_workshop_listings where slug = $1 and ($2 = '' or id::text <> $2))`,
			candidate, excludeID,
		).Scan(&taken)
		if err != nil {
			return "", err
		}
		if !taken {
			return candidate, nil
		}
		candidate = base + "-" + randomSuffix()
	}
	// Wide suffix as a last resort.
	var buf [4]byte
	_, _ = rand.Read(buf[:])
	return base + "-" + hex.EncodeToString(buf[:]), nil
}

// queryer is the small subset of pgxpool.Pool / pgx.Tx that uniqueSlug
// needs. Lets the helper run inside or outside a transaction.
type queryer interface {
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
}

// --- GET /workshop/ ---

func (h *Handlers) List(w http.ResponseWriter, r *http.Request) {
	uid := kmw.UserID(r.Context())

	page := 1
	if v := r.URL.Query().Get("page"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			page = n
		}
	}
	const pageSize = 24
	offset := (page - 1) * pageSize

	sort := r.URL.Query().Get("sort")
	orderBy := "l.published_at desc"
	if sort == "popular" {
		orderBy = "l.likes_count desc, l.published_at desc"
	}

	// Optional ?type=<project_type> filter. Empty (or "all") means no
	// filter; we validate against the small known set so a bad query
	// param can't slip a SQL fragment in. Tying the filter to the source
	// project's denormalized type keeps the join cheap (no jsonb probe).
	typeFilter := strings.TrimSpace(r.URL.Query().Get("type"))
	if typeFilter == "all" {
		typeFilter = ""
	}
	if typeFilter != "" {
		switch typeFilter {
		case "mechanical", "electronics", "architecture":
			// ok
		default:
			writeError(w, http.StatusBadRequest, "invalid type filter")
			return
		}
	}

	// args[0] = uid, args[1] = pageSize+1, args[2] = offset, args[3?] = typeFilter
	args := []any{uid, pageSize + 1, offset}
	whereType := ""
	if typeFilter != "" {
		args = append(args, typeFilter)
		whereType = " where p.project_type = $4 "
	}

	// We over-fetch by 1 row to compute has_more without a count(*). The
	// projects join is required to surface project_type; it's already
	// implicit via the listing's project_id FK so it adds no rows.
	q := fmt.Sprintf(`
        select l.id, l.slug, l.title, l.description, l.thumbnail_url,
               l.likes_count, l.forks_count, l.published_at, l.updated_at,
               u.id, u.name, u.avatar_url,
               coalesce(p.project_type, 'mechanical') as project_type,
               case when $1 = '' then false
                    else exists(
                        select 1 from cloud_workshop_likes
                        where listing_id = l.id and user_id::text = $1
                    )
               end as liked_by_me
        from cloud_workshop_listings l
        join users u on u.id = l.user_id
        join projects p on p.id = l.project_id
        %s
        order by %s
        limit $2 offset $3
    `, whereType, orderBy)

	rows, err := h.Pool.Query(r.Context(), q, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer rows.Close()

	out := make([]listingView, 0, pageSize)
	for rows.Next() {
		var v listingView
		if err := rows.Scan(
			&v.ID, &v.Slug, &v.Title, &v.Description, &v.ThumbnailURL,
			&v.LikesCount, &v.ForksCount, &v.PublishedAt, &v.UpdatedAt,
			&v.Author.ID, &v.Author.Name, &v.Author.AvatarURL,
			&v.ProjectType,
			&v.LikedByMe,
		); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		out = append(out, v)
	}

	hasMore := len(out) > pageSize
	if hasMore {
		out = out[:pageSize]
	}

	writeJSON(w, http.StatusOK, listResponse{
		Listings: out,
		Page:     page,
		PageSize: pageSize,
		HasMore:  hasMore,
	})
}

// --- GET /workshop/{slug} ---

func (h *Handlers) Get(w http.ResponseWriter, r *http.Request) {
	uid := kmw.UserID(r.Context())
	slug := chi.URLParam(r, "slug")

	var v listingDetailView
	err := h.Pool.QueryRow(r.Context(), `
        select l.id, l.slug, l.title, l.description, l.thumbnail_url,
               l.likes_count, l.forks_count, l.published_at, l.updated_at,
               l.project_id,
               u.id, u.name, u.avatar_url,
               coalesce(p.project_type, 'mechanical') as project_type,
               case when $1 = '' then false
                    else exists(
                        select 1 from cloud_workshop_likes
                        where listing_id = l.id and user_id::text = $1
                    )
               end as liked_by_me
        from cloud_workshop_listings l
        join users u on u.id = l.user_id
        join projects p on p.id = l.project_id
        where l.slug = $2
    `, uid, slug).Scan(
		&v.ID, &v.Slug, &v.Title, &v.Description, &v.ThumbnailURL,
		&v.LikesCount, &v.ForksCount, &v.PublishedAt, &v.UpdatedAt,
		&v.ProjectID,
		&v.Author.ID, &v.Author.Name, &v.Author.AvatarURL,
		&v.ProjectType,
		&v.LikedByMe,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "listing not found")
			return
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	// Cheap aggregate of the file tree — only files that haven't been
	// soft-deleted count. coalesce on max(updated_at) so a brand-new
	// project with no files doesn't return a NULL.
	if err := h.Pool.QueryRow(r.Context(), `
        select count(*),
               coalesce(sum(coalesce(size, length(content))), 0),
               coalesce(max(updated_at), $2)
        from files
        where project_id = $1 and deleted_at is null and kind <> 'folder'
    `, v.ProjectID, v.UpdatedAt).Scan(&v.FileCount, &v.TotalBytes, &v.LastEdited); err != nil {
		// Don't fail the whole request on a stats hiccup.
		v.FileCount = 0
		v.TotalBytes = 0
		v.LastEdited = v.UpdatedAt
	}

	writeJSON(w, http.StatusOK, v)
}

// --- POST /workshop/publish ---

func (h *Handlers) Publish(w http.ResponseWriter, r *http.Request) {
	uid := kmw.UserID(r.Context())
	if uid == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return
	}
	var body publishRequest
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	body.ProjectID = strings.TrimSpace(body.ProjectID)
	if body.ProjectID == "" {
		writeError(w, http.StatusBadRequest, "project_id is required")
		return
	}

	// Ownership + visibility check. Project must exist, the caller
	// must own it, and visibility cannot be 'private' — public listing
	// of a private project would be confusing UX (file fetches would
	// 403 for visitors).
	var ownerID, visibility, projectName string
	err := h.Pool.QueryRow(r.Context(),
		`select owner_id, visibility, name from projects where id = $1`,
		body.ProjectID,
	).Scan(&ownerID, &visibility, &projectName)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "project not found")
			return
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if ownerID != uid {
		writeError(w, http.StatusForbidden, "only the owner can publish")
		return
	}
	if visibility == "private" {
		writeError(w, http.StatusBadRequest,
			"project is private — set visibility to unlisted or public first")
		return
	}

	title := strings.TrimSpace(body.Title)
	if title == "" {
		title = projectName
	}
	if title == "" {
		title = "Untitled listing"
	}
	description := strings.TrimSpace(body.Description)

	tx, err := h.Pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer tx.Rollback(r.Context())

	// Idempotent re-publish: if a listing already exists for this
	// project, update title/description and bump updated_at.
	var existingID, existingSlug string
	err = tx.QueryRow(r.Context(),
		`select id, slug from cloud_workshop_listings where project_id = $1`,
		body.ProjectID,
	).Scan(&existingID, &existingSlug)
	if err != nil && !errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	if existingID != "" {
		if _, err := tx.Exec(r.Context(), `
            update cloud_workshop_listings
            set title = $2, description = $3, updated_at = now()
            where id = $1
        `, existingID, title, description); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		if err := tx.Commit(r.Context()); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, publishResponse{Slug: existingSlug, ID: existingID})
		return
	}

	// New listing path.
	base := slugify(title)
	slug, err := uniqueSlug(r.Context(), tx, base, "")
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	var newID string
	err = tx.QueryRow(r.Context(), `
        insert into cloud_workshop_listings
            (project_id, user_id, slug, title, description)
        values ($1, $2, $3, $4, $5)
        returning id
    `, body.ProjectID, uid, slug, title, description).Scan(&newID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	// First-time publish notification. Fired AFTER commit so the user
	// only ever gets an email for a listing that actually exists. The
	// republish path above (existingID != "") deliberately skips this —
	// repeated republishes would otherwise spam the user. Errors are
	// logged and swallowed so a flaky email provider doesn't surface as
	// a 5xx on Publish.
	if h.Mailer != nil {
		var (
			recipient string
		)
		if err := h.Pool.QueryRow(r.Context(),
			`select email from users where id = $1`, uid,
		).Scan(&recipient); err == nil && recipient != "" {
			listingURL := strings.TrimRight(h.Cfg.CORSOrigin, "/") + "/workshop/" + slug
			if err := h.Mailer.SendTemplate(r.Context(), "workshop_published", recipient, uid, map[string]any{
				"Title":      title,
				"ListingURL": listingURL,
				"AppURL":     h.Cfg.CORSOrigin,
			}); err != nil {
				// Don't fail the request — log and move on.
				_ = err
			}
		}
	}

	writeJSON(w, http.StatusCreated, publishResponse{Slug: slug, ID: newID})
}

// --- DELETE /workshop/{slug} ---

func (h *Handlers) Unpublish(w http.ResponseWriter, r *http.Request) {
	uid := kmw.UserID(r.Context())
	if uid == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return
	}
	slug := chi.URLParam(r, "slug")

	// FK on cloud_workshop_likes cascades, so we just delete the
	// listing row. Confirm ownership in the same statement so a
	// non-owner gets 404 (not "deleted").
	tag, err := h.Pool.Exec(r.Context(),
		`delete from cloud_workshop_listings where slug = $1 and user_id = $2`,
		slug, uid,
	)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if tag.RowsAffected() == 0 {
		// Could be either "no such slug" or "not yours" — either way
		// 404 is the safe surface (don't leak existence).
		writeError(w, http.StatusNotFound, "listing not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// --- POST /workshop/{slug}/like ---

func (h *Handlers) ToggleLike(w http.ResponseWriter, r *http.Request) {
	uid := kmw.UserID(r.Context())
	if uid == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return
	}
	slug := chi.URLParam(r, "slug")

	tx, err := h.Pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer tx.Rollback(r.Context())

	var listingID string
	if err := tx.QueryRow(r.Context(),
		`select id from cloud_workshop_listings where slug = $1`, slug,
	).Scan(&listingID); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "listing not found")
			return
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	// Probe existing row to decide insert vs delete. on-conflict could
	// also work but the count update is asymmetric so the explicit
	// branch is clearer.
	var liked bool
	if err := tx.QueryRow(r.Context(),
		`select exists(
            select 1 from cloud_workshop_likes
            where user_id = $1 and listing_id = $2
        )`, uid, listingID,
	).Scan(&liked); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	var likesCount int
	if liked {
		if _, err := tx.Exec(r.Context(),
			`delete from cloud_workshop_likes where user_id = $1 and listing_id = $2`,
			uid, listingID,
		); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		if err := tx.QueryRow(r.Context(),
			`update cloud_workshop_listings
                set likes_count = greatest(likes_count - 1, 0)
                where id = $1
                returning likes_count`,
			listingID,
		).Scan(&likesCount); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		liked = false
	} else {
		if _, err := tx.Exec(r.Context(),
			`insert into cloud_workshop_likes(user_id, listing_id) values ($1, $2)
                on conflict do nothing`,
			uid, listingID,
		); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		if err := tx.QueryRow(r.Context(),
			`update cloud_workshop_listings
                set likes_count = likes_count + 1
                where id = $1
                returning likes_count`,
			listingID,
		).Scan(&likesCount); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		liked = true
	}

	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, likeResponse{LikedByMe: liked, LikesCount: likesCount})
}

// --- POST /workshop/{slug}/fork ---

func (h *Handlers) Fork(w http.ResponseWriter, r *http.Request) {
	uid := kmw.UserID(r.Context())
	if uid == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return
	}
	slug := chi.URLParam(r, "slug")

	var body forkRequest
	// Empty bodies are fine — fall back to the listing's title.
	if r.ContentLength > 0 {
		_ = decodeJSON(r, &body)
	}

	tx, err := h.Pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer tx.Rollback(r.Context())

	var (
		listingID    string
		srcProjectID string
		listingTitle string
	)
	if err := tx.QueryRow(r.Context(), `
        select id, project_id, title
        from cloud_workshop_listings
        where slug = $1
    `, slug).Scan(&listingID, &srcProjectID, &listingTitle); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "listing not found")
			return
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	// Pull the source project's metadata so the fork preserves the
	// description + project_type (visibility resets to 'private' — the
	// forker can re-publish if they want). project_type carries over so
	// an electronics fork doesn't suddenly render with the mechanical
	// editor.
	var (
		srcDesc        string
		srcProjectType string
	)
	if err := tx.QueryRow(r.Context(),
		`select description, coalesce(project_type, 'mechanical') from projects where id = $1`,
		srcProjectID,
	).Scan(&srcDesc, &srcProjectType); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	newName := strings.TrimSpace(body.ProjectName)
	if newName == "" {
		newName = listingTitle + " (fork)"
	}

	// Create the new project + owner membership row.
	var newProjectID string
	if err := tx.QueryRow(r.Context(), `
        insert into projects(owner_id, name, description, visibility, project_type)
        values ($1, $2, $3, 'private', $4)
        returning id
    `, uid, newName, srcDesc, srcProjectType).Scan(&newProjectID); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if _, err := tx.Exec(r.Context(),
		`insert into project_members(project_id, user_id, role) values ($1, $2, 'owner')`,
		newProjectID, uid,
	); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	// Copy the file tree. Two-pass insert to preserve parent_id
	// pointers: first map old ids -> new ids while inserting, then
	// patch parent_id in a second sweep.
	rows, err := tx.Query(r.Context(), `
        select id, parent_id, name, kind, content, storage_key, mime_type, size
        from files
        where project_id = $1 and deleted_at is null
        order by parent_id nulls first, created_at asc
        limit $2
    `, srcProjectID, maxForkFiles+1)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	type fileRow struct {
		oldID      string
		oldParent  *string
		name, kind string
		content    string
		storageKey *string
		mimeType   *string
		size       *int64
	}
	var srcFiles []fileRow
	for rows.Next() {
		var f fileRow
		if err := rows.Scan(
			&f.oldID, &f.oldParent, &f.name, &f.kind,
			&f.content, &f.storageKey, &f.mimeType, &f.size,
		); err != nil {
			rows.Close()
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		srcFiles = append(srcFiles, f)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	truncated := false
	if len(srcFiles) > maxForkFiles {
		srcFiles = srcFiles[:maxForkFiles]
		truncated = true
	}

	// First pass: insert each row with parent_id=NULL, capture id map.
	idMap := make(map[string]string, len(srcFiles))
	for _, f := range srcFiles {
		var newID string
		if err := tx.QueryRow(r.Context(), `
            insert into files(project_id, parent_id, name, kind, content,
                              storage_key, mime_type, size)
            values ($1, null, $2, $3, $4, $5, $6, $7)
            returning id
        `, newProjectID, f.name, f.kind, f.content,
			f.storageKey, f.mimeType, f.size,
		).Scan(&newID); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		idMap[f.oldID] = newID
	}

	// Second pass: rewrite parent_id where the old parent was also
	// copied. Files whose parent wasn't in the slice (e.g. truncated
	// past the cap) become root-level — better than orphan refs.
	for _, f := range srcFiles {
		if f.oldParent == nil {
			continue
		}
		newParent, ok := idMap[*f.oldParent]
		if !ok {
			continue
		}
		newID := idMap[f.oldID]
		if _, err := tx.Exec(r.Context(),
			`update files set parent_id = $1 where id = $2`,
			newParent, newID,
		); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
	}

	// Bump forks_count on the listing in the same tx so failures
	// don't leave a half-counted listing.
	if _, err := tx.Exec(r.Context(),
		`update cloud_workshop_listings
         set forks_count = forks_count + 1, updated_at = now()
         where id = $1`,
		listingID,
	); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	writeJSON(w, http.StatusCreated, forkResponse{
		ProjectID: newProjectID,
		Truncated: truncated,
	})
}

// --- GET /workshop/parts ---
//
// Browse public Parts across the Workshop. A row appears here when:
//   1. its containing project's `visibility` is NOT 'private' (so the
//      blob URLs the row references are reachable);
//   2. the file row is `kind = 'part'` (and not soft-deleted);
//   3. the Part JSON's `visibility` field is exactly 'public'.
//
// Returned shape (mirrors the spec in the issue):
//
//   { rows: [{ file_id, project_id, slug?, name, manufacturer?, mpn?,
//              category?, primary_photo_url?, author }],
//     limit, total }
//
// `slug` is included when the parent project has a workshop listing —
// the frontend uses it to deep-link "back to project". Sorting:
//
//   is_verified_publisher desc, files.updated_at desc.
//
// Hard cap of 100 rows.

type partAuthorView struct {
	UserID              string `json:"user_id"`
	Name                string `json:"name"`
	IsVerifiedPublisher bool   `json:"is_verified_publisher"`
}

type workshopPartRow struct {
	FileID          string          `json:"file_id"`
	ProjectID       string          `json:"project_id"`
	Slug            *string         `json:"slug,omitempty"`
	Name            string          `json:"name"`
	Manufacturer    string          `json:"manufacturer,omitempty"`
	MPN             string          `json:"mpn,omitempty"`
	Category        string          `json:"category,omitempty"`
	PrimaryPhotoURL string          `json:"primary_photo_url,omitempty"`
	Author          partAuthorView  `json:"author"`
}

type workshopPartsResponse struct {
	Rows  []workshopPartRow `json:"rows"`
	Limit int               `json:"limit"`
	Total int               `json:"total"`
}

func (h *Handlers) ListParts(w http.ResponseWriter, r *http.Request) {
	const hardLimit = 100

	q := strings.TrimSpace(r.URL.Query().Get("search"))
	cat := strings.TrimSpace(r.URL.Query().Get("category"))
	verifiedOnly := r.URL.Query().Get("verified_only") == "true"

	// Build the SQL with positional args. We extract Part fields out of
	// `files.content` via jsonb operators; the project-level visibility
	// filter on `projects` keeps the row count tiny in practice. Ordering
	// is verified-first so curated suppliers float to the top.
	args := []any{}
	conditions := []string{
		"f.kind = 'part'",
		"f.deleted_at is null",
		"p.visibility <> 'private'",
		// Strict 'public' on the Part itself.
		"(f.content::jsonb ->> 'visibility') = 'public'",
	}

	pushArg := func(v any) string {
		args = append(args, v)
		return fmt.Sprintf("$%d", len(args))
	}

	if q != "" {
		// Case-insensitive contains over name + manufacturer + mpn. We
		// pull these out of the JSON column so we don't need a generated
		// column or index — the project/visibility filter already shrinks
		// the working set enough.
		ph := pushArg("%" + q + "%")
		conditions = append(conditions,
			fmt.Sprintf("(coalesce(f.content::jsonb ->> 'name','') ilike %[1]s "+
				" or coalesce(f.content::jsonb ->> 'manufacturer','') ilike %[1]s "+
				" or coalesce(f.content::jsonb ->> 'mpn','') ilike %[1]s)", ph))
	}
	if cat != "" {
		ph := pushArg(cat)
		conditions = append(conditions,
			fmt.Sprintf("(f.content::jsonb ->> 'category') = %s", ph))
	}
	if verifiedOnly {
		conditions = append(conditions, "u.is_verified_publisher = true")
	}

	limitPh := pushArg(hardLimit)

	sql := fmt.Sprintf(`
		select
		    f.id,
		    f.project_id,
		    coalesce(f.content::jsonb ->> 'name', '')         as name,
		    coalesce(f.content::jsonb ->> 'manufacturer', '') as manufacturer,
		    coalesce(f.content::jsonb ->> 'mpn', '')          as mpn,
		    coalesce(f.content::jsonb ->> 'category', '')     as category,
		    -- First photo with primary=true; else the first photo at all.
		    coalesce(
		        (
		            select photo ->> 'storage_key'
		              from jsonb_array_elements(coalesce(f.content::jsonb -> 'photos', '[]'::jsonb)) photo
		             where (photo ->> 'primary') = 'true'
		             limit 1
		        ),
		        (
		            select photo ->> 'storage_key'
		              from jsonb_array_elements(coalesce(f.content::jsonb -> 'photos', '[]'::jsonb)) photo
		             limit 1
		        ),
		        ''
		    ) as primary_photo_key,
		    f.updated_at,
		    u.id, coalesce(u.name, ''), coalesce(u.is_verified_publisher, false),
		    wl.slug
		  from files f
		  join projects p on p.id = f.project_id
		  join users    u on u.id = p.owner_id
		  left join cloud_workshop_listings wl on wl.project_id = p.id
		 where %s
		 order by u.is_verified_publisher desc, f.updated_at desc
		 limit %s
	`, strings.Join(conditions, " and "), limitPh)

	rows, err := h.Pool.Query(r.Context(), sql, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer rows.Close()

	out := make([]workshopPartRow, 0, 32)
	for rows.Next() {
		var (
			fid, pid, name, manuf, mpn, cat, photoKey string
			updatedAt                                 time.Time
			authorID, authorName                      string
			verified                                  bool
			slug                                      *string
		)
		if err := rows.Scan(
			&fid, &pid,
			&name, &manuf, &mpn, &cat, &photoKey, &updatedAt,
			&authorID, &authorName, &verified, &slug,
		); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		row := workshopPartRow{
			FileID:       fid,
			ProjectID:    pid,
			Slug:         slug,
			Name:         name,
			Manufacturer: manuf,
			MPN:          mpn,
			Category:     cat,
			Author: partAuthorView{
				UserID:              authorID,
				Name:                authorName,
				IsVerifiedPublisher: verified,
			},
		}
		if photoKey != "" {
			row.PrimaryPhotoURL = h.publicBlobURL(photoKey, updatedAt)
		}
		out = append(out, row)
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	writeJSON(w, http.StatusOK, workshopPartsResponse{
		Rows:  out,
		Limit: hardLimit,
		Total: len(out),
	})
}

// publicBlobURL replicates Storage.PublicURL without taking a Storage dep.
// Local backend → /api/blobs/<key>?v=<unix>; CDN configured →
// <cdn>/<key>?v=<unix>. Path segments are URL-escaped.
func (h *Handlers) publicBlobURL(key string, updatedAt time.Time) string {
	if key == "" {
		return ""
	}
	cdn := ""
	if h.Cfg != nil {
		cdn = strings.TrimRight(h.Cfg.CDNBaseURL, "/")
	}
	parts := strings.Split(strings.TrimLeft(key, "/"), "/")
	for i, p := range parts {
		parts[i] = url.PathEscape(p)
	}
	escaped := strings.Join(parts, "/")
	base := "/api/blobs/" + escaped
	if cdn != "" {
		base = cdn + "/" + escaped
	}
	if !updatedAt.IsZero() {
		return base + "?v=" + strconv.FormatInt(updatedAt.Unix(), 10)
	}
	return base
}
