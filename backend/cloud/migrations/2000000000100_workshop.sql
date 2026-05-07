-- Workshop tables for the hosted (cloud) tier.
-- Cloud-only — applied alongside the rest of backend/cloud/migrations/*.
--
-- A listing is a thin pointer to a `projects` row that the owner has
-- decided to publish. Forking creates a brand-new project row owned by
-- the forker; the original listing's project is not modified beyond a
-- bumped forks_count.
--
-- Likes are a simple (user, listing) join table. Counts are denormalized
-- onto cloud_workshop_listings and maintained in the request handler
-- inside a single tx (no DB triggers).

create table if not exists cloud_workshop_listings (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null unique references projects(id) on delete cascade,
    user_id uuid not null references users(id) on delete cascade,
    slug text not null unique,
    title text not null,
    description text not null default '',
    thumbnail_url text,
    likes_count int not null default 0,
    forks_count int not null default 0,
    published_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists cloud_workshop_listings_user_id_idx
    on cloud_workshop_listings(user_id);
create index if not exists cloud_workshop_listings_published_at_idx
    on cloud_workshop_listings(published_at desc);

create table if not exists cloud_workshop_likes (
    user_id uuid not null references users(id) on delete cascade,
    listing_id uuid not null references cloud_workshop_listings(id) on delete cascade,
    created_at timestamptz not null default now(),
    primary key (user_id, listing_id)
);
create index if not exists cloud_workshop_likes_listing_idx
    on cloud_workshop_likes(listing_id);
