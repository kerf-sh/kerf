-- Add `extension` column to files so `.script.py` and `.script.ts` can coexist
-- as distinct scripting variants under the same `kind='script'` umbrella.
--
-- The column is nullable text: NULL means "detect from name pattern" (backwards
-- compat for pre-extension rows), ".py" means Python scripting, ".ts" means
-- TypeScript (the Phase 1 browser-side stub).
alter table files add column if not exists extension text;
create index if not exists files_extension_idx on files(extension);