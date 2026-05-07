//go:build cloud
// +build cloud

package git

import (
	"context"
	"fmt"
	"strings"

	gogit "github.com/go-git/go-git/v5"
	"github.com/go-git/go-git/v5/plumbing"
)

// branchView is the JSON shape returned by /branches.
type branchView struct {
	Name      string `json:"name"`
	HeadSHA   string `json:"head_sha"`
	IsDefault bool   `json:"is_default"`
}

// listBranches walks refs/heads/* and returns the current set. The
// default branch flag is read from cloud_git_repos.default_branch so
// the caller doesn't have to look it up separately.
func (s *Service) listBranches(
	ctx context.Context,
	repo *gogit.Repository,
	projectID string,
) ([]branchView, error) {
	row, err := s.getRepoRow(ctx, projectID)
	if err != nil {
		return nil, fmt.Errorf("repo row: %w", err)
	}

	iter, err := repo.Branches()
	if err != nil {
		return nil, fmt.Errorf("branches: %w", err)
	}
	defer iter.Close()

	var out []branchView
	if err := iter.ForEach(func(ref *plumbing.Reference) error {
		name := ref.Name().Short()
		out = append(out, branchView{
			Name:      name,
			HeadSHA:   ref.Hash().String(),
			IsDefault: name == row.DefaultBranch,
		})
		return nil
	}); err != nil {
		return nil, err
	}
	return out, nil
}

// createBranch points a new branch ref at fromSHA (or the current HEAD
// if fromSHA is empty). Refuses to create a duplicate.
//
// Note: in a bare repo, "current HEAD" means the symbolic ref's target
// branch tip, not a working-tree HEAD.
func (s *Service) createBranch(
	ctx context.Context,
	repo *gogit.Repository,
	name, fromSHA string,
) error {
	if !validBranchName(name) {
		return fmt.Errorf("invalid branch name %q", name)
	}
	refName := plumbing.NewBranchReferenceName(name)
	if _, err := repo.Reference(refName, false); err == nil {
		return fmt.Errorf("branch %q already exists", name)
	}

	var hash plumbing.Hash
	if fromSHA != "" {
		hash = plumbing.NewHash(fromSHA)
		if hash.IsZero() {
			return fmt.Errorf("invalid sha %q", fromSHA)
		}
		// Validate the SHA exists in the repo.
		if _, err := repo.CommitObject(hash); err != nil {
			return fmt.Errorf("from_sha %s not found: %w", fromSHA, err)
		}
	} else {
		head, err := repo.Head()
		if err != nil {
			return fmt.Errorf("no HEAD; specify from_sha: %w", err)
		}
		hash = head.Hash()
	}

	if err := repo.Storer.SetReference(plumbing.NewHashReference(refName, hash)); err != nil {
		return fmt.Errorf("set branch ref: %w", err)
	}
	return nil
}

// switchHEAD moves the symbolic HEAD ref to point at the named branch.
// Used by /checkout — we don't have a working tree, but tools like
// `git log` and `Repository.Head()` follow this for "current" semantics.
func (s *Service) switchHEAD(repo *gogit.Repository, branch string) error {
	refName := plumbing.NewBranchReferenceName(branch)
	if _, err := repo.Reference(refName, false); err != nil {
		return fmt.Errorf("branch %q not found", branch)
	}
	return repo.Storer.SetReference(plumbing.NewSymbolicReference(plumbing.HEAD, refName))
}

// branchHead returns the head SHA of the named branch.
func (s *Service) branchHead(repo *gogit.Repository, branch string) (plumbing.Hash, error) {
	ref, err := repo.Reference(plumbing.NewBranchReferenceName(branch), true)
	if err != nil {
		return plumbing.ZeroHash, err
	}
	return ref.Hash(), nil
}

// validBranchName is a defensive check on the user-supplied branch
// name. Mirrors the basic git ref name rules — lowercase ASCII letters,
// digits, and a few separators. Avoids `..`, leading/trailing slash,
// control chars, and anything that would confuse the storer's ref
// resolver.
func validBranchName(s string) bool {
	if s == "" || len(s) > 200 {
		return false
	}
	if strings.HasPrefix(s, "/") || strings.HasSuffix(s, "/") {
		return false
	}
	if strings.Contains(s, "..") || strings.Contains(s, "//") {
		return false
	}
	for _, r := range s {
		switch {
		case r >= 'a' && r <= 'z':
		case r >= 'A' && r <= 'Z':
		case r >= '0' && r <= '9':
		case r == '/' || r == '-' || r == '_' || r == '.':
		default:
			return false
		}
	}
	return true
}

// refreshBranchCache rewrites cloud_git_branches for the project from
// the current ref state. Best-effort.
func (s *Service) refreshBranchCache(
	ctx context.Context,
	repo *gogit.Repository,
	projectID string,
) error {
	row, err := s.getRepoRow(ctx, projectID)
	if err != nil {
		return err
	}
	iter, err := repo.Branches()
	if err != nil {
		return err
	}
	defer iter.Close()

	tx, err := s.Pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	if _, err := tx.Exec(ctx,
		`delete from cloud_git_branches where project_id = $1`, projectID); err != nil {
		return err
	}

	if err := iter.ForEach(func(ref *plumbing.Reference) error {
		name := ref.Name().Short()
		_, err := tx.Exec(ctx, `
            insert into cloud_git_branches(project_id, name, head_sha, is_default)
            values ($1, $2, $3, $4)
        `, projectID, name, ref.Hash().String(), name == row.DefaultBranch)
		return err
	}); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

