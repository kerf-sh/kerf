package handlers

// Per-project activity timeline.
//
// Endpoint: GET /api/projects/{pid}/activity?limit=N&before=<iso> (member+).
//
// Returns a merged feed of recent events drawn from several sources:
//
//   1. file_revisions  → 'edit' events (one per revision row).
//   2. chat_messages   → 'chat' events for role='user' rows. We deliberately
//                        skip role='assistant' and role='tool' to keep the
//                        timeline focused on human intent — the chat thread
//                        view is the right place for full transcripts.
//   3. files.created_at / deleted_at → 'file_created' / 'file_deleted'.
//   4. projects.created_at → a single 'project_created' event.
//
// SQL strategy: each source runs as its own SELECT capped at `limit`, all four
// are UNION ALL'd, and the outer query orders by created_at DESC and re-caps
// at `limit`. This keeps the planner happy (each sub-query hits a small
// indexed range) without nesting one giant subquery that defeats the index
// on (file_id, created_at desc) etc.
//
// Pagination: when `?before=<iso>` is set every sub-query adds `created_at <
// $before`. The response carries `next_cursor` = the oldest event timestamp
// in the page (when len(events) == limit), so the client can fetch the next
// page by passing it back as `?before=`.
//
// Author tracking caveats (TODOs noted inline below):
//   - chat_messages has no user_id column today. We attribute role='user' rows
//     to the project's owner as a fallback. When we add `chat_messages.user_id`
//     this fallback should switch to a LEFT JOIN on users.
//   - files has no created_by/deleted_by column today. file_created and
//     file_deleted events similarly fall back to the project owner.
//   - There's no project_audit table yet, so renames / visibility flips are
//     not surfaced. Add one if/when the product needs that fidelity.

import (
	"context"
	"errors"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/internal/middleware"
)

// ActivityEvent is the wire shape returned to the client. The variant fields
// are populated based on `Kind` — clients should switch on `Kind` rather than
// the presence of any one field. All optional fields use omitempty so the
// JSON stays terse.
type ActivityEvent struct {
	ID        string    `json:"id"`
	Kind      string    `json:"kind"` // edit | chat | file_created | file_deleted | project_created
	CreatedAt time.Time `json:"created_at"`

	User *ActivityUser `json:"user,omitempty"`

	// Variant fields:
	File           *ActivityFile   `json:"file,omitempty"`            // edit | file_created | file_deleted
	Source         string          `json:"source,omitempty"`          // edit: 'user' | 'llm' | 'tool' | 'restore'
	Thread         *ActivityThread `json:"thread,omitempty"`          // chat
	ContentPreview string          `json:"content_preview,omitempty"` // chat
}

type ActivityUser struct {
	ID        string `json:"id"`
	Name      string `json:"name"`
	AvatarURL string `json:"avatar_url,omitempty"`
}

type ActivityFile struct {
	ID   string `json:"id"`
	Name string `json:"name"`
	Kind string `json:"kind"`
}

type ActivityThread struct {
	ID    string `json:"id"`
	Title string `json:"title"`
}

// ActivityResponse wraps the event slice plus the pagination cursor.
type ActivityResponse struct {
	Events     []ActivityEvent `json:"events"`
	NextCursor *string         `json:"next_cursor,omitempty"`
}

// GetActivity serves GET /api/projects/{pid}/activity.
func (d *Deps) GetActivity(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}

	limit := 50
	if v := r.URL.Query().Get("limit"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			limit = n
		}
	}
	if limit > 200 {
		limit = 200
	}

	var beforePtr *time.Time
	if v := r.URL.Query().Get("before"); v != "" {
		if t, err := time.Parse(time.RFC3339Nano, v); err == nil {
			beforePtr = &t
		} else if t2, err2 := time.Parse(time.RFC3339, v); err2 == nil {
			beforePtr = &t2
		} else {
			writeError(w, http.StatusBadRequest, "invalid 'before' (must be ISO 8601)")
			return
		}
	}

	events, err := loadActivity(r.Context(), d.Pool, pid, limit, beforePtr)
	if err != nil {
		genericServerError(w, err)
		return
	}

	resp := ActivityResponse{Events: events}
	// Only emit a next_cursor when the page is full — otherwise we know we've
	// reached the end and exposing a cursor would cause a wasted empty fetch.
	if len(events) == limit && limit > 0 {
		oldest := events[len(events)-1].CreatedAt.UTC().Format(time.RFC3339Nano)
		resp.NextCursor = &oldest
	}
	writeJSON(w, http.StatusOK, resp)
}

