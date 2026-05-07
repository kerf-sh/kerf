package handlers

// Bill-of-Materials rollup.
//
// Endpoint: GET /api/projects/{pid}/bom (member+).
//
// Algorithm:
//   1. Pull every non-deleted file in the project once into an in-memory map
//      so the walk doesn't re-query for each component.
//   2. For each kind='assembly' file, recursively walk its components.
//      - Component points at a kind='part'  → bump count for that Part.
//      - Component points at a kind='assembly' → recurse, multiplying the
//        nested counts by the parent's quantity (always 1 in the current
//        Component schema, but the multiplier shape is here for when we add
//        an explicit `quantity` field to the Component).
//      - Anything else (jscad, step, drawing, sketch, folder) → ignored.
//   3. Cycle protection: per top-level walk, track the set of assembly file
//      IDs already on the recursion stack. Re-entering one is silently
//      skipped (a warning is appended).
//   4. Aggregate by MPN when present, else by file_id. The Part's first
//      distributor with a price_usd is the "primary" for unit-price purposes.
//
// The same logic is reused from the LLM `generate_bom` tool. The HTTP
// handler returns a richer envelope (`{rows, total_price_usd, warnings}`)
// while the tool wraps the same shape inside its standard payload.

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"sort"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/internal/middleware"
)

// ----- Public handler -------------------------------------------------------

// BOMRow is the wire shape returned to the client. The Part is included
// verbatim so the frontend can render manufacturer / MPN / category / model
// presence without a follow-up fetch per row.
//
// `NonStocked` and `Note` are populated from per-assembly BOM overrides (BOM
// rework). They are omitempty so older clients (and the LLM `generate_bom`
// tool, which doesn't apply overrides) keep their existing payload shape.
type BOMRow struct {
	Part               BOMPart     `json:"part"`
	FileID             string      `json:"file_id"`
	Path               string      `json:"path"`
	Count              int         `json:"count"`
	UnitPriceUSD       *float64    `json:"unit_price_usd,omitempty"`
	TotalPriceUSD      *float64    `json:"total_price_usd,omitempty"`
	PrimaryDistributor *bomDistRef `json:"primary_distributor,omitempty"`
	NonStocked         bool        `json:"non_stocked,omitempty"`
	Note               string      `json:"note,omitempty"`
}

type bomDistRef struct {
	Name string `json:"name"`
	URL  string `json:"url"`
	SKU  string `json:"sku,omitempty"`
}

// BOMPart is the part metadata projection we return — a strict subset of the
// Part JSON schema so we don't accidentally leak free-form `metadata` into a
// field the client might trip over. Add fields here as the UI grows.
type BOMPart struct {
	Version         int        `json:"version"`
	Name            string     `json:"name"`
	Description     string     `json:"description,omitempty"`
	Category        string     `json:"category,omitempty"`
	Manufacturer    string     `json:"manufacturer,omitempty"`
	MPN             string     `json:"mpn,omitempty"`
	Value           string     `json:"value,omitempty"`
	DatasheetURL    string     `json:"datasheet_url,omitempty"`
	Distributors    []BOMDist  `json:"distributors"`
	ModelStorageKey string     `json:"model_storage_key,omitempty"`
	ModelMimeType   string     `json:"model_mime_type,omitempty"`
}

type BOMDist struct {
	Name      string   `json:"name"`
	SKU       string   `json:"sku,omitempty"`
	URL       string   `json:"url"`
	PriceUSD  *float64 `json:"price_usd,omitempty"`
	Stock     *int     `json:"stock,omitempty"`
	FetchedAt string   `json:"fetched_at,omitempty"`
}

// BOMResponse is the envelope returned by GET /bom.
type BOMResponse struct {
	Rows          []BOMRow `json:"rows"`
	TotalPriceUSD *float64 `json:"total_price_usd,omitempty"`
	Warnings      []string `json:"warnings"`
}

// GetBOM serves GET /api/projects/{pid}/bom.
func (d *Deps) GetBOM(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}
	rows, total, warnings, err := bomCompute(r.Context(), d.Pool, pid)
	if err != nil {
		genericServerError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, BOMResponse{
		Rows:          rows,
		TotalPriceUSD: total,
		Warnings:      warnings,
	})
}

// ----- Shared computation ---------------------------------------------------

// fileRow is the slice of `files` we need to walk the BOM tree.
type fileRow struct {
	ID       string
	ParentID *string
	Name     string
	Kind     string
	Content  string
}

// componentRef is the parsed shape of an assembly's components. We mirror
// just the fields needed for BOM (file_id + optional quantity); the full
// schema lives in tools/assembly_tools.go.
type componentRef struct {
	FileID   string `json:"file_id"`
	ObjectID string `json:"object_id"`
	PartID   string `json:"part_id"` // legacy
	Quantity *int   `json:"quantity,omitempty"`
}

