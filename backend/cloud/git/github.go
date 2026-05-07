//go:build cloud
// +build cloud

package git

import (
	"context"
	"errors"
	"fmt"
	"net/url"
	"strings"

	gogit "github.com/go-git/go-git/v5"
	gitconfig "github.com/go-git/go-git/v5/config"
	"github.com/go-git/go-git/v5/plumbing"
	"github.com/go-git/go-git/v5/plumbing/object"
	httpauth "github.com/go-git/go-git/v5/plumbing/transport/http"
	"github.com/jackc/pgx/v5"
)

// githubAuth wraps a user's stored token in the BasicAuth shape that
// GitHub expects over HTTPS: username "x-access-token" + token as
// password. (TokenAuth would set a Bearer header — GitHub's smart-HTTP
// endpoint expects Basic.)
func githubAuth(token string) *httpauth.BasicAuth {
	return &httpauth.BasicAuth{Username: "x-access-token", Password: token}
}

// loadGithubToken decrypts the per-user token from cloud_github_tokens.
// Returns pgx.ErrNoRows if the user hasn't linked their GitHub account.
func (s *Service) loadGithubToken(ctx context.Context, userID string) (string, error) {
	var enc []byte
	err := s.Pool.QueryRow(ctx, `
        select access_token_encrypted from cloud_github_tokens where user_id = $1
    `, userID).Scan(&enc)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return "", pgx.ErrNoRows
		}
		return "", err
	}
	return decryptToken(s.Cfg.JWTSecret, enc)
}

// saveGithubToken upserts the encrypted token + GitHub user metadata.
func (s *Service) saveGithubToken(
	ctx context.Context,
	userID, token, scope string,
	githubUserID int64,
	githubLogin string,
) error {
	enc, err := encryptToken(s.Cfg.JWTSecret, token)
	if err != nil {
		return err
	}
	_, err = s.Pool.Exec(ctx, `
        insert into cloud_github_tokens
            (user_id, access_token_encrypted, scope, github_user_id, github_login, updated_at)
        values ($1, $2, $3, $4, $5, now())
        on conflict (user_id) do update set
            access_token_encrypted = excluded.access_token_encrypted,
            scope = excluded.scope,
            github_user_id = excluded.github_user_id,
            github_login = excluded.github_login,
            updated_at = now()
    `, userID, enc, scope, githubUserID, githubLogin)
	return err
}

// deleteGithubToken removes the user's stored token (used by /auth/github DELETE).
func (s *Service) deleteGithubToken(ctx context.Context, userID string) error {
	_, err := s.Pool.Exec(ctx, `delete from cloud_github_tokens where user_id = $1`, userID)
	return err
}

// cloneFromGitHub creates a fresh bare repo for the project by cloning
// `repoURL` directly into the project's S3 prefix. If `token` is
// non-empty, it's used as auth (private repo case). If empty, anonymous
// clone is attempted (public repos).
//
// Caller must hold the project lock and have already verified that the
// project doesn't already have a bare repo. cloneInto handles the
// best-effort cleanup of partial clones (a few orphan objects can land
// in S3 if the network drops mid-fetch).
func (s *Service) cloneFromGitHub(
	ctx context.Context,
	projectID, repoURL, token, branch string,
) (*gogit.Repository, error) {
	opts := &gogit.CloneOptions{
		URL:    repoURL,
		Mirror: false,
	}
	if branch != "" {
		opts.ReferenceName = plumbing.NewBranchReferenceName(branch)
		opts.SingleBranch = true
	}
	if token != "" {
		opts.Auth = githubAuth(token)
	}
	repo, err := s.cloneInto(ctx, projectID, opts)
	if err != nil {
		return nil, fmt.Errorf("clone %s: %w", repoURL, err)
	}
	return repo, nil
}

