//go:build cloud
// +build cloud

// Package library implements the manufacturer-PR submission flow that
// closes Library Phase 3 (ROADMAP row 73).
//
// Anyone (any authenticated user) submits a Part via POST
// /api/library/submissions. Submissions land in
// library_part_submissions with status='pending'. Admins review via
// GET /api/admin/library/submissions and PUT
// /api/admin/library/submissions/{id}. Approval copies the payload
// into a new files row (kind='part') in the target workspace's seed
// Library project; rejection stamps a reason.
//
// Build-tag fence mirrors backend/cloud/workshop: every file here is
// gated by `//go:build cloud`. Tiny request helpers (writeJSON /
// writeError / decodeJSON) are duplicated locally — same trade-off as
// the workshop package — to avoid an import of backend/internal/handlers.
package library

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/internal/config"
	kmw "github.com/imranp/kerf/backend/internal/middleware"
)

// Hard caps on the submission payload. The Library is meant for tightly
// metadata-rich rows, not arbitrary JSON dumps — capping at 64KiB keeps
// the queue surveyable and prevents a single submission from blowing up
// the row size hash.
const (
	maxPayloadBytes = 64 * 1024 // 64 KiB
	maxStringField  = 200       // names / mpn / manufacturer / category
	maxDescription  = 4000      // description / photos url
	maxReviewNote   = 1000
	maxListPageSize = 100
)

// Handlers wires the submission endpoints. Constructed by the cloud
// build of cmd/server (see cloud_enabled.go) and mounted under
// /api/library and /api/admin/library by the same caller.
type Handlers struct {
	Pool *pgxpool.Pool
	Cfg  *config.Config
}

// MountSubmit attaches POST /submissions to an authed router. The
// caller is expected to have already routed under /api/library and
// applied RequireAuth.
func (h *Handlers) MountSubmit(authed chi.Router) {
	authed.Post("/submissions", h.SubmitPart)
}

// MountAdmin attaches the admin queue routes to an authed router. The
// caller is expected to have already routed under /api/admin/library
// and applied RequireAuth. The admin role check is enforced inside
// each handler (mirrors /api/admin/distributors).
func (h *Handlers) MountAdmin(authed chi.Router) {
	authed.Get("/submissions", h.ListSubmissions)
	authed.Put("/submissions/{id}", h.ReviewSubmission)
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

// requireAdmin returns true (and writes the appropriate error
// otherwise) when the caller's account_role is 'admin' or 'system'.
// Mirrors the helper in handlers/distributor_admin.go.
func (h *Handlers) requireAdmin(w http.ResponseWriter, r *http.Request) bool {
	uid := kmw.UserID(r.Context())
	if uid == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return false
	}
	var role string
	err := h.Pool.QueryRow(r.Context(),
		`select account_role from users where id = $1`, uid).Scan(&role)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return false
	}
	if role != "admin" && role != "system" {
		writeError(w, http.StatusForbidden, "admin access required")
		return false
	}
	return true
}

// --- request / response shapes ---

type submitRequest struct {
	TargetWorkspaceSlug string          `json:"target_workspace_slug"`
	Payload             json.RawMessage `json:"payload"`
}

type submitResponse struct {
	ID string `json:"id"`
}

type submissionView struct {
	ID                string          `json:"id"`
	SubmitterUserID   string          `json:"submitter_user_id"`
	SubmitterName     string          `json:"submitter_name,omitempty"`
	SubmitterEmail    string          `json:"submitter_email,omitempty"`
	TargetWorkspaceID string          `json:"target_workspace_id"`
	TargetWorkspace   string          `json:"target_workspace_slug,omitempty"`
	Payload           json.RawMessage `json:"payload"`
	Status            string          `json:"status"`
	ReviewNote        string          `json:"review_note"`
	ReviewerID        *string         `json:"reviewer_id,omitempty"`
	CreatedAt         time.Time       `json:"created_at"`
	UpdatedAt         time.Time       `json:"updated_at"`
}

type listResponse struct {
	Submissions []submissionView `json:"submissions"`
	Page        int              `json:"page"`
	PageSize    int              `json:"page_size"`
	HasMore     bool             `json:"has_more"`
}

type reviewRequest struct {
	Action     string `json:"action"`
	ReviewNote string `json:"review_note"`
}

// --- POST /api/library/submissions ---

