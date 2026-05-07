//go:build cloud
// +build cloud

package git

import (
	"context"
	"errors"
	"fmt"
	"sort"

	gogit "github.com/go-git/go-git/v5"
	"github.com/go-git/go-git/v5/plumbing"
	"github.com/go-git/go-git/v5/plumbing/filemode"
	"github.com/go-git/go-git/v5/plumbing/object"
)

// mergeResult describes the outcome of mergeBranch. Either Conflicts is
// non-empty (no commit was made; nothing on disk changed) or NewCommit
// is set (the merge commit was written and the target branch's ref was
// updated). FastForward indicates a no-op merge that just moved the
// branch ref.
type mergeResult struct {
	NewCommit   plumbing.Hash
	FastForward bool
	Conflicts   []string
}

// mergeBranch performs a three-way merge of `from` into `into`, using
// the merge-base as the common ancestor.
//
// Behavior:
//   - If `into` is an ancestor of `from`, fast-forward `into` to `from`.
//   - If `from` is an ancestor of `into`, no-op.
//   - Otherwise, do a path-level three-way diff. For paths where one
//     side equals the base, take the other side. For paths where both
//     sides changed differently, record a conflict and abort. Successful
//     merges produce a real merge commit with two parents.
//
// v1 semantics: no in-app conflict resolution. Conflicts come back as a
// path list and the user is expected to pull down, fix locally, push
// back up. This matches the spec.
//
// Caller must hold the project lock.
func (s *Service) mergeBranch(
	ctx context.Context,
	repo *gogit.Repository,
	projectID, fromBranch, intoBranch string,
	sig object.Signature,
) (*mergeResult, error) {
	if fromBranch == intoBranch {
		return nil, errors.New("cannot merge branch into itself")
	}

	fromHead, err := s.branchHead(repo, fromBranch)
	if err != nil {
		return nil, fmt.Errorf("from branch %q: %w", fromBranch, err)
	}
	intoHead, err := s.branchHead(repo, intoBranch)
	if err != nil {
		return nil, fmt.Errorf("into branch %q: %w", intoBranch, err)
	}

	fromCommit, err := repo.CommitObject(fromHead)
	if err != nil {
		return nil, err
	}
	intoCommit, err := repo.CommitObject(intoHead)
	if err != nil {
		return nil, err
	}

	// Already up to date: from is an ancestor of into.
	isAncestor, err := fromCommit.IsAncestor(intoCommit)
	if err != nil {
		return nil, fmt.Errorf("ancestor check: %w", err)
	}
	if isAncestor {
		return &mergeResult{NewCommit: intoHead, FastForward: false}, nil
	}

	// Fast-forward: into is an ancestor of from.
	isAncestor, err = intoCommit.IsAncestor(fromCommit)
	if err != nil {
		return nil, fmt.Errorf("ancestor check: %w", err)
	}
	if isAncestor {
		newRef := plumbing.NewHashReference(plumbing.NewBranchReferenceName(intoBranch), fromHead)
		if err := repo.Storer.SetReference(newRef); err != nil {
			return nil, fmt.Errorf("ff ref update: %w", err)
		}
		return &mergeResult{NewCommit: fromHead, FastForward: true}, nil
	}

	// Three-way merge. Compute the merge base.
	bases, err := fromCommit.MergeBase(intoCommit)
	if err != nil {
		return nil, fmt.Errorf("merge base: %w", err)
	}
	if len(bases) == 0 {
		return nil, errors.New("no common ancestor between branches")
	}
	base := bases[0]

	baseTree, err := base.Tree()
	if err != nil {
		return nil, fmt.Errorf("base tree: %w", err)
	}
	intoTree, err := intoCommit.Tree()
	if err != nil {
		return nil, fmt.Errorf("into tree: %w", err)
	}
	fromTree, err := fromCommit.Tree()
	if err != nil {
		return nil, fmt.Errorf("from tree: %w", err)
	}

	merged, conflicts, err := mergeTrees(repo, baseTree, intoTree, fromTree)
	if err != nil {
		return nil, fmt.Errorf("merge trees: %w", err)
	}
	if len(conflicts) > 0 {
		sort.Strings(conflicts)
		return &mergeResult{Conflicts: conflicts}, nil
	}

	// Build the merge commit.
	msg := fmt.Sprintf("Merge branch '%s' into '%s'", fromBranch, intoBranch)
	commit, err := writeCommit(repo, merged, []plumbing.Hash{intoHead, fromHead}, sig, msg)
	if err != nil {
		return nil, err
	}
	newRef := plumbing.NewHashReference(plumbing.NewBranchReferenceName(intoBranch), commit)
	if err := repo.Storer.SetReference(newRef); err != nil {
		return nil, fmt.Errorf("set branch ref: %w", err)
	}
	return &mergeResult{NewCommit: commit}, nil
}

