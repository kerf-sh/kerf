-- FEM worker: Gmsh mesh generation + FEniCSx / CalculiX stress analysis.
--
-- Job lifecycle:
--   1. POST /api/projects/{pid}/files/{fid}/fem  → insert with status=queued
--   2. Go worker pool claims via FOR UPDATE SKIP LOCKED  → status=running
--   3. pyworker /run-fem receives step_bytes + input_spec JSON
--   4. Gmsh meshes the STEP, FEniCSx runs the analysis, result JSON written
--   5. Job row updated to status=done + result_json; or status=error + error text

create table if not exists fem_jobs (
    id            uuid primary key default gen_random_uuid(),
    file_id       uuid not null references files(id) on delete cascade,
    project_id    uuid not null references projects(id) on delete cascade,
    status        text not null default 'queued'
                  check (status in ('queued','running','done','error')),
    input_spec    jsonb not null default '{}',
    result_json   jsonb,                              -- populated when done
    error         text,
    started_at    timestamptz,
    finished_at   timestamptz,
    created_at    timestamptz not null default now()
);

create index if not exists fem_jobs_status_idx
    on fem_jobs(status, created_at)
    where status in ('queued','running');

-- One active job per file. Re-enqueueing is an explicit operator action.
create unique index if not exists fem_jobs_file_id_unique
    on fem_jobs(file_id)
    where status in ('queued','running');