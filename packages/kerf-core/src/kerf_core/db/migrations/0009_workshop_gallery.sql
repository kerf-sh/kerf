-- 0009_workshop_gallery.sql
-- Consolidated baseline migration (folded 2026-05-18).
-- Original migrations folded into this file are delimited below;
-- SQL is byte-exact and applied in the original order.

-- ════════════ folded: 052_project_workshop_images.sql ════════════

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

-- ════════════ folded: 055_workshop_primary_image.sql ════════════

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

-- ════════════ folded: 061_user_github_id.sql ════════════

-- Add github_id to users for GitHub Sign-In (login/signup).
-- Distinct from cloud_github_tokens (repo-connect OAuth tokens).
ALTER TABLE users ADD COLUMN IF NOT EXISTS github_id text;
CREATE UNIQUE INDEX IF NOT EXISTS users_github_id_unique ON users (github_id) WHERE github_id IS NOT NULL;

-- ════════════ folded: 062_workshop_readme.sql ════════════

-- 062_workshop_readme.sql
--
-- Add `readme` markdown field to the projects table so Workshop-published
-- projects carry a rich, AI-generated README (Markdown) as their primary
-- content surface.
--
-- Design notes:
--   * The field is nullable; existing rows default to NULL (no README).
--   * The README is stored as raw Markdown text.  Sanitisation is the
--     responsibility of the rendering layer (frontend: rehype-sanitize /
--     react-markdown; backend: bleach if needed before returning to API).
--   * `readme_generated_at` tracks when the field was last written so the
--     frontend can show a "generated N minutes ago" label and the backend
--     can skip re-generation when the project has not changed.
--   * `cover_storage_key` is a separate field for the auto-rendered hero
--     image (a distinct concern from the auto-captured thumbnail_storage_key
--     which is the live editor snapshot).  When present, it overrides the
--     thumbnail in the Workshop browse grid / listing hero.
--
-- Round-trip: kerf-api reads and writes both fields in the workshop publish
-- handler and the /workshop/:slug GET endpoint.

alter table projects
    add column if not exists readme               text,
    add column if not exists readme_generated_at  timestamptz,
    add column if not exists cover_storage_key    text,
    add column if not exists cover_generated_at   timestamptz;