// bomOverride mirrors the per-Part override shape authored by the inline
// BOM panel inside AssemblyEditor (BOM rework). Quantity replaces the
// rolled-up count; non_stocked excludes the row from the cost roll-up but
// keeps it visible; note appears as a free-text annotation.
type bomOverride struct {
	PartFileID       string `json:"part_file_id"`
	QuantityOverride *int   `json:"quantity_override,omitempty"`
	NonStocked       bool   `json:"non_stocked,omitempty"`
	Note             string `json:"note,omitempty"`
}

type assemblyRef struct {
	Components []componentRef `json:"components"`
	Children   []componentRef `json:"children"` // legacy
	Overrides  []bomOverride  `json:"overrides,omitempty"`
}

func parseAssemblyComponents(content string) []componentRef {
	if strings.TrimSpace(content) == "" {
		return nil
	}
	var d assemblyRef
	if err := json.Unmarshal([]byte(content), &d); err != nil {
		return nil
	}
	if len(d.Components) > 0 {
		return d.Components
	}
	return d.Children
}

// parseAssemblyOverrides extracts the assembly's BOM override list. Returns
// nil for malformed JSON or assemblies without overrides.
func parseAssemblyOverrides(content string) []bomOverride {
	if strings.TrimSpace(content) == "" {
		return nil
	}
	var d assemblyRef
	if err := json.Unmarshal([]byte(content), &d); err != nil {
		return nil
	}
	return d.Overrides
}

