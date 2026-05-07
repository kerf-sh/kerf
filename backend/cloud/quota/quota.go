//go:build cloud
// +build cloud

// Package quota gates expensive operations behind balance and storage
// limit checks. Callers in the OSS layer call into these helpers via the
// cloud.Service so the OSS code itself never imports cloud.
package quota

import (
	"context"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// LLMAllowed returns whether the user has positive credit and what their
// current balance is. A balance of exactly zero is rejected — we don't want
// to start a turn we can't bill for at all.
func LLMAllowed(ctx context.Context, pool *pgxpool.Pool, userID string) (allowed bool, balance float64, err error) {
	err = pool.QueryRow(ctx,
		`select credits_usd from cloud_user_balances where user_id = $1`,
		userID,
	).Scan(&balance)
	if err != nil {
		if err == pgx.ErrNoRows {
			// No row yet — user has never topped up.
			return false, 0, nil
		}
		return false, 0, err
	}
	return balance > 0, balance, nil
}

// StorageAllowed returns whether `addBytes` more storage would be allowed
// for the user, plus their current storage footprint in bytes.
//
// Free tier: anything below freeMB is always allowed (so a never-paying
// user with the default project still works). Above the free tier we
// require a positive balance to grow further; runtime monthly settlement
// charges what they used.
func StorageAllowed(
	ctx context.Context,
	pool *pgxpool.Pool,
	userID string,
	freeMB int,
	addBytes int64,
) (allowed bool, currentBytes int64, err error) {
	// Sum the bytes_delta across all storage events. Deletes record
	// negative deltas, so the running sum is the live footprint.
	err = pool.QueryRow(ctx, `
        select coalesce(sum(bytes_delta), 0)::bigint
        from usage_events
        where user_id = $1 and kind = 'storage'
    `, userID).Scan(&currentBytes)
	if err != nil {
		return false, 0, err
	}

	projected := currentBytes + addBytes
	freeBytes := int64(freeMB) * 1024 * 1024
	if projected <= freeBytes {
		return true, currentBytes, nil
	}

	// Above the free tier: require a positive balance.
	var bal float64
	err = pool.QueryRow(ctx,
		`select credits_usd from cloud_user_balances where user_id = $1`,
		userID,
	).Scan(&bal)
	if err != nil {
		if err == pgx.ErrNoRows {
			return false, currentBytes, nil
		}
		return false, currentBytes, err
	}
	return bal > 0, currentBytes, nil
}
