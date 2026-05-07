# Distributor APIs (Library Phase 2)

Live pricing and stock for `.part` files come from real distributor
APIs (DigiKey, Mouser, LCSC). The distributor metadata lives inside
the Part JSON's `distributors` array; the kerf server refreshes it
periodically and on-demand. The LLM never calls a distributor API
directly — read the existing `distributors[*].price_usd` and
`distributors[*].stock` fields and trust them.

## How prices get populated

There are two paths:

1. **Manual.** A user (or you, on their behalf via instructions to
   them) calls `POST /api/projects/:pid/files/:fid/distributors/refresh`.
   The server walks the Part's `distributors` array, looks each entry
   up against the matching distributor service, and rewrites the
   Part. The endpoint returns the updated Part JSON.
2. **Automatic.** Every 6 hours, a boot-time goroutine sweeps every
   Part whose `distributors[*].fetched_at` is older than 24 hours
   and refreshes them through the same code path. The sweep respects
   per-distributor rate limits.

Both paths require the operator to have configured an API credential
for that distributor — see "When a distributor is missing" below.

## What's in a distributor entry

```json
{
  "name": "digikey",
  "sku": "311-10.0KCRCT-ND",
  "url": "https://www.digikey.com/.../RC0805FR-0710KL",
  "price_usd": 0.014,
  "stock": 5000,
  "fetched_at": "2026-05-01T12:00:00Z"
}
```

- `name` is the canonical lowercase distributor key. Supported
  live-priced names: `digikey`, `mouser`, `lcsc`.
- `sku` is what the distributor calls the part. Required for `Lookup`;
  if missing, the sync falls back to a free-text Search using the
  Part's `manufacturer + name` or `mpn`.
- `url` is the human-facing product page. Always populated (either
  user-supplied or filled in by the refresh).
- `price_usd` and `stock` are populated by the refresh. May be missing
  on a brand-new entry until the next sweep.
- `fetched_at` is RFC3339 UTC. The "stale" cutoff is 24 hours.

## Supported distributors

| Name        | API support           | Pricing currency  | Notes                                    |
| ----------- | --------------------- | ----------------- | ---------------------------------------- |
| `digikey`   | Yes (OAuth2 + REST)   | USD               | Lookup by SKU; falls back to keyword.    |
| `mouser`    | Yes (REST + key)      | USD               | Locale-bound; configure US for USD.      |
| `lcsc`      | Yes (REST)            | CNY → USD via FX  | USD conversion needs the cloud FX cache. |
| `mcmaster`  | URL-only              | n/a               | No public API; store the catalog URL.    |

`mcmaster` distributors render in the BOM panel as a clickable link
but never get a `price_usd` or `stock` value — McMaster doesn't
publish a pricing API. For mech parts that need a paper-trail, write
the `mcmaster.com/<sku>` URL into `distributors[0].url` and leave
`price_usd` empty. Don't fabricate prices.

## When a distributor is missing

If you ask the user to refresh prices but no rows come back populated,
the most likely cause is the operator hasn't configured credentials for
that distributor. The admin UI is at `/admin/distributors`. Tell the
user something like:

> The DigiKey lookup returned nothing because no DigiKey API
> credentials are configured. Open `/admin/distributors` (admin only)
> and add a DigiKey OAuth client_id + client_secret, then try the
> refresh again.

Don't claim you can configure it for them — the credential entry is
out of band of the LLM tool surface for security reasons.

## Errors you might see

The refresh endpoint returns HTTP 502 for distributor-side failures
(rate limits, expired tokens, malformed responses). The error body
includes a short reason. If a refresh is hitting a steady 502, the
admin's stored credentials likely need re-entering — JWT secret
rotations invalidate stored credentials by design.

## What you should NOT do

- Don't write `price_usd` or `stock` values yourself. They're managed
  by the refresh subsystem; manual edits will be overwritten on the
  next sweep.
- Don't invent SKUs. If the user gives you a manufacturer + MPN,
  search DigiKey or Mouser through the web (out of band) and write
  the SKU + URL into the entry; the refresh will populate price/stock
  on the next pass.
- Don't try to mirror a distributor's full catalog into the project.
  The library is intentionally per-design — Parts are added when
  they're referenced by an Assembly, not pre-filled.

## Manual refresh request shape

```http
POST /api/projects/<pid>/files/<fid>/distributors/refresh

200 OK
{
  "updated": 2,
  "content": "{\n  \"version\": 1,\n  \"name\": \"...\",\n  \"distributors\": [...]\n}"
}
```

The `updated` count is the number of `distributors[*]` entries whose
`fetched_at` was rewritten. `0` is a valid (stable) result —
distributors that were already fresh, or whose service isn't
configured, simply pass through unchanged.
