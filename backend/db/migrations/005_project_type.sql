-- project_type: forward-compatible enum gating which renderer/LLM tools/file
-- kinds a project surfaces.

alter table projects
    add column if not exists project_type text not null default 'mechanical'
    check (project_type in ('mechanical','electronics','architecture','jewelry'));

create index if not exists projects_project_type_idx on projects(project_type);
