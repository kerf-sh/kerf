-- Cross-project derived-artifact cache.

create table if not exists derived_artifacts (
    id uuid primary key default gen_random_uuid(),
    source_file_id uuid not null references files(id) on delete cascade,
    content_sha256 text not null,
    derived_kind text not null
        check (derived_kind in ('jscad_mesh', 'sketch_geom2', 'circuit_board_3d')),
    payload bytea not null,
    payload_size_bytes int not null default 0,
    created_at timestamptz not null default now(),
    last_accessed_at timestamptz not null default now()
);

create unique index if not exists derived_artifacts_key_idx
    on derived_artifacts(source_file_id, content_sha256, derived_kind);
create index if not exists derived_artifacts_lru_idx
    on derived_artifacts(last_accessed_at);
