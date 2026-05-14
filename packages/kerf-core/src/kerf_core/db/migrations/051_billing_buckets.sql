-- Three-bucket billing model: kerf_free | kerf_paid | byo_<provider>.
--
-- This migration adds the columns + tables the chat-handler bucket selector
-- needs.  cloud_user_balances is asserted (not created) because the
-- billing flow already SELECTs from it from kerf-billing/handlers.py and
-- cloud_debit_balance() is the credit accountant.

-- ── cloud_user_balances: pre-existing.  If somehow absent (fresh OSS DB
--    that never ran the cloud bootstrap), create a sane empty shape.
create table if not exists cloud_user_balances (
    user_id     uuid primary key references users(id) on delete cascade,
    credits_usd numeric(12, 4) not null default 0
);

-- ── api_tokens: pre-existing (migration 025).  Asserted-only.

-- ─────────────────────────────────────────────────────────────────────
-- Free-tier monthly quota counters
-- ─────────────────────────────────────────────────────────────────────
-- Lives on cloud_user_balances rather than a separate user_quotas table —
-- one row per user, dripped down to zero by chat-token usage, reset on the
-- 1st of every month by the daily background task in kerf-billing.
--
-- Default 100k input / 20k output tokens is enough for ~50 short chat
-- turns on a cheap model.  Calibrated against ~2¢ of COGS.
alter table cloud_user_balances
    add column if not exists free_tokens_in_remaining  bigint not null default 100000,
    add column if not exists free_tokens_out_remaining bigint not null default 20000,
    add column if not exists free_quota_resets_at      timestamptz not null default (date_trunc('month', now()) + interval '1 month');


-- ─────────────────────────────────────────────────────────────────────
-- BYO provider keys (encrypted at rest)
-- ─────────────────────────────────────────────────────────────────────
-- One row per (user, provider).  encrypted_key is AES-GCM ciphertext from
-- kerf_core.utils.encrypt.encrypt_secret with domain="byo-provider-key".
-- The nonce is bundled into the encrypted_key blob (encrypt_secret prepends
-- it), so the nonce column is redundant but kept for forward-compat in
-- case we switch encryption strategies.
create table if not exists user_provider_keys (
    user_id       uuid not null references users(id) on delete cascade,
    provider      text not null,
    encrypted_key bytea not null,
    nonce         bytea not null default ''::bytea,
    created_at    timestamptz not null default now(),
    primary key (user_id, provider)
);
create index if not exists user_provider_keys_user_idx
    on user_provider_keys(user_id);


-- ─────────────────────────────────────────────────────────────────────
-- BYO preference toggle
-- ─────────────────────────────────────────────────────────────────────
alter table users
    add column if not exists prefer_byo boolean not null default false;


-- ─────────────────────────────────────────────────────────────────────
-- Per-API-token daily spend cap (anti-compromise)
-- ─────────────────────────────────────────────────────────────────────
-- Limits the blast radius if a kerf-sdk API token leaks.  Reset daily by
-- the same background task that resets free-tier quotas.
alter table api_tokens
    add column if not exists max_spend_per_day_usd numeric(10, 2) not null default 50.00,
    add column if not exists spend_today_usd       numeric(10, 4) not null default 0.00,
    add column if not exists spend_today_date      date           not null default current_date;


-- ─────────────────────────────────────────────────────────────────────
-- usage_events.payer
-- ─────────────────────────────────────────────────────────────────────
-- Which bucket paid for this event.  No CHECK constraint — the byo_<provider>
-- variants make a clean enum awkward; we'll lint values at the application
-- layer instead.
alter table usage_events
    add column if not exists payer text not null default 'kerf_paid';
