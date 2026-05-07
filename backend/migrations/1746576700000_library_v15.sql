-- Library v1.5 — verified-publisher curation flag.
--
-- The `is_verified_publisher` column marks user accounts that the kerf
-- maintainers have hand-curated (Adafruit, SparkFun, Pololu, McMaster,
-- Misumi, etc.). The Workshop /api/workshop/parts endpoint uses it to
-- support a `verified_only=true` filter and the frontend renders a badge
-- next to listings authored by these users.
--
-- The remaining v1.5 features — per-Part visibility ('private' /
-- 'unlisted' / 'public') and attached product photos — live inside the
-- Part JSON document (the `content` column on `kind='part'` files). No
-- new column on `files`. See src/lib/part.js + part_tools.go.

alter table users add column if not exists is_verified_publisher boolean not null default false;
create index if not exists users_is_verified_publisher_idx on users(is_verified_publisher) where is_verified_publisher = true;
