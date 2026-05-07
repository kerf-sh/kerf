//go:build cloud
// +build cloud

// Package git implements real version control on top of the live editor
// for the cloud (hosted) tier. The DB's `files` table remains the
// canonical store for what the user is currently editing; this package
// adds a deliberate "save this version" feature backed by a real bare
// git repo PER PROJECT and optional GitHub sync.
//
// All Go files here are gated by the `cloud` build tag. The OSS
// `file_revisions` undo layer (backend/migrations/* + handlers/revisions.go)
// is untouched and continues to provide always-on undo.
//
// Storage layout (S3-compatible object store, NOT disk):
//
//	<cfg.S3Bucket>/<cfg.Cloud.Git.Prefix>/<project_id>/   — bare repo
//
// Each project's bare repo is a tree of S3 objects mirroring a `.git/`
// directory: `objects/<aa>/<rest>`, `refs/heads/<name>`, `HEAD`,
// `config`, etc. We layer a `billy.Filesystem` over S3 (see billyfs.go)
// and feed it to go-git's `storage/filesystem` backend, which handles
// every git object semantic on top of whatever filesystem you give it.
//
// `cloud_git_repos`, `cloud_git_branches`, and `cloud_git_commits` in
// Postgres mirror metadata for fast graph rendering. The bare repo is
// authoritative for object content; the cache is best-effort and is
// refreshed on every mutating operation (commit, branch, merge, pull).
//
// This design is fully stateless: a fresh container can serve any
// project's git ops without any local on-disk state. Cross-container
// safety for ref updates is provided by S3 conditional PUTs in the
// billyfs layer (see billyfs.go).
package git

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"

	"github.com/aws/aws-sdk-go-v2/aws"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/internal/config"
	"github.com/imranp/kerf/backend/internal/storage"
)

// Service is the long-lived handle. Constructed once by cloud_enabled.go
// and shared across requests. The per-project mutex map serializes
// mutating ops on the same project so a commit and a checkout don't
// step on each other within one process; cross-process safety for refs
// is handled by S3 conditional PUTs (billyfs.go).
type Service struct {
	Cfg     *config.Config
	Pool    *pgxpool.Pool
	Storage storage.Storage

	// Mailer is the optional transactional-email sink. The OAuth callback
	// fires a "github_linked" notification through it. nil disables that
	// branch — set by cloud_enabled.go after Boot, kept out of New() so
	// the construction sequence stays linear (mailer would have to exist
	// before git, which is the wrong direction for boot ordering when
	// future mailer init grows DB dependencies).
	Mailer mailerSink

	// s3 is the S3 client used to back per-project billy filesystems.
	// We construct our own (rather than reaching into the OSS Storage
	// implementation) so this service works whether or not the OSS
	// blob backend is also using S3 — and so we don't import OSS
	// internals.
	s3     *s3.Client
	bucket string

	// prefix is the trimmed S3 key prefix under which all per-project
	// repo trees live. E.g. "git" → keys like "git/<pid>/HEAD".
	prefix string

	// projectLocks is a sync.Map keyed by project_id (string) with
	// values of type *sync.Mutex. Allocated lazily on first lock to
	// avoid bloating memory for projects that never enable git.
	projectLocks sync.Map
}

// mailerSink is the minimum slice of *email.Mailer the git OAuth flow
// uses. Defined locally so this package doesn't import backend/cloud/email
// at the type level (the concrete value is plugged in by cloud_enabled.go,
// which already imports both packages).
type mailerSink interface {
	SendTemplate(ctx context.Context, template, recipient, userID string, data map[string]any) error
}

// New constructs the service against the configured S3 bucket. It does
// not touch any project repos; those are created lazily by /init or
// /import.
//
// Storage is the OSS blob backend — the snapshotter reads from it for
// files with non-empty storage_key (e.g. uploaded STEP binaries) so
// every commit captures the full project state, text + binary alike.
//
// Required config: cfg.S3Bucket (we share the bucket with the OSS
// storage layer) and S3 credentials. cfg.Cloud.Git.Prefix is the key
// prefix (default "git"). If the bucket is empty, returns a clear error
// — callers should ensure storage.backend is set to "s3" in cloud
// deployments.
func New(cfg *config.Config, pool *pgxpool.Pool, store storage.Storage) (*Service, error) {
	if cfg == nil {
		return nil, errors.New("git.New: nil config")
	}
	if pool == nil {
		return nil, errors.New("git.New: nil pool")
	}
	if cfg.S3Bucket == "" {
		return nil, errors.New("git.New: cloud git requires storage.s3.bucket to be set (the bucket is shared with the OSS blob layer)")
	}
	prefix := strings.Trim(cfg.Cloud.Git.Prefix, "/")
	if prefix == "" {
		prefix = "git"
	}

	client, err := buildS3Client(cfg)
	if err != nil {
		return nil, fmt.Errorf("git.New: build s3 client: %w", err)
	}

	return &Service{
		Cfg:     cfg,
		Pool:    pool,
		Storage: store,
		s3:      client,
		bucket:  cfg.S3Bucket,
		prefix:  prefix,
	}, nil
}

// buildS3Client mirrors the OSS storage/s3.NewS3 client construction so
// the cloud git service works against any S3-compatible endpoint
// (AWS S3, Cloudflare R2, MinIO, etc.). We deliberately do NOT depend
// on internals of the OSS storage package — both layers go through the
// same public AWS SDK.
func buildS3Client(cfg *config.Config) (*s3.Client, error) {
	ctx := context.Background()
	loaders := []func(*awsconfig.LoadOptions) error{}
	if cfg.S3Region != "" {
		loaders = append(loaders, awsconfig.WithRegion(cfg.S3Region))
	}
	if cfg.S3AccessKeyID != "" && cfg.S3SecretAccessKey != "" {
		loaders = append(loaders, awsconfig.WithCredentialsProvider(
			credentials.NewStaticCredentialsProvider(cfg.S3AccessKeyID, cfg.S3SecretAccessKey, ""),
		))
	}
	awsCfg, err := awsconfig.LoadDefaultConfig(ctx, loaders...)
	if err != nil {
		return nil, err
	}
	clientOpts := []func(*s3.Options){}
	if cfg.S3Endpoint != "" {
		ep := cfg.S3Endpoint
		clientOpts = append(clientOpts, func(o *s3.Options) {
			o.BaseEndpoint = aws.String(ep)
			o.UsePathStyle = true
		})
	}
	return s3.NewFromConfig(awsCfg, clientOpts...), nil
}

// lockProject returns the project's mutex, allocating one on first call.
// Mutating handlers must hold the lock for the duration of the op so a
// concurrent checkout/commit/merge/push/pull can't interleave WITHIN
// the same container. Across containers, the conditional-PUT lock-file
// path in billyfs.go is what protects ref updates.
func (s *Service) lockProject(projectID string) *sync.Mutex {
	if v, ok := s.projectLocks.Load(projectID); ok {
		return v.(*sync.Mutex)
	}
	m := &sync.Mutex{}
	actual, _ := s.projectLocks.LoadOrStore(projectID, m)
	return actual.(*sync.Mutex)
}
