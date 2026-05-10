-- Phase 4 hardening: chain-corruption detection.
--
-- Each revision row gains a `content_sha256` column holding the SHA-256
-- of its FULLY-RECONSTRUCTED content. The reader verifies this hash
-- after walking parents + applying diffs; a mismatch means the chain
-- got corrupted (a parent row was edited in-place, a diff was lost,
-- or the algorithm changed under us). Verification is best-effort —
-- legacy rows pre-dating this column have NULL hashes and skip the
-- check.
--
-- This is additive only: NULL is allowed, no backfill required. New
-- writes populate the column; the migrate-revisions backfill command
-- fills it for old rows opportunistically.

alter table file_revisions
    add column if not exists content_sha256 bytea;
