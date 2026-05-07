//go:build cloud
// +build cloud

package git

import (
	"context"
	"fmt"
	"io"
	"sort"
	"strings"
	"time"

	gogit "github.com/go-git/go-git/v5"
	"github.com/go-git/go-git/v5/plumbing"
	"github.com/go-git/go-git/v5/plumbing/filemode"
	"github.com/go-git/go-git/v5/plumbing/object"
)

// dbFile is a flattened row from the project's `files` table used while
// building or applying a tree snapshot. Only the fields the snapshotter
// touches are kept.
type dbFile struct {
	ID         string
	ParentID   *string
	Name       string
	Kind       string
	Content    string
	StorageKey *string
}

// loadProjectFiles reads every non-deleted file row for a project. The
// caller is expected to be holding the project lock so the read is
// consistent with whatever mutating op is in flight.
func (s *Service) loadProjectFiles(ctx context.Context, projectID string) ([]dbFile, error) {
	rows, err := s.Pool.Query(ctx, `
        select id, parent_id, name, kind, content, storage_key
        from files
        where project_id = $1 and deleted_at is null
        order by parent_id nulls first, kind desc, name asc
    `, projectID)
	if err != nil {
		return nil, fmt.Errorf("load project files: %w", err)
	}
	defer rows.Close()
	var out []dbFile
	for rows.Next() {
		var f dbFile
		if err := rows.Scan(&f.ID, &f.ParentID, &f.Name, &f.Kind, &f.Content, &f.StorageKey); err != nil {
			return nil, fmt.Errorf("scan: %w", err)
		}
		out = append(out, f)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

// treeNode is the in-memory shape used to assemble the tree bottom-up.
// Children are keyed by name to detect collisions deterministically.
type treeNode struct {
	name     string
	mode     filemode.FileMode
	hash     plumbing.Hash // populated during build, not before
	isBlob   bool
	children map[string]*treeNode
	// blobBytes is the file's content for blobs. For tree nodes, nil.
	blobBytes []byte
}

func newTreeNode(name string) *treeNode {
	return &treeNode{
		name:     name,
		mode:     filemode.Dir,
		children: map[string]*treeNode{},
	}
}

// snapshotProjectIntoTree walks the files table, materializes blobs for
// every non-folder row, builds the tree hierarchy, and returns the root
// tree's hash. The repo's object store is mutated in place — caller is
// responsible for then writing a commit pointing at the returned hash.
//
// Encoding rules:
//   - kind='folder' → tree (no blob).
//   - kind in ('file','assembly','drawing','step') with non-empty
//     content → blob from content.
//   - kind any with a non-empty storage_key → blob from
//     s.Storage.Get(key) (binary fetch). storage_key takes precedence
//     over content if both are set.
//   - Empty rows still produce a zero-byte blob so the path round-trips
//     through checkout.
func (s *Service) snapshotProjectIntoTree(
	ctx context.Context,
	repo *gogit.Repository,
	projectID string,
) (plumbing.Hash, error) {
	files, err := s.loadProjectFiles(ctx, projectID)
	if err != nil {
		return plumbing.ZeroHash, err
	}

	// Build a parent_id → []dbFile index, then walk from roots
	// (parent_id IS NULL) into a tree of treeNodes.
	byParent := map[string][]dbFile{}
	byID := map[string]dbFile{}
	for _, f := range files {
		key := ""
		if f.ParentID != nil {
			key = *f.ParentID
		}
		byParent[key] = append(byParent[key], f)
		byID[f.ID] = f
	}
	root := newTreeNode("") // synthetic root

	var visit func(parentKey string, parentNode *treeNode) error
	visit = func(parentKey string, parentNode *treeNode) error {
		for _, f := range byParent[parentKey] {
			child, err := s.fileToNode(ctx, repo, f)
			if err != nil {
				return err
			}
			// Defensive: collision on same-named siblings would silently
			// drop one. Append a short suffix so both end up in the tree
			// — the user can fix the rename in the editor.
			name := child.name
			if _, ok := parentNode.children[name]; ok {
				name = name + ".dup-" + f.ID[:8]
				child.name = name
			}
			parentNode.children[name] = child
			if !child.isBlob {
				if err := visit(f.ID, child); err != nil {
					return err
				}
			}
		}
		return nil
	}
	if err := visit("", root); err != nil {
		return plumbing.ZeroHash, err
	}

	// Recursively encode every tree node. Blobs already have hashes
	// from fileToNode; trees get their hash here.
	return writeTree(repo, root)
}

// fileToNode materializes one DB row into a treeNode. For blobs, the
// blob is written into the repo's object store immediately so the
// caller doesn't have to re-walk.
func (s *Service) fileToNode(ctx context.Context, repo *gogit.Repository, f dbFile) (*treeNode, error) {
	n := newTreeNode(f.Name)
	if f.Kind == "folder" {
		n.isBlob = false
		n.mode = filemode.Dir
		return n, nil
	}

	var data []byte
	if f.StorageKey != nil && *f.StorageKey != "" && s.Storage != nil {
		rc, _, err := s.Storage.Get(ctx, *f.StorageKey)
		if err != nil {
			return nil, fmt.Errorf("storage get %s: %w", *f.StorageKey, err)
		}
		buf, err := io.ReadAll(rc)
		_ = rc.Close()
		if err != nil {
			return nil, fmt.Errorf("read storage blob %s: %w", *f.StorageKey, err)
		}
		data = buf
	} else {
		data = []byte(f.Content)
	}

	hash, err := writeBlob(repo, data)
	if err != nil {
		return nil, err
	}
	n.isBlob = true
	n.mode = filemode.Regular
	n.hash = hash
	n.blobBytes = data
	return n, nil
}

// writeBlob stores a raw byte slice as a git blob and returns the hash.
func writeBlob(repo *gogit.Repository, data []byte) (plumbing.Hash, error) {
	obj := repo.Storer.NewEncodedObject()
	obj.SetType(plumbing.BlobObject)
	obj.SetSize(int64(len(data)))
	w, err := obj.Writer()
	if err != nil {
		return plumbing.ZeroHash, fmt.Errorf("blob writer: %w", err)
	}
	if _, err := w.Write(data); err != nil {
		_ = w.Close()
		return plumbing.ZeroHash, fmt.Errorf("blob write: %w", err)
	}
	if err := w.Close(); err != nil {
		return plumbing.ZeroHash, fmt.Errorf("blob close: %w", err)
	}
	hash, err := repo.Storer.SetEncodedObject(obj)
	if err != nil {
		return plumbing.ZeroHash, fmt.Errorf("blob set: %w", err)
	}
	return hash, nil
}

// writeTree encodes a treeNode (and its descendants) into the repo's
// object store, returning the hash of the encoded tree. Free function
// because it doesn't need any Service state — pure repo + node walk.
func writeTree(repo *gogit.Repository, node *treeNode) (plumbing.Hash, error) {
	tree := &object.Tree{}
	// Sort children by name so the tree encoding is deterministic
	// (matches `git mktree`'s ordering).
	names := make([]string, 0, len(node.children))
	for n := range node.children {
		names = append(names, n)
	}
	sort.Strings(names)
	for _, name := range names {
		child := node.children[name]
		var hash plumbing.Hash
		if child.isBlob {
			hash = child.hash
		} else {
			h, err := writeTree(repo, child)
			if err != nil {
				return plumbing.ZeroHash, err
			}
			hash = h
		}
		tree.Entries = append(tree.Entries, object.TreeEntry{
			Name: name,
			Mode: child.mode,
			Hash: hash,
		})
	}
	obj := repo.Storer.NewEncodedObject()
	if err := tree.Encode(obj); err != nil {
		return plumbing.ZeroHash, fmt.Errorf("tree encode: %w", err)
	}
	hash, err := repo.Storer.SetEncodedObject(obj)
	if err != nil {
		return plumbing.ZeroHash, fmt.Errorf("tree set: %w", err)
	}
	return hash, nil
}

// writeCommit creates a commit pointing at the given tree, with the
// supplied parents and signature.
func writeCommit(
	repo *gogit.Repository,
	tree plumbing.Hash,
	parents []plumbing.Hash,
	sig object.Signature,
	message string,
) (plumbing.Hash, error) {
	c := &object.Commit{
		Author:       sig,
		Committer:    sig,
		Message:      strings.TrimSpace(message) + "\n",
		TreeHash:     tree,
		ParentHashes: parents,
	}
	obj := repo.Storer.NewEncodedObject()
	if err := c.Encode(obj); err != nil {
		return plumbing.ZeroHash, fmt.Errorf("commit encode: %w", err)
	}
	hash, err := repo.Storer.SetEncodedObject(obj)
	if err != nil {
		return plumbing.ZeroHash, fmt.Errorf("commit set: %w", err)
	}
	return hash, nil
}

// hasUncommittedChanges reports whether the live `files` table differs
// from the tree at HEAD on the given branch. Used by /checkout to warn
// the user before overwriting their working state.
//
// "Different" means: the snapshot tree of the current files table has a
// different hash than the HEAD commit's tree. Snapshot is built into a
// temporary side-effect-only tree (objects do get persisted, but stale
// objects are GC-able and harmless).
func (s *Service) hasUncommittedChanges(
	ctx context.Context,
	repo *gogit.Repository,
	projectID string,
	branch string,
) (bool, error) {
	ref, err := repo.Reference(plumbing.NewBranchReferenceName(branch), true)
	if err != nil {
		// No HEAD on this branch — every state counts as "uncommitted".
		return true, nil
	}
	commit, err := repo.CommitObject(ref.Hash())
	if err != nil {
		return false, fmt.Errorf("commit object %s: %w", ref.Hash(), err)
	}
	currentTree, err := s.snapshotProjectIntoTree(ctx, repo, projectID)
	if err != nil {
		return false, err
	}
	return currentTree != commit.TreeHash, nil
}

// checkoutTreeIntoProject replaces the project's files table with the
// contents of `treeHash`. Files in the table that aren't in the tree
// are soft-deleted (deleted_at = now()); files in the tree get an
// upsert keyed by path under the project.
//
// This is intentionally not atomic across the entire tree: each row is
// upserted in its own statement inside one transaction. For very large
// trees this could be slow but is bounded by the project size.
func (s *Service) checkoutTreeIntoProject(
	ctx context.Context,
	repo *gogit.Repository,
	projectID string,
	treeHash plumbing.Hash,
) error {
	rootTree, err := repo.TreeObject(treeHash)
	if err != nil {
		return fmt.Errorf("tree %s: %w", treeHash, err)
	}

	// Walk the tree into a path -> entry map.
	type targetEntry struct {
		path     string // forward-slash separated; "" is root
		name     string
		isDir    bool
		blobHash plumbing.Hash
		parent   string // path of parent dir, "" = root
	}
	var entries []targetEntry
	var walk func(t *object.Tree, parentPath string) error
	walk = func(t *object.Tree, parentPath string) error {
		for _, e := range t.Entries {
			path := e.Name
			if parentPath != "" {
				path = parentPath + "/" + e.Name
			}
			if e.Mode == filemode.Dir {
				entries = append(entries, targetEntry{
					path: path, name: e.Name, isDir: true, parent: parentPath,
				})
				sub, err := repo.TreeObject(e.Hash)
				if err != nil {
					return fmt.Errorf("subtree %s: %w", e.Hash, err)
				}
				if err := walk(sub, path); err != nil {
					return err
				}
				continue
			}
			entries = append(entries, targetEntry{
				path: path, name: e.Name, isDir: false,
				blobHash: e.Hash, parent: parentPath,
			})
		}
		return nil
	}
	if err := walk(rootTree, ""); err != nil {
		return err
	}

	tx, err := s.Pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	// Snapshot the existing rows by path so we can decide upsert vs
	// insert and figure out which ones are absent from the new tree.
	existingRows, err := tx.Query(ctx, `
        select id, parent_id, name, kind
        from files
        where project_id = $1 and deleted_at is null
    `, projectID)
	if err != nil {
		return fmt.Errorf("list existing: %w", err)
	}
	type liveRow struct {
		id, name, kind string
		parentID       *string
	}
	live := map[string]liveRow{} // id -> row
	for existingRows.Next() {
		var r liveRow
		if err := existingRows.Scan(&r.id, &r.parentID, &r.name, &r.kind); err != nil {
			existingRows.Close()
			return fmt.Errorf("scan existing: %w", err)
		}
		live[r.id] = r
	}
	existingRows.Close()
	if err := existingRows.Err(); err != nil {
		return err
	}
	// Build live id -> path index.
	livePath := func(id string) string {
		segs := []string{}
		for cur := id; cur != ""; {
			r, ok := live[cur]
			if !ok {
				break
			}
			segs = append([]string{r.name}, segs...)
			if r.parentID == nil {
				break
			}
			cur = *r.parentID
		}
		return strings.Join(segs, "/")
	}
	livePathIndex := map[string]string{} // path -> id
	for id := range live {
		livePathIndex[livePath(id)] = id
	}

	// Process targets in walk order so parents exist before children.
	// We track path -> id as we go.
	pathToID := map[string]string{}
	for _, e := range entries {
		var parentID *string
		if e.parent != "" {
			pid, ok := pathToID[e.parent]
			if !ok {
				return fmt.Errorf("checkout: parent missing for %s", e.path)
			}
			parentID = &pid
		}
		kind := "file"
		if e.isDir {
			kind = "folder"
		}
		// Read blob content if applicable.
		var content string
		if !e.isDir {
			blob, err := repo.BlobObject(e.blobHash)
			if err != nil {
				return fmt.Errorf("blob %s: %w", e.blobHash, err)
			}
			rc, err := blob.Reader()
			if err != nil {
				return fmt.Errorf("blob reader %s: %w", e.blobHash, err)
			}
			data, err := io.ReadAll(rc)
			_ = rc.Close()
			if err != nil {
				return fmt.Errorf("blob read %s: %w", e.blobHash, err)
			}
			content = string(data)
		}

		if existingID, ok := livePathIndex[e.path]; ok {
			// Update existing row in place — preserve id so revisions
			// keep linking. Soft-deleted rows aren't in the index.
			if e.isDir {
				if _, err := tx.Exec(ctx, `
                    update files set
                        name = $2, kind = 'folder',
                        parent_id = $3, updated_at = now()
                    where id = $1
                `, existingID, e.name, parentID); err != nil {
					return err
				}
			} else {
				if _, err := tx.Exec(ctx, `
                    update files set
                        name = $2, kind = case kind when 'folder' then 'file' else kind end,
                        content = $3, parent_id = $4, updated_at = now()
                    where id = $1
                `, existingID, e.name, content, parentID); err != nil {
					return err
				}
			}
			pathToID[e.path] = existingID
		} else {
			// Brand new row.
			var newID string
			if err := tx.QueryRow(ctx, `
                insert into files(project_id, parent_id, name, kind, content)
                values ($1, $2, $3, $4, $5)
                returning id
            `, projectID, parentID, e.name, kind, content).Scan(&newID); err != nil {
				return fmt.Errorf("insert %s: %w", e.path, err)
			}
			pathToID[e.path] = newID
		}
	}

	// Soft-delete any live rows whose path is not in the new tree.
	for path, id := range livePathIndex {
		if _, ok := pathToID[path]; ok {
			continue
		}
		if _, err := tx.Exec(ctx, `
            update files set deleted_at = now(), updated_at = now()
            where id = $1
        `, id); err != nil {
			return fmt.Errorf("soft-delete %s: %w", id, err)
		}
	}

	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit tx: %w", err)
	}
	return nil
}

// nowSig builds a Signature for a commit using the current time.
func nowSig(name, email string) object.Signature {
	if name == "" {
		name = "Kerf User"
	}
	if email == "" {
		email = "noreply@kerf.local"
	}
	return object.Signature{Name: name, Email: email, When: time.Now().UTC()}
}
