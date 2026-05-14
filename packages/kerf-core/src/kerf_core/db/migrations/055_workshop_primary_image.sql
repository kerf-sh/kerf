-- Add is_primary flag to project_workshop_images.
-- At most one image per project may be primary (enforced via partial
-- unique index). When is_primary = true the image is used as the
-- project tile + Workshop browse-grid thumbnail instead of the
-- auto-captured thumbnail_storage_key; the auto-capture becomes a
-- fallback shown only when no gallery image is pinned.

alter table project_workshop_images
  add column if not exists is_primary boolean not null default false;

-- Partial unique index: at most one primary per project.
create unique index if not exists workshop_images_primary_uniq
  on project_workshop_images(project_id)
  where is_primary;
