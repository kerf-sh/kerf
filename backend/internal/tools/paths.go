package tools

import (
	"context"
	"errors"
	"fmt"
	"path"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// fileNode is the minimal in-memory representation of a `files` row used by
// the path resolver.
type fileNode struct {
	ID       uuid.UUID
	ParentID *uuid.UUID
	Name     string
	Kind     string
}

// resolvedPath is the result of resolving a logical path against the project's
// file tree. If the leaf doesn't exist, ID is uuid.Nil and ParentID points to
// the deepest existing folder. Name is always the last path segment.
type resolvedPath struct {
	ID       uuid.UUID
	ParentID *uuid.UUID
	Name     string
	Kind     string
	Exists   bool
}

// normalizePath enforces our POSIX-like, leading-slash, no-trailing-slash form.
func normalizePath(p string) (string, error) {
	if p == "" {
		return "", errors.New("path required")
	}
	if !strings.HasPrefix(p, "/") {
		p = "/" + p
	}
	cleaned := path.Clean(p)
	if cleaned == "." || cleaned == "" {
		return "/", nil
	}
	return cleaned, nil
}

// splitPath splits "/a/b/c" into ["a","b","c"]. Returns empty for "/".
func splitPath(p string) []string {
	p = strings.Trim(p, "/")
	if p == "" {
		return nil
	}
	return strings.Split(p, "/")
}

// listProjectFiles loads every (non-soft-deleted) file row for a project so
// we can walk the tree in memory. Caches keyed by parent_id then name.
func listProjectFiles(ctx context.Context, pc ProjectCtx) ([]fileNode, error) {
	rows, err := pc.Pool.Query(ctx,
		`select id, parent_id, name, kind from files where project_id = $1 and deleted_at is null`,
		pc.ProjectID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []fileNode
	for rows.Next() {
		var n fileNode
		if err := rows.Scan(&n.ID, &n.ParentID, &n.Name, &n.Kind); err != nil {
			return nil, err
		}
		out = append(out, n)
	}
	return out, rows.Err()
}

// indexByParent groups nodes by their parent id (uuid.Nil = root).
func indexByParent(nodes []fileNode) map[uuid.UUID][]fileNode {
	idx := map[uuid.UUID][]fileNode{}
	for _, n := range nodes {
		var pid uuid.UUID
		if n.ParentID != nil {
			pid = *n.ParentID
		}
		idx[pid] = append(idx[pid], n)
	}
	return idx
}

// resolvePath walks the file tree to find the node at `pathStr`. Returns
// Exists=false if the leaf is missing — in that case ParentID points to the
// nearest existing parent folder so callers can decide whether to create it.
func resolvePath(ctx context.Context, pc ProjectCtx, pathStr string) (resolvedPath, error) {
	clean, err := normalizePath(pathStr)
	if err != nil {
		return resolvedPath{}, err
	}
	if clean == "/" {
		return resolvedPath{Name: "/", Kind: "folder", Exists: true}, nil
	}
	parts := splitPath(clean)
	nodes, err := listProjectFiles(ctx, pc)
	if err != nil {
		return resolvedPath{}, err
	}
	idx := indexByParent(nodes)

	var currentParent *uuid.UUID
	var current fileNode
	for i, segment := range parts {
		var pid uuid.UUID
		if currentParent != nil {
			pid = *currentParent
		}
		children := idx[pid]
		var found *fileNode
		for k := range children {
			if children[k].Name == segment {
				found = &children[k]
				break
			}
		}
		if found == nil {
			// Missing — the leaf is the segment, parent is currentParent.
			if i == len(parts)-1 {
				return resolvedPath{
					ParentID: currentParent,
					Name:     segment,
					Exists:   false,
				}, nil
			}
			return resolvedPath{
				ParentID: currentParent,
				Name:     segment,
				Exists:   false,
			}, errPathSegmentMissing(segment)
		}
		current = *found
		idCopy := found.ID
		currentParent = &idCopy
	}
	return resolvedPath{
		ID:       current.ID,
		ParentID: current.ParentID,
		Name:     current.Name,
		Kind:     current.Kind,
		Exists:   true,
	}, nil
}

func errPathSegmentMissing(s string) error {
	return fmt.Errorf("path segment %q not found", s)
}

// pathFromFileID reconstructs the absolute path of a file by walking up
// parent_id pointers. Returns "/" for root-level errors.
func pathFromFileID(ctx context.Context, pc ProjectCtx, fid uuid.UUID) (string, error) {
	parts := []string{}
	current := fid
	for i := 0; i < 64; i++ { // depth guard
		var name string
		var parent *uuid.UUID
		err := pc.Pool.QueryRow(ctx,
			`select name, parent_id from files where id = $1 and project_id = $2`,
			current, pc.ProjectID).Scan(&name, &parent)
		if err != nil {
			if errors.Is(err, pgx.ErrNoRows) {
				return "", fmt.Errorf("file %s not found", current)
			}
			return "", err
		}
		parts = append([]string{name}, parts...)
		if parent == nil {
			return "/" + strings.Join(parts, "/"), nil
		}
		current = *parent
	}
	return "", fmt.Errorf("path too deep")
}

// ensureFolders creates any missing folder rows along the given segments.
// Returns the parent_id pointer for the final folder (so a leaf file can be
// inserted under it).
func ensureFolders(ctx context.Context, pc ProjectCtx, segments []string) (*uuid.UUID, error) {
	if len(segments) == 0 {
		return nil, nil
	}
	var currentParent *uuid.UUID
	for _, seg := range segments {
		var existing uuid.UUID
		var query string
		args := []any{pc.ProjectID, seg}
		if currentParent == nil {
			query = `select id from files where project_id = $1 and parent_id is null and name = $2`
		} else {
			query = `select id from files where project_id = $1 and parent_id = $3 and name = $2`
			args = append(args, *currentParent)
		}
		err := pc.Pool.QueryRow(ctx, query, args...).Scan(&existing)
		if err == nil {
			c := existing
			currentParent = &c
			continue
		}
		if !errors.Is(err, pgx.ErrNoRows) {
			return nil, err
		}
		var newID uuid.UUID
		err = pc.Pool.QueryRow(ctx,
			`insert into files(project_id, parent_id, name, kind, content)
			 values ($1,$2,$3,'folder','')
			 returning id`,
			pc.ProjectID, currentParent, seg).Scan(&newID)
		if err != nil {
			return nil, err
		}
		c := newID
		currentParent = &c
	}
	return currentParent, nil
}
