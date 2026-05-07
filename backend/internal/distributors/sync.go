package distributors

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// PartDistributor mirrors the on-disk Part shape for the distributor
// list. Defined here (rather than imported from handlers/tools) to
// keep this package leaf-style — the sync sweep parses Part JSON
// itself and writes it back through the same code path the LLM tools
// use (a plain UPDATE on files.content + a revision row).
type PartDistributor struct {
	Name      string   `json:"name"`
	SKU       string   `json:"sku,omitempty"`
	URL       string   `json:"url"`
	PriceUSD  *float64 `json:"price_usd,omitempty"`
	Stock     *int     `json:"stock,omitempty"`
	FetchedAt string   `json:"fetched_at,omitempty"`
}

// StalePartAge is how old a distributor entry's fetched_at must be
// before the background sweep re-pulls it. Aligned with the spec:
// 24 hours is the right cadence for prices, more frequent than that
// burns rate-limit budget without much benefit.
const StalePartAge = 24 * time.Hour

// SweepInterval is the cadence of the boot-time goroutine that walks
// every Part and refreshes stale distributor entries.
const SweepInterval = 6 * time.Hour

// RefreshPart updates every distributor entry on `partJSON` whose name
// matches an enabled service. Returns the (possibly-mutated) Part JSON
// and the count of updated entries.
//
// On a per-entry failure we log + continue so one bad SKU doesn't block
// the others. The Part is rewritten only if at least one entry was
// touched, so a Part with all-stale lookups doesn't churn revisions.
func RefreshPart(ctx context.Context, reg *Registry, partJSON string) (string, int, error) {
	if reg == nil || strings.TrimSpace(partJSON) == "" {
		return partJSON, 0, nil
	}
	// Parse loose — we want to preserve unknown fields (metadata, photos,
	// etc.) so we round-trip through json.RawMessage.
	var doc map[string]json.RawMessage
	if err := json.Unmarshal([]byte(partJSON), &doc); err != nil {
		return partJSON, 0, fmt.Errorf("parse part json: %w", err)
	}
	rawDist, ok := doc["distributors"]
	if !ok {
		return partJSON, 0, nil
	}
	var dists []PartDistributor
	if err := json.Unmarshal(rawDist, &dists); err != nil {
		return partJSON, 0, fmt.Errorf("parse distributors: %w", err)
	}
	if len(dists) == 0 {
		return partJSON, 0, nil
	}

	// Pull the part name + manufacturer + mpn from the doc so we can
	// fall back to a Search if a distributor entry has no SKU yet.
	var (
		mpn          string
		manufacturer string
		name         string
	)
	if v, ok := doc["mpn"]; ok {
		_ = json.Unmarshal(v, &mpn)
	}
	if v, ok := doc["manufacturer"]; ok {
		_ = json.Unmarshal(v, &manufacturer)
	}
	if v, ok := doc["name"]; ok {
		_ = json.Unmarshal(v, &name)
	}

	updated := 0
	for i := range dists {
		entry := &dists[i]
		if !reg.Has(entry.Name) {
			continue
		}
		svc, err := reg.Acquire(ctx, entry.Name)
		if err != nil {
			log.Printf("distributors: acquire %s for sku %q: %v", entry.Name, entry.SKU, err)
			continue
		}
		var (
			result *DistributorPart
		)
		if entry.SKU != "" {
			result, err = svc.Lookup(ctx, entry.SKU)
		} else {
			fallback := mpn
			if fallback == "" {
				fallback = strings.TrimSpace(manufacturer + " " + name)
			}
			if fallback == "" {
				continue
			}
			results, serr := svc.Search(ctx, fallback, 1)
			if serr != nil {
				err = serr
			} else if len(results) > 0 {
				result = results[0]
			}
		}
		if err != nil || result == nil {
			if err != nil {
				log.Printf("distributors: lookup %s/%s: %v", entry.Name, entry.SKU, err)
			}
			continue
		}
		// Track usage — best effort.
		reg.MarkUsed(ctx, entry.Name)

		// Mutate the entry in place. Preserve URL when the API returns
		// an empty one (some calls don't include it).
		if result.URL != "" {
			entry.URL = result.URL
		}
		if result.SKU != "" {
			entry.SKU = result.SKU
		}
		entry.PriceUSD = result.PriceUSD
		entry.Stock = result.Stock
		entry.FetchedAt = result.FetchedAt.UTC().Format(time.RFC3339)
		updated++
	}

	if updated == 0 {
		return partJSON, 0, nil
	}

	// Re-marshal the distributors slice back into the document.
	rawNew, err := json.Marshal(dists)
	if err != nil {
		return partJSON, updated, fmt.Errorf("encode distributors: %w", err)
	}
	doc["distributors"] = rawNew
	out, err := json.MarshalIndent(doc, "", "  ")
	if err != nil {
		return partJSON, updated, fmt.Errorf("encode part: %w", err)
	}
	return string(out), updated, nil
}

