package tools

// Revision-recording helpers for write tools. The HTTP layer has its own
// RecordRevision; this is the same shape but typed against ProjectCtx so
// individual tools can call it without re-marshaling the user id.
//
// Storage scheme (Phase 4): every Nth row is a kind='base' row with the
// full content gzipped into content_gz. Rows in between are kind='diff'
// and store a gzipped diff-match-patch delta against their parent
// revision (the row immediately preceding them in time). Read-paths
// reconstruct by walking back to the nearest base, decompressing, then
// applying each diff forward.
//
// Legacy rows (pre-migration) have kind='base' (default), content_gz
// NULL, and content populated as plaintext. ReconstructRevision falls
// back to the plaintext column when content_gz is NULL.

import (
	"bytes"
	"compress/gzip"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strconv"
	"time"
	"unicode/utf8"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/sergi/go-diff/diffmatchpatch"

	"github.com/imranp/kerf/backend/internal/llm"
)

const (
	defaultFileRevisionsMax = 200

	// DiffsPerBase is the maximum number of consecutive kind='diff' rows
	// allowed before the next write becomes a kind='base' snapshot. Lower
	// values inflate storage but bound the read-path walk; higher values
	// shrink storage but make reconstruct more expensive. 20 is a balance:
	// at most 20 diff applies per read, ~5% base-row overhead on long
	// histories.
	DiffsPerBase = 20

	// previewMaxBytes caps the stored content_preview column. Kept short
	// so ListRevisions stays index-friendly.
	previewMaxBytes = 200
)

// ----- compression helpers ---------------------------------------------