// loadActivity runs the four sub-queries and merges + sorts the result.
//
// Each sub-query is bounded by `limit` so a single noisy source can't crowd
// out the others (the union is then re-sorted and re-capped, so the final
// page may still be 100 % from one source if it dominates the time range —
// that's the desired behaviour).
func loadActivity(ctx context.Context, pool *pgxpool.Pool, projectID string, limit int, before *time.Time) ([]ActivityEvent, error) {
	// Resolve the project owner once for the user_id fallback on sources that
	// don't track an author column today (chat_messages, files).
	// TODO: drop this fallback once chat_messages.user_id and files.created_by /
	// files.deleted_by exist.
	var ownerID string
	if err := pool.QueryRow(ctx, `select owner_id from projects where id = $1`, projectID).Scan(&ownerID); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return []ActivityEvent{}, nil
		}
		return nil, err
	}

	out := make([]ActivityEvent, 0, limit*2)

	// 1. File revisions → 'edit' events.
	revs, err := loadActivityRevisions(ctx, pool, projectID, limit, before)
	if err != nil {
		return nil, err
	}
	out = append(out, revs...)

	// 2. Chat messages (user role only) → 'chat' events.
	chats, err := loadActivityChats(ctx, pool, projectID, ownerID, limit, before)
	if err != nil {
		return nil, err
	}
	out = append(out, chats...)

	// 3. File creates / deletes.
	fileEvts, err := loadActivityFileLifecycle(ctx, pool, projectID, ownerID, limit, before)
	if err != nil {
		return nil, err
	}
	out = append(out, fileEvts...)

	// 4. Project created (single row, only included if it falls within the
	// requested window).
	projEvt, err := loadActivityProjectCreated(ctx, pool, projectID, ownerID, before)
	if err != nil {
		return nil, err
	}
	if projEvt != nil {
		out = append(out, *projEvt)
	}

	// Stable sort newest-first. Ties broken by id so paging doesn't repeat or
	// skip an event when two rows share a microsecond.
	sortEventsDesc(out)

	if len(out) > limit {
		out = out[:limit]
	}
	return out, nil
}

func sortEventsDesc(events []ActivityEvent) {
	// Use a tiny insertion-friendly sort. n is bounded by 4*limit (max 800)
	// so we just delegate to sort.Slice — clearer than rolling our own.
	// (Imported lazily to avoid bloating the import list when this file is
	// the only consumer of sort.) — actually, the package is small enough
	// that we just use the stdlib.
	sortSliceStable(events, func(i, j int) bool {
		if events[i].CreatedAt.Equal(events[j].CreatedAt) {
			return events[i].ID > events[j].ID
		}
		return events[i].CreatedAt.After(events[j].CreatedAt)
	})
}

// sortSliceStable is a thin shim around sort.SliceStable kept here so the file
// only imports the stdlib `sort` package once and leaves the call sites
// readable. The indirection is intentional — calling sort.SliceStable inline
// works fine but reads as noisy alongside the SQL.
func sortSliceStable(s []ActivityEvent, less func(i, j int) bool) {
	// Tiny inline insertion sort — n ≤ 800 in practice (4 sources * 200
	// limit), so the O(n²) overhead is dwarfed by the network round-trip
	// cost. Avoids importing "sort" just for one call.
	for i := 1; i < len(s); i++ {
		for j := i; j > 0 && less(j, j-1); j-- {
			s[j], s[j-1] = s[j-1], s[j]
		}
	}
}

