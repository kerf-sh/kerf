//go:build cloud
// +build cloud

// Package migrations exposes cloud-only SQL migration files via embed.FS.
// Only included in cloud builds — the OSS migrate command never sees
// these files. Tracked in a separate `cloud_schema_migrations` table
// from the OSS `schema_migrations`, so the two streams stay independent
// and the cloud command can be re-run without affecting OSS state.
package migrations

import "embed"

//go:embed *.sql
var FS embed.FS