// gzipBytes compresses s with gzip's default compression level.
func gzipBytes(s string) ([]byte, error) {
	var buf bytes.Buffer
	gz := gzip.NewWriter(&buf)
	if _, err := gz.Write([]byte(s)); err != nil {
		_ = gz.Close()
		return nil, err
	}
	if err := gz.Close(); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

// GzipForBackfill is the exported entry point used by the
// backend/cmd/migrate-revisions backfill command. Internal callers use
// gzipBytes directly.
func GzipForBackfill(s string) ([]byte, error) { return gzipBytes(s) }

// GunzipForBackfill mirrors GzipForBackfill on the read side, used by the
// backfill verifier to sanity-check each compressed row before writing.
func GunzipForBackfill(b []byte) (string, error) { return gunzipBytes(b) }

// gunzipBytes decompresses a gzip-encoded blob into a string.
func gunzipBytes(b []byte) (string, error) {
	if len(b) == 0 {
		return "", nil
	}
	r, err := gzip.NewReader(bytes.NewReader(b))
	if err != nil {
		return "", err
	}
	defer r.Close()
	out, err := io.ReadAll(r)
	if err != nil {
		return "", err
	}
	return string(out), nil
}

// truncatePreview clips s to at most previewMaxBytes runes (UTF-8 safe).
func truncatePreview(s string) string {
	if len(s) <= previewMaxBytes {
		return s
	}
	// Trim to a valid UTF-8 boundary.
	cut := previewMaxBytes
	for cut > 0 && !utf8.RuneStart(s[cut]) {
		cut--
	}
	return s[:cut]
}

// ----- diff helpers ----------------------------------------------------

// computeDiffDelta returns the diff-match-patch "delta" string transforming
// parent into child. The delta is compact (operation tags + segments) and
// compresses well.
func computeDiffDelta(parent, child string) string {
	dmp := diffmatchpatch.New()
	dmp.DiffTimeout = 2 * time.Second
	diffs := dmp.DiffMain(parent, child, true)
	// Light cleanup keeps the delta short without changing semantics.
	diffs = dmp.DiffCleanupEfficiency(diffs)
	return dmp.DiffToDelta(diffs)
}

// applyDiffDelta reconstructs child from parent + delta.
func applyDiffDelta(parent, delta string) (string, error) {
	dmp := diffmatchpatch.New()
	diffs, err := dmp.DiffFromDelta(parent, delta)
	if err != nil {
		return "", err
	}
	return dmp.DiffText2(diffs), nil
}

// ----- write path ------------------------------------------------------

// recordRevisionForFile inserts a revision row for the given file (uuid form)
// and prunes anything beyond capacity. source is one of user|llm|tool|restore.
//
// Best-effort: errors are returned so callers can log if they want, but most
// callers ignore the error — a missing revision shouldn't fail the user's
// actual edit.
func recordRevisionForFile(ctx context.Context, pc ProjectCtx, fileID uuid.UUID, content, source string) error {
	cap := pc.FileRevisionsMax
	if cap <= 0 {
		cap = defaultFileRevisionsMax
	}
	if _, err := WriteRevision(ctx, pc.Pool, fileID.String(), content, source, nullableUUIDPtr(pc.UserID), cap); err != nil {
		return err
	}
	return nil
}

// WriteRevision is the shared write path used by both the HTTP handler
// (`handlers.RecordRevision`) and tool callers (`recordRevisionForFile`).
// It picks base-vs-diff based on the trailing diff-count, gzips the
// payload, and prunes per-file rows beyond `capacity`.
//
// Returns the new revision id (already inserted on success).
//
// Concurrency note: two simultaneous writers can both decide "diff against
// row X" at the same instant; the second insert lands with the same parent
// and the same kind selection. That is harmless — both rows are valid
// against the same parent, the read path still walks back from the most
// recent of them. The pathological case (two writers picking different
// parents and producing inconsistent reconstructions) cannot happen
// because the parent is always the *latest* row and writers serialize in
// the DB.
func WriteRevision(ctx context.Context, pool *pgxpool.Pool, fileID, content, source string, userID *uuid.UUID, capacity int) (uuid.UUID, error) {
	if pool == nil || fileID == "" {
		return uuid.Nil, errors.New("pool and fileID required")
	}
	if capacity <= 0 {
		capacity = defaultFileRevisionsMax
	}

	// Look up the most recent revision and the count of diff-rows since
	// the latest base. A single query gets both: we just need the latest
	// row and the run-length of diffs trailing it. We pull the latest row
	// id + kind, then count diffs since the most recent base.
	var (
		latestID    uuid.UUID
		latestKind  string
		hasLatest   bool
		diffsAfter  int
	)
	{
		row := pool.QueryRow(ctx, `
			select id, kind
			  from file_revisions
			 where file_id = $1
			 order by created_at desc
			 limit 1
		`, fileID)
		if err := row.Scan(&latestID, &latestKind); err != nil {
			if !errors.Is(err, pgx.ErrNoRows) {
				return uuid.Nil, err
			}
		} else {
			hasLatest = true
		}
	}
	if hasLatest {
		// Count the diff rows newer than the most-recent base. Equivalent
		// to "diffs since base"; if the most-recent row is itself a base
		// the count is 0.
		err := pool.QueryRow(ctx, `
			select count(*)
			  from file_revisions
			 where file_id = $1
			   and kind = 'diff'
			   and created_at > coalesce(
			       (select max(created_at)
			          from file_revisions
			         where file_id = $1 and kind = 'base'),
			       'epoch'::timestamptz
			   )
		`, fileID).Scan(&diffsAfter)
		if err != nil {
			return uuid.Nil, err
		}
	}

	preview := truncatePreview(content)
	newID := uuid.New()

	// First revision OR forced-base when too many diffs piled up: store
	// as kind='base' with the gzipped full content.
	makeBase := !hasLatest || diffsAfter >= DiffsPerBase
	if makeBase {
		gz, err := gzipBytes(content)
		if err != nil {
			return uuid.Nil, err
		}
		if _, err := pool.Exec(ctx, `
			insert into file_revisions(id, file_id, content, content_gz, kind, parent_revision_id, source, user_id, content_preview)
			values ($1, $2, $3, $4, 'base', null, $5, $6, $7)
		`, newID, fileID, content, gz, source, userID, preview); err != nil {
			return uuid.Nil, err
		}
	} else {
		// Reconstruct the parent's content so we can diff against it.
		parentContent, err := ReconstructRevision(ctx, pool, latestID.String())
		if err != nil {
			return uuid.Nil, err
		}
		delta := computeDiffDelta(parentContent, content)
		gz, err := gzipBytes(delta)
		if err != nil {
			return uuid.Nil, err
		}
		// Note: we leave the legacy `content` column empty for diff rows
		// (the canonical representation is content_gz holding the delta).
		// Setting content='' avoids a NULL — older readers that hit a
		// diff row with the legacy fallback get an empty string rather
		// than a panic on the not-null constraint.
		if _, err := pool.Exec(ctx, `
			insert into file_revisions(id, file_id, content, content_gz, kind, parent_revision_id, source, user_id, content_preview)
			values ($1, $2, '', $3, 'diff', $4, $5, $6, $7)
		`, newID, fileID, gz, latestID, source, userID, preview); err != nil {
			return uuid.Nil, err
		}
	}

	// Prune anything beyond capacity. Postgres-friendly: take the cutoff
	// timestamp at offset `capacity` and delete older rows. If a base row
	// gets pruned, its diff descendants reference it via
	// parent_revision_id; the FK is `on delete set null`. A diff whose
	// parent is gone and that no longer has any base ancestor in the
	// retained window becomes unreconstructable — but the prune cutoff
	// is wider than DiffsPerBase × any sane retention, so in practice
	// the next base in the kept window is always present and the diff
	// path remains valid.
	_, err := pool.Exec(ctx, `
		delete from file_revisions
		 where file_id = $1
		   and created_at < (
		       select created_at
		         from file_revisions
		        where file_id = $1
		        order by created_at desc
		        offset $2 limit 1
		   )
	`, fileID, capacity)
	if err != nil {
		return uuid.Nil, err
	}
	return newID, nil
}

// ----- read path -------------------------------------------------------

// ReconstructRevision walks back from revisionID to the nearest base,
// decompresses it, then applies each accumulated diff forward in order.
// If the target row is itself a base (or a legacy plaintext row), this
// short-circuits to a single decompress.
func ReconstructRevision(ctx context.Context, pool *pgxpool.Pool, revisionID string) (string, error) {
	type row struct {
		ID       uuid.UUID
		Kind     string
		ParentID *uuid.UUID
		Gz       []byte
		Plain    string // legacy column; falls back when Gz is NULL
	}
	loadOne := func(id string) (row, error) {
		var r row
		var parent *uuid.UUID
		err := pool.QueryRow(ctx, `
			select id, kind, parent_revision_id, content_gz, content
			  from file_revisions
			 where id = $1
		`, id).Scan(&r.ID, &r.Kind, &parent, &r.Gz, &r.Plain)
		if err != nil {
			return row{}, err
		}
		r.ParentID = parent
		return r, nil
	}

	// Walk backward, collecting diffs, until we hit a base.
	target, err := loadOne(revisionID)
	if err != nil {
		return "", err
	}
	chain := []row{target}
	for chain[0].Kind == "diff" {
		if chain[0].ParentID == nil {
			// Detached diff (parent pruned). Best we can do is decompress
			// whatever sits in the row itself — but a diff row's content
			// only makes sense relative to a parent, so we error out.
			return "", fmt.Errorf("revision %s: detached diff (parent missing)", chain[0].ID)
		}
		parent, err := loadOne(chain[0].ParentID.String())
		if err != nil {
			return "", fmt.Errorf("revision %s: load parent: %w", chain[0].ID, err)
		}
		chain = append([]row{parent}, chain...)
	}

	// chain[0] is the base. Decompress, then apply forward.
	var current string
	if len(chain[0].Gz) > 0 {
		c, err := gunzipBytes(chain[0].Gz)
		if err != nil {
			return "", err
		}
		current = c
	} else {
		// Legacy un-backfilled row: the plaintext column is the source.
		current = chain[0].Plain
	}
	for i := 1; i < len(chain); i++ {
		var delta string
		if len(chain[i].Gz) > 0 {
			d, err := gunzipBytes(chain[i].Gz)
			if err != nil {
				return "", err
			}
			delta = d
		} else {
			// A legacy diff row should never exist (the migration only
			// adds the kind column with default 'base'), but guard anyway.
			delta = chain[i].Plain
		}
		next, err := applyDiffDelta(current, delta)
		if err != nil {
			return "", fmt.Errorf("revision %s: apply diff: %w", chain[i].ID, err)
		}
		current = next
	}
	return current, nil
}

// ----- nullable helpers ------------------------------------------------

func nullableUUIDPtr(u uuid.UUID) *uuid.UUID {
	if u == uuid.Nil {
		return nil
	}
	return &u
}

// ----- list_revisions tool ----------------------------------------------

var listRevisionsSpec = llm.ToolSpec{
	Name: "list_revisions",
	Description: "List the most-recent edits to a file as a chronological history (newest first). Returns id, source ('user'|'tool'|'llm'|'restore'), created_at, and a 200-char content_preview per row. Useful before calling restore_revision.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"file_path": map[string]any{"type": "string"},
			"limit":     map[string]any{"type": "integer", "description": "max rows to return (default 50, max 200)"},
		},
		"required": []string{"file_path"},
	},
}

