-- Per-user UI preferences.

alter table users add column preferences jsonb not null default '{}'::jsonb;
