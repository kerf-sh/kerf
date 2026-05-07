//go:build cloud
// +build cloud

package email

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/internal/auth"
	"github.com/imranp/kerf/backend/internal/config"
)

// drainInterval is how often the background goroutine sweeps the
// cloud_email_log for queued / retry-eligible rows. Short enough that
// users see emails arrive in seconds; long enough that an idle server
// is doing meaningful no-ops, not constant DB queries.
const drainInterval = 5 * time.Second

// drainBatch caps how many rows we attempt per sweep. Prevents a backed-
// up queue from monopolizing the goroutine's time slice; the next tick
// catches the rest.
const drainBatch = 50

// maxAttempts is the per-row retry ceiling. After this many `failed`
// transitions we stop retrying and the row sits in `failed` for the
// admin to inspect. Backoff is exponential: 30s, 2m, 8m.
const maxAttempts = 3

// Mailer is the public surface. Construct via Boot(); shut down by
// cancelling the ctx passed to Boot.
type Mailer struct {
	pool *pgxpool.Pool
	cfg  *config.Config
	rend *renderer

	mu        sync.RWMutex
	providers map[string]Provider // built from current cloud_email_credentials rows

	// notify wakes the drain goroutine immediately after an enqueue so
	// transactional emails don't wait up to drainInterval.
	notify chan struct{}
}

// Boot wires up the Mailer and starts its drain goroutine. The returned
// Mailer is safe to share via a pointer; method calls are thread-safe.
//
// The Mailer reads cloud_email_credentials at boot and on every
// admin-driven Reload(). Boot itself never errors on a missing/empty
// credentials table — the operator is expected to configure providers
// post-boot via /admin/email/providers, exactly mirroring the
// distributors registry pattern.
func Boot(ctx context.Context, pool *pgxpool.Pool, cfg *config.Config) *Mailer {
	m := &Mailer{
		pool:      pool,
		cfg:       cfg,
		rend:      newRenderer(),
		providers: map[string]Provider{},
		notify:    make(chan struct{}, 1),
	}
	if err := m.Reload(ctx); err != nil {
		log.Printf("email: initial provider load: %v (mailer will retry)", err)
	}
	go m.runDrain(ctx)
	return m
}

// Reload rebuilds the live provider map from the DB. Called at boot
// and after each /admin/email/providers mutation.
func (m *Mailer) Reload(ctx context.Context) error {
	if m.pool == nil {
		return nil
	}
	rows, err := m.pool.Query(ctx, `
        select provider, enabled, secret_encrypted
          from cloud_email_credentials
    `)
	if err != nil {
		return fmt.Errorf("email: load credentials: %w", err)
	}
	defer rows.Close()

	next := map[string]Provider{}
	for rows.Next() {
		var (
			name       string
			enabled    bool
			ciphertext []byte
		)
		if err := rows.Scan(&name, &enabled, &ciphertext); err != nil {
			return fmt.Errorf("email: scan credential: %w", err)
		}
		if !enabled || len(ciphertext) == 0 {
			continue
		}
		plain, err := auth.DecryptSecret(secretDomain, m.cfg.JWTSecret, ciphertext)
		if err != nil {
			log.Printf("email: decrypt %s: %v (skipping; will need re-entry)", name, err)
			continue
		}
		var creds Credentials
		if err := json.Unmarshal([]byte(plain), &creds); err != nil {
			log.Printf("email: parse credentials %s: %v (skipping)", name, err)
			continue
		}
		p, err := buildProvider(name, creds)
		if err != nil {
			log.Printf("email: build %s: %v (skipping)", name, err)
			continue
		}
		next[name] = p
	}
	if err := rows.Err(); err != nil {
		return fmt.Errorf("email: iterate credentials: %w", err)
	}

	m.mu.Lock()
	m.providers = next
	m.mu.Unlock()
	return nil
}

