-- Add 'section' to the files.kind enumeration for plane cross-section results.
-- A .section file stores the edge compound produced by BRepAlgoAPI_Section
-- (a 2D outline that can be dimensioned, exported to DXF, or chained into
-- feature_pad).

alter table files drop constraint if exists files_kind_check;
alter table files add constraint files_kind_check check (
    kind in ('file','folder','assembly','step','drawing','sketch','part','feature','circuit','equations','material','simulation','script','step-ref','assembly_lock','canvas','schedule','view','sheet','duct','pipe','conduit','subd','mesh','render','section')
);