// pushAllBranches pushes every local branch up to GitHub. Force-push is
// off by default; users who diverge are expected to pull first.
func (s *Service) pushAllBranches(
	ctx context.Context,
	repo *gogit.Repository,
	token string,
) error {
	if token == "" {
		return errors.New("github not linked: cannot push")
	}
	if _, err := repo.Remote("origin"); err != nil {
		return errors.New("no origin remote configured (call /connect or /import first)")
	}
	err := repo.PushContext(ctx, &gogit.PushOptions{
		RemoteName: "origin",
		Auth:       githubAuth(token),
		RefSpecs: []gitconfig.RefSpec{
			gitconfig.RefSpec("refs/heads/*:refs/heads/*"),
		},
	})
	if err != nil && !errors.Is(err, gogit.NoErrAlreadyUpToDate) {
		return fmt.Errorf("push: %w", err)
	}
	return nil
}

// fetchAndFastForward fetches origin and tries to fast-forward the
// named local branch to its remote tracking ref. Returns (ahead, behind)
// counts when a non-FF is detected so the handler can return 409.
//
// Bare repo: there's no working tree to merge into; we manipulate refs
// directly via the storer.
func (s *Service) fetchAndFastForward(
	ctx context.Context,
	repo *gogit.Repository,
	token, branch string,
) (ahead, behind int, ffErr error) {
	if token == "" {
		return 0, 0, errors.New("github not linked: cannot pull")
	}
	if _, err := repo.Remote("origin"); err != nil {
		return 0, 0, errors.New("no origin remote configured")
	}
	err := repo.FetchContext(ctx, &gogit.FetchOptions{
		RemoteName: "origin",
		Auth:       githubAuth(token),
		RefSpecs: []gitconfig.RefSpec{
			gitconfig.RefSpec("+refs/heads/*:refs/remotes/origin/*"),
		},
	})
	if err != nil && !errors.Is(err, gogit.NoErrAlreadyUpToDate) {
		return 0, 0, fmt.Errorf("fetch: %w", err)
	}

	// Find local + remote ref for the branch.
	localRefName := plumbing.NewBranchReferenceName(branch)
	remoteRefName := plumbing.NewRemoteReferenceName("origin", branch)

	remoteRef, err := repo.Reference(remoteRefName, true)
	if err != nil {
		return 0, 0, fmt.Errorf("remote ref %s not found: %w", branch, err)
	}
	localRef, err := repo.Reference(localRefName, true)
	if err != nil {
		// No local branch yet — create it pointing at the remote.
		newRef := plumbing.NewHashReference(localRefName, remoteRef.Hash())
		if err := repo.Storer.SetReference(newRef); err != nil {
			return 0, 0, fmt.Errorf("create local branch %s: %w", branch, err)
		}
		return 0, 0, nil
	}

	if localRef.Hash() == remoteRef.Hash() {
		return 0, 0, nil
	}

	// Compute ahead/behind via ancestry.
	localCommit, err := repo.CommitObject(localRef.Hash())
	if err != nil {
		return 0, 0, err
	}
	remoteCommit, err := repo.CommitObject(remoteRef.Hash())
	if err != nil {
		return 0, 0, err
	}
	localIsAncestor, err := localCommit.IsAncestor(remoteCommit)
	if err != nil {
		return 0, 0, err
	}
	if localIsAncestor {
		// Fast-forward.
		newRef := plumbing.NewHashReference(localRefName, remoteRef.Hash())
		if err := repo.Storer.SetReference(newRef); err != nil {
			return 0, 0, fmt.Errorf("ff local %s: %w", branch, err)
		}
		return 0, 0, nil
	}
	// Diverged — count commits each direction (via merge-base).
	bases, err := localCommit.MergeBase(remoteCommit)
	if err != nil {
		return 0, 0, err
	}
	if len(bases) == 0 {
		// Unrelated histories.
		return -1, -1, errors.New("local and remote have no common ancestor")
	}
	base := bases[0]
	ahead = countCommitsBetween(repo, base.Hash, localRef.Hash())
	behind = countCommitsBetween(repo, base.Hash, remoteRef.Hash())
	return ahead, behind, errNonFastForward
}

