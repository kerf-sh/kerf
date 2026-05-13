package tools

// Part tools — Library / BOM authoring.
//
// Two tools live here:
//   - `create_part`: scaffold a new `.part` file with a canonical JSON shape.
//   - `generate_bom`: walk every assembly in the project, recurse through
//      nested assemblies, and roll up leaf Part references.
//
// Per-field tools (`set_part_metadata`, `add_distributor_link`,
// `add_part_photo`, `set_part_visibility`) were removed when the LLM tool
// surface was consolidated. The model now mutates Parts by editing the JSON
// directly via write_file / edit_file after consulting docs/llm/part.md.
//
// Schema (mirrors src/lib/part.js):
//
//   {
//     "version": 1,
//     "name": "10kΩ resistor 0805",
//     "description": "string",
//     "category": "resistor",
//     "manufacturer": "Yageo",
//     "mpn": "RC0805FR-0710KL",
//     "value": "10kΩ",
//     "datasheet_url": "https://...",
//     "distributors": [
//       { "name": "digikey", "sku": "311-...", "url": "https://...",
//         "price_usd": 0.014, "stock": 5000, "fetched_at": "2026-..." }
//     ],
//     "model_storage_key": "projects/<pid>/assets/<uuid>-foo.step",
//     "model_mime_type": "model/step",
//     "symbol_file_id": "uuid",
//     "footprint_file_id": "uuid",
//     "metadata": { ... }
//   }

import (
	"context"
	"encoding/json"
	"fmt"
	"net/url"
	"sort"
	"strings"

	"github.com/google/uuid"

	"github.com/imranp/kerf/backend/internal/llm"
)

// ----- Part document type ---------------------------------------------------

type partDistributor struct {
	Name      string   `json:"name"`
	SKU       string   `json:"sku,omitempty"`
	URL       string   `json:"url"`
	PriceUSD  *float64 `json:"price_usd,omitempty"`
	Stock     *int     `json:"stock,omitempty"`
	FetchedAt string   `json:"fetched_at,omitempty"`
}

type partPhotoTool struct {
	StorageKey string `json:"storage_key"`
	MimeType   string `json:"mime_type"`
	Caption    string `json:"caption,omitempty"`
	Primary    bool   `json:"primary,omitempty"`
	Width      int    `json:"width,omitempty"`
	Height     int    `json:"height,omitempty"`
	Bytes      int    `json:"bytes,omitempty"`
}

type partDoc struct {
	Version         int               `json:"version"`
	Name            string            `json:"name"`
	Description     string            `json:"description,omitempty"`
	Category        string            `json:"category,omitempty"`
	Manufacturer    string            `json:"manufacturer,omitempty"`
	MPN             string            `json:"mpn,omitempty"`
	Value           string            `json:"value,omitempty"`
	DatasheetURL    string            `json:"datasheet_url,omitempty"`
	Distributors    []partDistributor `json:"distributors"`
	ModelStorageKey string            `json:"model_storage_key,omitempty"`
	ModelMimeType   string            `json:"model_mime_type,omitempty"`
	SymbolFileID    string            `json:"symbol_file_id,omitempty"`
	FootprintFileID string            `json:"footprint_file_id,omitempty"`
	Visibility      string            `json:"visibility,omitempty"`
	Photos          []partPhotoTool   `json:"photos,omitempty"`
	Metadata        map[string]any    `json:"metadata,omitempty"`
	// Configurations / variants — see backend/internal/llm/docs/configurations.md.
	// `DefaultConfig` is the id of the configuration the file picks when no
	// explicit pin is supplied; `Configurations` is the row list (id +
	// label + per-config params). Empty array (or empty default) means
	// "no variants" and the file behaves like every other Part.
	DefaultConfig  string              `json:"default_config,omitempty"`
	Configurations []partConfiguration `json:"configurations,omitempty"`
	MaterialPath   string              `json:"material_path,omitempty"`
}

// partConfiguration mirrors the configurations / variants entry shape on a
// Part's JSON content. Tools that author or read configs (add_configuration,
// generate_bom) round-trip these fields verbatim. `Params` is a free-form
// map so each config can override any subset of the equations scope; the
// runner merges it OVER the equations scope before evaluation.
type partConfiguration struct {
	ID     string         `json:"id"`
	Label  string         `json:"label,omitempty"`
	Params map[string]any `json:"params,omitempty"`
}

// parsePartContent is tolerant: missing / malformed JSON falls back to a
// minimal valid doc with version=1 and an empty distributors array. This
// keeps the BOM rollup resilient to half-written files (e.g. a Part the
// LLM is in the middle of authoring).
func parsePartContent(s string) partDoc {
	var d partDoc
	if strings.TrimSpace(s) != "" {
		_ = json.Unmarshal([]byte(s), &d)
	}
	if d.Version == 0 {
		d.Version = 1
	}
	if d.Distributors == nil {
		d.Distributors = []partDistributor{}
	}
	return d
}

