-- Cloud-only schema. Applied only when the migrate command is invoked
-- with a cloud-aware build (see cmd/migrate auto-detection of
-- backend/cloud/migrations).
--
-- Tables prefixed `cloud_` to make the OSS/cloud boundary obvious in DB
-- introspection.

-- Per-user prepaid credit balance. Top-ups via Paystack add to this;
-- usage_events debits at event time.
create table if not exists cloud_user_balances (
    user_id uuid primary key references users(id) on delete cascade,
    credits_usd numeric(12, 6) not null default 0,
    updated_at timestamptz not null default now()
);

-- Paystack customer linkage. Created on first checkout/top-up.
create table if not exists cloud_paystack_customers (
    user_id uuid primary key references users(id) on delete cascade,
    customer_code text unique,
    customer_id bigint,
    email citext not null,
    created_at timestamptz not null default now()
);

-- Top-up invoices. status: 'pending' | 'success' | 'failed' | 'abandoned'.
-- amount_usd is what the user agreed to top up; amount_zar / fx_rate are
-- captured at charge time so refund calculations don't drift.
create table if not exists cloud_invoices (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    reference text unique not null,            -- Paystack reference
    status text not null default 'pending'
        check (status in ('pending','success','failed','abandoned')),
    amount_usd numeric(12, 2) not null,
    amount_zar numeric(12, 2) not null,
    fx_rate numeric(12, 6) not null,           -- USD→ZAR rate used (incl. spread)
    paystack_response jsonb,                    -- raw verify response for audit
    created_at timestamptz not null default now(),
    paid_at timestamptz
);
create index if not exists cloud_invoices_user_id_idx on cloud_invoices(user_id, created_at desc);
create index if not exists cloud_invoices_status_idx on cloud_invoices(status);

-- FX rate cache. Refreshed daily from cloud.fx.refresh_url. Latest row
-- per (base, target) pair is the active one; older rows are kept for
-- historical recompute (e.g. refund using the rate at the time).
create table if not exists cloud_fx_rates (
    id uuid primary key default gen_random_uuid(),
    base_currency text not null,
    target_currency text not null,
    rate numeric(12, 6) not null,             -- raw fetched rate (no spread)
    fetched_at timestamptz not null default now()
);
create index if not exists cloud_fx_rates_pair_idx
    on cloud_fx_rates(base_currency, target_currency, fetched_at desc);

-- Add a simple SQL function so OSS handlers (which can't import the
-- cloud package) can debit a balance atomically. Lives in cloud
-- migrations because the table doesn't exist in OSS-only DBs.
create or replace function cloud_debit_balance(p_user uuid, p_amount numeric)
returns void language sql as $$
    insert into cloud_user_balances(user_id, credits_usd)
    values (p_user, -p_amount)
    on conflict (user_id) do update
    set credits_usd = cloud_user_balances.credits_usd - p_amount,
        updated_at = now();
$$;