// countCommitsBetween walks from `tip` until it hits `base`, returning
// the number of commits exclusive of base. Used only for the ahead/
// behind summary; failures are swallowed and return 0.
func countCommitsBetween(repo *gogit.Repository, base, tip plumbing.Hash) int {
	if base == tip {
		return 0
	}
	iter, err := repo.Log(&gogit.LogOptions{From: tip})
	if err != nil {
		return 0
	}
	defer iter.Close()
	count := 0
	_ = iter.ForEach(func(c *object.Commit) error {
		if c.Hash == base {
			return errStopIter
		}
		count++
		return nil
	})
	return count
}

// errNonFastForward signals that the local branch can't be fast-forwarded.
var errNonFastForward = errors.New("non-fast-forward")

// connectGitHub attaches an existing project's bare repo to a GitHub
// remote, then pushes all branches. Stores the github_owner/repo on
// cloud_git_repos so future /push/pull know where to go.
//
// `repoURL` should be the full HTTPS URL (https://github.com/owner/repo.git).
func (s *Service) connectGitHub(
	ctx context.Context,
	repo *gogit.Repository,
	projectID, owner, repoName, token string,
) error {
	if owner == "" || repoName == "" {
		return errors.New("github_owner and github_repo are required")
	}
	repoURL := fmt.Sprintf("https://github.com/%s/%s.git", owner, repoName)

	// Add or replace `origin`.
	if existing, err := repo.Remote("origin"); err == nil {
		// Replace if URL differs.
		urls := existing.Config().URLs
		if len(urls) == 0 || urls[0] != repoURL {
			if err := repo.DeleteRemote("origin"); err != nil {
				return fmt.Errorf("delete origin: %w", err)
			}
		}
	}
	if _, err := repo.Remote("origin"); err != nil {
		if _, err := repo.CreateRemote(&gitconfig.RemoteConfig{
			Name: "origin",
			URLs: []string{repoURL},
		}); err != nil {
			return fmt.Errorf("create origin: %w", err)
		}
	}

	// Stamp the cloud_git_repos row with the GitHub coordinates.
	if _, err := s.Pool.Exec(ctx, `
        update cloud_git_repos
        set github_owner = $2,
            github_repo = $3,
            github_remote_url = $4
        where project_id = $1
    `, projectID, owner, repoName, repoURL); err != nil {
		return fmt.Errorf("update repo row: %w", err)
	}

	// Push all branches up.
	if err := s.pushAllBranches(ctx, repo, token); err != nil {
		return fmt.Errorf("push: %w", err)
	}
	if _, err := s.Pool.Exec(ctx, `
        update cloud_git_repos set last_pushed_at = now() where project_id = $1
    `, projectID); err != nil {
		return err
	}
	return nil
}

// parseGitHubURL turns a GitHub URL of any common form into (owner, repo).
// Accepts:
//
//	https://github.com/owner/repo
//	https://github.com/owner/repo.git
//	git@github.com:owner/repo.git
//
// Returns an error for anything else; we don't try to be clever.
func parseGitHubURL(raw string) (owner, repo string, err error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return "", "", errors.New("empty url")
	}
	// SSH form.
	if strings.HasPrefix(raw, "git@github.com:") {
		path := strings.TrimPrefix(raw, "git@github.com:")
		path = strings.TrimSuffix(path, ".git")
		parts := strings.SplitN(path, "/", 2)
		if len(parts) != 2 {
			return "", "", fmt.Errorf("malformed ssh url %q", raw)
		}
		return parts[0], parts[1], nil
	}
	u, err := url.Parse(raw)
	if err != nil {
		return "", "", fmt.Errorf("parse url: %w", err)
	}
	if u.Host != "github.com" {
		return "", "", fmt.Errorf("not a github.com url: %s", u.Host)
	}
	path := strings.TrimPrefix(u.Path, "/")
	path = strings.TrimSuffix(path, ".git")
	parts := strings.SplitN(path, "/", 2)
	if len(parts) != 2 {
		return "", "", fmt.Errorf("expected /owner/repo path: %s", u.Path)
	}
	return parts[0], parts[1], nil
}
