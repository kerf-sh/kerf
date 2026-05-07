package storage

import (
	"context"
	"fmt"
	"io"
	"mime"
	"net/url"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/imranp/kerf/backend/internal/config"
)

// Local is a filesystem-backed Storage implementation.
type Local struct {
	root   string
	cdnURL string // optional CDN prefix used by PublicURL
}

// NewLocal returns a Storage rooted at cfg.LocalStoragePath.
func NewLocal(cfg *config.Config) (*Local, error) {
	root := cfg.LocalStoragePath
	if root == "" {
		root = "./.kerf-storage"
	}
	abs, err := filepath.Abs(root)
	if err != nil {
		return nil, fmt.Errorf("storage/local: resolve path: %w", err)
	}
	if err := os.MkdirAll(abs, 0o755); err != nil {
		return nil, fmt.Errorf("storage/local: mkdir %s: %w", abs, err)
	}
	return &Local{
		root:   abs,
		cdnURL: strings.TrimRight(cfg.CDNBaseURL, "/"),
	}, nil
}

func (l *Local) safePath(key string) (string, error) {
	clean := filepath.Clean("/" + strings.TrimLeft(key, "/"))
	if clean == "/" {
		return "", fmt.Errorf("storage/local: empty key")
	}
	full := filepath.Join(l.root, clean)
	rel, err := filepath.Rel(l.root, full)
	if err != nil || strings.HasPrefix(rel, "..") {
		return "", fmt.Errorf("storage/local: invalid key %q", key)
	}
	return full, nil
}

// Put writes an object to disk under root/key.
func (l *Local) Put(ctx context.Context, key string, body io.Reader, contentType string, size int64) (PutResult, error) {
	dst, err := l.safePath(key)
	if err != nil {
		return PutResult{}, err
	}
	if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
		return PutResult{}, fmt.Errorf("storage/local: mkdir parent: %w", err)
	}
	tmp, err := os.CreateTemp(filepath.Dir(dst), ".upload-*")
	if err != nil {
		return PutResult{}, err
	}
	tmpPath := tmp.Name()
	written, err := io.Copy(tmp, body)
	cerr := tmp.Close()
	if err != nil {
		_ = os.Remove(tmpPath)
		return PutResult{}, err
	}
	if cerr != nil {
		_ = os.Remove(tmpPath)
		return PutResult{}, cerr
	}
	if err := os.Rename(tmpPath, dst); err != nil {
		_ = os.Remove(tmpPath)
		return PutResult{}, err
	}
	if contentType == "" {
		contentType = guessContentType(key)
	}
	return PutResult{Key: key, Size: written, ContentType: contentType}, nil
}

// Get opens an object for reading.
func (l *Local) Get(ctx context.Context, key string) (io.ReadCloser, string, error) {
	src, err := l.safePath(key)
	if err != nil {
		return nil, "", err
	}
	f, err := os.Open(src)
	if err != nil {
		return nil, "", err
	}
	return f, guessContentType(key), nil
}

// Delete removes an object. Missing files are not an error.
func (l *Local) Delete(ctx context.Context, key string) error {
	src, err := l.safePath(key)
	if err != nil {
		return err
	}
	if err := os.Remove(src); err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
}

// SignedURL is unsupported on local; returns "".
func (l *Local) SignedURL(ctx context.Context, key string, ttl time.Duration) (string, error) {
	return "", nil
}

// PublicURL returns the auth-protected blob route, with an optional cache
// buster. If a CDN base is configured (rare for the local backend, but
// allowed for parity with s3), it's used as the prefix instead.
func (l *Local) PublicURL(key string, updatedAt time.Time) string {
	base := "/api/blobs/" + escapeKey(key)
	if l.cdnURL != "" {
		base = l.cdnURL + "/" + escapeKey(key)
	}
	if !updatedAt.IsZero() {
		return base + "?v=" + strconv.FormatInt(updatedAt.Unix(), 10)
	}
	return base
}

// escapeKey URL-escapes each path segment so slashes survive while spaces
// and other unsafe characters get encoded. url.PathEscape would also
// escape '/' which we need to keep.
func escapeKey(key string) string {
	parts := strings.Split(strings.TrimLeft(key, "/"), "/")
	for i, p := range parts {
		parts[i] = url.PathEscape(p)
	}
	return strings.Join(parts, "/")
}

