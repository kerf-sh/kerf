-- Add 'feature' and 'circuit' to the files.kind enumeration.

alter table files drop constraint if exists files_kind_check;
alter table files add constraint files_kind_check check (
    kind in ('file','folder','assembly','step','drawing','sketch','part','feature','circuit')
);
