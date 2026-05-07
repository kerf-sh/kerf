-- project_thumbnails: cached 3D preview rendered client-side on save.
-- The blob lives in the storage backend (local/s3); this table only
-- tracks the key + last-update time so the API can build the URL and
-- the browser can cache-bust on change.

alter table projects add column if not exists thumbnail_storage_key text;
alter table projects add column if not exists thumbnail_updated_at timestamptz;
