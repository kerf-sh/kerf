-- Library Phase 2 — operator-configured distributor API credentials.

create table if not exists distributor_credentials (
    id uuid primary key default gen_random_uuid(),
    name text not null unique,
    enabled boolean not null default true,
    secret_encrypted bytea not null,
    rate_limit_per_minute int not null default 60 check (rate_limit_per_minute > 0),
    last_used_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists distributor_credentials_enabled_idx
    on distributor_credentials(enabled) where enabled = true;