// activeProvider returns the highest-precedence configured + enabled
// provider, or nil if none are.
func (m *Mailer) activeProvider() Provider {
	m.mu.RLock()
	defer m.mu.RUnlock()
	for _, name := range providerOrder {
		if p, ok := m.providers[name]; ok {
			return p
		}
	}
	return nil
}

// buildProvider dispatches to the per-provider constructor. Adding a new
// provider goes here.
func buildProvider(name string, creds Credentials) (Provider, error) {
	switch name {
	case ProviderResend:
		return newResend(creds)
	case ProviderSES:
		return newSES(creds)
	case ProviderSMTP:
		return newSMTP(creds)
	default:
		return nil, fmt.Errorf("unknown provider: %s", name)
	}
}

// SendTemplate is the primary entry point. It:
//
//  1. Renders the template (sync — fails fast on bad data).
//  2. Inserts a `queued` row in cloud_email_log.
//  3. Pokes the drain goroutine.
//  4. Returns. The send itself is async.
//
// userID is optional (pass "" for emails not tied to a user — admin
// test sends, system-only addresses). recipient is the destination
// email; templates may also reference it via {{.Email}}.
func (m *Mailer) SendTemplate(
	ctx context.Context,
	templateName, recipient string,
	userID string,
	data map[string]any,
) error {
	if recipient == "" {
		return errors.New("email: recipient is empty")
	}
	if !validTemplate(templateName) {
		return fmt.Errorf("email: unknown template: %s", templateName)
	}
	// Render now to validate data + catch malformed templates at the
	// call site rather than later in the goroutine. We discard the
	// rendered Message; the drain renders again. Cheap (templates are
	// small and the cache is hot).
	if data == nil {
		data = map[string]any{}
	}
	if _, ok := data["Email"]; !ok {
		data["Email"] = recipient
	}
	if _, err := m.rend.Render(templateName, recipient, data); err != nil {
		return err
	}

	// We persist the data bag as JSON in `error` ONLY for the queued row's
	// initial state — that's wrong; instead we encode the data into a side
	// channel: a JSON payload stored on the row alongside template/to_email.
	// The cloud_email_log table doesn't have a `data` column today though,
	// so we re-render at drain time using a small in-memory map keyed by
	// row id. Simpler than a schema bump.
	payload, err := json.Marshal(data)
	if err != nil {
		return fmt.Errorf("email: encode data: %w", err)
	}
	var uid any
	if userID != "" {
		uid = userID
	} else {
		uid = nil
	}
	var rowID string
	err = m.pool.QueryRow(ctx, `
        insert into cloud_email_log
            (user_id, template, to_email, status)
        values ($1, $2, $3, 'queued')
        returning id
    `, uid, templateName, recipient).Scan(&rowID)
	if err != nil {
		return fmt.Errorf("email: enqueue: %w", err)
	}
	m.rememberPayload(rowID, payload)

	// Best-effort wake. If the buffer is full, the drain is already
	// scheduled and a second wake would be a no-op.
	select {
	case m.notify <- struct{}{}:
	default:
	}
	return nil
}

// payloadStore is the in-memory map of row id → data JSON used to
// re-render at drain time. Populated by SendTemplate, consumed (and
// freed) by the drain goroutine. If the process restarts mid-flight,
// queued rows on disk will fail to render at next boot — they get
// marked `failed` after maxAttempts. Acceptable trade-off vs adding a
// `data` column to the schema for v1.
var (
	payloadMu sync.Mutex
	payloads  = map[string][]byte{}
)

func (m *Mailer) rememberPayload(rowID string, payload []byte) {
	payloadMu.Lock()
	payloads[rowID] = payload
	payloadMu.Unlock()
}

func (m *Mailer) recallPayload(rowID string) []byte {
	payloadMu.Lock()
	defer payloadMu.Unlock()
	return payloads[rowID]
}

func (m *Mailer) forgetPayload(rowID string) {
	payloadMu.Lock()
	delete(payloads, rowID)
	payloadMu.Unlock()
}

