// Package migrations exposes the OSS SQL migration files via embed.FS so
// the migrate command can be a single self-contained binary (no runtime
// file-path resolution, works under `go install` / `brew install`).
//
// The cloud build has a parallel package at backend/cloud/migrations/
// that's only compiled with `-tags=cloud`. Each migration set is tracked
// in its own table — `schema_migrations` (OSS) and
// `cloud_schema_migrations` (cloud) — so the two streams never interleave.
package migrations

import "embed"

//go:embed *.sql
var FS embed.FS
