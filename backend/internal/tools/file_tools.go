package tools

import (
	"context"
	"encoding/json"
	"errors"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/imranp/kerf/backend/internal/llm"
)

// ----------------------------- list_files -------------------------------

var listFilesSpec = llm.ToolSpec{
	Name:        "list_files",
	Description: "List every file in the current project as a flat array of absolute paths.",
	InputSchema: map[string]any{
		"type":       "object",
		"properties": map[string]any{},
	},
}

type listedFile struct {
	Path string  `json:"path"`
	Kind string  `json:"kind"`
	Size *int64  `json:"size,omitempty"`
}

func runListFiles(ctx context.Context, pc ProjectCtx, _ json.RawMessage) (string, error) {
	rows, err := pc.Pool.Query(ctx,
		`select id, parent_id, name, kind, length(content), size
		 from files where project_id = $1`,
		pc.ProjectID)
	if err != nil {
		return "", err
	}
	defer rows.Close()

	type row struct {
		id      uuid.UUID
		parent  *uuid.UUID
		name    string
		kind    string
		clen    int64
		size    *int64
	}
	var all []row
	idx := map[uuid.UUID]row{}
	for rows.Next() {
		var r row
		if err := rows.Scan(&r.id, &r.parent, &r.name, &r.kind, &r.clen, &r.size); err != nil {
			return "", err
		}
		all = append(all, r)
		idx[r.id] = r
	}

	pathOf := func(id uuid.UUID) string {
		parts := []string{}
		cur := id
		for i := 0; i < 64; i++ {
			r, ok := idx[cur]
			if !ok {
				return ""
			}
			parts = append([]string{r.name}, parts...)
			if r.parent == nil {
				break
			}
			cur = *r.parent
		}
		return "/" + strings.Join(parts, "/")
	}

	out := make([]listedFile, 0, len(all))
	for _, r := range all {
		size := r.size
		if size == nil && r.kind != "folder" && r.kind != "step" {
			s := r.clen
			size = &s
		}
		out = append(out, listedFile{
			Path: pathOf(r.id),
			Kind: r.kind,
			Size: size,
		})
	}
	return okPayload(map[string]any{"files": out}), nil
}

// ------------------------------ read_file -------------------------------

var readFileSpec = llm.ToolSpec{
	Name:        "read_file",
	Description: "Read the full text content of a file by absolute path. Errors on binary kinds (e.g. step).",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"path": map[string]any{"type": "string"},
		},
		"required": []string{"path"},
	},
}

type readFileArgs struct {
	Path string `json:"path"`
}

func runReadFile(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a readFileArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	rp, err := resolvePath(ctx, pc, a.Path)
	if err != nil {
		return errPayload(err.Error(), "NOT_FOUND"), nil
	}
	if !rp.Exists {
		return errPayload("file not found: "+a.Path, "NOT_FOUND"), nil
	}
	if rp.Kind == "step" {
		return errPayload("cannot read binary kind 'step' as text; use the download URL", "BINARY"), nil
	}
	if rp.Kind == "folder" {
		return errPayload("path is a folder", "IS_FOLDER"), nil
	}
	var content string
	if err := pc.Pool.QueryRow(ctx,
		`select content from files where id = $1 and project_id = $2`,
		rp.ID, pc.ProjectID).Scan(&content); err != nil {
		return "", err
	}
	return okPayload(map[string]any{"path": a.Path, "content": content}), nil
}

// ------------------------------ write_file ------------------------------

var writeFileSpec = llm.ToolSpec{
	Name:        "write_file",
	Description: "Replace the entire content of a text file. Creates intermediate folders if missing. Use edit_file for targeted edits.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"path":    map[string]any{"type": "string"},
			"content": map[string]any{"type": "string"},
		},
		"required": []string{"path", "content"},
	},
}

type writeFileArgs struct {
	Path    string `json:"path"`
	Content string `json:"content"`
}

