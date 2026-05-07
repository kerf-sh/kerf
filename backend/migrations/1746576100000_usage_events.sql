-- usage_events: per-user log of LLM token use and storage deltas.
-- Lives in OSS migrations because both OSS and cloud builds record events.
-- The cloud build computes cost + debits balances on top of the same rows.

create table if not exists usage_events (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    project_id uuid references projects(id) on delete set null,

    -- "token" or "storage". Kept loose (text) to allow future kinds
    -- without a migration; CHECK enforces the current vocabulary.
    kind text not null check (kind in ('token','storage')),

    -- Token kind
    model text,
    input_tokens int not null default 0,
    output_tokens int not null default 0,

    -- Storage kind
    bytes_delta bigint not null default 0,

    -- Cost in USD (computed at event time using the active pricing).
    -- Always populated; OSS builds compute it for visibility, cloud
    -- builds debit balances against it.
    usd_cost numeric(12, 6) not null default 0,

    created_at timestamptz not null default now()
);
create index if not exists usage_events_user_id_idx on usage_events(user_id, created_at desc);
create index if not exists usage_events_project_id_idx on usage_events(project_id, created_at desc);
create index if not exists usage_events_kind_idx on usage_events(kind, created_at desc);
