-- Library v1.5 — verified-publisher curation flag.

alter table users add column if not exists is_verified_publisher boolean not null default false;
create index if not exists users_is_verified_publisher_idx on users(is_verified_publisher) where is_verified_publisher = true;
