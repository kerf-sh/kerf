-- 0003_revisions_prefs.sql
-- Consolidated baseline migration (folded 2026-05-18).
-- Original migrations folded into this file are delimited below;
-- SQL is byte-exact and applied in the original order.

-- ════════════ folded: 013_revision_diffs.sql ════════════

-- Phase 4: diff-based + compressed revisions.

alter table file_revisions
    add column if not exists kind text not null default 'base'
        check (kind in ('base', 'diff'));

alter table file_revisions
    add column if not exists content_gz bytea;

alter table file_revisions
    add column if not exists parent_revision_id uuid
        references file_revisions(id) on delete set null;

alter table file_revisions
    add column if not exists content_preview text;

create index if not exists file_revisions_file_id_kind_idx
    on file_revisions(file_id, kind);

-- ════════════ folded: 014_drop_jewelry_type.sql ════════════

-- Drop the 'jewelry' project_type.

update projects set project_type = 'mechanical' where project_type = 'jewelry';

alter table projects drop constraint if exists projects_project_type_check;
alter table projects add constraint projects_project_type_check
    check (project_type in ('mechanical','electronics','architecture'));

-- ════════════ folded: 015_project_tags.sql ════════════

-- Drop the project_type enum; replace with free-form `tags TEXT[]`.

alter table projects add column tags text[] not null default '{}';
update projects set tags = array[project_type] where project_type is not null;
alter table projects drop constraint if exists projects_project_type_check;
alter table projects drop column project_type;
create index if not exists projects_tags_gin_idx on projects using gin (tags);

-- ════════════ folded: 016_user_avatar_storage.sql ════════════

-- User avatars: storage_key tracks the blob.

alter table users add column if not exists avatar_storage_key text;
alter table users add column if not exists avatar_updated_at timestamptz;

-- ════════════ folded: 017_user_preferences.sql ════════════

-- Per-user UI preferences.

alter table users add column preferences jsonb not null default '{}'::jsonb;

-- ════════════ folded: 018_revision_sha256.sql ════════════

-- Phase 4 hardening: chain-corruption detection.

alter table file_revisions
    add column if not exists content_sha256 bytea;
