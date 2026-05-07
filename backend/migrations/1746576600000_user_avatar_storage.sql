-- User avatars: storage_key tracks the blob; avatar_url remains the
-- resolved public URL the frontend renders (CDN base or /api/blobs/).
-- The backend recomputes avatar_url from avatar_storage_key on every
-- relevant change (upload, delete, OAuth pull).

alter table users add column if not exists avatar_storage_key text;
alter table users add column if not exists avatar_updated_at timestamptz;
