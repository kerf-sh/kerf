-- Add 'sketch' to the files.kind enumeration so parametric 2D sketches can be
-- stored alongside other file kinds. Sketches live as JSON in `files.content`
-- and are edited exclusively through the dedicated sketch UI; LLM tools other
-- than `create_sketch` refuse to mutate them.

alter table files drop constraint if exists files_kind_check;
alter table files add constraint files_kind_check check (
    kind in ('file','folder','assembly','step','drawing','sketch')
);
