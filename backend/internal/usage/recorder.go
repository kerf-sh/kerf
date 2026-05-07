// Package usage records per-user token + storage events to the
// usage_events table. Lives in OSS so plain `go build` records events
// for visibility ("how much have I burned this month"); cloud builds
// layer billing on top by computing cost + debiting balances.
//
// The functions here never compute USD cost — they leave usd_cost = 0.
// Cloud-side code is responsible for filling that in (and debiting
// cloud_user_balances) by reading the rows it cares about.
package usage

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// RecordToken inserts a token usage event. projectID may be nil for
// project-less calls (currently none — every chat is project-scoped —
// but the column is nullable for forward compat).
func RecordToken(ctx context.Context, pool *pgxpool.Pool, userID string, projectID *string, model string, inputTokens, outputTokens int) error {
	_, err := pool.Exec(ctx, `
		insert into usage_events(user_id, project_id, kind, model, input_tokens, output_tokens)
		values ($1, $2, 'token', $3, $4, $5)
	`, userID, projectID, model, inputTokens, outputTokens)
	return err
}

// RecordStorage inserts a storage delta event. deltaBytes is signed —
// positive on create/grow, negative on shrink/delete — so summing the
// column for a user gives current bytes in use.
func RecordStorage(ctx context.Context, pool *pgxpool.Pool, userID string, projectID *string, deltaBytes int64) error {
	if deltaBytes == 0 {
		return nil
	}
	_, err := pool.Exec(ctx, `
		insert into usage_events(user_id, project_id, kind, bytes_delta)
		values ($1, $2, 'storage', $3)
	`, userID, projectID, deltaBytes)
	return err
}
