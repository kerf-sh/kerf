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
