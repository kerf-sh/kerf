-- project_thumbnails: cached 3D preview rendered client-side on save.

alter table projects add column if not exists thumbnail_storage_key text;
alter table projects add column if not exists thumbnail_updated_at timestamptz;