func runWriteFile(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a writeFileArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	clean, err := normalizePath(a.Path)
	if err != nil {
		return errPayload(err.Error(), "BAD_ARGS"), nil
	}
	parts := splitPath(clean)
	if len(parts) == 0 {
		return errPayload("cannot write the root", "BAD_ARGS"), nil
	}
	rp, _ := resolvePath(ctx, pc, clean)
	if rp.Exists {
		if rp.Kind == "step" || rp.Kind == "folder" {
			return errPayload("cannot write to kind="+rp.Kind, "BAD_KIND"), nil
		}
		if _, err := pc.Pool.Exec(ctx,
			`update files set content = $1, updated_at = now() where id = $2 and project_id = $3`,
			a.Content, rp.ID, pc.ProjectID); err != nil {
			return "", err
		}
		return okPayload(map[string]any{"path": clean, "bytes": len(a.Content)}), nil
	}
	parent, err := ensureFolders(ctx, pc, parts[:len(parts)-1])
	if err != nil {
		return "", err
	}
	leaf := parts[len(parts)-1]
	var newID uuid.UUID
	err = pc.Pool.QueryRow(ctx,
		`insert into files(project_id, parent_id, name, kind, content)
		 values ($1,$2,$3,'file',$4)
		 returning id`,
		pc.ProjectID, parent, leaf, a.Content).Scan(&newID)
	if err != nil {
		return "", err
	}
	return okPayload(map[string]any{"path": clean, "bytes": len(a.Content), "id": newID.String()}), nil
}

// ------------------------------ edit_file -------------------------------

var editFileSpec = llm.ToolSpec{
	Name:        "edit_file",
	Description: "Replace a unique substring inside a text file. Errors if old_string occurs zero or more than one time. Use this for surgical edits.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"path":       map[string]any{"type": "string"},
			"old_string": map[string]any{"type": "string"},
			"new_string": map[string]any{"type": "string"},
		},
		"required": []string{"path", "old_string", "new_string"},
	},
}

type editFileArgs struct {
	Path      string `json:"path"`
	OldString string `json:"old_string"`
	NewString string `json:"new_string"`
}

func runEditFile(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a editFileArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	if a.OldString == "" {
		return errPayload("old_string must be non-empty", "BAD_ARGS"), nil
	}
	rp, err := resolvePath(ctx, pc, a.Path)
	if err != nil || !rp.Exists {
		return errPayload("file not found: "+a.Path, "NOT_FOUND"), nil
	}
	if rp.Kind == "step" || rp.Kind == "folder" {
		return errPayload("cannot edit kind="+rp.Kind, "BAD_KIND"), nil
	}
	var content string
	if err := pc.Pool.QueryRow(ctx,
		`select content from files where id = $1 and project_id = $2`,
		rp.ID, pc.ProjectID).Scan(&content); err != nil {
		return "", err
	}
	count := strings.Count(content, a.OldString)
	if count == 0 {
		return errPayload("old_string not found", "NOT_FOUND"), nil
	}
	if count > 1 {
		return errPayload("old_string is ambiguous (matched "+itoa(count)+" times)", "AMBIGUOUS"), nil
	}
	updated := strings.Replace(content, a.OldString, a.NewString, 1)
	if _, err := pc.Pool.Exec(ctx,
		`update files set content = $1, updated_at = now() where id = $2 and project_id = $3`,
		updated, rp.ID, pc.ProjectID); err != nil {
		return "", err
	}
	return okPayload(map[string]any{"path": a.Path, "replaced": 1}), nil
}

// ----------------------------- create_file ------------------------------

var createFileSpec = llm.ToolSpec{
	Name:        "create_file",
	Description: "Create a new file, folder, or assembly. Auto-creates intermediate folders. kind defaults to 'file'.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"path":    map[string]any{"type": "string"},
			"content": map[string]any{"type": "string"},
			"kind": map[string]any{
				"type": "string",
				"enum": []string{"file", "folder", "assembly"},
			},
		},
		"required": []string{"path"},
	},
}

type createFileArgs struct {
	Path    string `json:"path"`
	Content string `json:"content"`
	Kind    string `json:"kind"`
}

func runCreateFile(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a createFileArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	if a.Kind == "" {
		a.Kind = "file"
	}
	if a.Kind != "file" && a.Kind != "folder" && a.Kind != "assembly" {
		return errPayload("invalid kind (must be file|folder|assembly)", "BAD_ARGS"), nil
	}
	clean, err := normalizePath(a.Path)
	if err != nil {
		return errPayload(err.Error(), "BAD_ARGS"), nil
	}
	parts := splitPath(clean)
	if len(parts) == 0 {
		return errPayload("cannot create the root", "BAD_ARGS"), nil
	}
	if rp, _ := resolvePath(ctx, pc, clean); rp.Exists {
		return errPayload("path already exists", "EXISTS"), nil
	}
	parent, err := ensureFolders(ctx, pc, parts[:len(parts)-1])
	if err != nil {
		return "", err
	}
	leaf := parts[len(parts)-1]
	var newID uuid.UUID
	err = pc.Pool.QueryRow(ctx,
		`insert into files(project_id, parent_id, name, kind, content)
		 values ($1,$2,$3,$4,$5)
		 returning id`,
		pc.ProjectID, parent, leaf, a.Kind, a.Content).Scan(&newID)
	if err != nil {
		return "", err
	}
	return okPayload(map[string]any{"path": clean, "id": newID.String()}), nil
}

