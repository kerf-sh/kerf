package distributors

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"golang.org/x/time/rate"

	"github.com/imranp/kerf/backend/internal/auth"
	"github.com/imranp/kerf/backend/internal/config"
)

// secretDomain is the per-purpose constant mixed into the AES-GCM key.
// Changing this string will invalidate every stored credential.
const secretDomain = "distributor-credentials"

// HTTPTimeout caps every distributor API call. Distributor APIs are
// generally fast but can stall — bounding the wait keeps the refresh
// sweep from accumulating goroutines on a slow upstream.
const HTTPTimeout = 10 * time.Second

// Registry owns the live (decrypted) Service instances plus the rate
// limiter for each. Reload() rebuilds the map from the
// distributor_credentials table; the admin handler invokes this after
// every PUT/DELETE so changes take effect without a server bounce.
type Registry struct {
	pool   *pgxpool.Pool
	cfg    *config.Config
	client *http.Client

	// fxConvert is an optional CNY→USD converter (cloud-only via the
	// FX fetcher). When nil, LCSC returns CNY-priced results which the
	// implementation flags by leaving PriceUSD nil and noting the
	// raw price in Raw.
	fxConvert FXConverter

	mu       sync.RWMutex
	services map[string]Service
	limiters map[string]*rate.Limiter
	meta     map[string]ServiceMeta // last-known DB metadata
}

// FXConverter is the minimal slice of the cloud FX fetcher this
// package needs. Its concrete type lives in cloud/fx — we depend on
// the interface here so the OSS build doesn't pull in cloud code.
type FXConverter interface {
	// Convert returns `amount` of `from` currency in `to` currency.
	// Implementations should use the stored daily rate; ok=false means
	// the rate isn't available and the caller should fall back to
	// returning the un-converted value with a nil PriceUSD.
	Convert(amount float64, from, to string) (out float64, ok bool)
}

// ServiceMeta is the public row description (no secret material) the
// admin handler returns. Mirrors the distributor_credentials table.
type ServiceMeta struct {
	Name       string     `json:"name"`
	Enabled    bool       `json:"enabled"`
	RateLimit  int        `json:"rate_limit_per_minute"`
	LastUsedAt *time.Time `json:"last_used_at,omitempty"`
	HasSecret  bool       `json:"has_secret"`
	UpdatedAt  time.Time  `json:"updated_at"`
}

// New constructs a Registry and performs an initial Reload. A failure
// to load is *non-fatal* at boot: we log and continue with an empty
// service map, since the admin can configure credentials post-boot via
// the UI.
func New(ctx context.Context, cfg *config.Config, pool *pgxpool.Pool, fx FXConverter) *Registry {
	r := &Registry{
		pool:      pool,
		cfg:       cfg,
		client:    &http.Client{Timeout: HTTPTimeout},
		fxConvert: fx,
		services:  map[string]Service{},
		limiters:  map[string]*rate.Limiter{},
		meta:      map[string]ServiceMeta{},
	}
	if err := r.Reload(ctx); err != nil {
		fmt.Printf("distributors: initial load failed: %v (will operate empty until reloaded)\n", err)
	}
	return r
}