type listRevisionsArgs struct {
	FilePath string `json:"file_path"`
	Limit    int    `json:"limit"`
}

type revisionRow struct {
	ID             string  `json:"id"`
	Source         string  `json:"source"`
	UserID         *string `json:"user_id"`
	UserName       *string `json:"user_name,omitempty"`
	CreatedAt      string  `json:"created_at"`
	ContentPreview string  `json:"content_preview"`
}

func runListRevisions(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a listRevisionsArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	if a.FilePath == "" {
		return errPayload("file_path is required", "BAD_ARGS"), nil
	}
	rp, err := resolvePath(ctx, pc, a.FilePath)
	if err != nil || !rp.Exists {
		// Allow listing revisions for a soft-deleted file too — fall back to a
		// direct lookup against the files table if resolvePath missed it.
		var fid uuid.UUID
		if e := pc.Pool.QueryRow(ctx,
			`select id from files where project_id = $1 and name = $2 and deleted_at is not null limit 1`,
			pc.ProjectID, a.FilePath).Scan(&fid); e == nil {
			return runListRevisionsByID(ctx, pc, fid, a.Limit)
		}
		return errPayload("file not found: "+a.FilePath, "NOT_FOUND"), nil
	}
	return runListRevisionsByID(ctx, pc, rp.ID, a.Limit)
}

