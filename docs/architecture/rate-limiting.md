# Rate Limiting

## Why Postgres-first

Kerf deploys as a single Koyeb service group. All app servers share the
same managed Postgres instance already used for every other stateful
operation. Adding Postgres-backed rate limiting requires:

- One new table (`rate_limit_buckets`, ~200 bytes per active bucket),
- One UPSERT per rate-limited request,
- A 15-minute GC worker to prune old rows.

A Redis cluster (e.g. Upstash Redis) would reduce latency per UPSERT
from ~1 ms (local Postgres) to ~0.1 ms, but introduces an additional
dependency, operational cost, and a second source of truth. That trade-off
is not yet justified.

**Defer Redis until:**
- Postgres `pg_stat_activity` shows `rate_limit_buckets` UPSERTs consuming
  measurable CPU (> 5% of total query time), OR
- p99 UPSERT latency exceeds 10 ms (check `pg_stat_statements`), OR
- Rate-limit calls represent > 10% of total QPS.

See the "When to migrate to Redis" section below.

---

## Sliding-window pattern + UPSERT atomicity

Each request to a rate-limited endpoint performs:

```sql
INSERT INTO rate_limit_buckets (bucket_key, window_start, count)
VALUES (
    $key,
    to_timestamp(floor(extract(epoch from now()) / $window_seconds) * $window_seconds),
    1
)
ON CONFLICT (bucket_key, window_start) DO UPDATE
    SET count = rate_limit_buckets.count + 1
RETURNING count;
```

- `bucket_key` = `"{route_prefix}:{user_id_or_ip}"`.
- `window_start` is computed **server-side** by Postgres using integer-floor
  truncation of the Unix epoch. This is deterministic and immune to
  clock skew between app servers.
- The UPSERT is **atomic**: concurrent inserts for the same `(bucket_key,
  window_start)` are serialised by the primary-key constraint — no lost
  updates, no double-counting.
- If `count > max_per_window` after the UPSERT, the helper raises
  `HTTPException(429)`.

---

## Hot endpoints and their limits

| Endpoint | Limit | Window | Key by |
|---|---|---|---|
| `POST /auth/login` | 10 | 60 s | IP |
| `POST /auth/register` | 5 | 3600 s | IP |
| `POST /projects/{pid}/threads/{tid}/messages` | 30 | 60 s | user_id |
| `POST /api/projects/{pid}/files/{fid}/photos` | 60 | 60 s | user_id |
| `POST /api/projects/{pid}/git/push` | 10 | 60 s | project_id |

IP is taken from the `X-Forwarded-For` header (set by Koyeb's reverse
proxy / nginx); if absent, the raw `request.client.host` is used.

---

## 429 response shape contract

```json
{
  "detail": "rate limit exceeded",
  "retry_after": 42
}
```

- HTTP status: `429 Too Many Requests`
- `Retry-After` header: `42` (seconds until the next window opens)
- `retry_after` in the JSON body is the same integer, exposed for
  frontend toast rendering.

The frontend (`src/lib/api.js`) intercepts 429 responses in `request()`:
1. Parses `retry_after` from the JSON body.
2. Calls `toast.error("Too many requests — try again in N seconds")`.
3. Throws `ApiError(429, "rate limit exceeded")` so call-site `.catch()`
   handlers still run.

---

## GC worker

`RateLimitGCWorker` (in `packages/kerf-core/src/kerf_core/workers/`)
runs every 15 minutes and deletes rows older than 24 hours:

```sql
DELETE FROM rate_limit_buckets
WHERE window_start < now() - interval '24 hours';
```

Without GC the table would grow continuously; with default window sizes
(60 s) and ~5 active endpoints, accumulation rate is roughly
`5 * (users + IPs active per minute)` rows / minute.

---

## When to migrate to Redis

Operational signals that justify adding a managed Redis (e.g. Upstash Redis):

1. **Postgres CPU**: `rate_limit_buckets` UPSERTs appear in
   `pg_stat_statements` with > 5% of total `total_exec_time`.
2. **Latency**: p99 of `/auth/login` climbs above 50 ms and profiling
   shows the UPSERT is the bottleneck.
3. **Scale**: sustained QPS exceeds ~500 req/s across all rate-limited
   endpoints (at which point Postgres read/write throughput for tiny
   UPSERTs becomes measurable overhead).

### Migration path (same call site)

1. Add `upstash_redis_url` to settings and the Koyeb service env vars
   (via `koyeb secrets create` or the Koyeb dashboard).
2. Implement `kerf_core.rate_limit_redis.enforce(client, key, ...)` with
   the same signature as the Postgres `enforce`.
3. In `kerf_core/rate_limit.py`, check a feature flag / env var and
   delegate to the Redis backend.
4. The FastAPI dependency (`rate_limit()` factory in `dependencies.py`)
   and all route call sites are unchanged.

#### Managed Redis options

- **Upstash Redis** — serverless Redis with a free tier; works from any
  host including Koyeb. See https://upstash.com/docs/redis/overall/getstarted.
- **Koyeb managed Redis** — if your provider offers a Redis addon, add it
  via the Koyeb dashboard and inject the `REDIS_URL` as a secret.
