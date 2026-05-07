// Package storage abstracts blob storage for binary assets (e.g. STEP files).
//
// Two backends are supported:
//
//   - localfs — writes to a directory on disk (default ./.kerf-storage).
//   - s3      — uses the AWS SDK v2 against S3 or any S3-compatible endpoint.
//
// Selection rule: if cfg.StorageBackend == "s3", or if it is empty AND
// cfg.S3Bucket is set, we use S3. Otherwise we fall back to local.
package storage

import (
	"context"
	"fmt"
	"io"
	"time"

	"github.com/imranp/kerf/backend/internal/config"
)

// PutResult captures the metadata recorded for a successfully stored object.
type PutResult struct {
	Key         string
	Size        int64
	ContentType string
}

// Storage is the interface every backend implements.
type Storage interface {
	Put(ctx context.Context, key string, body io.Reader, contentType string, size int64) (PutResult, error)
	Get(ctx context.Context, key string) (io.ReadCloser, string, error)
	Delete(ctx context.Context, key string) error
	// SignedURL returns a presigned URL good for `ttl` (or "" if not supported).
	SignedURL(ctx context.Context, key string, ttl time.Duration) (string, error)
	// PublicURL returns a best-effort URL for the object. Local backend
	// returns the /api/blobs/<key> route — auth required.
	PublicURL(key string) string
}

// New returns the configured Storage backend.
//
//   - "s3"   or (auto-detect when S3_BUCKET is set) → S3 backend.
//   - "local" or (auto-detect when nothing is set)  → local filesystem.
func New(cfg *config.Config) (Storage, error) {
	backend := cfg.StorageBackend
	if backend == "" {
		if cfg.S3Bucket != "" {
			backend = "s3"
		} else {
			backend = "local"
		}
	}
	switch backend {
	case "s3":
		if cfg.S3Bucket == "" {
			return nil, fmt.Errorf("storage: S3_BUCKET is required when STORAGE_BACKEND=s3")
		}
		return NewS3(cfg)
	case "local":
		return NewLocal(cfg)
	default:
		return nil, fmt.Errorf("storage: unknown backend %q (expected local|s3)", backend)
	}
}
