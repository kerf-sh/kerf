//go:build cloud
// +build cloud

package git

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strconv"
	"strings"

	"github.com/go-chi/chi/v5"
	gogit "github.com/go-git/go-git/v5"
	"github.com/go-git/go-git/v5/plumbing"
	"github.com/go-git/go-git/v5/plumbing/object"
	"github.com/jackc/pgx/v5"

	kmw "github.com/imranp/kerf/backend/internal/middleware"
)

// MountProjectRoutes attaches the /api/projects/{pid}/git/* handlers
// onto the supplied (already-authed) sub-router. The caller routed
// under /api/projects/{pid}/git and applied RequireAuth before invoking
// this method (see cloud_enabled.go).
func (s *Service) MountProjectRoutes(r chi.Router) {
	r.Post("/init", s.handleInit)
	r.Post("/import", s.handleImport)
	r.Post("/connect", s.handleConnect)
	r.Get("/log", s.handleLog)
	r.Get("/branches", s.handleBranches)
	r.Post("/branches", s.handleCreateBranch)
	r.Post("/checkout", s.handleCheckout)
	r.Post("/commit", s.handleCommit)
	r.Post("/merge", s.handleMerge)
	r.Post("/push", s.handlePush)
	r.Post("/pull", s.handlePull)
	r.Get("/diff/{sha}", s.handleDiff)
	r.Delete("/repo", s.handleDeleteRepo)
}

// --- request / response shapes ---

type initResponse struct {
	ProjectID     string `json:"project_id"`
	DefaultBranch string `json:"default_branch"`
	HeadSHA       string `json:"head_sha"`
}

type importRequest struct {
	GithubURL string `json:"github_url"`
	Branch    string `json:"branch,omitempty"`
}

type connectRequest struct {
	GithubOwner string `json:"github_owner"`
	GithubRepo  string `json:"github_repo"`
}

type createBranchRequest struct {
	Name    string `json:"name"`
	FromSHA string `json:"from_sha,omitempty"`
}

type checkoutRequest struct {
	Branch string `json:"branch"`
	Force  bool   `json:"force,omitempty"`
}

type commitRequest struct {
	Message string `json:"message"`
	Branch  string `json:"branch,omitempty"`
}

type mergeRequest struct {
	FromBranch string `json:"from_branch"`
	IntoBranch string `json:"into_branch"`
}

type pullRequest struct {
	Branch string `json:"branch,omitempty"`
}

// --- helpers ---

func writeJSON(w http.ResponseWriter, status int, body any) {
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

func decodeJSON(r *http.Request, dst any) error {
	dec := json.NewDecoder(r.Body)
	dec.DisallowUnknownFields()
	return dec.Decode(dst)
}

// requireRole returns the caller's role on the project (or "" if none),
// writing a 404 on miss to avoid leaking project existence. Mirrors the
// requireMember helper in handlers/handlers.go.
func (s *Service) requireRole(w http.ResponseWriter, r *http.Request, projectID string) (uid, role string) {
	uid = kmw.UserID(r.Context())
	if uid == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return "", ""
	}
	var ownerID string
	err := s.Pool.QueryRow(r.Context(),
		`select owner_id from projects where id = $1`, projectID,
	).Scan(&ownerID)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "project not found")
			return uid, ""
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return uid, ""
	}
	if ownerID == uid {
		return uid, "owner"
	}
	var memberRole string
	err = s.Pool.QueryRow(r.Context(),
		`select role from project_members where project_id = $1 and user_id = $2`,
		projectID, uid,
	).Scan(&memberRole)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "project not found")
			return uid, ""
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return uid, ""
	}
	return uid, memberRole
}

// requireEditor enforces editor-or-owner. Returns (uid, true) on pass.
func (s *Service) requireEditor(w http.ResponseWriter, r *http.Request, projectID string) (string, bool) {
	uid, role := s.requireRole(w, r, projectID)
	if role == "" {
		return "", false
	}
	if role != "owner" && role != "editor" {
		writeError(w, http.StatusForbidden, "editor or owner role required")
		return "", false
	}
	return uid, true
}

