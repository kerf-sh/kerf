//go:build cloud
// +build cloud

package git

import (
	"context"
	"errors"
	"fmt"
	"os"

	gogit "github.com/go-git/go-git/v5"
	"github.com/go-git/go-git/v5/plumbing/cache"
	"github.com/go-git/go-git/v5/storage/filesystem"
	"github.com/jackc/pgx/v5"
)

// projectKeyPrefix returns the absolute S3 key prefix (no trailing
// slash) under which a project's bare repo lives. Example:
// "git/abc-1234".
func (s *Service) projectKeyPrefix(projectID string) string {
	return s.prefix + "/" + projectID
}

// bareFS builds a billy.Filesystem rooted at the project's S3 prefix
// and the matching go-git filesystem.Storage. The pair is built fresh
// per call — both are cheap (no IO at construction time) and not safe
// to share across concurrent goroutines (go-git's storer caches state).
//
// The returned *s3FS is the same instance as the storer's underlying
// fs; it's exposed separately so callers can do prefix-level S3 ops
// (deleteByPrefix, listAnyKey) without going through the storer.
func (s *Service) bareFS(projectID string) (*s3FS, *filesystem.Storage) {
	root := s.projectKeyPrefix(projectID)
	fs := newS3FS(s.s3, s.bucket, root)
	storer := filesystem.NewStorage(fs, cache.NewObjectLRUDefault())
	return fs, storer
}

// openRepo opens an existing bare repo for the project. Returns
// os.ErrNotExist if no objects exist under the project prefix. The
// existence check is one ListObjectsV2 with MaxKeys=1, so the cost is
// O(1) and bounded.
func (s *Service) openRepo(projectID string) (*gogit.Repository, error) {
	base, storer := s.bareFS(projectID)
	exists, err := base.listAnyKey(context.Background(), base.root)
	if err != nil {
		return nil, fmt.Errorf("openRepo: probe %s: %w", base.root, err)
	}
	if !exists {
		return nil, os.ErrNotExist
	}
	repo, err := gogit.Open(storer, nil)
	if err != nil {
		return nil, fmt.Errorf("openRepo: %w", err)
	}
	return repo, nil
}

// initBareRepo creates a fresh bare repo at the project's prefix.
// Refuses to clobber an existing repo. The "init" itself is just a
// few small object PUTs (HEAD, config, refs/) — go-git's
// `storage/filesystem` writes them all through our billyfs layer.
func (s *Service) initBareRepo(projectID string) (*gogit.Repository, error) {
	base, storer := s.bareFS(projectID)
	exists, err := base.listAnyKey(context.Background(), base.root)
	if err != nil {
		return nil, fmt.Errorf("initBareRepo: probe %s: %w", base.root, err)
	}
	if exists {
		return nil, fmt.Errorf("bare repo already exists under %s", base.root)
	}
	repo, err := gogit.Init(storer, nil)
	if err != nil {
		return nil, fmt.Errorf("init bare %s: %w", base.root, err)
	}
	return repo, nil
}

// removeBareRepo wipes every object under the project's prefix. This
// is the equivalent of `rm -rf <bare-repo>` on disk: idempotent on a
// missing prefix, returns an error if any individual delete fails.
//
// Cost: one ListObjectsV2 per page (1000 keys/page) + one DeleteObject
// per key. For a typical small Kerf project that's ~50 objects = 1
// list + 50 deletes ≈ 51 round trips. We could batch with
// DeleteObjects but project deletion is rare and not latency-critical.
func (s *Service) removeBareRepo(projectID string) error {
	base, _ := s.bareFS(projectID)
	return base.deleteByPrefix(context.Background(), base.root)
}

// repoExists is a cheap "is there anything under this project's prefix?"
// check. Used by handlers that distinguish "git not enabled" from
// "DB row present, S3 prefix gone (corruption)".
func (s *Service) repoExists(projectID string) bool {
	base, _ := s.bareFS(projectID)
	exists, err := base.listAnyKey(context.Background(), base.root)
	if err != nil {
		return false
	}
	return exists
}

// cloneInto runs `git clone` against an external URL and writes every
// resulting object straight into the project's S3 prefix. Replaces the
// old PlainCloneContext path (which wanted a disk dir).
func (s *Service) cloneInto(
	ctx context.Context,
	projectID string,
	opts *gogit.CloneOptions,
) (*gogit.Repository, error) {
	base, storer := s.bareFS(projectID)
	repo, err := gogit.CloneContext(ctx, storer, nil, opts)
	if err != nil {
		// Best-effort cleanup — partial clones can leave a few
		// objects behind that would confuse a retry.
		_ = base.deleteByPrefix(ctx, base.root)
		return nil, err
	}
	return repo, nil
}

// repoRow is the cached metadata row from cloud_git_repos.
type repoRow struct {
	ProjectID       string
	DefaultBranch   string
	GithubOwner     *string
	GithubRepo      *string
	GithubRemoteURL *string
}

// getRepoRow fetches the cloud_git_repos row for a project, or returns
// pgx.ErrNoRows if git isn't enabled.
func (s *Service) getRepoRow(ctx context.Context, projectID string) (*repoRow, error) {
	var r repoRow
	err := s.Pool.QueryRow(ctx, `
        select project_id, default_branch, github_owner, github_repo, github_remote_url
        from cloud_git_repos
        where project_id = $1
    `, projectID).Scan(&r.ProjectID, &r.DefaultBranch, &r.GithubOwner, &r.GithubRepo, &r.GithubRemoteURL)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, pgx.ErrNoRows
		}
		return nil, err
	}
	return &r, nil
}

// upsertRepoRow ensures a cloud_git_repos row exists for the project.
// `defaultBranch` is the branch name to set on first insert; subsequent
// calls leave it as-is.
func (s *Service) upsertRepoRow(ctx context.Context, projectID, defaultBranch string) error {
	_, err := s.Pool.Exec(ctx, `
        insert into cloud_git_repos(project_id, default_branch)
        values ($1, $2)
        on conflict (project_id) do nothing
    `, projectID, defaultBranch)
	return err
}

