-- Performance Phase 3: server-side STEP pre-tessellation.
--
-- After a STEP upload finalizes, a row lands in `step_tessellation_jobs`
-- and a background worker:
--   1. fetches the STEP blob via Storage,
--   2. runs occt-import-js (Node sidecar) to produce a glTF binary (.glb),
--   3. uploads the .glb to `mesh_storage_key`, and
--   4. flips the job to status='done' + writes files.mesh_storage_key.
--
-- The frontend prefers the .glb (cheap GLTFLoader parse) over re-parsing
-- the STEP via WASM, falling back to the existing in-browser path when
-- the job is still queued/running or has errored.

create table if not exists step_tessellation_jobs (
    id uuid primary key default gen_random_uuid(),
    file_id uuid not null references files(id) on delete cascade,
    status text not null default 'queued'
        check (status in ('queued','running','done','error')),
    error text,
    mesh_storage_key text,           -- populated when done
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz not null default now()
);

create index if not exists step_tessellation_jobs_status_idx
    on step_tessellation_jobs(status, created_at)
    where status in ('queued','running');

-- One job row per file. Re-enqueueing is an explicit operator action
-- (UPDATE ... SET status='queued') rather than a duplicate insert.
create unique index if not exists step_tessellation_jobs_file_id_unique
    on step_tessellation_jobs(file_id);

-- New column on files: mesh_storage_key holds the .glb blob's storage key
-- once the worker has produced one. NULL until the job completes (or
-- forever if the file isn't a STEP / the worker errored).
alter table files add column if not exists mesh_storage_key text;