// Reload rebuilds the service + rate-limiter maps from the DB. Called
// at boot and after every admin mutation. Holds the write lock for
// the duration of the rebuild so concurrent readers always see a
// consistent snapshot.
func (r *Registry) Reload(ctx context.Context) error {
	rows, err := r.pool.Query(ctx, `
		select name, enabled, secret_encrypted, rate_limit_per_minute, last_used_at, updated_at
		  from distributor_credentials
	`)
	if err != nil {
		return fmt.Errorf("query distributor_credentials: %w", err)
	}
	defer rows.Close()

	nextServices := map[string]Service{}
	nextLimiters := map[string]*rate.Limiter{}
	nextMeta := map[string]ServiceMeta{}

	for rows.Next() {
		var (
			name       string
			enabled    bool
			ciphertext []byte
			limit      int
			lastUsed   *time.Time
			updatedAt  time.Time
		)
		if err := rows.Scan(&name, &enabled, &ciphertext, &limit, &lastUsed, &updatedAt); err != nil {
			return fmt.Errorf("scan distributor row: %w", err)
		}
		nextMeta[name] = ServiceMeta{
			Name:       name,
			Enabled:    enabled,
			RateLimit:  limit,
			LastUsedAt: lastUsed,
			HasSecret:  len(ciphertext) > 0,
			UpdatedAt:  updatedAt,
		}
		if !enabled || len(ciphertext) == 0 {
			continue
		}
		plaintext, err := auth.DecryptSecret(secretDomain, r.cfg.JWTSecret, ciphertext)
		if err != nil {
			// Don't poison the whole reload; log + skip this row.
			fmt.Printf("distributors: decrypt %s: %v (skipping; will need re-entry)\n", name, err)
			continue
		}
		var creds Credentials
		if err := json.Unmarshal([]byte(plaintext), &creds); err != nil {
			fmt.Printf("distributors: parse credentials %s: %v (skipping)\n", name, err)
			continue
		}
		svc, err := r.buildService(name, creds)
		if err != nil {
			fmt.Printf("distributors: build service %s: %v (skipping)\n", name, err)
			continue
		}
		nextServices[name] = svc
		// rate.Limiter takes events/second; convert per-minute to per-second
		// and allow a small burst (= 1/4 of the per-minute budget, min 1)
		// so a burst of refresh calls doesn't trickle one-per-second.
		perSec := float64(limit) / 60.0
		if perSec <= 0 {
			perSec = 1
		}
		burst := limit / 4
		if burst < 1 {
			burst = 1
		}
		nextLimiters[name] = rate.NewLimiter(rate.Limit(perSec), burst)
	}
	if err := rows.Err(); err != nil {
		return fmt.Errorf("iterate distributor rows: %w", err)
	}

	r.mu.Lock()
	r.services = nextServices
	r.limiters = nextLimiters
	r.meta = nextMeta
	r.mu.Unlock()
	return nil
}

// buildService instantiates the per-distributor implementation. Adding
// a new distributor goes here.
func (r *Registry) buildService(name string, creds Credentials) (Service, error) {
	switch name {
	case ProviderDigiKey:
		return newDigiKey(r.client, creds), nil
	case ProviderMouser:
		return newMouser(r.client, creds), nil
	case ProviderLCSC:
		return newLCSC(r.client, creds, r.fxConvert), nil
	default:
		return nil, fmt.Errorf("unknown distributor: %s", name)
	}
}

// Service returns the live Service for `name`, or ErrNotConfigured
// when the distributor isn't enabled. Acquires a rate-limit token
// before returning so the caller doesn't have to think about it.
//
// The returned Service should be used immediately (within the
// surrounding ctx); if the caller needs to make many calls for the
// same distributor in a tight loop they should re-enter Service for
// each one to respect the rate limit.
func (r *Registry) Acquire(ctx context.Context, name string) (Service, error) {
	r.mu.RLock()
	svc, ok := r.services[name]
	lim := r.limiters[name]
	r.mu.RUnlock()
	if !ok || svc == nil {
		return nil, ErrNotConfigured
	}
	if lim != nil {
		if err := lim.Wait(ctx); err != nil {
			return nil, fmt.Errorf("rate limit wait: %w", err)
		}
	}
	return svc, nil
}

// Has reports whether a service is configured AND enabled. Fast — no
// rate-limit acquisition. Used by the per-Part refresh loop to skip
// entries whose distributor isn't wired up.
func (r *Registry) Has(name string) bool {
	r.mu.RLock()
	_, ok := r.services[name]
	r.mu.RUnlock()
	return ok
}

// MarkUsed bumps last_used_at on the row. Called after a successful
// API call so the admin UI can surface "last used 5 minutes ago." Best
// effort: errors are logged but not propagated.
func (r *Registry) MarkUsed(ctx context.Context, name string) {
	if r.pool == nil {
		return
	}
	_, err := r.pool.Exec(ctx,
		`update distributor_credentials set last_used_at = now(), updated_at = now() where name = $1`,
		name)
	if err != nil {
		fmt.Printf("distributors: mark-used %s: %v\n", name, err)
	}
}