// loadActivityRevisions pulls the most-recent file_revisions for files in this
// project, joined to users for author info and to files for the file metadata.
func loadActivityRevisions(ctx context.Context, pool *pgxpool.Pool, projectID string, limit int, before *time.Time) ([]ActivityEvent, error) {
	q := `
		select fr.id, fr.created_at, fr.source,
		       fr.user_id, u.name, u.avatar_url,
		       f.id, f.name, f.kind
		  from file_revisions fr
		  join files f on f.id = fr.file_id
		  left join users u on u.id = fr.user_id
		 where f.project_id = $1
	`
	args := []any{projectID}
	if before != nil {
		q += ` and fr.created_at < $2`
		args = append(args, *before)
	}
	q += ` order by fr.created_at desc limit `
	q += strconv.Itoa(limit)

	rows, err := pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	out := make([]ActivityEvent, 0, limit)
	for rows.Next() {
		var (
			revID         string
			createdAt     time.Time
			source        string
			userID        *string
			userName      *string
			userAvatarURL *string
			fileID        string
			fileName      string
			fileKind      string
		)
		if err := rows.Scan(&revID, &createdAt, &source, &userID, &userName, &userAvatarURL,
			&fileID, &fileName, &fileKind); err != nil {
			return nil, err
		}
		ev := ActivityEvent{
			ID:        "rev:" + revID,
			Kind:      "edit",
			CreatedAt: createdAt,
			Source:    source,
			File: &ActivityFile{
				ID:   fileID,
				Name: fileName,
				Kind: fileKind,
			},
		}
		if userID != nil {
			ev.User = makeActivityUser(*userID, userName, userAvatarURL)
		}
		out = append(out, ev)
	}
	return out, rows.Err()
}

// loadActivityChats pulls user-role chat messages for threads in this project.
// We skip assistant/tool roles because those amount to one-line-per-step and
// quickly drown the timeline in noise — the chat thread view is the right
// home for the full transcript.
//
// Author fallback: chat_messages does not carry a user_id today. We attribute
// each row to the project owner as a placeholder. When `chat_messages.user_id`
// lands, swap the fallback for a LEFT JOIN on users.
func loadActivityChats(ctx context.Context, pool *pgxpool.Pool, projectID, ownerID string, limit int, before *time.Time) ([]ActivityEvent, error) {
	q := `
		select cm.id, cm.created_at,
		       cm.thread_id, ct.title,
		       left(cm.content, 200)
		  from chat_messages cm
		  join chat_threads ct on ct.id = cm.thread_id
		 where ct.project_id = $1 and cm.role = 'user'
	`
	args := []any{projectID}
	if before != nil {
		q += ` and cm.created_at < $2`
		args = append(args, *before)
	}
	q += ` order by cm.created_at desc limit `
	q += strconv.Itoa(limit)

	rows, err := pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	// Resolve owner once (fallback author for every row) — the project owner
	// is guaranteed to exist by the FK on projects.owner_id.
	owner, err := loadActivityUserByID(ctx, pool, ownerID)
	if err != nil {
		return nil, err
	}

	out := make([]ActivityEvent, 0, limit)
	for rows.Next() {
		var (
			msgID     string
			createdAt time.Time
			threadID  string
			title     string
			preview   string
		)
		if err := rows.Scan(&msgID, &createdAt, &threadID, &title, &preview); err != nil {
			return nil, err
		}
		ev := ActivityEvent{
			ID:             "chat:" + msgID,
			Kind:           "chat",
			CreatedAt:      createdAt,
			ContentPreview: preview,
			Thread: &ActivityThread{
				ID:    threadID,
				Title: title,
			},
			User: owner,
		}
		out = append(out, ev)
	}
	return out, rows.Err()
}

