-- Resumable / chunked upload sessions.

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
