-- project_workshop_images: Thingiverse-style multi-image gallery
-- attached to a project for Workshop publishing. Complements the
-- existing single thumbnail_storage_key (auto-captured from the editor);
-- gallery images are uploader-curated cover art.
--
-- Caps enforced at upload time in kerf-api:
--   * 10 images per project
--   * 5 MB per image
--   * JPEG / PNG / WebP only

create table if not exists project_workshop_images (
    id              uuid primary key default gen_random_uuid(),
    project_id      uuid not null references projects(id) on delete cascade,
    sort_order      integer not null default 0,
    storage_key     text not null,
    caption         text,
    width_px        integer,
    height_px       integer,
    bytes           integer,
    created_at      timestamptz not null default now()
);

create index if not exists project_workshop_images_project_idx
    on project_workshop_images(project_id, sort_order);
