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
