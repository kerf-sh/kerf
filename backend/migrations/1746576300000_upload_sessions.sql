-- Resumable / chunked upload sessions. Each session tracks a single in-flight
-- binary upload (currently STEP files), broken into fixed-size chunks. The
-- client initialises the session with the file's claimed SHA-256, sends the
-- chunks, then calls finalize — at which point the server verifies the hash,
-- promotes the assembled blob into permanent storage, creates the matching
-- `files` row, and deletes the session.
--
-- Incomplete sessions auto-expire after `expires_at`; a janitor goroutine in
-- the server sweeps them and the corresponding temp storage prefix.

create table if not exists upload_sessions (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects(id) on delete cascade,
    user_id uuid not null references users(id) on delete cascade,
    filename text not null,
    size bigint not null,
    mime text,
    sha256 text not null,
    storage_key text not null,
    chunk_size int not null default 5242880,
    total_chunks int not null,
    received_chunks int[] not null default '{}',
    bytes_received bigint not null default 0,
    complete boolean not null default false,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null default now() + interval '24 hours'
);
create index if not exists upload_sessions_project_id_expires_idx on upload_sessions(project_id, expires_at);
create index if not exists upload_sessions_sha256_idx on upload_sessions(project_id, sha256);
