-- 0005_compute_jobs.sql
-- Consolidated baseline migration (folded 2026-05-18).
-- Original migrations folded into this file are delimited below;
-- SQL is byte-exact and applied in the original order.

-- ════════════ folded: 027_fem_jobs.sql ════════════

-- FEM worker: Gmsh mesh generation + FEniCSx / CalculiX stress analysis.

create table if not exists fem_jobs (
    id            uuid primary key default gen_random_uuid(),
    file_id       uuid not null references files(id) on delete cascade,
    project_id    uuid not null references projects(id) on delete cascade,
    status        text not null default 'queued'
                  check (status in ('queued','running','done','error')),
    input_spec    jsonb not null default '{}',
    result_json   jsonb,
    error         text,
    started_at    timestamptz,
    finished_at   timestamptz,
    created_at    timestamptz not null default now()
);

create index if not exists fem_jobs_status_idx
    on fem_jobs(status, created_at)
    where status in ('queued','running');

create unique index if not exists fem_jobs_file_id_unique
    on fem_jobs(file_id)
    where status in ('queued','running');

-- ════════════ folded: 028_sim_jobs.sql ════════════

-- SPICE simulation worker: ngspice batch simulation of .cir netlists.

create table if not exists sim_jobs (
    id            uuid primary key default gen_random_uuid(),
    file_id       uuid not null references files(id) on delete cascade,
    project_id    uuid not null references projects(id) on delete cascade,
    status        text not null default 'queued'
                  check (status in ('queued','running','done','error')),
    input_spec    jsonb not null default '{}',
    result_json   jsonb,
    error         text,
    started_at    timestamptz,
    finished_at   timestamptz,
    created_at    timestamptz not null default now()
);

create index if not exists sim_jobs_status_idx
    on sim_jobs(status, created_at)
    where status in ('queued','running');

create unique index if not exists sim_jobs_file_id_unique
    on sim_jobs(file_id)
    where status in ('queued','running');

-- ════════════ folded: 029_script_extension.sql ════════════

-- Add `extension` column to files for scripting variants.

alter table files add column if not exists extension text;
create index if not exists files_extension_idx on files(extension);

-- ════════════ folded: 030_cam_jobs.sql ════════════

-- CAM toolpath generation jobs.

create table if not exists cam_jobs (
    id            uuid primary key default gen_random_uuid(),
    file_id       uuid not null references files(id) on delete cascade,
    project_id    uuid not null references projects(id) on delete cascade,
    status        text not null default 'queued'
                  check (status in ('queued','running','done','error')),
    input_spec    jsonb not null default '{}',
    result_json   jsonb,
    output_key    text,
    error         text,
    started_at    timestamptz,
    finished_at   timestamptz,
    created_at    timestamptz not null default now()
);

create index if not exists cam_jobs_status_idx
    on cam_jobs(status, created_at)
    where status in ('queued','running');

create unique index if not exists cam_jobs_file_id_unique
    on cam_jobs(file_id)
    where status in ('queued','running');
