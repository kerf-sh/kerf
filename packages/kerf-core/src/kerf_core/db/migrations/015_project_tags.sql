-- Drop the project_type enum; replace with free-form `tags TEXT[]`.

alter table projects add column tags text[] not null default '{}';
update projects set tags = array[project_type] where project_type is not null;
alter table projects drop constraint if exists projects_project_type_check;
alter table projects drop column project_type;
create index if not exists projects_tags_gin_idx on projects using gin (tags);