func serializePartContent(d partDoc) (string, error) {
	if d.Version == 0 {
		d.Version = 1
	}
	if d.Distributors == nil {
		d.Distributors = []partDistributor{}
	}
	b, err := json.MarshalIndent(d, "", "  ")
	if err != nil {
		return "", err
	}
	return string(b), nil
}

// validatePartURL: cheap well-formed-URL check for distributor + datasheet
// links. We accept http/https only; anything else is suspicious enough to
// reject from a tool path.
func validatePartURL(u string) error {
	if u == "" {
		return nil
	}
	parsed, err := url.Parse(u)
	if err != nil {
		return fmt.Errorf("invalid url: %w", err)
	}
	if parsed.Scheme != "http" && parsed.Scheme != "https" {
		return fmt.Errorf("url must be http(s)")
	}
	if parsed.Host == "" {
		return fmt.Errorf("url is missing host")
	}
	return nil
}

// ----- create_part ----------------------------------------------------------

var createPartSpec = llm.ToolSpec{
	Name:        "create_part",
	Description: "Create a new Part file (kind='part') in the library. The Part stores manufacturer/MPN/distributor metadata as JSON; assemblies reference parts as Components and the BOM endpoint rolls them up. `name` is required; everything else can be filled in later by editing the file via write_file / edit_file (see docs/llm/part.md).",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"path": map[string]any{
				"type":        "string",
				"description": "Absolute path of the new Part file. Should end with .part. e.g. '/library/resistors/10k-0805.part'.",
			},
			"metadata": map[string]any{
				"type":        "object",
				"description": "Initial metadata. Must include `name`. Optional: description, category, manufacturer, mpn, value, datasheet_url, distributors, metadata.",
			},
		},
		"required": []string{"path", "metadata"},
	},
}

type createPartArgs struct {
	Path     string  `json:"path"`
	Metadata partDoc `json:"metadata"`
}

func runCreatePart(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a createPartArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	if strings.TrimSpace(a.Metadata.Name) == "" {
		return errPayload("metadata.name is required", "BAD_ARGS"), nil
	}
	clean, err := normalizePath(a.Path)
	if err != nil {
		return errPayload(err.Error(), "BAD_ARGS"), nil
	}
	parts := splitPath(clean)
	if len(parts) == 0 {
		return errPayload("cannot create the root", "BAD_ARGS"), nil
	}
	if !strings.HasSuffix(strings.ToLower(clean), ".part") {
		clean = clean + ".part"
		parts = splitPath(clean)
	}
	if rp, _ := resolvePath(ctx, pc, clean); rp.Exists {
		return errPayload("path already exists", "EXISTS"), nil
	}
	if err := validatePartURL(a.Metadata.DatasheetURL); err != nil {
		return errPayload("datasheet_url: "+err.Error(), "BAD_ARGS"), nil
	}
	for i, dl := range a.Metadata.Distributors {
		if strings.TrimSpace(dl.Name) == "" {
			return errPayload(fmt.Sprintf("distributor[%d].name is required", i), "BAD_ARGS"), nil
		}
		if err := validatePartURL(dl.URL); err != nil {
			return errPayload(fmt.Sprintf("distributor[%d].url: %s", i, err.Error()), "BAD_ARGS"), nil
		}
	}
	a.Metadata.Version = 1
	if a.Metadata.Distributors == nil {
		a.Metadata.Distributors = []partDistributor{}
	}
	body, err := serializePartContent(a.Metadata)
	if err != nil {
		return errPayload("encode part: "+err.Error(), "ERROR"), nil
	}
	parent, err := ensureFolders(ctx, pc, parts[:len(parts)-1])
	if err != nil {
		return "", err
	}
	leaf := parts[len(parts)-1]
	var newID uuid.UUID
	err = pc.Pool.QueryRow(ctx,
		`insert into files(project_id, parent_id, name, kind, content)
		 values ($1,$2,$3,'part',$4)
		 returning id`,
		pc.ProjectID, parent, leaf, body).Scan(&newID)
	if err != nil {
		return "", err
	}
	_ = recordRevisionForFile(ctx, pc, newID, body, "tool")
	return okPayload(map[string]any{
		"path": clean,
		"id":   newID.String(),
		"name": a.Metadata.Name,
	}), nil
}

// ----- generate_bom ---------------------------------------------------------
//
// Walk every assembly in the project, recurse through nested assemblies, and
// roll up the leaf Part references into a flat quantity table. Cycle
// protection: track the set of assembly IDs currently on the recursion stack
// (per top-level walk), entries are removed on exit so the same assembly can
// legitimately appear in two disjoint branches.
//
// Aggregation: by MPN when present, else by file id. Two parts with the same
// MPN collapse into one row (with a warning).