// resolveProjectName looks up projects.name for the initial-commit message.
func (s *Service) resolveProjectName(ctx context.Context, projectID string) string {
	var name string
	_ = s.Pool.QueryRow(ctx, `select name from projects where id = $1`, projectID).Scan(&name)
	return name
}

// loadUserSig builds a commit Signature from the user's row.
func (s *Service) loadUserSig(ctx context.Context, userID string) (object.Signature, error) {
	var name, email string
	err := s.Pool.QueryRow(ctx,
		`select name, email from users where id = $1`,
		userID,
	).Scan(&name, &email)
	if err != nil {
		return object.Signature{}, err
	}
	return nowSig(name, email), nil
}

// openRepoOr404 opens the project's bare repo, returning a 404 to the
// client if git isn't enabled yet.
func (s *Service) openRepoOr404(w http.ResponseWriter, r *http.Request, projectID string) (*gogit.Repository, bool) {
	repo, err := s.openRepo(projectID)
	if err != nil {
		if errors.Is(err, plumbing.ErrObjectNotFound) || strings.Contains(err.Error(), "not exist") {
			writeError(w, http.StatusNotFound, "git not enabled for this project (call /init)")
			return nil, false
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return nil, false
	}
	return repo, true
}

// --- POST /init ---

func (s *Service) handleInit(w http.ResponseWriter, r *http.Request) {
	pid := chi.URLParam(r, "pid")
	uid, ok := s.requireEditor(w, r, pid)
	if !ok {
		return
	}

	lock := s.lockProject(pid)
	lock.Lock()
	defer lock.Unlock()

	// Idempotent: if a row already exists, return its current state.
	if existing, err := s.getRepoRow(r.Context(), pid); err == nil {
		repo, err := s.openRepo(pid)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "repo row exists but bare repo missing on disk: "+err.Error())
			return
		}
		var headSHA string
		if h, err := s.branchHead(repo, existing.DefaultBranch); err == nil {
			headSHA = h.String()
		}
		writeJSON(w, http.StatusOK, initResponse{
			ProjectID:     pid,
			DefaultBranch: existing.DefaultBranch,
			HeadSHA:       headSHA,
		})
		return
	} else if !errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	// Fresh init.
	repo, err := s.initBareRepo(pid)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if err := s.upsertRepoRow(r.Context(), pid, "main"); err != nil {
		_ = s.removeBareRepo(pid)
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	sig, err := s.loadUserSig(r.Context(), uid)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "load user: "+err.Error())
		return
	}
	projectName := s.resolveProjectName(r.Context(), pid)
	msg := "Initial commit from Kerf project: " + projectName
	if projectName == "" {
		msg = "Initial commit"
	}
	commit, err := s.makeCommit(r.Context(), repo, pid, "main", msg, sig)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "initial commit: "+err.Error())
		return
	}
	// Best-effort cache refresh. Don't fail the request on cache hiccups.
	_ = s.refreshCommitCache(r.Context(), repo, pid)
	_ = s.refreshBranchCache(r.Context(), repo, pid)

	writeJSON(w, http.StatusCreated, initResponse{
		ProjectID:     pid,
		DefaultBranch: "main",
		HeadSHA:       commit.String(),
	})
}

// --- POST /import ---

