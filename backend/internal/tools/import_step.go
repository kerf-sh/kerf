package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"

	"github.com/imranp/kerf/backend/internal/llm"
)

const (
	maxStepBytes  = 50 * 1024 * 1024 // 50 MB hard cap.
	importTimeout = 30 * time.Second
)

var importStepSpec = llm.ToolSpec{
	Name:        "import_step",
	Description: "Download a STEP file from an HTTPS URL into the project. Times out after 30s; rejects files over 50MB.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"name":        map[string]any{"type": "string"},
			"url":         map[string]any{"type": "string"},
			"parent_path": map[string]any{"type": "string"},
		},
		"required": []string{"name", "url"},
	},
}

type importStepArgs struct {
	Name       string `json:"name"`
	URL        string `json:"url"`
	ParentPath string `json:"parent_path"`
}

func runImportStep(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a importStepArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	if pc.Storage == nil {
		return errPayload("storage backend not configured", "NO_STORAGE"), nil
	}
	if a.Name == "" || a.URL == "" {
		return errPayload("name and url are required", "BAD_ARGS"), nil
	}
	u, err := url.Parse(a.URL)
	if err != nil {
		return errPayload("invalid url: "+err.Error(), "BAD_ARGS"), nil
	}
	if u.Scheme != "https" {
		return errPayload("url scheme must be https", "BAD_ARGS"), nil
	}

	parentPath := a.ParentPath
	if parentPath == "" {
		parentPath = "/"
	}
	parentClean, err := normalizePath(parentPath)
	if err != nil {
		return errPayload(err.Error(), "BAD_ARGS"), nil
	}
	var parentID *uuid.UUID
	if parentClean != "/" {
		rp, err := resolvePath(ctx, pc, parentClean)
		if err != nil || !rp.Exists {
			return errPayload("parent_path not found", "NOT_FOUND"), nil
		}
		if rp.Kind != "folder" {
			return errPayload("parent_path is not a folder", "BAD_KIND"), nil
		}
		id := rp.ID
		parentID = &id
	}

	// Reject duplicate names under the same parent.
	leafPath := parentClean
	if !strings.HasSuffix(leafPath, "/") {
		leafPath += "/"
	}
	leafPath += a.Name
	if rp, _ := resolvePath(ctx, pc, leafPath); rp.Exists {
		return errPayload("a file already exists at "+leafPath, "EXISTS"), nil
	}

	// HEAD-style: do a GET with a 30s timeout but pre-check Content-Length.
	client := pc.HTTPClient
	if client == nil {
		client = &http.Client{Timeout: importTimeout}
	}
	dlCtx, cancel := context.WithTimeout(ctx, importTimeout)
	defer cancel()

	req, err := http.NewRequestWithContext(dlCtx, http.MethodGet, a.URL, nil)
	if err != nil {
		return errPayload(err.Error(), "ERROR"), nil
	}
	resp, err := client.Do(req)
	if err != nil {
		return errPayload("download failed: "+err.Error(), "DOWNLOAD"), nil
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return errPayload(fmt.Sprintf("download %d", resp.StatusCode), "DOWNLOAD"), nil
	}
	if cl := resp.Header.Get("Content-Length"); cl != "" {
		if n, err := strconv.ParseInt(cl, 10, 64); err == nil && n > maxStepBytes {
			return errPayload("file too large (>50MB)", "TOO_LARGE"), nil
		}
	}

	// Stream into storage with a hard cap.
	limited := &cappedReader{r: resp.Body, max: maxStepBytes}
	key := fmt.Sprintf("projects/%s/assets/%s-%s",
		pc.ProjectID.String(), uuid.New().String(), sanitizeName(a.Name))

	contentType := resp.Header.Get("Content-Type")
	if contentType == "" {
		contentType = "model/step"
	}

	pr, err := pc.Storage.Put(dlCtx, key, limited, contentType, 0)
	if err != nil {
		return errPayload("storage put: "+err.Error(), "STORAGE"), nil
	}
	if limited.exceeded {
		_ = pc.Storage.Delete(ctx, key)
		return errPayload("file too large (>50MB)", "TOO_LARGE"), nil
	}

	// Insert the files row.
	var newID uuid.UUID
	err = pc.Pool.QueryRow(ctx,
		`insert into files(project_id, parent_id, name, kind, content, storage_key, mime_type, size)
		 values ($1,$2,$3,'step','',$4,$5,$6)
		 returning id`,
		pc.ProjectID, parentID, a.Name, key, contentType, pr.Size,
	).Scan(&newID)
	if err != nil {
		_ = pc.Storage.Delete(ctx, key)
		return errPayload("db insert: "+err.Error(), "DB"), nil
	}

	return okPayload(map[string]any{
		"path": leafPath,
		"id":   newID.String(),
		"size": pr.Size,
	}), nil
}

// cappedReader stops returning bytes once max is exceeded and flips a flag so
// the caller can fail the operation. We deliberately don't truncate silently.
type cappedReader struct {
	r        io.Reader
	max      int64
	read     int64
	exceeded bool
}

func (c *cappedReader) Read(p []byte) (int, error) {
	if c.exceeded {
		return 0, io.EOF
	}
	n, err := c.r.Read(p)
	c.read += int64(n)
	if c.read > c.max {
		c.exceeded = true
		return n, io.EOF
	}
	return n, err
}

// sanitizeName replaces filesystem-hostile chars with `_`.
func sanitizeName(name string) string {
	var b strings.Builder
	for _, r := range name {
		switch r {
		case '/', '\\', '\x00':
			b.WriteByte('_')
		default:
			b.WriteRune(r)
		}
	}
	out := b.String()
	if out == "" {
		out = "asset"
	}
	return out
}
