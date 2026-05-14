-- User avatars: storage_key tracks the blob.

alter table users add column if not exists avatar_storage_key text;
alter table users add column if not exists avatar_updated_at timestamptz;
