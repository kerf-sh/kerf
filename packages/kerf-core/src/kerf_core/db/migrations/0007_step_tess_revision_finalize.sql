-- 0007_step_tess_revision_finalize.sql
-- Consolidated baseline migration (folded 2026-05-18).
-- Original migrations folded into this file are delimited below;
-- SQL is byte-exact and applied in the original order.

-- ════════════ folded: 047_step_tess_input_spec.sql ════════════

-- Server-side STEP pre-tessellation finalization.
--
-- 1. Add jsonb input_spec column to step_tessellation_jobs so the cloud-tier
--    auto-tess worker can carry per-upload resolution / export-format hints.
--
-- 2. Add content_sha256 column so we can write the mesh blob to
--    derived_artifacts keyed by (file_id, sha256, 'step_mesh') for idempotency.
--
-- 3. Extend derived_artifacts.derived_kind check constraint to accept
--    'step_mesh' (mesh artifact produced from a STEP file by the cloud-tier
--    auto-tess worker).

alter table step_tessellation_jobs
    add column if not exists input_spec jsonb;

alter table step_tessellation_jobs
    add column if not exists content_sha256 text;

alter table derived_artifacts
    drop constraint if exists derived_artifacts_derived_kind_check;

alter table derived_artifacts
    add constraint derived_artifacts_derived_kind_check
    check (derived_kind in ('jscad_mesh', 'sketch_geom2', 'circuit_board_3d', 'step_mesh'));

-- ════════════ folded: 048_revision_compaction.sql ════════════

-- Phase 4: revision DB efficiency — compaction improvements.
--
-- 1. content_codec column: 'plain' | 'gzip'
--    When present, signals that content_gz stores raw bytea compressed
--    content rather than the legacy base64-encoded-string-in-text field.
--    Existing rows (NULL / 'plain') are treated as the old encoding path.
--
-- 2. content_sha256 gets a NOT NULL constraint eventually, but for now
--    we just ensure the index exists for dedup lookups.
--
-- All changes are purely additive — no destructive alterations.

alter table file_revisions
    add column if not exists content_codec text not null default 'plain'
        check (content_codec in ('plain', 'gzip'));

-- Index for fast dedup look-up: "does this file already have a revision
-- with this exact sha256?" Used by write_revision to skip identical saves.
create index if not exists file_revisions_file_sha256_idx
    on file_revisions(file_id, content_sha256)
    where content_sha256 is not null;

-- Index used by safe pruning: given a file, find the oldest revision whose
-- id does NOT appear as anyone's parent_revision_id.
create index if not exists file_revisions_parent_revision_id_idx
    on file_revisions(parent_revision_id)
    where parent_revision_id is not null;

-- ════════════ folded: 049_revision_content_ref.sql ════════════

-- Phase 5: cross-file hash dedup — add 'ref' as a valid delta_kind value.
--
-- A 'ref' row is a zero-content pointer: it records that the file had
-- content identical to an existing 'base' row elsewhere in file_revisions.
-- The parent_revision_id of a 'ref' row points to that shared base row.
-- Reconstruction follows the pointer and returns the base row's content.
--
-- All changes are purely additive — no DROP, no MODIFY, no data loss.
--
-- Prior CHECK: delta_kind IN ('base', 'diff')
--   (NOTE: the column was named 'kind' not 'delta_kind' in the original
--    schema; we extend whichever constraint exists)
--
-- The safest cross-version approach is to drop the old check and add a
-- new one that includes 'ref'.  This is additive from the data perspective
-- because no existing rows have kind='ref'.

-- Step 1: drop the old check constraint on the 'kind' column (name may
-- vary across environments; use IF EXISTS on the named variant).
alter table file_revisions
    drop constraint if exists file_revisions_kind_check;

alter table file_revisions
    drop constraint if exists file_revisions_delta_kind_check;

-- Step 2: re-add the constraint including 'ref'.
alter table file_revisions
    add constraint file_revisions_kind_check
        check (kind in ('base', 'diff', 'ref'));

-- Step 3: index for cross-file dedup look-up.
-- "Does any base row in the table have this sha256?"
-- Used by write_revision before deciding to insert a duplicate blob.
create index if not exists file_revisions_sha256_base_idx
    on file_revisions(content_sha256)
    where kind = 'base';