// SubmitPart accepts a part-shaped JSON payload and queues it for
// review. Auth required (any role). Validates the minimum required
// fields (name, manufacturer, mpn, category, description) and a
// modest size cap before insert.
func (h *Handlers) SubmitPart(w http.ResponseWriter, r *http.Request) {
	uid := kmw.UserID(r.Context())
	if uid == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return
	}

	// Hard cap on the request body so a malicious caller can't OOM us.
	r.Body = http.MaxBytesReader(w, r.Body, maxPayloadBytes+1024)
	var body submitRequest
	dec := json.NewDecoder(r.Body)
	dec.DisallowUnknownFields()
	if err := dec.Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}

	slug := strings.TrimSpace(body.TargetWorkspaceSlug)
	if slug == "" {
		writeError(w, http.StatusBadRequest, "target_workspace_slug is required")
		return
	}

	if len(body.Payload) == 0 {
		writeError(w, http.StatusBadRequest, "payload is required")
		return
	}
	if len(body.Payload) > maxPayloadBytes {
		writeError(w, http.StatusBadRequest, "payload exceeds 64KiB cap")
		return
	}

	// Payload must parse as a JSON object and carry the minimum fields.
	var probe struct {
		Name         string `json:"name"`
		Manufacturer string `json:"manufacturer"`
		MPN          string `json:"mpn"`
		Category     string `json:"category"`
		Description  string `json:"description"`
	}
	if err := json.Unmarshal(body.Payload, &probe); err != nil {
		writeError(w, http.StatusBadRequest, "payload must be a JSON object")
		return
	}
	if err := validatePartProbe(probe.Name, probe.Manufacturer, probe.MPN, probe.Category, probe.Description); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	// Resolve the target workspace by slug. Submitting against an
	// unknown workspace is a 404 — same surface a public reader would
	// see — so we don't accidentally enumerate workspace ids.
	var workspaceID string
	err := h.Pool.QueryRow(r.Context(),
		`select id from workspaces where slug = $1`, slug,
	).Scan(&workspaceID)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "target workspace not found")
			return
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	var newID string
	err = h.Pool.QueryRow(r.Context(), `
		insert into library_part_submissions
		    (submitter_user_id, target_workspace_id, payload)
		values ($1, $2, $3::jsonb)
		returning id
	`, uid, workspaceID, string(body.Payload)).Scan(&newID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	writeJSON(w, http.StatusCreated, submitResponse{ID: newID})
}

// validatePartProbe enforces the minimum-fields contract. Length caps
// match the column comments on library_part_submissions.
func validatePartProbe(name, manufacturer, mpn, category, description string) error {
	name = strings.TrimSpace(name)
	manufacturer = strings.TrimSpace(manufacturer)
	mpn = strings.TrimSpace(mpn)
	category = strings.TrimSpace(category)
	description = strings.TrimSpace(description)
	if name == "" {
		return errors.New("payload.name is required")
	}
	if manufacturer == "" {
		return errors.New("payload.manufacturer is required")
	}
	if mpn == "" {
		return errors.New("payload.mpn is required")
	}
	if category == "" {
		return errors.New("payload.category is required")
	}
	if description == "" {
		return errors.New("payload.description is required")
	}
	if len(name) > maxStringField || len(manufacturer) > maxStringField ||
		len(mpn) > maxStringField || len(category) > maxStringField {
		return errors.New("payload string field exceeds length cap")
	}
	if len(description) > maxDescription {
		return errors.New("payload.description exceeds length cap")
	}
	return nil
}

// --- GET /api/admin/library/submissions ---

// ListSubmissions returns paginated submissions, newest first. Admin
// only. Optional ?status= filter (default 'pending').
func (h *Handlers) ListSubmissions(w http.ResponseWriter, r *http.Request) {
	if !h.requireAdmin(w, r) {
		return
	}

	status := strings.TrimSpace(r.URL.Query().Get("status"))
	if status == "" {
		status = "pending"
	}
	if status != "pending" && status != "approved" && status != "rejected" && status != "all" {
		writeError(w, http.StatusBadRequest, "invalid status filter")
		return
	}

	page := 1
	if v := r.URL.Query().Get("page"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			page = n
		}
	}
	pageSize := 25
	if v := r.URL.Query().Get("page_size"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			if n > maxListPageSize {
				n = maxListPageSize
			}
			pageSize = n
		}
	}
	offset := (page - 1) * pageSize

	// Over-fetch by 1 to compute has_more without a count(*).
	args := []any{pageSize + 1, offset}
	whereStatus := ""
	if status != "all" {
		args = append(args, status)
		whereStatus = " where s.status = $3 "
	}
	q := `
		select s.id, s.submitter_user_id, coalesce(u.name, ''), coalesce(u.email, ''),
		       s.target_workspace_id, coalesce(w.slug, ''),
		       s.payload::text, s.status, s.review_note, s.reviewer_id,
		       s.created_at, s.updated_at
		  from library_part_submissions s
		  left join users u on u.id = s.submitter_user_id
		  left join workspaces w on w.id = s.target_workspace_id
		` + whereStatus + `
		 order by s.created_at desc
		 limit $1 offset $2
	`
	rows, err := h.Pool.Query(r.Context(), q, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer rows.Close()

	out := make([]submissionView, 0, pageSize)
	for rows.Next() {
		var v submissionView
		var payloadStr string
		var reviewerID *string
		if err := rows.Scan(
			&v.ID, &v.SubmitterUserID, &v.SubmitterName, &v.SubmitterEmail,
			&v.TargetWorkspaceID, &v.TargetWorkspace,
			&payloadStr, &v.Status, &v.ReviewNote, &reviewerID,
			&v.CreatedAt, &v.UpdatedAt,
		); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		v.Payload = json.RawMessage(payloadStr)
		v.ReviewerID = reviewerID
		out = append(out, v)
	}

	hasMore := len(out) > pageSize
	if hasMore {
		out = out[:pageSize]
	}

	writeJSON(w, http.StatusOK, listResponse{
		Submissions: out,
		Page:        page,
		PageSize:    pageSize,
		HasMore:     hasMore,
	})
}

