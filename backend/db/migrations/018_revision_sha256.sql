-- Phase 4 hardening: chain-corruption detection.

alter table file_revisions
    add column if not exists content_sha256 bytea;
