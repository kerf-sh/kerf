-- Add 'gem' to the files.kind enumeration so gemstone library files (.gem,
-- JSON) can be stored alongside jewellery feature files.
--
-- A 'gem' file holds a JSON document of the shape:
--
--   { "version": 1,
--     "cut": "round_brilliant",
--     "diameter_mm": 6.5,
--     "carat_approx": 1.0,
--     "material": "diamond",
--     "proportions": {
--       "table_pct": 57.0,
--       "crown_angle_deg": 34.5,
--       "pavilion_angle_deg": 40.75,
--       "girdle_pct": 2.5,
--       "total_depth_pct": 61.8
--     },
--     "notes": "GIA ideal cut"
--   }
--
-- Gemstone library files are managed by the kerf-cad-core jewelry module.
-- Storing them as a file kind makes them queryable, restorable via
-- file_revisions, and shareable on Workshop.
--
-- Re-adds files_kind_check with the full cumulative kind list (as of 059)
-- plus 'gem' — must carry every prior kind forward or this migration
-- silently drops tool/plc_st/quadmesh/print/etc.

alter table files drop constraint if exists files_kind_check;
alter table files add constraint files_kind_check check (
    kind in ('file','folder','assembly','step','drawing','sketch','part','feature','circuit','equations','material','simulation','script','step-ref','assembly_lock','canvas','schedule','view','sheet','duct','pipe','conduit','subd','mesh','render','section','cam_layered','tool','plc_st','quadmesh','print','gem')
);
