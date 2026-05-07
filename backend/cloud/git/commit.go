//go:build cloud
// +build cloud

package git

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	gogit "github.com/go-git/go-git/v5"
	"github.com/go-git/go-git/v5/plumbing"
	"github.com/go-git/go-git/v5/plumbing/object"
	"github.com/jackc/pgx/v5"
)

// commitView is the JSON shape returned by /log endpoints.
type commitView struct {
	SHA         string    `json:"sha"`
	ParentSHAs  []string  `json:"parent_shas"`
	Message     string    `json:"message"`
	AuthorName  string    `json:"author_name"`
	AuthorEmail string    `json:"author_email"`
	CommittedAt time.Time `json:"committed_at"`
}

// makeCommit snapshots the project's current files into a tree, creates
// a commit object pointing at that tree (with the supplied parents and
// signature), and updates the branch ref to point at the new commit.
//
// Caller must hold the project lock.
func (s *Service) makeCommit(
	ctx context.Context,
	repo *gogit.Repository,
	projectID, branch, message string,
	sig object.Signature,
) (plumbing.Hash, error) {
	if branch == "" {
		return plumbing.ZeroHash, errors.New("makeCommit: empty branch")
	}
	if strings.TrimSpace(message) == "" {
		return plumbing.ZeroHash, errors.New("makeCommit: empty message")
	}

	tree, err := s.snapshotProjectIntoTree(ctx, repo, projectID)
	if err != nil {
		return plumbing.ZeroHash, fmt.Errorf("snapshot: %w", err)
	}

	// Resolve current branch tip (for parent linkage). If the branch
	// doesn't exist yet, this is the root commit on a new branch.
	branchRef := plumbing.NewBranchReferenceName(branch)
	var parents []plumbing.Hash
	if ref, err := repo.Reference(branchRef, true); err == nil {
		parents = []plumbing.Hash{ref.Hash()}
	}

	commit, err := writeCommit(repo, tree, parents, sig, message)
	if err != nil {
		return plumbing.ZeroHash, err
	}

	// Move (or create) the branch ref to the new commit.
	newRef := plumbing.NewHashReference(branchRef, commit)
	if err := repo.Storer.SetReference(newRef); err != nil {
		return plumbing.ZeroHash, fmt.Errorf("set branch ref: %w", err)
	}

	// First commit on a brand-new repo also seeds HEAD → branch.
	if _, err := repo.Reference(plumbing.HEAD, true); err != nil {
		_ = repo.Storer.SetReference(plumbing.NewSymbolicReference(plumbing.HEAD, branchRef))
	}

	return commit, nil
}

// listCommits returns up to `limit` commits walking back from the
// branch tip (or all branches if branch == ""). The DB cache is the
// fast path; we fall back to walking the bare repo when the cache is
// stale or empty (e.g. just after /import).
func (s *Service) listCommits(
	ctx context.Context,
	repo *gogit.Repository,
	projectID, branch string,
	limit int,
) ([]commitView, error) {
	if limit <= 0 || limit > 500 {
		limit = 50
	}

	// Walk the repo directly — keeps log output consistent with the
	// authoritative state even if the cache hasn't been refreshed.
	logOpts := &gogit.LogOptions{}
	if branch != "" {
		ref, err := repo.Reference(plumbing.NewBranchReferenceName(branch), true)
		if err != nil {
			return nil, fmt.Errorf("branch %q not found: %w", branch, err)
		}
		h := ref.Hash()
		logOpts.From = h
	}
	iter, err := repo.Log(logOpts)
	if err != nil {
		return nil, fmt.Errorf("log: %w", err)
	}
	defer iter.Close()

	out := make([]commitView, 0, limit)
	count := 0
	if err := iter.ForEach(func(c *object.Commit) error {
		if count >= limit {
			return errStopIter
		}
		count++
		parents := make([]string, 0, len(c.ParentHashes))
		for _, p := range c.ParentHashes {
			parents = append(parents, p.String())
		}
		out = append(out, commitView{
			SHA:         c.Hash.String(),
			ParentSHAs:  parents,
			Message:     strings.TrimRight(c.Message, "\n"),
			AuthorName:  c.Author.Name,
			AuthorEmail: c.Author.Email,
			CommittedAt: c.Committer.When,
		})
		return nil
	}); err != nil && !errors.Is(err, errStopIter) {
		return nil, err
	}
	return out, nil
}

// errStopIter signals "we've collected enough" inside an iter.ForEach.
var errStopIter = errors.New("stop")

// refreshCommitCache writes the commit graph into cloud_git_commits.
// Best-effort: failures are logged at the call site, never propagated
// to the user — the bare repo is canonical.
func (s *Service) refreshCommitCache(
	ctx context.Context,
	repo *gogit.Repository,
	projectID string,
) error {
	iter, err := repo.Log(&gogit.LogOptions{All: true})
	if err != nil {
		return fmt.Errorf("log all: %w", err)
	}
	defer iter.Close()

	tx, err := s.Pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	// Hard reset cache for this project then re-insert. Simpler than a
	// merge — the cache is small and only refreshed on mutating ops.
	if _, err := tx.Exec(ctx,
		`delete from cloud_git_commits where project_id = $1`, projectID); err != nil {
		return err
	}

	if err := iter.ForEach(func(c *object.Commit) error {
		parents := make([]string, 0, len(c.ParentHashes))
		for _, p := range c.ParentHashes {
			parents = append(parents, p.String())
		}
		_, err := tx.Exec(ctx, `
            insert into cloud_git_commits
                (project_id, sha, parent_shas, message, author_name, author_email, committed_at)
            values ($1, $2, $3, $4, $5, $6, $7)
            on conflict (project_id, sha) do nothing
        `,
			projectID, c.Hash.String(), parents,
			strings.TrimRight(c.Message, "\n"),
			c.Author.Name, c.Author.Email, c.Committer.When,
		)
		return err
	}); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

// loadCommitFromCache pulls a single row out of cloud_git_commits.
// Returns pgx.ErrNoRows if the sha isn't cached. Used by /diff/:sha
// where the cache miss falls back to the bare repo.
func (s *Service) loadCommitFromCache(
	ctx context.Context,
	projectID, sha string,
) (*commitView, error) {
	var v commitView
	err := s.Pool.QueryRow(ctx, `
        select sha, parent_shas, message, author_name, author_email, committed_at
        from cloud_git_commits
        where project_id = $1 and sha = $2
    `, projectID, sha).Scan(
		&v.SHA, &v.ParentSHAs, &v.Message, &v.AuthorName, &v.AuthorEmail, &v.CommittedAt,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, pgx.ErrNoRows
		}
		return nil, err
	}
	return &v, nil
}
