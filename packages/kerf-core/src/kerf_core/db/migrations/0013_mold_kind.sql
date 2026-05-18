-- 0013_mold_kind.sql
-- Add 'mold' to files.kind constraint for T-165 injection-mold tooling seed.
--
-- Extends the files_kind_check constraint to accept 'mold' files created by
-- the kerf-mold package. Follows the folded-baseline pattern: the authoritative
-- list in 0001_core_identity.sql is updated in parallel; this migration applies
-- the live constraint update on already-migrated databases.

alter table files drop constraint if exists files_kind_check;
alter table files add constraint files_kind_check check (
    kind in ('file','folder','assembly','step','drawing','sketch','part','feature','circuit','equations','material','simulation','script','step-ref','assembly_lock','canvas','schedule','view','sheet','duct','pipe','conduit','subd','mesh','render','section','cam_layered','tool','plc_st','plc_ld','quadmesh','print','gem','wiring','firmware','mold')
);
