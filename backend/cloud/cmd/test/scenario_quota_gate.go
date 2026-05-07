//go:build cloud
// +build cloud

package main

import (
	"context"

	"github.com/imranp/kerf/backend/cloud/quota"
)

// runQuotaGate exercises the balance-and-storage gates that the OSS
// handlers consult before kicking off LLM turns or large file writes.
//
//	LLMAllowed:
//	  balance == 0 → false
//	  balance == 0.50 → true
//
//	StorageAllowed (with FreeStorageMB=50):
//	  current 0, add 1 byte → true (under free tier)
//	  current 60MB-equivalent, add 0 → above free tier; needs balance > 0
func runQuotaGate(ctx context.Context, env *testEnv, suite *Suite) {
	const sc = "quota_gate"
	uid := CloudTestUserID

	// --- LLMAllowed at balance = 0 ---
	if _, err := env.Pool.Exec(ctx, `
        insert into cloud_user_balances(user_id, credits_usd) values ($1, 0)
        on conflict (user_id) do update set credits_usd = excluded.credits_usd
    `, uid); err != nil {
		suite.Failf(sc, "set balance=0: %v", err)
		return
	}
	allowed, balance, err := quota.LLMAllowed(ctx, env.Pool, uid)
	suite.AssertNoError(sc, "LLMAllowed at 0: no error", err)
	suite.AssertEqual(sc, "LLMAllowed at 0: allowed=false", false, allowed)
	suite.AssertFloatNear(sc, "LLMAllowed at 0: balance=0", 0, balance, 0.0001)

	// --- LLMAllowed at balance = 0.50 ---
	if _, err := env.Pool.Exec(ctx,
		`update cloud_user_balances set credits_usd = 0.50 where user_id = $1`, uid); err != nil {
		suite.Failf(sc, "set balance=0.50: %v", err)
		return
	}
	allowed, balance, err = quota.LLMAllowed(ctx, env.Pool, uid)
	suite.AssertNoError(sc, "LLMAllowed at 0.50: no error", err)
	suite.AssertEqual(sc, "LLMAllowed at 0.50: allowed=true", true, allowed)
	suite.AssertFloatNear(sc, "LLMAllowed at 0.50: balance=0.50", 0.5, balance, 0.0001)

	// --- StorageAllowed: under free tier (50MB default) ---
	allowedS, current, err := quota.StorageAllowed(ctx, env.Pool, uid, env.Cfg.Cloud.Pricing.FreeStorageMB, 1)
	suite.AssertNoError(sc, "StorageAllowed under free: no error", err)
	suite.AssertEqual(sc, "StorageAllowed under free: allowed=true", true, allowedS)
	suite.AssertEqual(sc, "StorageAllowed under free: current=0", int64(0), current)

	// --- StorageAllowed: above free tier without balance ---
	// Push current usage above 50MB by inserting a usage_event with a big
	// bytes_delta. We need a project to satisfy the FK on project_id —
	// but project_id is nullable so we omit it.
	const overFreeBytes = int64(60 * 1024 * 1024)
	if _, err := env.Pool.Exec(ctx, `
        insert into usage_events(user_id, kind, bytes_delta) values ($1, 'storage', $2)
    `, uid, overFreeBytes); err != nil {
		suite.Failf(sc, "seed storage event: %v", err)
		return
	}
	// Drop balance to 0 again so the gate denies above-free expansion.
	if _, err := env.Pool.Exec(ctx,
		`update cloud_user_balances set credits_usd = 0 where user_id = $1`, uid); err != nil {
		suite.Failf(sc, "set balance=0 (storage check): %v", err)
		return
	}
	allowedS, current, err = quota.StorageAllowed(ctx, env.Pool, uid, env.Cfg.Cloud.Pricing.FreeStorageMB, 1)
	suite.AssertNoError(sc, "StorageAllowed over free, balance=0: no error", err)
	suite.AssertEqual(sc, "StorageAllowed over free, balance=0: allowed=false", false, allowedS)
	suite.AssertEqual(sc, "StorageAllowed over free: current=60MB", overFreeBytes, current)

	// --- StorageAllowed: above free tier WITH balance → allowed ---
	if _, err := env.Pool.Exec(ctx,
		`update cloud_user_balances set credits_usd = 1.00 where user_id = $1`, uid); err != nil {
		suite.Failf(sc, "set balance=1.00 (storage check): %v", err)
		return
	}
	allowedS, _, err = quota.StorageAllowed(ctx, env.Pool, uid, env.Cfg.Cloud.Pricing.FreeStorageMB, 1)
	suite.AssertNoError(sc, "StorageAllowed over free, balance=1: no error", err)
	suite.AssertEqual(sc, "StorageAllowed over free, balance=1: allowed=true", true, allowedS)
}