func (s *Service) handleImport(w http.ResponseWriter, r *http.Request) {
	pid := chi.URLParam(r, "pid")
	uid, ok := s.requireEditor(w, r, pid)
	if !ok {
		return
	}

	var body importRequest
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	body.GithubURL = strings.TrimSpace(body.GithubURL)
	if body.GithubURL == "" {
		writeError(w, http.StatusBadRequest, "github_url is required")
		return
	}
	owner, repoName, err := parseGitHubURL(body.GithubURL)
	if err != nil {
		writeError(w, http.StatusBadRequest, "github_url: "+err.Error())
		return
	}

	lock := s.lockProject(pid)
	lock.Lock()
	defer lock.Unlock()

	// Refuse if the project already has git enabled — caller should
	// /repo DELETE first.
	if _, err := s.getRepoRow(r.Context(), pid); err == nil {
		writeError(w, http.StatusConflict, "git already enabled for this project")
		return
	} else if !errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	// Token is optional: anonymous clone works for public repos.
	token, err := s.loadGithubToken(r.Context(), uid)
	if err != nil && !errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	repo, err := s.cloneFromGitHub(r.Context(), pid, body.GithubURL, token, body.Branch)
	if err != nil {
		writeError(w, http.StatusBadGateway, "clone: "+err.Error())
		return
	}

	// Pick the default branch: prefer the one we cloned, else fall
	// back to whatever HEAD points at.
	defaultBranch := body.Branch
	if defaultBranch == "" {
		head, err := repo.Head()
		if err == nil {
			defaultBranch = head.Name().Short()
		} else {
			defaultBranch = "main"
		}
	}
	if err := s.upsertRepoRow(r.Context(), pid, defaultBranch); err != nil {
		_ = s.removeBareRepo(pid)
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if _, err := s.Pool.Exec(r.Context(), `
        update cloud_git_repos set
            github_owner = $2,
            github_repo = $3,
            github_remote_url = $4,
            last_fetched_at = now()
        where project_id = $1
    `, pid, owner, repoName, body.GithubURL); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	// Pull the imported tree into the project's files table.
	headRef, err := s.branchHead(repo, defaultBranch)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "resolve HEAD: "+err.Error())
		return
	}
	commit, err := repo.CommitObject(headRef)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "commit object: "+err.Error())
		return
	}
	if err := s.checkoutTreeIntoProject(r.Context(), repo, pid, commit.TreeHash); err != nil {
		writeError(w, http.StatusInternalServerError, "checkout into project: "+err.Error())
		return
	}

	_ = s.refreshCommitCache(r.Context(), repo, pid)
	_ = s.refreshBranchCache(r.Context(), repo, pid)

	writeJSON(w, http.StatusCreated, initResponse{
		ProjectID:     pid,
		DefaultBranch: defaultBranch,
		HeadSHA:       headRef.String(),
	})
}

// --- POST /connect ---

func (s *Service) handleConnect(w http.ResponseWriter, r *http.Request) {
	pid := chi.URLParam(r, "pid")
	uid, ok := s.requireEditor(w, r, pid)
	if !ok {
		return
	}
	var body connectRequest
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	body.GithubOwner = strings.TrimSpace(body.GithubOwner)
	body.GithubRepo = strings.TrimSpace(body.GithubRepo)
	if body.GithubOwner == "" || body.GithubRepo == "" {
		writeError(w, http.StatusBadRequest, "github_owner and github_repo are required")
		return
	}

	token, err := s.requireToken(r.Context(), uid)
	if err != nil {
		writeError(w, http.StatusPreconditionRequired, "github not linked: visit /auth/github/start first")
		return
	}

	lock := s.lockProject(pid)
	lock.Lock()
	defer lock.Unlock()

	repo, ok := s.openRepoOr404(w, r, pid)
	if !ok {
		return
	}
	if err := s.connectGitHub(r.Context(), repo, pid, body.GithubOwner, body.GithubRepo, token); err != nil {
		writeError(w, http.StatusBadGateway, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{
		"github_owner": body.GithubOwner,
		"github_repo":  body.GithubRepo,
	})
}

// --- GET /log ---

func (s *Service) handleLog(w http.ResponseWriter, r *http.Request) {
	pid := chi.URLParam(r, "pid")
	if _, role := s.requireRole(w, r, pid); role == "" {
		return
	}
	repo, ok := s.openRepoOr404(w, r, pid)
	if !ok {
		return
	}
	branch := r.URL.Query().Get("branch")
	limit := 50
	if v := r.URL.Query().Get("limit"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			limit = n
		}
	}
	commits, err := s.listCommits(r.Context(), repo, pid, branch, limit)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, commits)
}

