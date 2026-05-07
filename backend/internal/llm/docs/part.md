# Authoring `.part` files

A `.part` file is a Library Part — manufacturer / MPN / distributor
metadata for a real-world component. Assemblies' Components reference
parts; the BOM tool rolls up every Component instance to its source
Part.

Scaffold one with `create_part(path, metadata={...})`. After that, edit
the JSON via `write_file` / `edit_file`.

## File shape

```json
{
  "version": 1,
  "name": "10kΩ resistor 0805",
  "description": "1% tolerance, 1/8W",
  "category": "resistor",
  "manufacturer": "Yageo",
  "mpn": "RC0805FR-0710KL",
  "value": "10kΩ",
  "datasheet_url": "https://www.yageo.com/.../datasheet.pdf",

  "distributors": [
    { "name": "digikey",
      "sku": "311-10.0KCRCT-ND",
      "url": "https://www.digikey.com/en/products/detail/yageo/RC0805FR-0710KL/727836",
      "price_usd": 0.014,
      "stock": 5000,
      "fetched_at": "2026-05-01T12:00:00Z" },
    { "name": "mouser",
      "sku": "603-RC0805FR-0710KL",
      "url": "https://...",
      "price_usd": 0.012 }
  ],

  "model_storage_key":  "projects/<pid>/assets/<uuid>-r0805.step",
  "model_mime_type":    "model/step",
  "symbol_file_id":     "<uuid>",
  "footprint_file_id":  "<uuid>",
  "visibility":         "private",
  "photos": [
    { "storage_key": "parts/<file_id>/photo-<uuid>.jpg",
      "mime_type":   "image/jpeg",
      "caption":     "Front",
      "primary":     true,
      "bytes":       12345 }
  ],
  "metadata": { "rohs": true, "lifecycle": "active" }
}
```

## Field rules

- `version` must be `1`.
- `name` is required, non-empty.
- `mpn` is the BOM aggregation key; two parts with the same MPN
  collapse into one BOM row. Leave empty (`""`) for unlisted parts.
- `distributors` is an array; each entry needs at minimum `name` and
  `url`. `price_usd` and `stock` are optional; `fetched_at` is RFC3339.
- `visibility` ∈ `private | unlisted | public`. Public Parts whose
  containing project is also public are listed in the public Workshop.
- `model_storage_key` is the project-storage key for the 3D model
  (typically a STEP). Set this when `import_step` returned a key for
  the part — copy it from the import_step result. Do NOT invent keys.

## Distributor names

Use lowercase, no spaces. The frontend has logos for:

`digikey`, `mouser`, `lcsc`, `farnell`, `arrow`, `newark`, `mcmaster`,
`misumi`, `adafruit`, `sparkfun`, `seeed`.

Other names render with a generic icon.

## Photos

Photos live in project storage, addressed by `storage_key`. Don't try
to invent a key — the storage layer hands them out. Practical paths:
- The user uploaded a photo via the Part-photo button: the key is
  already on the Part. Do nothing.
- You need to attach a photo from a remote URL: tell the user to use
  the Part-photo button, OR (advanced) reference an `import_step`-style
  flow if one's added to this surface in future.

The first photo on a Part with no other primary is automatically
primary (`"primary": true`). Mark exactly one photo as primary; mark
the rest `false`.

## Visibility

```json
"visibility": "public"
```

Setting `"public"` does NOT publish the Part — the containing project
must also be public AND the user has to mark the project public via
project settings. Set `visibility` to advertise intent; the Workshop
filter does the gating.

## Common edits

### Set the MPN and add a Digi-Key link

```text
read_file('/library/r0805-10k.part')
edit_file with:
old: "mpn": "",
new: "mpn": "RC0805FR-0710KL",
```

Then to add a distributor link, edit the `distributors` array:

```text
old: "distributors": [],
new: "distributors": [
    {"name":"digikey","sku":"311-10.0KCRCT-ND","url":"https://www.digikey.com/..."}
  ],
```

### Mark a photo as primary

Find the photo entry and flip `"primary": false` → `"primary": true`,
making sure no other photo on the Part is primary.

### Hide a Part from the Workshop

```text
edit_file with:
old: "visibility": "public"
new: "visibility": "private"
```

## Live pricing and stock (Library Phase 2)

The fields `price_usd`, `stock`, and `fetched_at` on each distributor
entry are populated by the kerf distributor-refresh subsystem — NOT
by hand. See `docs/llm/distributors.md` for the full picture; the
short version:

- A boot-time goroutine refreshes every Part whose distributor entries
  are older than 24h, throttled by the per-distributor rate limit.
- Users can also trigger a synchronous refresh by hitting
  `POST /api/projects/:pid/files/:fid/distributors/refresh`. The BOM
  panel and the Library editor both expose a "Refresh prices" button
  that calls this.
- Manually written `price_usd` values will be overwritten on the next
  sweep. If the user wants a sticky price (e.g. for a quote they
  already locked in), tell them to put it in `metadata` not in the
  distributor entry.

When asked to "set the price" on a Part, the right move is usually
to make sure the distributor entry has a valid `sku` + `url` and let
the refresh populate the price. If the user wants a hard-coded price
for some reason (e.g. a contract part), put it under `metadata`:

```json
"metadata": { "contract_price_usd": 0.012 }
```

so the refresh doesn't clobber it.