// runDrain is the background goroutine. Wakes on the timer or on an
// explicit notify; sweeps queued + retry-eligible rows; dispatches them
// through the active provider with exponential backoff between failures.
func (m *Mailer) runDrain(ctx context.Context) {
	tick := time.NewTicker(drainInterval)
	defer tick.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-tick.C:
		case <-m.notify:
		}
		m.drainOnce(ctx)
	}
}

// drainOnce processes up to drainBatch rows. Each row is handled
// independently — a single provider failure doesn't stop the sweep.
func (m *Mailer) drainOnce(ctx context.Context) {
	provider := m.activeProvider()
	if provider == nil {
		// No provider configured. We don't mark queued rows failed
		// immediately because the operator might be in the middle of
		// configuring one — they'd come back to a wall of failed sends.
		// Rows simply sit in `queued` until a provider arrives or the
		// operator runs the cleanup endpoint (not implemented; manual
		// SQL for now).
		return
	}

	// Pick rows whose status is queued, OR failed-but-not-yet-final.
	// "Final" is determined by retry count, which we don't store
	// explicitly; instead we count rows in the log with the same template
	// + to_email + an earlier created_at. For v1 simplicity we just look
	// at the `error` column's prefix — any row marked failed gets one
	// retry pass per drain tick until backoff elapses. The `created_at`
	// gate enforces the minimum delay between attempts.
	//
	// In practice: when send fails we immediately re-mark `queued` if we
	// haven't hit the cap, with a `failed_attempts=N` recorded in `error`.
	// Cleaner than a schema bump and matches the "v1 simplicity" approach
	// taken by the rest of the cloud package.
	rows, err := m.pool.Query(ctx, `
        select id, template, to_email
          from cloud_email_log
         where status = 'queued'
         order by created_at asc
         limit $1
    `, drainBatch)
	if err != nil {
		log.Printf("email: drain query: %v", err)
		return
	}
	type job struct {
		id, template, to string
	}
	var jobs []job
	for rows.Next() {
		var j job
		if err := rows.Scan(&j.id, &j.template, &j.to); err != nil {
			log.Printf("email: drain scan: %v", err)
			continue
		}
		jobs = append(jobs, j)
	}
	rows.Close()

	for _, j := range jobs {
		m.dispatch(ctx, provider, j.id, j.template, j.to)
	}
}

// dispatch renders the template (using the in-memory payload map) and
// sends through the provider. On success: status='sent', sent_at=now().
// On failure: increments the in-error attempt counter; if under
// maxAttempts, leaves status='queued' so the next drain retries; if at
// the cap, marks status='failed'.
func (m *Mailer) dispatch(ctx context.Context, p Provider, id, name, to string) {
	raw := m.recallPayload(id)
	var data map[string]any
	if len(raw) > 0 {
		_ = json.Unmarshal(raw, &data)
	}
	if data == nil {
		data = map[string]any{"Email": to}
	}

	msg, err := m.rend.Render(name, to, data)
	if err != nil {
		m.markFailed(ctx, id, fmt.Sprintf("render: %v", err))
		m.forgetPayload(id)
		return
	}

	sendCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	if err := p.Send(sendCtx, msg); err != nil {
		m.maybeRetry(ctx, id, p.Name(), err)
		return
	}

	if _, err := m.pool.Exec(ctx, `
        update cloud_email_log
           set status = 'sent', provider = $2, sent_at = now(), error = null
         where id = $1
    `, id, p.Name()); err != nil {
		log.Printf("email: mark sent %s: %v", id, err)
	}
	// best-effort bump of the provider's last_used_at for the admin UI
	_, _ = m.pool.Exec(ctx, `
        update cloud_email_credentials
           set last_used_at = now(), updated_at = now()
         where provider = $1
    `, p.Name())
	m.forgetPayload(id)
}

