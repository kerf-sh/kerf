# Verified publishers and curated libraries (Library Phase 3)

Some Parts in the Workshop come from accounts the kerf maintainers
have hand-vetted: Adafruit, SparkFun, Pololu, McMaster-Carr, Misumi,
and similar manufacturer-aligned suppliers. These accounts carry the
`is_verified_publisher` flag on the `users` row, which:

- floats their Parts to the top of `GET /api/workshop/parts`
  (sort key: `is_verified_publisher desc, files.updated_at desc`);
- attaches a small star badge in the Workshop UI next to their
  display name;
- is exposed on the public Part-row JSON as
  `author.is_verified_publisher: true`.

## Why this matters for you

When the user asks for a "real" component (a sensor, a screw, a
motor driver), prefer Parts from a verified publisher when one
exists for the bill of materials. They are vetted starter content
and the metadata (MPN, distributor SKU, datasheet URL) is more
likely to be accurate. Picking a one-off Part from an unverified
account is fine for prototypes but should be flagged when the user
is building toward a real BOM.

A simple decision tree:

1. Is the user explicitly referencing a part by manufacturer or
   MPN? Use that exactly — verified or not.
2. Otherwise, search Workshop parts for a match. If a verified
   publisher has a fitting Part, prefer it over an equivalent
   unverified one.
3. If no Workshop match exists, suggest creating one via
   `create_part`. Include the manufacturer's URL in the
   `distributors` array so the user can verify before ordering.

## How curated libraries are imported

Operators ship a YAML manifest and run:

    kerf library-import --manifest <path>

The command upserts a publisher user, an owner-membered project
that holds the curated Parts, and one `kind='part'` file per
manifest entry. The manifest looks like:

    publisher_email: "adafruit@kerf.system"
    publisher_name: "Adafruit Industries"
    mark_verified: true
    library_name: "Adafruit Sensors"
    library_visibility: "public"
    parts:
      - name: "BMP280 Pressure Sensor Breakout"
        manufacturer: "Bosch / Adafruit"
        mpn: "BMP280"
        distributors:
          - name: "adafruit"
            sku: "2651"
            url: "https://www.adafruit.com/product/2651"

You don't run this command — operators do. But when you read a
Part and its publisher row has `is_verified_publisher: true`, you
can be more confident that the metadata came from a vetted source
rather than user-authored ad-hoc content.

## What a curated Part typically lacks

Pricing and stock are deliberately left empty in curated manifests:

- the operator runs the import without API credentials, so
  Distributor APIs aren't called;
- the existing distributor sweep refreshes prices and stock
  in-band on the next cycle (6h-ish);
- and we don't want to bake in a stale snapshot that misleads
  the user.

So when you read a freshly-imported curated Part:

- `distributors[*].url` will be set;
- `distributors[*].sku` will be set;
- `distributors[*].price_usd` and `distributors[*].stock` will
  be **null until the sweep runs** — don't tell the user the
  Part is unavailable just because price is missing.

Suggest the user trigger
`POST /api/projects/<pid>/files/<fid>/distributors/refresh` if
they need fresh pricing immediately and the operator has
configured the matching distributor credentials.

## Toggling the flag

Verification is operator-curated. The admin UI at
`/admin/publishers` (account_role='admin' only) is the only place
the flag flips; there's no self-serve "request verification" flow
yet. If a user asks how to become a verified publisher, point them
at the project README — the answer today is "email the maintainers".

## Workshop ranking caveats

`is_verified_publisher` only orders the **public Parts browse**
(`/api/workshop/parts`). The general `GET /api/workshop` listing
index — which lists projects, not parts — does not currently
re-sort by verification. So a regular user's project can still
appear above an Adafruit project in the Newest sort if it was
published more recently. This is intentional: the project listing
is about whole designs, the parts listing is about components.