// RefreshAllParts walks every Part whose distributor entries are
// stale (or have no fetched_at), refreshes them through the registry,
// and writes the updated content back. Bounded per-iteration scan so
// a long backlog doesn't block the next tick.
//
// `recordRevision` is the caller-supplied function that records a
// revision row for the updated file — we delegate so the sync package
// stays free of the revision-recording dep cycle (handlers depend on
// tools depend on llm).
func RefreshAllParts(ctx context.Context, pool *pgxpool.Pool, reg *Registry, recordRevision RecordRevisionFn) (int, error) {
	if reg == nil || len(reg.EnabledNames()) == 0 {
		return 0, nil
	}
	rows, err := pool.Query(ctx, `
		select id, content
		  from files
		 where kind = 'part' and deleted_at is null
		 order by updated_at desc
		 limit 500
	`)
	if err != nil {
		return 0, fmt.Errorf("query parts: %w", err)
	}
	defer rows.Close()

	type candidate struct {
		ID      string
		Content string
	}
	var pending []candidate
	for rows.Next() {
		var c candidate
		if err := rows.Scan(&c.ID, &c.Content); err != nil {
			return 0, fmt.Errorf("scan part row: %w", err)
		}
		if isStale(c.Content) {
			pending = append(pending, c)
		}
	}
	if err := rows.Err(); err != nil {
		return 0, err
	}
	rows.Close()

	updated := 0
	for _, c := range pending {
		select {
		case <-ctx.Done():
			return updated, ctx.Err()
		default:
		}
		newContent, n, err := RefreshPart(ctx, reg, c.Content)
		if err != nil {
			log.Printf("distributors: refresh part %s: %v", c.ID, err)
			continue
		}
		if n == 0 {
			continue
		}
		if _, err := pool.Exec(ctx,
			`update files set content = $2, updated_at = now() where id = $1 and deleted_at is null`,
			c.ID, newContent); err != nil {
			log.Printf("distributors: write part %s: %v", c.ID, err)
			continue
		}
		if recordRevision != nil {
			if err := recordRevision(ctx, c.ID, newContent); err != nil {
				log.Printf("distributors: revision %s: %v", c.ID, err)
			}
		}
		updated++
	}
	return updated, nil
}

// RecordRevisionFn is the indirection for revision recording. Pass
// nil to skip revision rows entirely (acceptable for boot-time sweeps
// in single-user installs where every prior revision is the user's
// own work).
type RecordRevisionFn func(ctx context.Context, fileID, content string) error

// isStale returns true when the Part has at least one distributor
// entry whose fetched_at is missing or older than StalePartAge AND
// the entry's name matches a distributor name we care about. We
// don't gate on Registry membership here because the sync sweep is
// invoked with a registry that already knows what's enabled — if
// the entry is for a disabled distributor, the per-entry refresh
// path quietly skips it.
func isStale(partJSON string) bool {
	if strings.TrimSpace(partJSON) == "" {
		return false
	}
	var d struct {
		Distributors []struct {
			Name      string `json:"name"`
			FetchedAt string `json:"fetched_at"`
		} `json:"distributors"`
	}
	if err := json.Unmarshal([]byte(partJSON), &d); err != nil {
		return false
	}
	now := time.Now().UTC()
	for _, e := range d.Distributors {
		if e.FetchedAt == "" {
			return true
		}
		t, err := time.Parse(time.RFC3339, e.FetchedAt)
		if err != nil {
			return true
		}
		if now.Sub(t) > StalePartAge {
			return true
		}
	}
	return false
}

// StartSweep kicks off the background goroutine that runs
// RefreshAllParts on a SweepInterval cadence. Cancel ctx to stop.
func StartSweep(ctx context.Context, pool *pgxpool.Pool, reg *Registry, recordRevision RecordRevisionFn) {
	go func() {
		// Initial run: wait 30s after boot so the registry has settled
		// and the operator hasn't just configured a credential they're
		// about to test manually (a sweep firing during their test
		// would be noisy).
		select {
		case <-ctx.Done():
			return
		case <-time.After(30 * time.Second):
		}
		if n, err := RefreshAllParts(ctx, pool, reg, recordRevision); err != nil {
			log.Printf("distributors: initial sweep failed: %v", err)
		} else if n > 0 {
			log.Printf("distributors: initial sweep refreshed %d part(s)", n)
		}
		t := time.NewTicker(SweepInterval)
		defer t.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-t.C:
				if n, err := RefreshAllParts(ctx, pool, reg, recordRevision); err != nil {
					log.Printf("distributors: sweep failed: %v", err)
				} else if n > 0 {
					log.Printf("distributors: sweep refreshed %d part(s)", n)
				}
			}
		}
	}()
}
