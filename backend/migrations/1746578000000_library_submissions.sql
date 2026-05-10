-- Library Phase 3 — manufacturer-PR submission queue.
--
-- Anyone (any authenticated user) can submit a Part to a curated Library
-- workspace via POST /api/library/submissions. The row lands here in
-- status='pending' until an admin reviews it via PUT
-- /api/admin/library/submissions/{id}. Approval copies the payload into
-- a new files row (kind='part') inside the target workspace's seed
-- Library project; rejection just stamps the reason.
--
-- The payload column carries the raw Part JSON (the same shape the
-- create_part tool produces — see backend/internal/tools/part_tools.go).
-- We don't enforce the JSON schema here; the handler validates the
-- minimum fields (name, manufacturer, mpn, category, description) and
-- rejects oversized blobs.
--
-- Lifecycle is one-shot: once a row is approved or rejected it stays
-- terminal. Re-submission means a new row.

create table if not exists library_part_submissions (
    id uuid primary key default gen_random_uuid(),
    submitter_user_id uuid not null references users(id) on delete cascade,
    target_workspace_id uuid not null references workspaces(id) on delete cascade,
    payload jsonb not null,
    status text not null default 'pending'
        check (status in ('pending', 'approved', 'rejected')),
    review_note text not null default '',
    reviewer_id uuid references users(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists library_part_submissions_status_idx
    on library_part_submissions(status);
create index if not exists library_part_submissions_submitter_idx
    on library_part_submissions(submitter_user_id);
create index if not exists library_part_submissions_target_idx
    on library_part_submissions(target_workspace_id);