var generateBOMSpec = llm.ToolSpec{
	Name:        "generate_bom",
	Description: "Generate a Bill of Materials for the current project. Walks every assembly file, recursively resolves nested assemblies, and aggregates leaf Part references by MPN (or by file id when MPN is missing). Returns rows with quantity, unit price (from the Part's first distributor with a price), and total price.",
	InputSchema: map[string]any{
		"type":       "object",
		"properties": map[string]any{},
	},
}

// bomRow / bomDistRef are the internal shapes the tool emits. They mirror
// handlers.BOMRow on purpose — we want JSON parity so the LLM and the HTTP
// handler return the same shape.
type bomDistRef struct {
	Name string `json:"name"`
	URL  string `json:"url"`
	SKU  string `json:"sku,omitempty"`
}

type bomRow struct {
	Part               partDoc     `json:"part"`
	FileID             string      `json:"file_id"`
	Path               string      `json:"path"`
	Count              int         `json:"count"`
	UnitPriceUSD       *float64    `json:"unit_price_usd,omitempty"`
	TotalPriceUSD      *float64    `json:"total_price_usd,omitempty"`
	PrimaryDistributor *bomDistRef `json:"primary_distributor,omitempty"`
	// Configurations / variants — populated when the rolled-up component
	// pinned a specific configuration (M3 vs M4 of one screw Part).
	ConfigID     string `json:"config_id,omitempty"`
	ConfigLabel  string `json:"config_label,omitempty"`
	MaterialPath string `json:"material_path,omitempty"`
}

// bomFileRow is the slice of `files` we need to walk.
type bomFileRow struct {
	ID       uuid.UUID
	ParentID *uuid.UUID
	Name     string
	Kind     string
	Content  string
}

type bomComponentRef struct {
	FileID   string `json:"file_id"`
	ObjectID string `json:"object_id"`
	PartID   string `json:"part_id"`
	Quantity *int   `json:"quantity,omitempty"`
	ConfigID string `json:"config_id,omitempty"`
}

type bomAssemblyRef struct {
	Components []bomComponentRef `json:"components"`
	Children   []bomComponentRef `json:"children"`
}

func parseBOMComponents(content string) []bomComponentRef {
	if strings.TrimSpace(content) == "" {
		return nil
	}
	var d bomAssemblyRef
	if err := json.Unmarshal([]byte(content), &d); err != nil {
		return nil
	}
	if len(d.Components) > 0 {
		return d.Components
	}
	return d.Children
}

func runGenerateBOM(ctx context.Context, pc ProjectCtx, _ json.RawMessage) (string, error) {
	rows, total, warnings, err := computeBOMTool(ctx, pc)
	if err != nil {
		return errPayload(err.Error(), "ERROR"), nil
	}
	return okPayload(map[string]any{
		"rows":            rows,
		"total_price_usd": total,
		"warnings":        warnings,
	}), nil
}

