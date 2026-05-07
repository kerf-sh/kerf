package handlers

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/imranp/kerf/backend/internal/llm"
	"github.com/imranp/kerf/backend/internal/middleware"
	"github.com/imranp/kerf/backend/internal/models"
	"github.com/imranp/kerf/backend/internal/tools"
)

// MaxAgentIterations bounds the tool-use feedback loop so a misbehaving model
// can't run forever (or rack up an unbounded LLM bill).
const MaxAgentIterations = 10

// agentSystemAddendum is appended to llm.SystemPrompt for every agent call so
// the model knows it has tools available and how to use them politely.
const agentSystemAddendum = "\n\nYou have file tools to inspect and modify the user's CAD project. " +
	"Always read a file before editing it. Use edit_file with unique substrings to make targeted changes. " +
	"Use write_file only when the change is large or for new files. " +
	"After tool calls, give a brief summary of what changed — do NOT repeat the full file contents back unless asked. " +
	"The user can see the file change in their editor automatically."

// ListMessages returns all messages for a thread.
func (d *Deps) ListMessages(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	tid := chi.URLParam(r, "tid")
	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}
	if !d.threadInProject(r.Context(), w, tid, pid) {
		return
	}
	rows, err := d.Pool.Query(r.Context(), `
		select id, thread_id, role, content, part_refs, tool_calls, tool_call_id, model, created_at
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
	// callIDToName collects (tool_call_id → tool name) pairs from assistant
	// rows as we scan them in chronological order, so we can denormalize
	// `tool_name` onto each subsequent `role='tool'` row.
	callIDToName := map[string]string{}
	for rows.Next() {
		var m models.Message
		if err := rows.Scan(&m.ID, &m.ThreadID, &m.Role, &m.Content, &m.PartRefs, &m.ToolCalls, &m.ToolCallID, &m.Model, &m.CreatedAt); err != nil {
			genericServerError(w, err)
			return
		}
		switch m.Role {
		case "assistant":
			// tool_calls is a JSONB array of {id, name, arguments}; parse minimally.
			if len(m.ToolCalls) > 0 && string(m.ToolCalls) != "[]" && string(m.ToolCalls) != "null" {
				var calls []struct {
					ID   string `json:"id"`
					Name string `json:"name"`
				}
				if err := json.Unmarshal(m.ToolCalls, &calls); err == nil {
					for _, c := range calls {
						if c.ID != "" {
							callIDToName[c.ID] = c.Name
						}
					}
				}
			}
		case "tool":
			if m.ToolCallID != nil {
				if name, ok := callIDToName[*m.ToolCallID]; ok {
					n := name
					m.ToolName = &n
				}
			}
		}
		out = append(out, m)
	}
	writeJSON(w, http.StatusOK, out)
}

type postMessageReq struct {
	Content  string           `json:"content"`
	PartRefs []models.PartRef `json:"part_refs"`
	Model    *string          `json:"model"`
}

type postMessageResp struct {
	UserMessage      models.Message   `json:"user_message"`
	AssistantMessage models.Message   `json:"assistant_message"`
	ToolMessages     []models.Message `json:"tool_messages"`
}

// PostMessage records the user's turn, runs the agent loop (LLM + tool calls),
// persists every step, and returns the user/assistant/tool bundle.
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

	// Resolve model: body.model -> thread.model -> cfg.DefaultModel.
	var threadModel *string
	if err := d.Pool.QueryRow(r.Context(), `select model from chat_threads where id = $1`, tid).Scan(&threadModel); err != nil {
		genericServerError(w, err)
		return
	}
	chosenModel := ""
	switch {
	case body.Model != nil && *body.Model != "":
		chosenModel = *body.Model
	case threadModel != nil && *threadModel != "":
		chosenModel = *threadModel
	default:
		chosenModel = d.Cfg.DefaultModel
	}

	if d.LLM.HasAny() {
		if _, _, err := d.LLM.Resolve(chosenModel); err != nil {
			if body.Model != nil && *body.Model != "" {
				writeError(w, http.StatusBadRequest, err.Error())
				return
			}
		}
	}

	// Insert user message.
	var userMsg models.Message
	err = d.Pool.QueryRow(r.Context(), `
		insert into chat_messages(thread_id, role, content, part_refs)
		values ($1,'user',$2,$3)
		returning id, thread_id, role, content, part_refs, tool_calls, tool_call_id, model, created_at
	`, tid, body.Content, partRefsJSON).Scan(
		&userMsg.ID, &userMsg.ThreadID, &userMsg.Role, &userMsg.Content,
		&userMsg.PartRefs, &userMsg.ToolCalls, &userMsg.ToolCallID, &userMsg.Model, &userMsg.CreatedAt)
	if err != nil {
		genericServerError(w, err)
		return
	}

	// Build LLM message list from history (mapped from DB rows).
	historyMsgs, err := d.loadLLMHistory(r.Context(), tid, userMsg.ID)
	if err != nil {
		genericServerError(w, err)
		return
	}
	parts, err := d.loadPartContexts(r.Context(), pid, body.PartRefs)
	if err != nil {
		genericServerError(w, err)
		return
	}
	finalUserContent := llm.BuildUserMessage(body.Content, parts)
	historyMsgs = append(historyMsgs, llm.Message{Role: "user", Content: finalUserContent})

	// Resolve provider + project context for the tool runner.
	if !d.LLM.HasAny() {
		assistantMsg, _ := d.insertAssistantMessage(r.Context(), tid, "LLM not configured — set ANTHROPIC_API_KEY", "none", nil)
		_ = d.touchThread(r.Context(), tid)
		writeJSON(w, http.StatusCreated, postMessageResp{
			UserMessage: userMsg, AssistantMessage: assistantMsg, ToolMessages: nil,
		})
		return
	}
	provider, providerModelID, err := d.LLM.Resolve(chosenModel)
	if err != nil {
		assistantMsg, _ := d.insertAssistantMessage(r.Context(), tid, "LLM error: "+err.Error(), "none", nil)
		_ = d.touchThread(r.Context(), tid)
		writeJSON(w, http.StatusCreated, postMessageResp{
			UserMessage: userMsg, AssistantMessage: assistantMsg, ToolMessages: nil,
		})
		return
	}

	pcProject, err := uuid.Parse(pid)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid project id")
		return
	}
	pcUser, err := uuid.Parse(uid)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid user id")
		return
	}
	projCtx := tools.ProjectCtx{
		Pool:       d.Pool,
		Storage:    d.Storage,
		ProjectID:  pcProject,
		UserID:     pcUser,
		Role:       role,
		HTTPClient: &http.Client{Timeout: 30 * time.Second},
	}

	// Agent loop.
	toolSpecs := tools.Specs(role)
	var (
		lastAssistant models.Message
		toolMsgs      []models.Message
	)

	for iter := 0; iter < MaxAgentIterations; iter++ {
		resp, err := provider.Complete(r.Context(), llm.CompleteRequest{
			Model:    providerModelID,
			System:   llm.SystemPrompt + agentSystemAddendum,
			Messages: historyMsgs,
			Tools:    toolSpecs,
		})
		if err != nil {
			lastAssistant, _ = d.insertAssistantMessage(r.Context(), tid, "LLM error: "+err.Error(), providerModelID, nil)
			_ = d.touchThread(r.Context(), tid)
			writeJSON(w, http.StatusCreated, postMessageResp{
				UserMessage: userMsg, AssistantMessage: lastAssistant, ToolMessages: toolMsgs,
			})
			return
		}

		// Persist this assistant turn.
		am, err := d.insertAssistantMessage(r.Context(), tid, resp.Content, providerModelID, resp.ToolCalls)
		if err != nil {
			genericServerError(w, err)
			return
		}
		lastAssistant = am

		// Append assistant turn to history (so the next provider call sees it).
		assistantHist := llm.Message{
			Role:      "assistant",
			Content:   resp.Content,
			ToolCalls: resp.ToolCalls,
		}
		historyMsgs = append(historyMsgs, assistantHist)

		if len(resp.ToolCalls) == 0 || resp.StopReason == "stop" {
			break
		}

		// Run every tool call and persist a `role='tool'` row for each.
		for _, tc := range resp.ToolCalls {
			result := tools.Execute(r.Context(), projCtx, tc.Name, json.RawMessage(tc.ArgumentsJSON))
			tm, err := d.insertToolMessage(r.Context(), tid, tc.ID, result)
			if err != nil {
				genericServerError(w, err)
				return
			}
			// Denormalize tool name onto the response so the client can render
			// the chip + decide whether to refresh files without cross-walking
			// to the previous assistant message.
			name := tc.Name
			tm.ToolName = &name
			toolMsgs = append(toolMsgs, tm)
			historyMsgs = append(historyMsgs, llm.Message{
				Role:       "tool",
				Content:    result,
				ToolCallID: tc.ID,
			})
		}

		if iter == MaxAgentIterations-1 {
			// Cap reached — append a final notice and stop.
			notice, _ := d.insertAssistantMessage(r.Context(), tid,
				"(stopped: max tool iterations reached)", providerModelID, nil)
			lastAssistant = notice
			break
		}
	}

	_ = d.touchThread(r.Context(), tid)

	writeJSON(w, http.StatusCreated, postMessageResp{
		UserMessage:      userMsg,
		AssistantMessage: lastAssistant,
		ToolMessages:     toolMsgs,
	})
}

// insertAssistantMessage writes one assistant chat_message row and returns it.
func (d *Deps) insertAssistantMessage(ctx context.Context, tid, content, modelID string, calls []llm.ToolCall) (models.Message, error) {
	tcJSON, err := encodeToolCalls(calls)
	if err != nil {
		return models.Message{}, err
	}
	var m models.Message
	err = d.Pool.QueryRow(ctx, `
		insert into chat_messages(thread_id, role, content, part_refs, tool_calls, model)
		values ($1,'assistant',$2,'[]'::jsonb,$3::jsonb,$4)
		returning id, thread_id, role, content, part_refs, tool_calls, tool_call_id, model, created_at
	`, tid, content, tcJSON, modelID).Scan(
		&m.ID, &m.ThreadID, &m.Role, &m.Content, &m.PartRefs, &m.ToolCalls, &m.ToolCallID, &m.Model, &m.CreatedAt)
	return m, err
}

// insertToolMessage writes one tool-result chat_message row and returns it.
func (d *Deps) insertToolMessage(ctx context.Context, tid, toolCallID, content string) (models.Message, error) {
	var m models.Message
	err := d.Pool.QueryRow(ctx, `
		insert into chat_messages(thread_id, role, content, part_refs, tool_call_id)
		values ($1,'tool',$2,'[]'::jsonb,$3)
		returning id, thread_id, role, content, part_refs, tool_calls, tool_call_id, model, created_at
	`, tid, content, toolCallID).Scan(
		&m.ID, &m.ThreadID, &m.Role, &m.Content, &m.PartRefs, &m.ToolCalls, &m.ToolCallID, &m.Model, &m.CreatedAt)
	return m, err
}

// touchThread bumps last_message_at + updated_at.
func (d *Deps) touchThread(ctx context.Context, tid string) error {
	_, err := d.Pool.Exec(ctx,
		`update chat_threads set last_message_at = now(), updated_at = now() where id = $1`,
		tid)
	return err
}

// encodeToolCalls converts our llm.ToolCall slice into a JSON array suitable
// for the chat_messages.tool_calls jsonb column.
func encodeToolCalls(calls []llm.ToolCall) (string, error) {
	if len(calls) == 0 {
		return "[]", nil
	}
	type wire struct {
		ID        string `json:"id"`
		Name      string `json:"name"`
		Arguments string `json:"arguments"`
	}
	arr := make([]wire, 0, len(calls))
	for _, c := range calls {
		arr = append(arr, wire{ID: c.ID, Name: c.Name, Arguments: c.ArgumentsJSON})
	}
	b, err := json.Marshal(arr)
	if err != nil {
		return "", err
	}
	return string(b), nil
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

// loadLLMHistory loads prior thread messages and maps them into the
// provider-agnostic llm.Message shape (preserving tool_calls + tool_call_id).
func (d *Deps) loadLLMHistory(ctx context.Context, threadID, excludeID string) ([]llm.Message, error) {
	rows, err := d.Pool.Query(ctx, `
		select role, content, tool_calls, tool_call_id from chat_messages
		where thread_id = $1 and id <> $2
		order by created_at asc
	`, threadID, excludeID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []llm.Message
	for rows.Next() {
		var (
			role       string
			content    string
			toolCalls  json.RawMessage
			toolCallID *string
		)
		if err := rows.Scan(&role, &content, &toolCalls, &toolCallID); err != nil {
			return nil, err
		}
		msg := llm.Message{Role: role, Content: content}
		if toolCallID != nil {
			msg.ToolCallID = *toolCallID
		}
		if len(toolCalls) > 0 && string(toolCalls) != "null" && string(toolCalls) != "[]" {
			type wire struct {
				ID        string `json:"id"`
				Name      string `json:"name"`
				Arguments string `json:"arguments"`
			}
			var arr []wire
			if err := json.Unmarshal(toolCalls, &arr); err == nil {
				for _, w := range arr {
					msg.ToolCalls = append(msg.ToolCalls, llm.ToolCall{
						ID: w.ID, Name: w.Name, ArgumentsJSON: w.Arguments,
					})
				}
			}
		}
		out = append(out, msg)
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
