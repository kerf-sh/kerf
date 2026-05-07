-- Library Phase 2 — operator-configured distributor API credentials.
--
-- Each row stores the encrypted shared secret for one distributor
-- service (DigiKey, Mouser, LCSC). The plaintext payload before
-- encryption is JSON-shaped:
--   - DigiKey: {"client_id": "...", "client_secret": "..."} (OAuth2
--     client_credentials grant)
--   - Mouser:  {"api_key": "..."}
--   - LCSC:    {"api_key": "..."}
--
-- Encryption: AES-GCM via backend/internal/auth.EncryptSecret with the
-- domain "distributor-credentials". The key derives from cfg.JWTSecret
-- so rotating the JWT secret invalidates every stored credential — the
-- operator simply re-enters them. See cloud/README.md for the gotcha.
--
-- Lives in OSS migrations (not cloud) because operators self-hosting
-- Kerf may want distributor lookups in the BOM panel even without the
-- cloud billing layer.

create table if not exists distributor_credentials (
    id uuid primary key default gen_random_uuid(),
    name text not null unique,
    enabled boolean not null default true,
    -- AES-GCM ciphertext. JSON plaintext per the comment above.
    secret_encrypted bytea not null,
    rate_limit_per_minute int not null default 60 check (rate_limit_per_minute > 0),
    last_used_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- Names are constrained at the application layer (digikey | mouser |
-- lcsc) — adding new distributors should not require a schema change.
create index if not exists distributor_credentials_enabled_idx
    on distributor_credentials(enabled) where enabled = true;
