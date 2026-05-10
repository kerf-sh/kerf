# BOM (Bill of Materials)

A **BOM** is a flat list of every Part referenced by an Assembly,
rolled up across nested `.assembly` files. The frontend renders it in
`InlineBOMPanel` inside `AssemblyEditor`; the backend exposes the
canonical rollup at `GET /api/projects/{pid}/bom` and a CSV export at
`GET /api/projects/{pid}/bom?format=csv`.

## Data flow

1. `AssemblyEditor` parses the active `.assembly` JSON.
2. Each Component's `file_id` (or `external_ref`) resolves to a Part
   row.
3. The backend handler walks nested assemblies and returns one row per
   `(file_id, config_id)` pair with the rolled-up quantity.
4. Per-row overrides on the assembly merge in (`quantity_override`,
   `non_stocked`, `note`).
5. The frontend `BOMTable` renders qty / stock / unit / total /
   distributor / MOQ / lead-time / U.Price / Alternates / Note.

## Override shape

Overrides live in the `.assembly` JSON itself:

```json
{
  "components": [...],
  "overrides": [
    { "part_file_id": "<uuid>", "quantity_override": 12 },
    { "part_file_id": "<uuid>", "non_stocked": true,
      "note": "soldered last; do not bag with the rest" }
  ]
}
```

Empty rows are dropped on save (the UI filters `null` overrides). When
no override row exists for a Part, the rollup uses the natural
quantity from `Component.count`.

## Distributor metadata

When a Part has `distributors[]` populated (typically by
`distributors.RefreshPart`, which pulls from DigiKey / Mouser / LCSC),
`BOMTable` surfaces the cheapest entry's `unit_price_usd`, `moq`, and
`lead_time_days`. The Alternates column lists the other up-to-three
distributors as compact `<name> $<price>` pills sorted ascending, with
a `+N more` overflow tooltip. Helpers `pickCheapestDistributor` /
`pickAlternates` are exported from `BOMTable.jsx` for testing.

## CSV export

`GET /api/projects/{pid}/bom?format=csv` returns the same rollup as
text/csv. Columns: `file_id, name, manufacturer, mpn, category,
quantity, unit, total_usd, moq, lead_time_days, distributor, note`.
Suitable for purchasing-team consumption or Excel pivoting.

## Known limits

- Overrides key on `part_file_id` only — there's no per-config-id
  override yet. If you need both an override and a non-default config,
  the override applies to whichever config the assembly's Component
  pins.
- "Alternates" caps the visible distributor list at 3; the rest live
  inside the tooltip.
- Lead time is days (`<14d` formatted as `Nd`, otherwise weeks `N wk`).
