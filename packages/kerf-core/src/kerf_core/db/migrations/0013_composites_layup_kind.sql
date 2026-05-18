-- 0013_composites_layup_kind.sql
-- Clean-baseline migration: adds 'layup' to the files.kind check constraint.
--
-- This extends the kind enum for the kerf-composites package (T-173).
-- The DROP/ADD pattern is idempotent and matches the precedent in 0001_core_identity.sql.
--
-- ⚠ FLAG: Requires a parent-coordinated DB reset if applied on a live DB that
-- already has rows with kind values not in the new constraint set. On a fresh
-- DB (or after reset) this is fully idempotent.

alter table files drop constraint if exists files_kind_check;
alter table files add constraint files_kind_check check (
    kind in (
        'file','folder','assembly','step','drawing','sketch','part','feature',
        'circuit','equations','material','simulation','script','step-ref',
        'assembly_lock','canvas','schedule','view','sheet','duct','pipe',
        'conduit','subd','mesh','render','section','cam_layered','tool',
        'plc_st','plc_ld','quadmesh','print','gem','wiring','firmware',
        'layup'
    )
);
