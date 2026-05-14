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