// --- GET /branches ---

func (s *Service) handleBranches(w http.ResponseWriter, r *http.Request) {
	pid := chi.URLParam(r, "pid")
	if _, role := s.requireRole(w, r, pid); role == "" {
		return
	}
	repo, ok := s.openRepoOr404(w, r, pid)
	if !ok {
		return
	}
	out, err := s.listBranches(r.Context(), repo, pid)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, out)
}

// --- POST /branches ---

func (s *Service) handleCreateBranch(w http.ResponseWriter, r *http.Request) {
	pid := chi.URLParam(r, "pid")
	if _, ok := s.requireEditor(w, r, pid); !ok {
		return
	}
	var body createBranchRequest
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	body.Name = strings.TrimSpace(body.Name)

	lock := s.lockProject(pid)
	lock.Lock()
	defer lock.Unlock()

	repo, ok := s.openRepoOr404(w, r, pid)
	if !ok {
		return
	}
	if err := s.createBranch(r.Context(), repo, body.Name, body.FromSHA); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	_ = s.refreshBranchCache(r.Context(), repo, pid)
	head, _ := s.branchHead(repo, body.Name)
	writeJSON(w, http.StatusCreated, branchView{
		Name:    body.Name,
		HeadSHA: head.String(),
	})
}

// --- POST /checkout ---

func (s *Service) handleCheckout(w http.ResponseWriter, r *http.Request) {
	pid := chi.URLParam(r, "pid")
	if _, ok := s.requireEditor(w, r, pid); !ok {
		return
	}
	var body checkoutRequest
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	body.Branch = strings.TrimSpace(body.Branch)
	if body.Branch == "" {
		writeError(w, http.StatusBadRequest, "branch is required")
		return
	}

	lock := s.lockProject(pid)
	lock.Lock()
	defer lock.Unlock()

	repo, ok := s.openRepoOr404(w, r, pid)
	if !ok {
		return
	}

	// Refuse to clobber uncommitted changes unless force=true.
	if !body.Force {
		row, err := s.getRepoRow(r.Context(), pid)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		// Check against the *current* HEAD branch (pre-checkout).
		dirty, err := s.hasUncommittedChanges(r.Context(), repo, pid, row.DefaultBranch)
		if err == nil && dirty {
			// Try the actual current HEAD branch as a fallback.
			if h, err := repo.Head(); err == nil {
				dirty2, err2 := s.hasUncommittedChanges(r.Context(), repo, pid, h.Name().Short())
				if err2 == nil {
					dirty = dirty2
				}
			}
		}
		if dirty {
			writeJSON(w, http.StatusConflict, map[string]any{
				"error":           "uncommitted changes; commit or pass force=true",
				"has_uncommitted": true,
			})
			return
		}
	}

	headHash, err := s.branchHead(repo, body.Branch)
	if err != nil {
		writeError(w, http.StatusNotFound, "branch "+body.Branch+" not found")
		return
	}
	commit, err := repo.CommitObject(headHash)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if err := s.checkoutTreeIntoProject(r.Context(), repo, pid, commit.TreeHash); err != nil {
		writeError(w, http.StatusInternalServerError, "checkout: "+err.Error())
		return
	}
	if err := s.switchHEAD(repo, body.Branch); err != nil {
		writeError(w, http.StatusInternalServerError, "set HEAD: "+err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"branch":   body.Branch,
		"head_sha": headHash.String(),
	})
}

// --- POST /commit ---

