-- Drop the 'jewelry' project_type. It was a relabeled mechanical with a
-- narrower kinds list and the same JSCAD starter — no real surfacing tools
-- shipped to back the distinct domain. Any existing jewelry projects fold
-- into mechanical so the CHECK constraint can be tightened.

update projects set project_type = 'mechanical' where project_type = 'jewelry';

alter table projects drop constraint if exists projects_project_type_check;
alter table projects add constraint projects_project_type_check
    check (project_type in ('mechanical','electronics','architecture'));
