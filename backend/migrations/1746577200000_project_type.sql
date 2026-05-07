-- project_type: forward-compatible enum gating which renderer/LLM tools/file
-- kinds a project surfaces. The seam for moving Kerf beyond mechanical CAD
-- into adjacent domains (electronics via tscircuit, architecture, jewelry).
--
-- The chat/files/revisions plumbing stays shared; the *type* gates UI defaults
-- and LLM-prompt tuning. v1 is permissive on the API: any kind may be created
-- in any project — the FileTree create menu just filters its dropdown to the
-- type's native kinds. See ROADMAP.md "Multi-domain support: project types".
--
-- All existing rows default to 'mechanical' so the change is zero-behavioral
-- for current users. Adding a fifth type later is a CHECK-constraint update,
-- no data migration required.

alter table projects
    add column if not exists project_type text not null default 'mechanical'
    check (project_type in ('mechanical','electronics','architecture','jewelry'));

create index if not exists projects_project_type_idx on projects(project_type);
