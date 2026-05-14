-- Performance Phase 3: server-side STEP pre-tessellation.

create table if not exists step_tessellation_jobs (
    id uuid primary key default gen_random_uuid(),
    file_id uuid not null references files(id) on delete cascade,
    status text not null default 'queued'
        check (status in ('queued','running','done','error')),
    error text,
    mesh_storage_key text,
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz not null default now()
);

create index if not exists step_tessellation_jobs_status_idx
    on step_tessellation_jobs(status, created_at)
    where status in ('queued','running');

create unique index if not exists step_tessellation_jobs_file_id_unique
    on step_tessellation_jobs(file_id);

alter table files add column if not exists mesh_storage_key text;
