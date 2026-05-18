-- 0013_kind_pid.sql
-- Clean-baseline kind addition for kerf-piping (T-167).
--
-- Adds the 'pid' kind to files.kind check constraint so that P&ID diagram
-- files can be stored in the files table.
--
-- BASELINE NOTE: fold 'pid' into the files_kind_check in 0001_core_identity.sql
-- when the next full DB reset occurs (add it alongside 'wiring','firmware').
--
-- Idempotent: drop-and-recreate the constraint so re-running on an up-to-date
-- DB is a no-op (the new set is a strict superset of the old set).

alter table files drop constraint if exists files_kind_check;
alter table files add constraint files_kind_check check (
    kind in (
        'file','folder','assembly','step','drawing','sketch','part','feature',
        'circuit','equations','material','simulation','script','step-ref',
        'assembly_lock','canvas','schedule','view','sheet','duct','pipe',
        'conduit','subd','mesh','render','section','cam_layered','tool',
        'plc_st','plc_ld','quadmesh','print','gem','wiring','firmware','pid'
    )
);
