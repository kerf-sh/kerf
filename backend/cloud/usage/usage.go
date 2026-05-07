//go:build cloud
// +build cloud

// Package usage records token and storage events to the OSS-shared
// usage_events table and (for token events) atomically debits the cloud
// balance.
//
// The OSS server records the same events for visibility but never debits.
// The cloud build layers debits on top.
package usage

import (
	"context"
	"fmt"
	"log"
	"sync"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// LowBalanceThresholdUSD is the credit balance below which a low-balance
// notification is fired (rate-limited via cloud_email_log to once per
// 24h per user — see email.Mailer.EligibleForLowBalance).
const LowBalanceThresholdUSD = 1.0

// MailerSink is the minimum slice of email.Mailer the usage package
// invokes. Defined as an interface here so this package doesn't import
// backend/cloud/email at the type level (cloud_enabled.go plugs the
// concrete *email.Mailer in via SetMailer at boot).
type MailerSink interface {
	SendTemplate(ctx context.Context, template, recipient, userID string, data map[string]any) error
	EligibleForLowBalance(ctx context.Context, userID string) (bool, error)
}

// mailerMu guards the package-global mailer pointer. SetMailer is called
// once at boot from cloud_enabled.go; usage code reads the value to fire
// low-balance notifications. Plain pointer + mutex is overkill for one
// boot-time write but the lock is cheap and the pattern stays robust if
// the mailer ever becomes hot-swappable.
var (
	mailerMu sync.RWMutex
	mailer   MailerSink
	// notifyAppURL is captured alongside the mailer so the low-balance
	// template can render an absolute "Top up" link without re-threading
	// the config through every RecordTokenEvent call site.
	notifyAppURL string
)

// SetMailer wires the boot-time mailer + the public app URL used in
// low-balance email templates. Pass nil to detach (tests).
func SetMailer(m MailerSink, appURL string) {
	mailerMu.Lock()
	mailer = m
	notifyAppURL = appURL
	mailerMu.Unlock()
}

// RecordTokenEvent inserts a token usage row and atomically debits the
// user's prepaid balance.
//
// Both writes happen in the same transaction so a partial failure can't
// leave the user charged but unrecorded (or vice versa). userID is required;
// projectID is optional (some token events — e.g. assistant-side validation
// — aren't tied to a project).
func RecordTokenEvent(
	ctx context.Context,
	pool *pgxpool.Pool,
	userID string,
	projectID *string,
	model string,
	inTokens, outTokens int,
	costUSD float64,
) error {
	if userID == "" {
		return fmt.Errorf("usage: userID required")
	}
	tx, err := pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if _, err := tx.Exec(ctx, `
        insert into usage_events
            (user_id, project_id, kind, model, input_tokens, output_tokens, usd_cost)
        values ($1, $2, 'token', $3, $4, $5, $6)
    `, userID, projectID, model, inTokens, outTokens, costUSD); err != nil {
		return fmt.Errorf("usage: insert token event: %w", err)
	}

	// cloud_debit_balance is defined in the cloud migration. It upserts
	// against cloud_user_balances, so the row is created on first debit.
	if _, err := tx.Exec(ctx, `select cloud_debit_balance($1, $2)`, userID, costUSD); err != nil {
		return fmt.Errorf("usage: debit: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return err
	}

	// Low-balance notification. Read the post-debit balance and, if it's
	// under the threshold AND we haven't sent a low-balance email to
	// this user in the past 24h, queue one. All errors here are logged
	// and swallowed — billing succeeded, the email is pure UX gravy.
	maybeFireLowBalance(ctx, pool, userID)
	return nil
}

// maybeFireLowBalance is the post-debit hook. Reads current balance,
// dedupes against the email log via Mailer.EligibleForLowBalance (24h
// window), and enqueues a single send. Idempotent — multiple debits
// inside the window collapse to one notification.
func maybeFireLowBalance(ctx context.Context, pool *pgxpool.Pool, userID string) {
	mailerMu.RLock()
	m := mailer
	appURL := notifyAppURL
	mailerMu.RUnlock()
	if m == nil {
		return
	}
	bal, err := BalanceFor(ctx, pool, userID)
	if err != nil {
		log.Printf("usage: balance lookup for low-balance check: %v", err)
		return
	}
	if bal >= LowBalanceThresholdUSD {
		return
	}
	ok, err := m.EligibleForLowBalance(ctx, userID)
	if err != nil {
		log.Printf("usage: low-balance dedup: %v", err)
		return
	}
	if !ok {
		return
	}
	var recipient string
	if err := pool.QueryRow(ctx, `select email from users where id = $1`, userID).Scan(&recipient); err != nil {
		log.Printf("usage: low-balance email lookup: %v", err)
		return
	}
	if recipient == "" {
		return
	}
	if err := m.SendTemplate(ctx, "low_balance", recipient, userID, map[string]any{
		"BalanceUSD": bal,
		"AppURL":     appURL,
	}); err != nil {
		log.Printf("usage: queue low-balance: %v", err)
	}
}

// RecordStorageEvent records a storage delta (positive on add, negative on
// delete). Storage is billed monthly via MonthlyStorageDebit, not at write
// time, so we don't touch cloud_user_balances here.
func RecordStorageEvent(
	ctx context.Context,
	pool *pgxpool.Pool,
	userID string,
	projectID *string,
	deltaBytes int64,
	costUSD float64,
) error {
	if userID == "" {
		return fmt.Errorf("usage: userID required")
	}
	_, err := pool.Exec(ctx, `
        insert into usage_events
            (user_id, project_id, kind, bytes_delta, usd_cost)
        values ($1, $2, 'storage', $3, $4)
    `, userID, projectID, deltaBytes, costUSD)
	if err != nil {
		return fmt.Errorf("usage: insert storage event: %w", err)
	}
	return nil
}

// MonthlyStorageDebit walks all users with a non-zero storage footprint
// and debits a single rolled-up storage charge for the prior calendar month.
//
// TODO(billing): implement once we have a cron infrastructure decision.
// Likely shape: sum daily peak bytes for the month, multiply by
// pricing.StorageDailyCost, debit via cloud_debit_balance, and emit a
// summary 'storage' event with a bytes_delta of 0 so it's auditable.
func MonthlyStorageDebit(ctx context.Context, pool *pgxpool.Pool) error {
	return fmt.Errorf("MonthlyStorageDebit: not implemented")
}

// BalanceFor returns the user's current credit balance in USD. Missing
// rows are treated as zero rather than an error — a brand new user simply
// hasn't topped up yet.
func BalanceFor(ctx context.Context, pool *pgxpool.Pool, userID string) (float64, error) {
	var bal float64
	err := pool.QueryRow(ctx,
		`select credits_usd from cloud_user_balances where user_id = $1`,
		userID,
	).Scan(&bal)
	if err != nil {
		if err == pgx.ErrNoRows {
			return 0, nil
		}
		return 0, err
	}
	return bal, nil
}