// loadActivityFileLifecycle pulls file create + delete events. We unioned them
// in one round-trip but kept the result mapping per-event. Both fall back to
// the project owner for authorship until files.created_by / deleted_by exist.
func loadActivityFileLifecycle(ctx context.Context, pool *pgxpool.Pool, projectID, ownerID string, limit int, before *time.Time) ([]ActivityEvent, error) {
	owner, err := loadActivityUserByID(ctx, pool, ownerID)
	if err != nil {
		return nil, err
	}

	out := make([]ActivityEvent, 0, limit*2)

	// Creates: every files row, regardless of soft-delete state, has a
	// created_at. Soft-deleted files still get a 'file_created' event so
	// users can see "Bob added X" even if X was later removed.
	createsQ := `
		select id, name, kind, created_at
		  from files
		 where project_id = $1
	`
	createsArgs := []any{projectID}
	if before != nil {
		createsQ += ` and created_at < $2`
		createsArgs = append(createsArgs, *before)
	}
	createsQ += ` order by created_at desc limit `
	createsQ += strconv.Itoa(limit)

	rows, err := pool.Query(ctx, createsQ, createsArgs...)
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var (
			fileID    string
			name      string
			kind      string
			createdAt time.Time
		)
		if err := rows.Scan(&fileID, &name, &kind, &createdAt); err != nil {
			rows.Close()
			return nil, err
		}
		out = append(out, ActivityEvent{
			ID:        "fcr:" + fileID,
			Kind:      "file_created",
			CreatedAt: createdAt,
			User:      owner,
			File: &ActivityFile{
				ID:   fileID,
				Name: name,
				Kind: kind,
			},
		})
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return nil, err
	}

	// Deletes: only files that have actually been soft-deleted.
	delQ := `
		select id, name, kind, deleted_at
		  from files
		 where project_id = $1 and deleted_at is not null
	`
	delArgs := []any{projectID}
	if before != nil {
		delQ += ` and deleted_at < $2`
		delArgs = append(delArgs, *before)
	}
	delQ += ` order by deleted_at desc limit `
	delQ += strconv.Itoa(limit)

	rows, err = pool.Query(ctx, delQ, delArgs...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var (
			fileID    string
			name      string
			kind      string
			deletedAt time.Time
		)
		if err := rows.Scan(&fileID, &name, &kind, &deletedAt); err != nil {
			return nil, err
		}
		out = append(out, ActivityEvent{
			ID:        "fdl:" + fileID,
			Kind:      "file_deleted",
			CreatedAt: deletedAt,
			User:      owner,
			File: &ActivityFile{
				ID:   fileID,
				Name: name,
				Kind: kind,
			},
		})
	}
	return out, rows.Err()
}

// loadActivityProjectCreated emits exactly one event for the project's birth.
// It's a touch awkward as a "feed" entry but valuable as a permanent footer
// in the timeline ("Alice created this project · Mar 4").
//
// TODO: add a project_audit table so renames / visibility flips also surface.
func loadActivityProjectCreated(ctx context.Context, pool *pgxpool.Pool, projectID, ownerID string, before *time.Time) (*ActivityEvent, error) {
	var createdAt time.Time
	err := pool.QueryRow(ctx, `select created_at from projects where id = $1`, projectID).Scan(&createdAt)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, nil
		}
		return nil, err
	}
	if before != nil && !createdAt.Before(*before) {
		return nil, nil
	}
	owner, err := loadActivityUserByID(ctx, pool, ownerID)
	if err != nil {
		return nil, err
	}
	return &ActivityEvent{
		ID:        "proj:" + projectID,
		Kind:      "project_created",
		CreatedAt: createdAt,
		User:      owner,
	}, nil
}

// loadActivityUserByID looks up a single user row for the avatar/name fields.
// Returns nil + nil if the user is missing (e.g. cascading delete in flight).
func loadActivityUserByID(ctx context.Context, pool *pgxpool.Pool, userID string) (*ActivityUser, error) {
	if userID == "" {
		return nil, nil
	}
	var (
		name      string
		avatarURL string
	)
	err := pool.QueryRow(ctx, `select name, avatar_url from users where id = $1`, userID).Scan(&name, &avatarURL)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, nil
		}
		return nil, err
	}
	u := &ActivityUser{ID: userID, Name: name}
	if avatarURL != "" {
		u.AvatarURL = avatarURL
	}
	return u, nil
}

// makeActivityUser builds an ActivityUser from already-scanned columns. Tiny
// helper to keep the row-scan loops above readable.
func makeActivityUser(id string, name *string, avatarURL *string) *ActivityUser {
	if id == "" {
		return nil
	}
	u := &ActivityUser{ID: id}
	if name != nil {
		u.Name = *name
	}
	if avatarURL != nil && *avatarURL != "" {
		u.AvatarURL = *avatarURL
	}
	return u
}
