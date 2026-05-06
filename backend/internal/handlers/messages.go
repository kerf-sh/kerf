package handlers

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"

	"github.com/imranp/kerf/backend/internal/llm"
	"github.com/imranp/kerf/backend/internal/middleware"
	"github.com/imranp/kerf/backend/internal/models"
)

// ListMessages returns all messages for a thread.
func (d *Deps) ListMessages(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	tid := chi.URLParam(r, "tid")
	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}
	// Verify thread belongs to project.
	if !d.threadInProject(r.Context(), w, tid, pid) {
		return
	}
	rows, err := d.Pool.Query(r.Context(), `
		select id, thread_id, role, content, part_refs, created_at
		from chat_messages
		where thread_id = $1
		order by created_at asc
	`, tid)
	if err != nil {
		genericServerError(w, err)
		return
	}
	defer rows.Close()
	out := []models.Message{}
	for rows.Next() {
		var m models.Message
		if err := rows.Scan(&m.ID, &m.ThreadID, &m.Role, &m.Content, &m.PartRefs, &m.CreatedAt); err != nil {
			genericServerError(w, err)
			return
		}
		out = append(out, m)
	}
	writeJSON(w, http.StatusOK, out)
}

type postMessageReq struct {
	Content  string             `json:"content"`
	PartRefs []models.PartRef   `json:"part_refs"`
}

type postMessageResp struct {
	UserMessage      models.Message `json:"user_message"`
	AssistantMessage models.Message `json:"assistant_message"`
}

// PostMessage records the user's turn, calls the LLM with file context, and records the assistant reply.
func (d *Deps) PostMessage(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	tid := chi.URLParam(r, "tid")
	role := requireMember(w, r, d.Pool, pid, uid)
	if role == "" {
		return
	}
	if role == "viewer" {
		writeError(w, http.StatusForbidden, "viewer cannot post messages")
		return
	}
	if !d.threadInProject(r.Context(), w, tid, pid) {
		return
	}
	var body postMessageReq
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if body.Content == "" {
		writeError(w, http.StatusBadRequest, "content is required")
		return
	}
	if body.PartRefs == nil {
		body.PartRefs = []models.PartRef{}
	}
	partRefsJSON, err := json.Marshal(body.PartRefs)
	if err != nil {
		genericServerError(w, err)
		return
	}

	// Insert user message.
	var userMsg models.Message
	err = d.Pool.QueryRow(r.Context(), `
		insert into chat_messages(thread_id, role, content, part_refs)
		values ($1,'user',$2,$3)
		returning id, thread_id, role, content, part_refs, created_at
	`, tid, body.Content, partRefsJSON).Scan(
		&userMsg.ID, &userMsg.ThreadID, &userMsg.Role, &userMsg.Content, &userMsg.PartRefs, &userMsg.CreatedAt)
	if err != nil {
		genericServerError(w, err)
		return
	}

	// Build LLM call: history + part contexts.
	history, err := d.loadHistory(r.Context(), tid, userMsg.ID)
	if err != nil {
		genericServerError(w, err)
		return
	}
	parts, err := d.loadPartContexts(r.Context(), pid, body.PartRefs)
	if err != nil {
		genericServerError(w, err)
		return
	}

	assistantText, err := d.LLM.Complete(r.Context(), history, body.Content, parts)
	if err != nil {
		assistantText = "LLM error: " + err.Error()
	}

	// Insert assistant message.
	var assistantMsg models.Message
	err = d.Pool.QueryRow(r.Context(), `
		insert into chat_messages(thread_id, role, content, part_refs)
		values ($1,'assistant',$2,'[]'::jsonb)
		returning id, thread_id, role, content, part_refs, created_at
	`, tid, assistantText).Scan(
		&assistantMsg.ID, &assistantMsg.ThreadID, &assistantMsg.Role, &assistantMsg.Content, &assistantMsg.PartRefs, &assistantMsg.CreatedAt)
	if err != nil {
		genericServerError(w, err)
		return
	}

	// Update thread.last_message_at.
	_, _ = d.Pool.Exec(r.Context(),
		`update chat_threads set last_message_at = now(), updated_at = now() where id = $1`,
		tid)

	writeJSON(w, http.StatusCreated, postMessageResp{
		UserMessage:      userMsg,
		AssistantMessage: assistantMsg,
	})
}

func (d *Deps) threadInProject(ctx context.Context, w http.ResponseWriter, tid, pid string) bool {
	var x string
	err := d.Pool.QueryRow(ctx, `select id from chat_threads where id = $1 and project_id = $2`, tid, pid).Scan(&x)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeError(w, http.StatusNotFound, "thread not found")
			return false
		}
		genericServerError(w, err)
		return false
	}
	return true
}

func (d *Deps) loadHistory(ctx context.Context, threadID, excludeID string) ([]llm.HistoryMessage, error) {
	rows, err := d.Pool.Query(ctx, `
		select role, content from chat_messages
		where thread_id = $1 and id <> $2
		order by created_at asc
	`, threadID, excludeID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []llm.HistoryMessage
	for rows.Next() {
		var m llm.HistoryMessage
		if err := rows.Scan(&m.Role, &m.Content); err != nil {
			return nil, err
		}
		out = append(out, m)
	}
	return out, rows.Err()
}

func (d *Deps) loadPartContexts(ctx context.Context, projectID string, refs []models.PartRef) ([]llm.PartContext, error) {
	if len(refs) == 0 {
		return nil, nil
	}
	out := make([]llm.PartContext, 0, len(refs))
	for _, ref := range refs {
		if ref.FileID == "" {
			continue
		}
		var (
			name    string
			content string
		)
		err := d.Pool.QueryRow(ctx,
			`select name, content from files where id = $1 and project_id = $2`,
			ref.FileID, projectID).Scan(&name, &content)
		if err != nil {
			if errors.Is(err, pgx.ErrNoRows) {
				continue
			}
			return nil, err
		}
		out = append(out, llm.PartContext{
			FilePath: name,
			PartID:   ref.PartID,
			Content:  content,
		})
	}
	return out, nil
}
