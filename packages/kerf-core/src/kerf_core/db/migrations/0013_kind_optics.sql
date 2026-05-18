-- 0013_kind_optics.sql
-- Add 'optics' to the files.kind check constraint (T-169 optics seed).
--
-- Clean baseline: drop the existing constraint and replace it with the
-- extended set. Parent DB reset is required on first apply (flag below).
--
-- FLAG: parent-reset required — new files.kind value 'optics' added.

alter table files drop constraint if exists files_kind_check;
alter table files add constraint files_kind_check check (
    kind in (
        'file','folder','assembly','step','drawing','sketch','part','feature',
        'circuit','equations','material','simulation','script','step-ref',
        'assembly_lock','canvas','schedule','view','sheet','duct','pipe',
        'conduit','subd','mesh','render','section','cam_layered','tool',
        'plc_st','plc_ld','quadmesh','print','gem','wiring','firmware',
        'optics'
    )
);
