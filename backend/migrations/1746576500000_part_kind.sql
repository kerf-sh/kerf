-- Add 'part' to the files.kind enumeration so library Parts (KiCad-style
-- catalog entries) can live alongside the rest of the project tree. Parts
-- store rich JSON metadata in `files.content` (manufacturer, MPN, distributors,
-- and an optional storage_key pointing at a 3D model). They're edited via the
-- LibraryEditor on the frontend and via dedicated LLM tools (create_part,
-- set_part_metadata, add_distributor_link). The BOM endpoint walks every
-- assembly in the project and rolls these up into a quantity + cost table.

alter table files drop constraint if exists files_kind_check;
alter table files add constraint files_kind_check check (
    kind in ('file','folder','assembly','step','drawing','sketch','part')
);
