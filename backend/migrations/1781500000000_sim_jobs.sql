-- SPICE simulation worker: ngspice batch simulation of .cir netlists.
--
-- Job lifecycle:
--   1. POST /run-spice  → insert with status=queued
--   2. Go worker pool claims via FOR UPDATE SKIP LOCKED  → status=running
--   3. pyworker /run-spice receives netlist string + analysis spec
--   4. ngspice -b -o output.raw parses the netlist, writes .raw output
--   5. Job row updated to status=done + result_json; or status=error + error text

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
