-- Add `extension` column to files for scripting variants.

alter table files add column if not exists extension text;
create index if not exists files_extension_idx on files(extension);