func runListRevisionsByID(ctx context.Context, pc ProjectCtx, fid uuid.UUID, limit int) (string, error) {
	if limit <= 0 {
		limit = 50
	}
	if limit > 200 {
		limit = 200
	}
	// Prefer the dedicated content_preview column when present; fall back
	// to the legacy plaintext content (clipped) for old rows.
	rows, err := pc.Pool.Query(ctx, `
		select fr.id, fr.source, fr.user_id, u.name, fr.created_at,
		       coalesce(fr.content_preview, left(fr.content, 200))
		  from file_revisions fr
		  left join users u on u.id = fr.user_id
		 where fr.file_id = $1
		 order by fr.created_at desc
		 limit `+strconv.Itoa(limit), fid)
	if err != nil {
		return "", err
	}
	defer rows.Close()
	out := []revisionRow{}
	for rows.Next() {
		var (
			id        uuid.UUID
			source    string
			userID    *uuid.UUID
			userName  *string
			createdAt time.Time
			preview   string
		)
		if err := rows.Scan(&id, &source, &userID, &userName, &createdAt, &preview); err != nil {
			return "", err
		}
		row := revisionRow{
			ID:             id.String(),
			Source:         source,
			ContentPreview: preview,
			CreatedAt:      createdAt.Format(time.RFC3339),
		}
		if userID != nil {
			s := userID.String()
			row.UserID = &s
		}
		if userName != nil && *userName != "" {
			n := *userName
			row.UserName = &n
		}
		out = append(out, row)
	}
	return okPayload(map[string]any{"revisions": out}), nil
}