// bomCompute is the shared implementation backing both the HTTP handler and
// the LLM `generate_bom` tool. It's package-private; the tool layer reaches
// across via the `computeBOM` shim below.
func bomCompute(ctx context.Context, pool *pgxpool.Pool, projectID string) ([]BOMRow, *float64, []string, error) {
	files, err := loadProjectFilesForBOM(ctx, pool, projectID)
	if err != nil {
		return nil, nil, nil, err
	}
	byID := make(map[string]*fileRow, len(files))
	for i := range files {
		byID[files[i].ID] = &files[i]
	}

	// Build path table once so every BOMRow can carry an absolute path.
	paths := buildPathTable(files)

	// aggKey: prefer MPN; fallback to file id. Two parts with the same MPN
	// across the project collapse into one row (with a warning).
	type agg struct {
		count    int
		fileID   string
		fileRow  *fileRow
		warnings []string
	}
	aggregates := make(map[string]*agg)
	warnings := make([]string, 0)

	// addPart bumps the rollup for `partID` by `quantity`. The aggregate is
	// keyed by MPN when present; otherwise by file id (so two unnamed parts
	// don't collide).
	addPart := func(partFile *fileRow, quantity int) {
		doc := parsePartContent(partFile.Content)
		key := strings.TrimSpace(doc.MPN)
		if key == "" {
			key = "fid:" + partFile.ID
		}
		a := aggregates[key]
		if a == nil {
			a = &agg{
				fileID:  partFile.ID,
				fileRow: partFile,
			}
			aggregates[key] = a
		} else if a.fileID != partFile.ID && doc.MPN != "" {
			// Two different files share the same MPN — expected for libraries
			// that re-use canonical part metadata, but worth surfacing.
			warnings = append(warnings,
				fmt.Sprintf("Multiple parts share MPN %q (using first encountered)", doc.MPN))
		}
		a.count += quantity
	}

	// Recursive walker shared across the per-assembly loop. `visited` is
	// scoped per top-level walk so a Part can legitimately appear in two
	// branches of the same tree without being deduped — only assembly
	// re-entrancy is the cycle case.
	var walk func(fid string, multiplier int, visited map[string]bool) error
	walk = func(fid string, multiplier int, visited map[string]bool) error {
		f := byID[fid]
		if f == nil {
			return nil
		}
		if f.Kind == "part" {
			addPart(f, multiplier)
			return nil
		}
		if f.Kind != "assembly" {
			// jscad, step, drawing, sketch, folder, etc. — irrelevant for BOM.
			return nil
		}
		if visited[fid] {
			warnings = append(warnings,
				fmt.Sprintf("Cycle detected at assembly %q; skipping repeat visit", paths[fid]))
			return nil
		}
		visited[fid] = true
		defer delete(visited, fid)

		for _, c := range parseAssemblyComponents(f.Content) {
			if c.FileID == "" {
				continue
			}
			q := 1
			if c.Quantity != nil && *c.Quantity > 0 {
				q = *c.Quantity
			}
			if err := walk(c.FileID, multiplier*q, visited); err != nil {
				return err
			}
		}
		return nil
	}

	// Top-level walk: every assembly in the project is a starting point so a
	// project with several disjoint top assemblies BOMs them all. We don't
	// try to figure out which assembly is "the" root.
	//
	// As we walk, gather BOM overrides from every assembly into one
	// project-wide map keyed by part_file_id. Conflicts (two assemblies
	// override the same part with different values) keep the first encountered
	// and emit a warning — the alternative (last-write-wins) is order-
	// dependent on the file slice, which is unstable.
	overrideByPart := make(map[string]bomOverride)
	for i := range files {
		f := &files[i]
		if f.Kind != "assembly" {
			continue
		}
		visited := map[string]bool{}
		if err := walk(f.ID, 1, visited); err != nil {
			return nil, nil, nil, err
		}
		for _, ov := range parseAssemblyOverrides(f.Content) {
			pfid := strings.TrimSpace(ov.PartFileID)
			if pfid == "" {
				continue
			}
			if existing, ok := overrideByPart[pfid]; ok {
				// Skip duplicates that are content-identical (same assembly
				// edited twice, two assemblies happened to author the same
				// override). Only warn when the values actually disagree.
				if !overridesEqual(existing, ov) {
					warnings = append(warnings,
						fmt.Sprintf("Multiple assemblies override the same part file (using first encountered)"))
				}
				continue
			}
			overrideByPart[pfid] = ov
		}
	}

	// Materialize rows. Per-row overrides land here:
	//   - quantity_override replaces the rolled-up count.
	//   - non_stocked excludes the row from the cost roll-up (Total + grand
	//     total) but keeps the row visible so users still see what's marked.
	//   - note is passed through to the client.
	rows := make([]BOMRow, 0, len(aggregates))
	var grandTotal float64
	hasAnyPrice := false
	for _, a := range aggregates {
		doc := parsePartContent(a.fileRow.Content)
		ov, hasOverride := overrideByPart[a.fileID]
		count := a.count
		if hasOverride && ov.QuantityOverride != nil && *ov.QuantityOverride >= 0 {
			count = *ov.QuantityOverride
		}
		row := BOMRow{
			Part:   partDocToBOMPart(doc),
			FileID: a.fileID,
			Path:   paths[a.fileID],
			Count:  count,
		}
		if hasOverride {
			if ov.NonStocked {
				row.NonStocked = true
			}
			if ov.Note != "" {
				row.Note = ov.Note
			}
		}
		// Primary distributor = first one with a price_usd; failing that,
		// just the first. Lets the frontend always link out somewhere.
		var unitPrice *float64
		for _, dl := range doc.Distributors {
			if dl.PriceUSD != nil {
				unitPrice = dl.PriceUSD
				p := *dl.PriceUSD
				row.PrimaryDistributor = &bomDistRef{Name: dl.Name, URL: dl.URL, SKU: dl.SKU}
				_ = p
				break
			}
		}
		if row.PrimaryDistributor == nil && len(doc.Distributors) > 0 {
			d0 := doc.Distributors[0]
			row.PrimaryDistributor = &bomDistRef{Name: d0.Name, URL: d0.URL, SKU: d0.SKU}
		}
		if unitPrice != nil {
			row.UnitPriceUSD = unitPrice
			tot := (*unitPrice) * float64(count)
			row.TotalPriceUSD = &tot
			if !row.NonStocked {
				grandTotal += tot
				hasAnyPrice = true
			}
		}
		if doc.MPN == "" {
			warnings = append(warnings,
				fmt.Sprintf("Part %q has no MPN", doc.Name))
		}
		rows = append(rows, row)
	}

	// Stable order: by name then by path.
	sort.SliceStable(rows, func(i, j int) bool {
		if rows[i].Part.Name != rows[j].Part.Name {
			return rows[i].Part.Name < rows[j].Part.Name
		}
		return rows[i].Path < rows[j].Path
	})

	var totalPtr *float64
	if hasAnyPrice {
		totalPtr = &grandTotal
	}
	return rows, totalPtr, warnings, nil
}

// partDocToBOMPart projects the internal partDoc (defined in tools package)
// into the public BOMPart type. We deliberately re-define the type rather
// than importing tools/ to keep the dependency direction one-way.
func partDocToBOMPart(d partDoc) BOMPart {
	out := BOMPart{
		Version:         d.Version,
		Name:            d.Name,
		Description:     d.Description,
		Category:        d.Category,
		Manufacturer:    d.Manufacturer,
		MPN:             d.MPN,
		Value:           d.Value,
		DatasheetURL:    d.DatasheetURL,
		ModelStorageKey: d.ModelStorageKey,
		ModelMimeType:   d.ModelMimeType,
	}
	out.Distributors = make([]BOMDist, 0, len(d.Distributors))
	for _, dl := range d.Distributors {
		out.Distributors = append(out.Distributors, BOMDist{
			Name:      dl.Name,
			SKU:       dl.SKU,
			URL:       dl.URL,
			PriceUSD:  dl.PriceUSD,
			Stock:     dl.Stock,
			FetchedAt: dl.FetchedAt,
		})
	}
	return out
}

