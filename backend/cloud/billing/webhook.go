//go:build cloud
// +build cloud

package billing

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"

	"github.com/jackc/pgx/v5"
)

// webhookEnvelope is the outermost shape Paystack sends. We accept all
// events but only act on a subset; the rest are acknowledged with 200 so
// Paystack stops retrying.
type webhookEnvelope struct {
	Event string          `json:"event"`
	Data  json.RawMessage `json:"data"`
}

type chargeData struct {
	Reference string `json:"reference"`
	Status    string `json:"status"`
	Amount    int    `json:"amount"`
	Currency  string `json:"currency"`
	Customer  struct {
		ID           int64  `json:"id"`
		CustomerCode string `json:"customer_code"`
		Email        string `json:"email"`
	} `json:"customer"`
}

// Webhook handles POST /api/billing/webhook. Public route — auth is the
// HMAC signature, not a session.
//
// Behavior:
//  1. Read raw body (HMAC must be over the exact bytes sent).
//  2. Verify x-paystack-signature.
//  3. Dispatch on event:
//     - charge.success: idempotently mark invoice success and credit balance.
//     - everything else: log + 200 (so Paystack stops retrying).
func (h *Handlers) Webhook(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		writeError(w, http.StatusBadRequest, "read body")
		return
	}
	defer r.Body.Close()

	sig := r.Header.Get("x-paystack-signature")
	if h.Paystack == nil || !h.Paystack.VerifyWebhookSignature(body, sig) {
		// Don't echo why — opaque 401 is intentional.
		writeError(w, http.StatusUnauthorized, "invalid signature")
		return
	}

	var env webhookEnvelope
	if err := json.Unmarshal(body, &env); err != nil {
		writeError(w, http.StatusBadRequest, "decode envelope")
		return
	}

	switch env.Event {
	case "charge.success":
		if err := h.handleChargeSuccess(r, body, env.Data); err != nil {
			// Return 500 so Paystack retries — but still log so the
			// operator sees what's stuck.
			log.Printf("billing/webhook: charge.success: %v", err)
			writeError(w, http.StatusInternalServerError, "processing failed")
			return
		}
	default:
		log.Printf("billing/webhook: ignoring event=%s", env.Event)
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

// handleChargeSuccess runs the success path inside a single transaction.
// Idempotent: if the invoice is already 'success', it returns without
// debiting twice (Paystack retries are common).
func (h *Handlers) handleChargeSuccess(r *http.Request, rawBody []byte, data json.RawMessage) error {
	var d chargeData
	if err := json.Unmarshal(data, &d); err != nil {
		return fmt.Errorf("decode data: %w", err)
	}
	if d.Reference == "" {
		return errors.New("missing reference")
	}

	tx, err := h.Pool.BeginTx(r.Context(), pgx.TxOptions{})
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback(r.Context()) }()

	// Look up the invoice. Lock the row so concurrent webhook deliveries
	// for the same reference can't both apply the credit. We also pull
	// amount_zar + fx_rate so the receipt email can render the same
	// numbers the user agreed to at top-up time (FX may have moved
	// between the topup call and the webhook callback).
	var (
		userID    string
		status    string
		amountUSD float64
		amountZAR float64
		fxRate    float64
	)
	err = tx.QueryRow(r.Context(), `
        select user_id, status, amount_usd, amount_zar, fx_rate
        from cloud_invoices
        where reference = $1
        for update
    `, d.Reference).Scan(&userID, &status, &amountUSD, &amountZAR, &fxRate)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			// Webhook arrived for a reference we don't know about.
			// Could be a different environment hitting our endpoint;
			// treat as no-op so Paystack doesn't retry forever.
			log.Printf("billing/webhook: unknown reference %s — acking", d.Reference)
			return nil
		}
		return fmt.Errorf("invoice lookup: %w", err)
	}
	if status == "success" {
		// Already processed — replay protection.
		return nil
	}

	if _, err := tx.Exec(r.Context(), `
        update cloud_invoices
        set status = 'success',
            paid_at = now(),
            paystack_response = $2::jsonb
        where reference = $1
    `, d.Reference, string(rawBody)); err != nil {
		return fmt.Errorf("invoice update: %w", err)
	}

	// Credit the balance. We use a NEGATIVE debit to avoid duplicating
	// upsert SQL — debit(-x) is a credit of +x. Symmetry with the debit
	// path keeps any future schema changes localized.
	if _, err := tx.Exec(r.Context(),
		`select cloud_debit_balance($1, $2)`, userID, -amountUSD,
	); err != nil {
		return fmt.Errorf("credit balance: %w", err)
	}

	// Capture the customer linkage if we don't have it yet.
	if d.Customer.CustomerCode != "" {
		if _, err := tx.Exec(r.Context(), `
            insert into cloud_paystack_customers(user_id, customer_code, customer_id, email)
            values ($1, $2, $3, $4)
            on conflict (user_id) do update set
                customer_code = excluded.customer_code,
                customer_id = excluded.customer_id,
                email = excluded.email
        `, userID, d.Customer.CustomerCode, d.Customer.ID, d.Customer.Email); err != nil {
			return fmt.Errorf("paystack customer upsert: %w", err)
		}
	}

	if err := tx.Commit(r.Context()); err != nil {
		return err
	}

	// Fire the receipt email AFTER commit so the user only ever gets a
	// receipt for a balance change that actually persisted. The mailer
	// enqueues + returns; the actual SMTP/Resend dispatch happens off
	// this goroutine. Errors are logged and swallowed — a bounced
	// receipt must never block the webhook 200.
	if h.Mailer != nil {
		// Prefer the email on file (account email) over the Paystack
		// customer email; they're usually the same but the account
		// email is the source of truth for transactional sends.
		recipient := d.Customer.Email
		if userEmailLookup, err := userEmail(r.Context(), h.Pool, userID); err == nil && userEmailLookup != "" {
			recipient = userEmailLookup
		}
		if recipient != "" {
			if err := h.Mailer.SendTemplate(r.Context(), "billing_receipt", recipient, userID, map[string]any{
				"AmountUSD": amountUSD,
				"AmountZAR": amountZAR,
				"FXRate":    fxRate,
				"TxID":      d.Reference,
				"AppURL":    h.Cfg.CORSOrigin,
			}); err != nil {
				log.Printf("billing/webhook: queue receipt: %v", err)
			}
		}
	}
	return nil
}