// Meta returns a snapshot of every known distributor's metadata. The
// returned slice includes synthetic entries for AllProviders() that
// have no DB row yet (HasSecret=false, Enabled=false) so the admin UI
// can render an "unconfigured" row for each.
func (r *Registry) Meta() []ServiceMeta {
	r.mu.RLock()
	defer r.mu.RUnlock()
	out := make([]ServiceMeta, 0, len(AllProviders()))
	seen := map[string]bool{}
	for _, name := range AllProviders() {
		if m, ok := r.meta[name]; ok {
			out = append(out, m)
		} else {
			out = append(out, ServiceMeta{
				Name:      name,
				Enabled:   false,
				RateLimit: 60,
				HasSecret: false,
			})
		}
		seen[name] = true
	}
	// Future-proof: include any rows for distributors not in
	// AllProviders() (e.g. an experimental one added by a downstream).
	for name, m := range r.meta {
		if !seen[name] {
			out = append(out, m)
		}
	}
	return out
}

// Upsert persists a credential row, encrypting the supplied creds
// payload. Returns the post-write metadata. Reload is the caller's
// responsibility (the admin handler does it).
func (r *Registry) Upsert(ctx context.Context, name string, enabled bool, rateLimitPerMinute int, creds Credentials) (ServiceMeta, error) {
	if err := validateCredentials(name, creds); err != nil {
		return ServiceMeta{}, err
	}
	if rateLimitPerMinute <= 0 {
		rateLimitPerMinute = 60
	}
	plain, err := json.Marshal(creds)
	if err != nil {
		return ServiceMeta{}, fmt.Errorf("encode credentials: %w", err)
	}
	enc, err := auth.EncryptSecret(secretDomain, r.cfg.JWTSecret, string(plain))
	if err != nil {
		return ServiceMeta{}, fmt.Errorf("encrypt credentials: %w", err)
	}
	var (
		updatedAt  time.Time
		lastUsedAt *time.Time
	)
	err = r.pool.QueryRow(ctx, `
		insert into distributor_credentials(name, enabled, secret_encrypted, rate_limit_per_minute)
		values ($1, $2, $3, $4)
		on conflict (name) do update set
		    enabled = excluded.enabled,
		    secret_encrypted = excluded.secret_encrypted,
		    rate_limit_per_minute = excluded.rate_limit_per_minute,
		    updated_at = now()
		returning updated_at, last_used_at
	`, name, enabled, enc, rateLimitPerMinute).Scan(&updatedAt, &lastUsedAt)
	if err != nil {
		return ServiceMeta{}, fmt.Errorf("upsert credential: %w", err)
	}
	return ServiceMeta{
		Name:       name,
		Enabled:    enabled,
		RateLimit:  rateLimitPerMinute,
		LastUsedAt: lastUsedAt,
		HasSecret:  true,
		UpdatedAt:  updatedAt,
	}, nil
}

// Delete removes the credential row entirely. Idempotent — deleting a
// non-existent row is not an error.
func (r *Registry) Delete(ctx context.Context, name string) error {
	_, err := r.pool.Exec(ctx, `delete from distributor_credentials where name = $1`, name)
	if err != nil && !errors.Is(err, pgx.ErrNoRows) {
		return err
	}
	return nil
}

// SetFX swaps in a CNY→USD converter (typically the cloud FX fetcher)
// and reloads the registry so any LCSC service picks it up. Safe to
// call after construction; concurrent callers go through Reload's
// write lock.
func (r *Registry) SetFX(ctx context.Context, fx FXConverter) {
	r.mu.Lock()
	r.fxConvert = fx
	r.mu.Unlock()
	if err := r.Reload(ctx); err != nil {
		fmt.Printf("distributors: SetFX reload failed: %v\n", err)
	}
}

// EnabledNames returns a snapshot of the names that currently resolve
// to a live service. Used by the sync sweep to decide which Part
// distributor entries are worth refreshing.
func (r *Registry) EnabledNames() []string {
	r.mu.RLock()
	defer r.mu.RUnlock()
	names := make([]string, 0, len(r.services))
	for n := range r.services {
		names = append(names, n)
	}
	return names
}
