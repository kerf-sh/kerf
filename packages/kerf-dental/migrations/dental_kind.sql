-- dental_kind.sql
-- Dental project kind — add 'dental' to the project tags GIN index and
-- seed the dental_cases table for per-case anatomy / treatment metadata.
--
-- FLAG: parent-coordinated reset required before applying.
-- This migration MUST be folded into the kerf-core consolidated baseline
-- (packages/kerf-core/src/kerf_core/db/migrations/) before deploy.
-- DO NOT apply via ALTER TABLE on a live shared DB without a reset window.
--
-- The project tags column already exists (see 0003_revisions_prefs.sql
-- migration 015_project_tags.sql). The GIN index is already created.
-- This migration only adds the dental_cases table.

create table if not exists dental_cases (
    id          uuid primary key default gen_random_uuid(),
    project_id  uuid not null references projects(id) on delete cascade,
    patient_ref text not null default '',
    tooth_ids   text[] not null default '{}',
    treatment   text not null default 'crown'
        check (treatment in ('crown', 'aligner', 'guide', 'bridge', 'veneer', 'inlay')),
    notes       text not null default '',
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create index if not exists dental_cases_project_id_idx
    on dental_cases(project_id);

create index if not exists dental_cases_treatment_idx
    on dental_cases(treatment);