func (s *Service) handleCommit(w http.ResponseWriter, r *http.Request) {
	pid := chi.URLParam(r, "pid")
	uid, ok := s.requireEditor(w, r, pid)
	if !ok {
		return
	}
	var body commitRequest
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	body.Message = strings.TrimSpace(body.Message)
	if body.Message == "" {
		writeError(w, http.StatusBadRequest, "message is required")
		return
	}
	branch := strings.TrimSpace(body.Branch)

	lock := s.lockProject(pid)
	lock.Lock()
	defer lock.Unlock()

	repo, ok := s.openRepoOr404(w, r, pid)
	if !ok {
		return
	}
	if branch == "" {
		// Default to the current HEAD's branch, else the configured default.
		if h, err := repo.Head(); err == nil && h.Name().IsBranch() {
			branch = h.Name().Short()
		} else if row, err := s.getRepoRow(r.Context(), pid); err == nil {
			branch = row.DefaultBranch
		} else {
			branch = "main"
		}
	}

	sig, err := s.loadUserSig(r.Context(), uid)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "load user: "+err.Error())
		return
	}
	commit, err := s.makeCommit(r.Context(), repo, pid, branch, body.Message, sig)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	_ = s.refreshCommitCache(r.Context(), repo, pid)
	_ = s.refreshBranchCache(r.Context(), repo, pid)

	writeJSON(w, http.StatusCreated, map[string]any{
		"sha":    commit.String(),
		"branch": branch,
	})
}

// --- POST /merge ---

func (s *Service) handleMerge(w http.ResponseWriter, r *http.Request) {
	pid := chi.URLParam(r, "pid")
	uid, ok := s.requireEditor(w, r, pid)
	if !ok {
		return
	}
	var body mergeRequest
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	body.FromBranch = strings.TrimSpace(body.FromBranch)
	body.IntoBranch = strings.TrimSpace(body.IntoBranch)
	if body.FromBranch == "" || body.IntoBranch == "" {
		writeError(w, http.StatusBadRequest, "from_branch and into_branch are required")
		return
	}

	lock := s.lockProject(pid)
	lock.Lock()
	defer lock.Unlock()

	repo, ok := s.openRepoOr404(w, r, pid)
	if !ok {
		return
	}
	sig, err := s.loadUserSig(r.Context(), uid)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "load user: "+err.Error())
		return
	}
	res, err := s.mergeBranch(r.Context(), repo, pid, body.FromBranch, body.IntoBranch, sig)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if len(res.Conflicts) > 0 {
		writeJSON(w, http.StatusConflict, map[string]any{
			"error":     "merge conflicts",
			"conflicts": res.Conflicts,
		})
		return
	}
	_ = s.refreshCommitCache(r.Context(), repo, pid)
	_ = s.refreshBranchCache(r.Context(), repo, pid)

	writeJSON(w, http.StatusOK, map[string]any{
		"sha":          res.NewCommit.String(),
		"fast_forward": res.FastForward,
		"into_branch":  body.IntoBranch,
	})
}

// --- POST /push ---

func (s *Service) handlePush(w http.ResponseWriter, r *http.Request) {
	pid := chi.URLParam(r, "pid")
	uid, ok := s.requireEditor(w, r, pid)
	if !ok {
		return
	}
	token, err := s.requireToken(r.Context(), uid)
	if err != nil {
		writeError(w, http.StatusPreconditionRequired, "github not linked")
		return
	}

	lock := s.lockProject(pid)
	lock.Lock()
	defer lock.Unlock()

	repo, ok := s.openRepoOr404(w, r, pid)
	if !ok {
		return
	}
	if err := s.pushAllBranches(r.Context(), repo, token); err != nil {
		writeError(w, http.StatusBadGateway, "push: "+err.Error())
		return
	}
	if _, err := s.Pool.Exec(r.Context(), `
        update cloud_git_repos set last_pushed_at = now() where project_id = $1
    `, pid); err != nil {
		// Don't fail — the push succeeded; this is just metadata.
		_ = err
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "pushed"})
}

// --- POST /pull ---