// flatEntry is one leaf of a flattened tree: full forward-slash path,
// blob hash, and mode. Folders themselves aren't carried — they're
// reconstructed from the leaf paths.
type flatEntry struct {
	hash plumbing.Hash
	mode filemode.FileMode
}

// flattenTree walks `t` and returns a path → flatEntry map of all the
// blobs reachable from it.
func flattenTree(repo *gogit.Repository, t *object.Tree) (map[string]flatEntry, error) {
	out := map[string]flatEntry{}
	var walk func(t *object.Tree, prefix string) error
	walk = func(t *object.Tree, prefix string) error {
		for _, e := range t.Entries {
			path := e.Name
			if prefix != "" {
				path = prefix + "/" + e.Name
			}
			if e.Mode == filemode.Dir {
				sub, err := repo.TreeObject(e.Hash)
				if err != nil {
					return err
				}
				if err := walk(sub, path); err != nil {
					return err
				}
				continue
			}
			out[path] = flatEntry{hash: e.Hash, mode: e.Mode}
		}
		return nil
	}
	if err := walk(t, ""); err != nil {
		return nil, err
	}
	return out, nil
}

// mergeTrees does the path-level three-way merge of base/into/from.
// Returns the resulting tree hash and the list of conflict paths.
//
// Conflict rule (per path):
//   - If into[p] == from[p] → keep that.
//   - If into[p] == base[p] → take from[p] (incl. additions/deletions).
//   - If from[p] == base[p] → take into[p].
//   - Else → conflict at p.
func mergeTrees(
	repo *gogit.Repository,
	baseT, intoT, fromT *object.Tree,
) (plumbing.Hash, []string, error) {
	base, err := flattenTree(repo, baseT)
	if err != nil {
		return plumbing.ZeroHash, nil, err
	}
	into, err := flattenTree(repo, intoT)
	if err != nil {
		return plumbing.ZeroHash, nil, err
	}
	from, err := flattenTree(repo, fromT)
	if err != nil {
		return plumbing.ZeroHash, nil, err
	}

	// Union of all paths across the three trees.
	union := map[string]struct{}{}
	for p := range base {
		union[p] = struct{}{}
	}
	for p := range into {
		union[p] = struct{}{}
	}
	for p := range from {
		union[p] = struct{}{}
	}

	merged := map[string]flatEntry{}
	var conflicts []string
	for p := range union {
		b, hasB := base[p]
		i, hasI := into[p]
		f, hasF := from[p]

		eq := func(a, b flatEntry, ok1, ok2 bool) bool {
			if ok1 != ok2 {
				return false
			}
			if !ok1 {
				return true
			}
			return a.hash == b.hash && a.mode == b.mode
		}

		switch {
		case eq(i, f, hasI, hasF):
			if hasI {
				merged[p] = i
			}
		case eq(i, b, hasI, hasB):
			// Into didn't touch it; take from.
			if hasF {
				merged[p] = f
			}
		case eq(f, b, hasF, hasB):
			// From didn't touch it; take into.
			if hasI {
				merged[p] = i
			}
		default:
			conflicts = append(conflicts, p)
		}
	}

	if len(conflicts) > 0 {
		return plumbing.ZeroHash, conflicts, nil
	}

	// Reconstruct the tree from the flat path map.
	root := newTreeNode("")
	for path, entry := range merged {
		segs := splitPath(path)
		cur := root
		for i, seg := range segs {
			if i == len(segs)-1 {
				leaf := newTreeNode(seg)
				leaf.isBlob = true
				leaf.mode = entry.mode
				leaf.hash = entry.hash
				cur.children[seg] = leaf
				continue
			}
			child, ok := cur.children[seg]
			if !ok {
				child = newTreeNode(seg)
				cur.children[seg] = child
			}
			cur = child
		}
	}
	// writeTree (free function) handles deterministic encoding.
	hash, err := writeTree(repo, root)
	if err != nil {
		return plumbing.ZeroHash, nil, err
	}
	return hash, nil, nil
}

// splitPath splits a forward-slash path into its segments. "" yields
// nil (which the caller treats as "the root tree itself" — we never
// reach that branch in practice because the leaves are always blobs).
func splitPath(p string) []string {
	if p == "" {
		return nil
	}
	var out []string
	start := 0
	for i := 0; i < len(p); i++ {
		if p[i] == '/' {
			out = append(out, p[start:i])
			start = i + 1
		}
	}
	out = append(out, p[start:])
	return out
}