// --- Chunked upload helpers ------------------------------------------------
//
// Chunks live under root/_uploads/<uploadKey>/<n>.bin. The path layout makes
// it cheap to enumerate with os.ReadDir and to wipe with os.RemoveAll.

func (l *Local) chunkDir(uploadKey string) (string, error) {
	if uploadKey == "" || strings.ContainsAny(uploadKey, "/\\") {
		return "", fmt.Errorf("storage/local: invalid upload key %q", uploadKey)
	}
	return filepath.Join(l.root, "_uploads", uploadKey), nil
}

// PutChunk writes a single chunk to disk, replacing any prior content for
// that index (so a retried PUT doesn't double-count bytes).
func (l *Local) PutChunk(ctx context.Context, uploadKey string, chunkIndex int, body io.Reader) error {
	if chunkIndex < 0 {
		return fmt.Errorf("storage/local: negative chunk index")
	}
	dir, err := l.chunkDir(uploadKey)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return fmt.Errorf("storage/local: mkdir chunk dir: %w", err)
	}
	dst := filepath.Join(dir, strconv.Itoa(chunkIndex)+".bin")
	tmp, err := os.CreateTemp(dir, ".chunk-*")
	if err != nil {
		return err
	}
	tmpPath := tmp.Name()
	if _, err := io.Copy(tmp, body); err != nil {
		_ = tmp.Close()
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

// ListChunks returns chunk indices on disk, sorted ascending.
func (l *Local) ListChunks(ctx context.Context, uploadKey string) ([]int, error) {
	dir, err := l.chunkDir(uploadKey)
	if err != nil {
		return nil, err
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return []int{}, nil
		}
		return nil, err
	}
	out := make([]int, 0, len(entries))
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		name := e.Name()
		if !strings.HasSuffix(name, ".bin") {
			continue
		}
		idx, err := strconv.Atoi(strings.TrimSuffix(name, ".bin"))
		if err != nil {
			continue
		}
		out = append(out, idx)
	}
	sort.Ints(out)
	return out, nil
}

// ConcatChunksTo opens each chunk in index order and copies it into the
// destination object via Put-style atomic write.
func (l *Local) ConcatChunksTo(ctx context.Context, uploadKey string, dstKey string) (int64, error) {
	indices, err := l.ListChunks(ctx, uploadKey)
	if err != nil {
		return 0, err
	}
	if len(indices) == 0 {
		return 0, fmt.Errorf("storage/local: no chunks for upload %q", uploadKey)
	}

	dir, err := l.chunkDir(uploadKey)
	if err != nil {
		return 0, err
	}

	dst, err := l.safePath(dstKey)
	if err != nil {
		return 0, err
	}
	if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
		return 0, fmt.Errorf("storage/local: mkdir parent: %w", err)
	}
	tmp, err := os.CreateTemp(filepath.Dir(dst), ".upload-*")
	if err != nil {
		return 0, err
	}
	tmpPath := tmp.Name()
	var total int64
	for _, idx := range indices {
		path := filepath.Join(dir, strconv.Itoa(idx)+".bin")
		f, err := os.Open(path)
		if err != nil {
			_ = tmp.Close()
			_ = os.Remove(tmpPath)
			return 0, fmt.Errorf("storage/local: open chunk %d: %w", idx, err)
		}
		n, copyErr := io.Copy(tmp, f)
		_ = f.Close()
		if copyErr != nil {
			_ = tmp.Close()
			_ = os.Remove(tmpPath)
			return 0, copyErr
		}
		total += n
	}
	if err := tmp.Close(); err != nil {
		_ = os.Remove(tmpPath)
		return 0, err
	}
	if err := os.Rename(tmpPath, dst); err != nil {
		_ = os.Remove(tmpPath)
		return 0, err
	}
	return total, nil
}

// DeleteUpload removes the entire chunk directory for an upload.
func (l *Local) DeleteUpload(ctx context.Context, uploadKey string) error {
	dir, err := l.chunkDir(uploadKey)
	if err != nil {
		return err
	}
	if err := os.RemoveAll(dir); err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
}

func guessContentType(key string) string {
	ext := strings.ToLower(filepath.Ext(key))
	switch ext {
	case ".step", ".stp":
		return "model/step"
	}
	if ct := mime.TypeByExtension(ext); ct != "" {
		return ct
	}
	return "application/octet-stream"
}