// ----------------------------- delete_file ------------------------------

var deleteFileSpec = llm.ToolSpec{
	Name:        "delete_file",
	Description: "Delete the file or folder at the given absolute path (recursive for folders).",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"path": map[string]any{"type": "string"},
		},
		"required": []string{"path"},
	},
}

type deleteFileArgs struct {
	Path string `json:"path"`
}

func runDeleteFile(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a deleteFileArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	rp, err := resolvePath(ctx, pc, a.Path)
	if err != nil || !rp.Exists {
		return errPayload("file not found: "+a.Path, "NOT_FOUND"), nil
	}
	// Capture storage_key for later cleanup.
	var storageKey *string
	_ = pc.Pool.QueryRow(ctx,
		`select storage_key from files where id = $1 and project_id = $2`,
		rp.ID, pc.ProjectID).Scan(&storageKey)
	if _, err := pc.Pool.Exec(ctx,
		`delete from files where id = $1 and project_id = $2`,
		rp.ID, pc.ProjectID); err != nil {
		return "", err
	}
	if pc.Storage != nil && storageKey != nil && *storageKey != "" {
		_ = pc.Storage.Delete(ctx, *storageKey)
	}
	return okPayload(map[string]any{"path": a.Path}), nil
}

// ----------------------------- search_code ------------------------------

var searchCodeSpec = llm.ToolSpec{
	Name:        "search_code",
	Description: "Case-insensitive substring search across all text files in the project.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"query": map[string]any{"type": "string"},
			"max":   map[string]any{"type": "integer"},
		},
		"required": []string{"query"},
	},
}

type searchCodeArgs struct {
	Query string `json:"query"`
	Max   int    `json:"max"`
}

type searchMatch struct {
	Path    string `json:"path"`
	Line    int    `json:"line"`
	Preview string `json:"preview"`
}

func runSearchCode(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a searchCodeArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	if a.Query == "" {
		return errPayload("query is required", "BAD_ARGS"), nil
	}
	if a.Max <= 0 || a.Max > 200 {
		a.Max = 50
	}
	rows, err := pc.Pool.Query(ctx,
		`select id, content from files
		 where project_id = $1 and kind in ('file','assembly')`,
		pc.ProjectID)
	if err != nil {
		return "", err
	}
	defer rows.Close()
	type rawFile struct {
		id      uuid.UUID
		content string
	}
	var fs []rawFile
	for rows.Next() {
		var rf rawFile
		if err := rows.Scan(&rf.id, &rf.content); err != nil {
			return "", err
		}
		fs = append(fs, rf)
	}

	q := strings.ToLower(a.Query)
	matches := make([]searchMatch, 0)
	for _, rf := range fs {
		lines := strings.Split(rf.content, "\n")
		var path string
		for i, line := range lines {
			if strings.Contains(strings.ToLower(line), q) {
				if path == "" {
					p, err := pathFromFileID(ctx, pc, rf.id)
					if err != nil {
						break
					}
					path = p
				}
				preview := line
				if len(preview) > 200 {
					preview = preview[:200]
				}
				matches = append(matches, searchMatch{
					Path:    path,
					Line:    i + 1,
					Preview: preview,
				})
				if len(matches) >= a.Max {
					return okPayload(map[string]any{"matches": matches, "truncated": true}), nil
				}
			}
		}
	}
	return okPayload(map[string]any{"matches": matches}), nil
}

// --------------------------- validate_jscad -----------------------------

var validateJSCADSpec = llm.ToolSpec{
	Name:        "validate_jscad",
	Description: "Stub: returns ok=true. Real validation runs in the browser.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"path": map[string]any{"type": "string"},
		},
		"required": []string{"path"},
	},
}

type validateArgs struct {
	Path string `json:"path"`
}

func runValidateJSCAD(_ context.Context, _ ProjectCtx, args json.RawMessage) (string, error) {
	var a validateArgs
	_ = json.Unmarshal(args, &a)
	return okPayload(map[string]any{
		"path":    a.Path,
		"ok":      true,
		"checked": false,
		"note":    "client-side validation",
	}), nil
}

// itoa is a small helper to avoid importing strconv just for one call.
func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var b [20]byte
	i := len(b)
	for n > 0 {
		i--
		b[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		b[i] = '-'
	}
	return string(b[i:])
}

// silence unused-import for pgx in this file (used elsewhere in package).
var _ = pgx.ErrNoRows
var _ = errors.New
