-- Add 'cam_layered' to the files.kind enumeration.
-- A .cam.layered file stores the stacked 2-D contour output of the
-- feature_cam_layered op: one edge-segment list per Z (or X/Y) slice,
-- ready to feed into the existing cam_contour op with Z-step retracts.

alter table files drop constraint if exists files_kind_check;
alter table files add constraint files_kind_check check (
    kind in ('file','folder','assembly','step','drawing','sketch','part','feature','circuit','equations','material','simulation','script','step-ref','assembly_lock','canvas','schedule','view','sheet','duct','pipe','conduit','subd','mesh','render','section','cam_layered')
);
