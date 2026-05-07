package storage

import (
	"context"
	"fmt"
	"io"
	"mime"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/imranp/kerf/backend/internal/config"
)

// Local is a filesystem-backed Storage implementation.
type Local struct {
	root string
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
	return &Local{root: abs}, nil
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

// PublicURL returns the auth-protected blob route.
func (l *Local) PublicURL(key string) string {
	return "/api/blobs/" + url.PathEscape(key)
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