// --- PUT /api/admin/library/submissions/{id} ---

// ReviewSubmission applies an admin verdict. action='approve' copies
// the payload into a new files row (kind='part') inside the target
// workspace's seed Library project; action='reject' just stamps the
// reason. Both actions transition the submission to a terminal state.
func (h *Handlers) ReviewSubmission(w http.ResponseWriter, r *http.Request) {
	if !h.requireAdmin(w, r) {
		return
	}
	reviewerID := kmw.UserID(r.Context())
	subID := chi.URLParam(r, "id")
	if subID == "" {
		writeError(w, http.StatusBadRequest, "id is required")
		return
	}

	var body reviewRequest
	dec := json.NewDecoder(r.Body)
	dec.DisallowUnknownFields()
	if err := dec.Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	action := strings.TrimSpace(body.Action)
	if action != "approve" && action != "reject" {
		writeError(w, http.StatusBadRequest, "action must be 'approve' or 'reject'")
		return
	}
	note := strings.TrimSpace(body.ReviewNote)
	if len(note) > maxReviewNote {
		writeError(w, http.StatusBadRequest, "review_note exceeds length cap")
		return
	}

	tx, err := h.Pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer tx.Rollback(r.Context())

	// Load + lock the submission row so concurrent reviewers can't
	// double-apply.
	var (
		curStatus, payload, workspaceID string
	)
	err = tx.QueryRow(r.Context(), `
		select status, payload::text, target_workspace_id
		  from library_part_submissions
		 where id = $1
		 for update
	`, subID).Scan(&curStatus, &payload, &workspaceID)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "submission not found")
			return
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if curStatus != "pending" {
		writeError(w, http.StatusConflict, "submission already "+curStatus)
		return
	}

	if action == "approve" {
		// Pick the seed Library project for the target workspace. v1
		// convention: the first non-deleted project in the workspace,
		// ordered by created_at — matches the seed-publishers layout
		// (one project per workspace). If we ever support multiple
		// libraries per publisher we'll add a `target_project_id` column.
		var projectID string
		err := tx.QueryRow(r.Context(), `
			select id from projects
			 where workspace_id = $1
			 order by created_at asc
			 limit 1
		`, workspaceID).Scan(&projectID)
		if err != nil {
			if errors.Is(err, pgx.ErrNoRows) {
				writeError(w, http.StatusFailedDependency,
					"target workspace has no library project; create one before approving")
				return
			}
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}

		// Derive a file name from the payload's mpn (preferred) or name.
		fileName := approvedFileName(payload)

		if _, err := tx.Exec(r.Context(), `
			insert into files(project_id, parent_id, name, kind, content)
			values ($1, null, $2, 'part', $3)
		`, projectID, fileName, payload); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
	}

	// Stamp the verdict. Both branches converge here.
	newStatus := "approved"
	if action == "reject" {
		newStatus = "rejected"
	}
	if _, err := tx.Exec(r.Context(), `
		update library_part_submissions
		   set status = $2,
		       review_note = $3,
		       reviewer_id = $4,
		       updated_at = now()
		 where id = $1
	`, subID, newStatus, note, reviewerID); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"id":          subID,
		"status":      newStatus,
		"review_note": note,
		"reviewer_id": reviewerID,
	})
}

// approvedFileName picks a stable basename for the new files row. We
// prefer the part's MPN (forced lowercase, alnum-only) and fall back
// to its display name. ".part" is the canonical extension.
func approvedFileName(payloadJSON string) string {
	var probe struct {
		Name string `json:"name"`
		MPN  string `json:"mpn"`
	}
	_ = json.Unmarshal([]byte(payloadJSON), &probe)
	pick := strings.TrimSpace(probe.MPN)
	if pick == "" {
		pick = strings.TrimSpace(probe.Name)
	}
	if pick == "" {
		pick = "submission"
	}
	pick = strings.ToLower(pick)
	var b strings.Builder
	for _, r := range pick {
		switch {
		case r >= 'a' && r <= 'z', r >= '0' && r <= '9':
			b.WriteRune(r)
		case r == '-' || r == '_':
			b.WriteRune(r)
		default:
			b.WriteRune('-')
		}
	}
	out := strings.Trim(b.String(), "-")
	if out == "" {
		out = "submission"
	}
	if len(out) > 60 {
		out = out[:60]
	}
	return out + ".part"
}

