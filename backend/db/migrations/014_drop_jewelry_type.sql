-- Drop the 'jewelry' project_type.

update projects set project_type = 'mechanical' where project_type = 'jewelry';

alter table projects drop constraint if exists projects_project_type_check;
alter table projects add constraint projects_project_type_check
    check (project_type in ('mechanical','electronics','architecture'));
