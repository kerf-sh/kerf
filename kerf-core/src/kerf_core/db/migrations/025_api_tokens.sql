-- API tokens for kerf-sdk auth (workspace-scoped).

create table if not exists api_tokens (
    id          uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id) on delete cascade,
    user_id     uuid not null references users(id) on delete cascade,
    token_hash  text unique not null,
    name        text not null,
    scopes      jsonb not null default '["workspace:member-role"]',
    last_used_at timestamptz,
    revoked_at  timestamptz,
    created_at  timestamptz not null default now()
);
create index if not exists api_tokens_workspace_idx on api_tokens(workspace_id);
create index if not exists api_tokens_user_idx on api_tokens(user_id);
create index if not exists api_tokens_token_hash_idx on api_tokens(token_hash);