func (s *Service) handlePull(w http.ResponseWriter, r *http.Request) {
	pid := chi.URLParam(r, "pid")
	uid, ok := s.requireEditor(w, r, pid)
	if !ok {
		return
	}
	token, err := s.requireToken(r.Context(), uid)
	if err != nil {
		writeError(w, http.StatusPreconditionRequired, "github not linked")
		return
	}
	var body pullRequest
	if r.ContentLength > 0 {
		_ = decodeJSON(r, &body)
	}
	branch := strings.TrimSpace(body.Branch)

	lock := s.lockProject(pid)
	lock.Lock()
	defer lock.Unlock()

	repo, ok := s.openRepoOr404(w, r, pid)
	if !ok {
		return
	}
	if branch == "" {
		row, err := s.getRepoRow(r.Context(), pid)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		branch = row.DefaultBranch
	}

	ahead, behind, ffErr := s.fetchAndFastForward(r.Context(), repo, token, branch)
	if ffErr != nil {
		if errors.Is(ffErr, errNonFastForward) {
			writeJSON(w, http.StatusConflict, map[string]any{
				"error":  "non-fast-forward",
				"ahead":  ahead,
				"behind": behind,
			})
			return
		}
		writeError(w, http.StatusBadGateway, ffErr.Error())
		return
	}
	if _, err := s.Pool.Exec(r.Context(), `
        update cloud_git_repos set last_fetched_at = now() where project_id = $1
    `, pid); err != nil {
		_ = err
	}
	_ = s.refreshCommitCache(r.Context(), repo, pid)
	_ = s.refreshBranchCache(r.Context(), repo, pid)
	writeJSON(w, http.StatusOK, map[string]string{"status": "pulled"})
}

// --- GET /diff/{sha} ---

func (s *Service) handleDiff(w http.ResponseWriter, r *http.Request) {
	pid := chi.URLParam(r, "pid")
	if _, role := s.requireRole(w, r, pid); role == "" {
		return
	}
	repo, ok := s.openRepoOr404(w, r, pid)
	if !ok {
		return
	}
	sha := chi.URLParam(r, "sha")
	hash := plumbing.NewHash(sha)
	if hash.IsZero() {
		writeError(w, http.StatusBadRequest, "invalid sha")
		return
	}
	commit, err := repo.CommitObject(hash)
	if err != nil {
		writeError(w, http.StatusNotFound, "commit not found")
		return
	}
	// Diff against first parent (or empty tree for root commits).
	var parentTree *object.Tree
	if commit.NumParents() > 0 {
		parent, err := commit.Parent(0)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		parentTree, err = parent.Tree()
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
	}
	commitTree, err := commit.Tree()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	patch, err := commitDiff(parentTree, commitTree)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = io.WriteString(w, patch)
}

// commitDiff returns a unified-diff string between two trees. The empty
// tree (parent for root commits) is represented by passing nil.
func commitDiff(from, to *object.Tree) (string, error) {
	var changes object.Changes
	var err error
	if from == nil {
		// Treat as empty: emit "all of `to` was added".
		var sb strings.Builder
		err := to.Files().ForEach(func(f *object.File) error {
			sb.WriteString("--- /dev/null\n+++ b/")
			sb.WriteString(f.Name)
			sb.WriteString("\n")
			content, err := f.Contents()
			if err != nil {
				return err
			}
			for _, line := range strings.Split(content, "\n") {
				sb.WriteString("+")
				sb.WriteString(line)
				sb.WriteString("\n")
			}
			return nil
		})
		return sb.String(), err
	}
	changes, err = from.Diff(to)
	if err != nil {
		return "", err
	}
	patch, err := changes.Patch()
	if err != nil {
		return "", err
	}
	return patch.String(), nil
}

// --- DELETE /repo ---

func (s *Service) handleDeleteRepo(w http.ResponseWriter, r *http.Request) {
	pid := chi.URLParam(r, "pid")
	uid, role := s.requireRole(w, r, pid)
	if role == "" {
		return
	}
	if role != "owner" {
		writeError(w, http.StatusForbidden, "only the project owner can delete the git repo")
		return
	}
	_ = uid

	lock := s.lockProject(pid)
	lock.Lock()
	defer lock.Unlock()

	if _, err := s.Pool.Exec(r.Context(),
		`delete from cloud_git_repos where project_id = $1`, pid); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if err := s.removeBareRepo(pid); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

