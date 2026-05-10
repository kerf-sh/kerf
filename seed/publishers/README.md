# seed/publishers

Curated seed content for the **`kerf-system`** verified-publisher account — the
first-party `kerf` library that ships with the binary so a fresh install has
something for `LibraryPicker` and the Workshop "Verified" filter to surface
out of the box.

## What this seeds

Running `npm run seed:publishers` (or `go run ./cmd/seed-publishers` from
`backend/`) is **idempotent** and produces the following rows on first run:

1. A `users` row with:
   - `id = 6b657266-0000-4000-8000-000000000001` (the literal ASCII bytes
     of `kerf` followed by zeros — fixed UUID so re-runs find the row).
   - `email = system@kerf.local`
   - `name = Kerf System`
   - `account_role = 'system'`
   - `is_verified_publisher = true`
   - `is_system = true`
2. A `workspaces` row owned by that user, with `slug = 'kerf-system'`,
   `name = 'Kerf System'`, plus the matching `workspace_members(role='owner')`.
3. A `projects` row called `Common Components`, `visibility = 'public'`,
   inside the `kerf-system` workspace.
4. One `files` row per `parts/*.json` in this directory, `kind='part'`,
   `content` set to the JSON-encoded `partDoc` (the same shape Kerf reads
   when a `.part` file is opened in the editor — see
   `backend/internal/tools/part_tools.go`).

Re-running the script never duplicates rows: users / workspaces / projects
upsert by their stable identifiers; parts upsert by `(project_id, name)`
inside the project.

## Layout

```
seed/publishers/
├── README.md          (this file)
└── parts/
    ├── resistor-10k-0603.json
    ├── resistor-1k-0603.json
    ├── resistor-330r-0603.json
    ├── capacitor-100nf-0603.json
    └── capacitor-10uf-0805.json
```

Each file under `parts/` is a JSON document conforming to `partDoc`
(`backend/internal/tools/part_tools.go`). The minimum viable set of fields
is `version`, `name`, and `distributors`; everything else is optional but
recommended (`description`, `category`, `manufacturer`, `mpn`, `value`,
`visibility`, `metadata`).

## Why this is small

This is intentionally a **demonstration set** — five common SMD passives —
to prove the verified-publisher pipeline end-to-end without inflating the
repo. The maintainer-PR-submission flow (manufacturers contributing larger
catalogs) is the next milestone; expect to scale to per-vendor seed
directories (`seed/publishers/adafruit/`, `seed/publishers/sparkfun/`,
etc.) once that flow lands.

## Adding a part by PR

Drop a new `<slug>.json` file into `parts/`. Keep the file under ~1 KB and
mirror the shape of the existing examples. Re-run `npm run seed:publishers`
locally to confirm the seed succeeds and the part appears under the
`Common Components` project in the `kerf-system` workspace.