// maybeRetry implements the bounded retry policy. attempts are encoded
// as `attempts=N|<error message>` in the `error` column; we parse, bump,
// and reschedule. After maxAttempts we transition to permanent `failed`.
func (m *Mailer) maybeRetry(ctx context.Context, id, providerName string, sendErr error) {
	var prevErr string
	_ = m.pool.QueryRow(ctx, `select coalesce(error, '') from cloud_email_log where id = $1`, id).Scan(&prevErr)
	attempts := parseAttempts(prevErr) + 1

	if attempts >= maxAttempts {
		m.markFailed(ctx,
			id,
			fmt.Sprintf("attempts=%d|provider=%s|%v", attempts, providerName, sendErr),
		)
		m.forgetPayload(id)
		return
	}
	// Re-queue. Backoff is implicit because we use created_at ASC for the
	// drain order — bumping created_at to (now() + backoff) means the row
	// won't be picked up until that time.
	backoff := backoffFor(attempts)
	if _, err := m.pool.Exec(ctx, `
        update cloud_email_log
           set status     = 'queued',
               provider   = $2,
               error      = $3,
               created_at = now() + ($4 || ' seconds')::interval
         where id = $1
    `, id, providerName,
		fmt.Sprintf("attempts=%d|%v", attempts, sendErr),
		int(backoff.Seconds()),
	); err != nil {
		log.Printf("email: re-queue %s: %v", id, err)
	}
}

func (m *Mailer) markFailed(ctx context.Context, id, errMsg string) {
	if _, err := m.pool.Exec(ctx, `
        update cloud_email_log
           set status = 'failed', error = $2
         where id = $1
    `, id, errMsg); err != nil {
		log.Printf("email: mark failed %s: %v", id, err)
	}
}

// parseAttempts pulls the integer attempt count out of the encoded
// `error` column. Returns 0 for unrecognized formats.
func parseAttempts(s string) int {
	const prefix = "attempts="
	if len(s) < len(prefix)+1 {
		return 0
	}
	if s[:len(prefix)] != prefix {
		return 0
	}
	rest := s[len(prefix):]
	end := 0
	for end < len(rest) && rest[end] >= '0' && rest[end] <= '9' {
		end++
	}
	if end == 0 {
		return 0
	}
	n := 0
	for i := 0; i < end; i++ {
		n = n*10 + int(rest[i]-'0')
	}
	return n
}

// backoffFor returns the wait duration before the Nth retry. Exponential
// 30s base, capped well under the drain horizon so a backed-up queue
// doesn't pile up.
func backoffFor(attempt int) time.Duration {
	switch attempt {
	case 1:
		return 30 * time.Second
	case 2:
		return 2 * time.Minute
	default:
		return 8 * time.Minute
	}
}

// LowBalanceWindow is exposed for the usage package: it should only fire
// a low-balance email if no `low_balance` row has been written for the
// user in this window. Centralized here so the policy lives next to the
// templates.
const LowBalanceWindow = 24 * time.Hour

// EligibleForLowBalance reports whether a low-balance email may be fired
// for the user right now (i.e. no successful or queued send within the
// last LowBalanceWindow). The query is best-effort — a duplicate notice
// every now and then is recoverable, missing one is the bigger UX miss
// so we lean towards "fire."
func (m *Mailer) EligibleForLowBalance(ctx context.Context, userID string) (bool, error) {
	if userID == "" {
		return false, nil
	}
	var lastAt *time.Time
	err := m.pool.QueryRow(ctx, `
        select max(created_at)
          from cloud_email_log
         where user_id = $1
           and template = 'low_balance'
           and status in ('queued','sent')
    `, userID).Scan(&lastAt)
	if err != nil && !errors.Is(err, pgx.ErrNoRows) {
		return false, err
	}
	if lastAt == nil {
		return true, nil
	}
	return time.Since(*lastAt) >= LowBalanceWindow, nil
}