// loadProjectFilesForBOM pulls every non-deleted file with content. We could
// be slicker about which kinds we read content for (only assemblies and
// parts have JSON we care about), but the project file count is small
// enough — and the Postgres roundtrip count matters more than payload size.
func loadProjectFilesForBOM(ctx context.Context, pool *pgxpool.Pool, projectID string) ([]fileRow, error) {
	rows, err := pool.Query(ctx, `
		select id, parent_id, name, kind, content
		  from files
		 where project_id = $1 and deleted_at is null
		   and kind in ('assembly','part','folder','file','step','drawing','sketch')
	`, projectID)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, nil
		}
		return nil, err
	}
	defer rows.Close()
	var out []fileRow
	for rows.Next() {
		var f fileRow
		if err := rows.Scan(&f.ID, &f.ParentID, &f.Name, &f.Kind, &f.Content); err != nil {
			return nil, err
		}
		out = append(out, f)
	}
	return out, rows.Err()
}

// overridesEqual returns true when two BOM overrides have identical effective
// content. Used to suppress the "multiple assemblies override the same part"
// warning when the duplicate is just the same author re-saving the same row.
func overridesEqual(a, b bomOverride) bool {
	if a.NonStocked != b.NonStocked {
		return false
	}
	if a.Note != b.Note {
		return false
	}
	if (a.QuantityOverride == nil) != (b.QuantityOverride == nil) {
		return false
	}
	if a.QuantityOverride != nil && b.QuantityOverride != nil {
		if *a.QuantityOverride != *b.QuantityOverride {
			return false
		}
	}
	return true
}

// buildPathTable returns id→absolute-POSIX path for every file in the slice.
func buildPathTable(files []fileRow) map[string]string {
	byID := make(map[string]*fileRow, len(files))
	for i := range files {
		byID[files[i].ID] = &files[i]
	}
	out := make(map[string]string, len(files))
	for _, f := range files {
		parts := []string{f.Name}
		cur := f.ParentID
		for i := 0; i < 64 && cur != nil; i++ {
			p, ok := byID[*cur]
			if !ok {
				break
			}
			parts = append([]string{p.Name}, parts...)
			cur = p.ParentID
		}
		out[f.ID] = "/" + strings.Join(parts, "/")
	}
	return out
}

// ----- partDoc shadow type (mirrors tools/part_tools.go) --------------------
//
// We keep an internal copy of the Part shape to avoid a handlers→tools import
// cycle. The two definitions need to stay in sync — a single test that loads
// a Part through both paths (the LLM tool create_part and the BOM endpoint)
// would catch any drift; for now the surface is small enough that field-level
// parallelism is reviewable by inspection.

type partDist struct {
	Name      string   `json:"name"`
	SKU       string   `json:"sku,omitempty"`
	URL       string   `json:"url"`
	PriceUSD  *float64 `json:"price_usd,omitempty"`
	Stock     *int     `json:"stock,omitempty"`
	FetchedAt string   `json:"fetched_at,omitempty"`
}

type partDoc struct {
	Version         int            `json:"version"`
	Name            string         `json:"name"`
	Description     string         `json:"description,omitempty"`
	Category        string         `json:"category,omitempty"`
	Manufacturer    string         `json:"manufacturer,omitempty"`
	MPN             string         `json:"mpn,omitempty"`
	Value           string         `json:"value,omitempty"`
	DatasheetURL    string         `json:"datasheet_url,omitempty"`
	Distributors    []partDist     `json:"distributors"`
	ModelStorageKey string         `json:"model_storage_key,omitempty"`
	ModelMimeType   string         `json:"model_mime_type,omitempty"`
	SymbolFileID    string         `json:"symbol_file_id,omitempty"`
	FootprintFileID string         `json:"footprint_file_id,omitempty"`
	Metadata        map[string]any `json:"metadata,omitempty"`
}

func parsePartContent(s string) partDoc {
	var d partDoc
	if strings.TrimSpace(s) != "" {
		_ = json.Unmarshal([]byte(s), &d)
	}
	if d.Version == 0 {
		d.Version = 1
	}
	if d.Distributors == nil {
		d.Distributors = []partDist{}
	}
	return d
}
