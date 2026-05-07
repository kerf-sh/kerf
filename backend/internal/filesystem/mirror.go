// Package filesystem implements the "filesystem" storage backend, where
// each project mirrors to a real directory under a configured root and
// file content lives on disk as ordinary files.
//
// The DB remains the source of truth for metadata (file rows, parent_id
// chains, soft-deletes). Writes are write-through to disk; reads pull
// content from disk. The package is only constructed when
// `[storage].backend = "filesystem"` in kerf.toml — other backends keep
// using the existing `content` column.
package filesystem

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"
)

// Mirror writes through file changes to a disk tree rooted at Root.
type Mirror struct {
	root string
}

// New returns a Mirror rooted at root. Creates the root if missing.
func New(root string) (*Mirror, error) {
	if root == "" {
		return nil, fmt.Errorf("filesystem.New: empty root")
	}
	abs, err := filepath.Abs(root)
	if err != nil {
		return nil, fmt.Errorf("filesystem.New: abs %s: %w", root, err)
	}
	if err := os.MkdirAll(abs, 0o755); err != nil {
		return nil, fmt.Errorf("filesystem.New: mkdir %s: %w", abs, err)
	}
	return &Mirror{root: abs}, nil
}

// Root returns the absolute root directory.
func (m *Mirror) Root() string { return m.root }

// ProjectDir returns the absolute path of a project's directory. The dir
// may not yet exist; call EnsureProjectDir first if you need it created.
func (m *Mirror) ProjectDir(projectName string) string {
	return filepath.Join(m.root, slug(projectName))
}

// EnsureProjectDir mkdirs the project's directory. Idempotent.
func (m *Mirror) EnsureProjectDir(projectName string) error {
	return os.MkdirAll(m.ProjectDir(projectName), 0o755)
}

// RemoveProject removes the project's directory tree. Best-effort: a
// missing directory is not an error.
func (m *Mirror) RemoveProject(projectName string) error {
	dir := m.ProjectDir(projectName)
	if err := os.RemoveAll(dir); err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
}

// FilePath builds the absolute on-disk path for a file given its project
// and the path segments returned by SegmentsForFile (or built directly).
func (m *Mirror) FilePath(projectName string, segments []string) string {
	parts := append([]string{m.ProjectDir(projectName)}, segments...)
	return filepath.Join(parts...)
}

// WriteFile atomically writes content to the file. Creates parent dirs.
func (m *Mirror) WriteFile(projectName string, segments []string, content string) error {
	dst := m.FilePath(projectName, segments)
	if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
		return fmt.Errorf("filesystem.WriteFile: mkdir parent: %w", err)
	}
	tmp, err := os.CreateTemp(filepath.Dir(dst), ".kerf-*")
	if err != nil {
		return fmt.Errorf("filesystem.WriteFile: tempfile: %w", err)
	}
	tmpPath := tmp.Name()
	if _, err := tmp.WriteString(content); err != nil {
		tmp.Close()
		_ = os.Remove(tmpPath)
		return err
	}
	if err := tmp.Close(); err != nil {
		_ = os.Remove(tmpPath)
		return err
	}
	if err := os.Rename(tmpPath, dst); err != nil {
		_ = os.Remove(tmpPath)
		return err
	}
	return nil
}

// ReadFile returns the on-disk content of a file. Returns ("", nil) when
// the file isn't on disk yet (e.g. a row created before filesystem mode
// was enabled — caller should fall back to the DB content column).
func (m *Mirror) ReadFile(projectName string, segments []string) (string, bool, error) {
	src := m.FilePath(projectName, segments)
	b, err := os.ReadFile(src)
	if err != nil {
		if os.IsNotExist(err) {
			return "", false, nil
		}
		return "", false, err
	}
	return string(b), true, nil
}

// RemoveFile deletes a file. Missing files are not an error.
func (m *Mirror) RemoveFile(projectName string, segments []string) error {
	dst := m.FilePath(projectName, segments)
	if err := os.Remove(dst); err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
}

// Mkdir creates a directory at segments (and all parents).
func (m *Mirror) Mkdir(projectName string, segments []string) error {
	return os.MkdirAll(m.FilePath(projectName, segments), 0o755)
}

// RemoveAll recursively removes a directory tree. Missing is not an error.
func (m *Mirror) RemoveAll(projectName string, segments []string) error {
	dst := m.FilePath(projectName, segments)
	if err := os.RemoveAll(dst); err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
}

// Move renames a file or folder.
func (m *Mirror) Move(projectName string, oldSegments, newSegments []string) error {
	src := m.FilePath(projectName, oldSegments)
	dst := m.FilePath(projectName, newSegments)
	if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
		return err
	}
	return os.Rename(src, dst)
}

// SegmentsForFile walks up the parent_id chain and returns the path
// segments for a file (leaf last). The project ID scopes the lookup.
func SegmentsForFile(ctx context.Context, pool *pgxpool.Pool, projectID, fileID string) ([]string, error) {
	current := fileID
	var out []string
	for i := 0; i < 64; i++ {
		var (
			name   string
			parent *string
		)
		if err := pool.QueryRow(ctx,
			`select name, parent_id::text from files where id = $1 and project_id = $2`,
			current, projectID).Scan(&name, &parent); err != nil {
			return nil, fmt.Errorf("segments: %w", err)
		}
		out = append([]string{sanitizeName(name)}, out...)
		if parent == nil {
			return out, nil
		}
		current = *parent
	}
	return nil, fmt.Errorf("file tree too deep")
}

// SegmentsForParent returns the path segments leading up to a parent
// folder (so a leaf can be appended to form the full path). Returns nil
// when parentID is nil (file lives at the project root).
func SegmentsForParent(ctx context.Context, pool *pgxpool.Pool, projectID string, parentID *string) ([]string, error) {
	if parentID == nil || *parentID == "" {
		return nil, nil
	}
	return SegmentsForFile(ctx, pool, projectID, *parentID)
}

// slug turns a project name into a filesystem-safe directory name. Keeps
// alphanumerics, hyphen, underscore, and dot; everything else becomes a
// hyphen. Empty input maps to "untitled".
func slug(name string) string {
	name = strings.TrimSpace(name)
	if name == "" {
		return "untitled"
	}
	var b strings.Builder
	prev := false
	for _, r := range name {
		switch {
		case (r >= 'a' && r <= 'z') ||
			(r >= 'A' && r <= 'Z') ||
			(r >= '0' && r <= '9') ||
			r == '-' || r == '_' || r == '.':
			b.WriteRune(r)
			prev = false
		default:
			if !prev {
				b.WriteByte('-')
				prev = true
			}
		}
	}
	out := strings.Trim(b.String(), "-.")
	if out == "" {
		return "untitled"
	}
	return out
}

// sanitizeName cleans a file/folder name. Strips path separators since a
// single name segment shouldn't contain them.
func sanitizeName(name string) string {
	name = strings.TrimSpace(name)
	name = strings.ReplaceAll(name, "/", "_")
	name = strings.ReplaceAll(name, "\\", "_")
	if name == "" || name == "." || name == ".." {
		return "_"
	}
	return name
}
