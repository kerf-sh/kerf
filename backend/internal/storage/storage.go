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
	// PublicURL returns a public-facing URL for the given key. When
	// cfg.Storage.CDNBaseURL is set, returns "<cdn>/<key>?v=<unix>".
	// Otherwise returns "/api/blobs/<key>?v=<unix>". The cache-buster is
	// optional — pass time.Time{} (zero) to omit. The local backend always
	// emits the /api/blobs/ route since blobs are auth-protected; the s3
	// backend prefers cdn_base, falls back to public_url_base, otherwise
	// returns the virtual-hosted s3 URL.
	PublicURL(key string, updatedAt time.Time) string

	// --- Chunked upload helpers (Phase 2) -------------------------------
	//
	// uploadKey is an opaque identifier scoped to one in-flight upload —
	// for the local backend it doubles as a temp directory name; for S3
	// it's the upload session id used to look up the multipart upload id.
	// chunkIndex is 0-based.

	// PutChunk stores chunk #chunkIndex of an upload. body is a contiguous
	// byte stream for that chunk; the implementation reads it to EOF.
	PutChunk(ctx context.Context, uploadKey string, chunkIndex int, body io.Reader) error
	// ListChunks returns the indices already received, sorted ascending.
	ListChunks(ctx context.Context, uploadKey string) ([]int, error)
	// ConcatChunksTo assembles all received chunks (in index order) into a
	// single object at dstKey, returning the total byte count written.
	// The implementation may stream chunks directly without re-reading.
	ConcatChunksTo(ctx context.Context, uploadKey string, dstKey string) (int64, error)
	// DeleteUpload wipes all temp state for an upload (chunks, multipart
	// abort, etc). Idempotent: missing uploads are not an error.
	DeleteUpload(ctx context.Context, uploadKey string) error
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
	case "filesystem":
		// Filesystem mode mirrors user-facing files to disk via the
		// filesystem.Mirror; binary assets (STEP uploads, thumbnails)
		// don't have a good "real-file" representation, so they keep
		// using the local blob backend at cfg.LocalStoragePath.
		return NewLocal(cfg)
	default:
		return nil, fmt.Errorf("storage: unknown backend %q (expected local|s3|filesystem)", backend)
	}
}
