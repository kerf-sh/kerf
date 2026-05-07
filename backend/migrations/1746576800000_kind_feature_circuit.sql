-- Add 'feature' and 'circuit' to the files.kind enumeration so OCCT B-rep
-- timelines (.feature, JSON) and tscircuit electronics designs
-- (.circuit.tsx, TSX source) can live alongside the rest of the project tree.
--
-- 'feature' files store a feature-tree JSON (see backend/internal/tools/feature_tools.go)
-- and are managed exclusively through the feature_* LLM tools — write_file /
-- edit_file / delete_file refuse '.feature' paths (READONLY_FEATURE).
--
-- 'circuit' files store tscircuit JSX source. They have dedicated tools
-- (add_component / connect / set_component_prop) but are also editable by
-- hand for advanced cases.

alter table files drop constraint if exists files_kind_check;
alter table files add constraint files_kind_check check (
    kind in ('file','folder','assembly','step','drawing','sketch','part','feature','circuit')
);