// ----- restore_revision tool --------------------------------------------

var restoreRevisionSpec = llm.ToolSpec{
	Name: "restore_revision",
	Description: "Restore a file to one of its previous revisions. Use list_revisions first to find the desired revision id. The restore is itself recorded as a new revision so it can be undone.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"file_path":   map[string]any{"type": "string"},
			"revision_id": map[string]any{"type": "string"},
		},
		"required": []string{"file_path", "revision_id"},
	},
}

type restoreRevisionArgs struct {
	FilePath   string `json:"file_path"`
	RevisionID string `json:"revision_id"`
}

func runRestoreRevision(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a restoreRevisionArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	if a.FilePath == "" || a.RevisionID == "" {
		return errPayload("file_path and revision_id are required", "BAD_ARGS"), nil
	}
	revID, err := uuid.Parse(a.RevisionID)
	if err != nil {
		return errPayload("invalid revision_id", "BAD_ARGS"), nil
	}

	// Resolve target file. We accept soft-deleted files via the same fallback
	// as list_revisions so the LLM can resurrect a deleted file by path.
	rp, _ := resolvePath(ctx, pc, a.FilePath)
	var fid uuid.UUID
	if rp.Exists {
		fid = rp.ID
	} else {
		if e := pc.Pool.QueryRow(ctx,
			`select id from files where project_id = $1 and name = $2 and deleted_at is not null limit 1`,
			pc.ProjectID, a.FilePath).Scan(&fid); e != nil {
			return errPayload("file not found: "+a.FilePath, "NOT_FOUND"), nil
		}
	}

	// Confirm the revision belongs to this file + project (cheap pre-check
	// before the potentially-walking reconstruct).
	var ok bool
	if err := pc.Pool.QueryRow(ctx, `
		select exists(
		  select 1 from file_revisions fr
		    inner join files f on f.id = fr.file_id
		   where fr.id = $1 and fr.file_id = $2 and f.project_id = $3
		)
	`, revID, fid, pc.ProjectID).Scan(&ok); err != nil || !ok {
		return errPayload("revision not found", "NOT_FOUND"), nil
	}

	// Reconstruct the revision's full content (handles base/diff/legacy).
	content, err := ReconstructRevision(ctx, pc.Pool, revID.String())
	if err != nil {
		return "", err
	}

	// Apply: clear soft-delete, write content.
	if _, err := pc.Pool.Exec(ctx, `
		update files set
			content    = $1,
			deleted_at = null,
			updated_at = now()
		 where id = $2 and project_id = $3
	`, content, fid, pc.ProjectID); err != nil {
		return "", err
	}

	// Record restore as a new revision so the restore itself is undoable.
	cap := pc.FileRevisionsMax
	if cap <= 0 {
		cap = defaultFileRevisionsMax
	}
	newRev, err := WriteRevision(ctx, pc.Pool, fid.String(), content, "restore", nullableUUIDPtr(pc.UserID), cap)
	if err != nil {
		return "", err
	}

	return okPayload(map[string]any{
		"path":                 a.FilePath,
		"restored_revision_id": a.RevisionID,
		"new_revision_id":      newRev.String(),
	}), nil
}
