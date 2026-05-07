-- Cloud-only transactional email subsystem.
--
-- Two tables:
--   cloud_email_credentials — operator-configured provider creds, AES-GCM
--     encrypted with the same scheme used by distributor_credentials and
--     cloud_github_tokens (see backend/internal/auth/encrypt.go). Domain
--     string `cloud:email-credentials`.
--   cloud_email_log — every email we attempt to send, queued first then
--     dispatched by the in-process drain goroutine. Status transitions:
--     queued → sent | failed (after 3 retries with exponential backoff).
--
-- The OSS build never references these tables; they live behind the
-- `cloud` build tag and the cloud migration runner.

create table if not exists cloud_email_credentials (
    id uuid primary key default gen_random_uuid(),
    provider text not null unique check (provider in ('resend','ses','smtp')),
    enabled boolean not null default true,
    -- AES-GCM-encrypted JSON: {api_key, from_email, from_name?, region?,
    -- smtp_host?, smtp_port?, smtp_username?, smtp_password?}.
    -- Provider-specific fields outside the common ones are tolerated.
    secret_encrypted bytea not null,
    rate_limit_per_minute int not null default 60,
    last_used_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists cloud_email_log (
    id uuid primary key default gen_random_uuid(),
    -- Some emails (e.g. an admin test send to a non-account address) won't
    -- have a user_id; keep nullable. ON DELETE SET NULL so user deletions
    -- preserve the audit trail.
    user_id uuid references users(id) on delete set null,
    template text not null,
    to_email text not null,
    -- Provider that handled the send. Null while queued.
    provider text,
    status text not null default 'queued'
        check (status in ('queued','sent','failed')),
    error text,
    sent_at timestamptz,
    created_at timestamptz not null default now()
);

-- Most reads are "what did this user receive recently?" — covered by the
-- (user_id, created_at desc) index.
create index if not exists cloud_email_log_user_idx
    on cloud_email_log(user_id, created_at desc);

-- Drain queries scan for queued/failed rows; partial index keeps the
-- working set small once history accumulates.
create index if not exists cloud_email_log_status_idx
    on cloud_email_log(status, created_at)
    where status in ('queued','failed');