func computeBOMTool(ctx context.Context, pc ProjectCtx) ([]bomRow, *float64, []string, error) {
	rows, err := pc.Pool.Query(ctx, `
		select id, parent_id, name, kind, content
		  from files
		 where project_id = $1 and deleted_at is null
		   and kind in ('assembly','part','folder','file','step','drawing','sketch')
	`, pc.ProjectID)
	if err != nil {
		return nil, nil, nil, err
	}
	defer rows.Close()
	var files []bomFileRow
	for rows.Next() {
		var f bomFileRow
		if err := rows.Scan(&f.ID, &f.ParentID, &f.Name, &f.Kind, &f.Content); err != nil {
			return nil, nil, nil, err
		}
		files = append(files, f)
	}

	byID := make(map[uuid.UUID]*bomFileRow, len(files))
	for i := range files {
		byID[files[i].ID] = &files[i]
	}
	paths := buildBOMPathTable(files)

	type agg struct {
		count    int
		fileID   uuid.UUID
		fileRow  *bomFileRow
		configID string
	}
	aggregates := make(map[string]*agg)
	warnings := make([]string, 0)

	resolveActiveConfig := func(doc partDoc, pinned string) string {
		if len(doc.Configurations) == 0 {
			return ""
		}
		if pinned != "" {
			for _, c := range doc.Configurations {
				if c.ID == pinned {
					return c.ID
				}
			}
		}
		def := strings.TrimSpace(doc.DefaultConfig)
		if def != "" {
			for _, c := range doc.Configurations {
				if c.ID == def {
					return c.ID
				}
			}
		}
		return doc.Configurations[0].ID
	}

	addPart := func(partFile *bomFileRow, quantity int, configID string) {
		doc := parsePartContent(partFile.Content)
		base := strings.TrimSpace(doc.MPN)
		if base == "" {
			base = "fid:" + partFile.ID.String()
		}
		key := base
		if configID != "" {
			key = base + "|cfg=" + configID
		}
		a := aggregates[key]
		if a == nil {
			a = &agg{
				fileID:   partFile.ID,
				fileRow:  partFile,
				configID: configID,
			}
			aggregates[key] = a
		} else if a.fileID != partFile.ID && doc.MPN != "" {
			warnings = append(warnings,
				fmt.Sprintf("Multiple parts share MPN %q (using first encountered)", doc.MPN))
		}
		a.count += quantity
	}

	var walk func(fid uuid.UUID, multiplier int, configHint string, visited map[uuid.UUID]bool)
	walk = func(fid uuid.UUID, multiplier int, configHint string, visited map[uuid.UUID]bool) {
		f := byID[fid]
		if f == nil {
			return
		}
		if f.Kind == "part" {
			doc := parsePartContent(f.Content)
			cfgID := resolveActiveConfig(doc, configHint)
			addPart(f, multiplier, cfgID)
			return
		}
		if f.Kind != "assembly" {
			return
		}
		if visited[fid] {
			warnings = append(warnings,
				fmt.Sprintf("Cycle detected at assembly %q; skipping repeat visit", paths[fid]))
			return
		}
		visited[fid] = true
		defer delete(visited, fid)

		for _, c := range parseBOMComponents(f.Content) {
			if c.FileID == "" {
				continue
			}
			cid, err := uuid.Parse(c.FileID)
			if err != nil {
				continue
			}
			q := 1
			if c.Quantity != nil && *c.Quantity > 0 {
				q = *c.Quantity
			}
			nextHint := configHint
			if c.ConfigID != "" {
				nextHint = c.ConfigID
			}
			walk(cid, multiplier*q, nextHint, visited)
		}
	}

	for i := range files {
		f := &files[i]
		if f.Kind != "assembly" {
			continue
		}
		visited := map[uuid.UUID]bool{}
		walk(f.ID, 1, "", visited)
	}

	out := make([]bomRow, 0, len(aggregates))
	var grandTotal float64
	hasAnyPrice := false
	for _, a := range aggregates {
		doc := parsePartContent(a.fileRow.Content)
		row := bomRow{
			Part:         doc,
			FileID:       a.fileID.String(),
			Path:         paths[a.fileID],
			Count:        a.count,
			MaterialPath: doc.MaterialPath,
		}
		if a.configID != "" {
			row.ConfigID = a.configID
			for _, c := range doc.Configurations {
				if c.ID == a.configID {
					if c.Label != "" {
						row.ConfigLabel = c.Label
					} else {
						row.ConfigLabel = c.ID
					}
					break
				}
			}
		}
		var unitPrice *float64
		for _, dl := range doc.Distributors {
			if dl.PriceUSD != nil {
				unitPrice = dl.PriceUSD
				row.PrimaryDistributor = &bomDistRef{Name: dl.Name, URL: dl.URL, SKU: dl.SKU}
				break
			}
		}
		if row.PrimaryDistributor == nil && len(doc.Distributors) > 0 {
			d0 := doc.Distributors[0]
			row.PrimaryDistributor = &bomDistRef{Name: d0.Name, URL: d0.URL, SKU: d0.SKU}
		}
		if unitPrice != nil {
			row.UnitPriceUSD = unitPrice
			tot := (*unitPrice) * float64(a.count)
			row.TotalPriceUSD = &tot
			grandTotal += tot
			hasAnyPrice = true
		}
		if doc.MPN == "" {
			warnings = append(warnings, fmt.Sprintf("Part %q has no MPN", doc.Name))
		}
		out = append(out, row)
	}

	// Stable order by name, then config id (so M3/M4/M5 of the same Part
	// stay next to each other), then path.
	sort.SliceStable(out, func(i, j int) bool {
		if out[i].Part.Name != out[j].Part.Name {
			return out[i].Part.Name < out[j].Part.Name
		}
		if out[i].ConfigID != out[j].ConfigID {
			return out[i].ConfigID < out[j].ConfigID
		}
		return out[i].Path < out[j].Path
	})

	var totalPtr *float64
	if hasAnyPrice {
		totalPtr = &grandTotal
	}
	return out, totalPtr, warnings, nil
}

func buildBOMPathTable(files []bomFileRow) map[uuid.UUID]string {
	byID := make(map[uuid.UUID]*bomFileRow, len(files))
	for i := range files {
		byID[files[i].ID] = &files[i]
	}
	out := make(map[uuid.UUID]string, len(files))
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
