-- Library Phase 3 — manufacturer-PR submission queue.

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
