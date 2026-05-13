package handlers

import (
	"encoding/json"
	"net/http"

	"github.com/google/uuid"

	"github.com/imranp/kerf/backend/internal/middleware"
	"github.com/imranp/kerf/backend/internal/tools"
)

type jsonRPCRequest struct {
	JSONRPC string          `json:"jsonrpc"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params"`
	ID      any             `json:"id"`
}

type jsonRPCResponse struct {
	JSONRPC string        `json:"jsonrpc"`
	Result  any           `json:"result,omitempty"`
	Error   *jsonRPCError `json:"error,omitempty"`
	ID      any           `json:"id"`
}

type jsonRPCError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

type rpcParams struct {
	ProjectID string `json:"project_id"`
}

func (d *Deps) HandleRPC(w http.ResponseWriter, r *http.Request) {
	uidStr := middleware.UserID(r.Context())
	if uidStr == "" {
		sendRPCError(w, nil, -32600, "unauthorized")
		return
	}

	var req jsonRPCRequest
	if err := decodeJSON(r, &req); err != nil {
		sendRPCError(w, req.ID, -32700, "parse error")
		return
	}

	if req.JSONRPC != "2.0" {
		sendRPCError(w, req.ID, -32600, "invalid request: jsonrpc must be 2.0")
		return
	}

	var params rpcParams
	if err := json.Unmarshal(req.Params, &params); err != nil {
		sendRPCError(w, req.ID, -32600, "invalid params")
		return
	}

	if params.ProjectID == "" {
		sendRPCError(w, req.ID, -32602, "project_id is required")
		return
	}

	projectID, err := uuid.Parse(params.ProjectID)
	if err != nil {
		sendRPCError(w, req.ID, -32602, "invalid project_id format")
		return
	}

	uid, err := uuid.Parse(uidStr)
	if err != nil {
		sendRPCError(w, req.ID, -32603, "internal error: invalid user id")
		return
	}

	role, exists, err := projectRole(r.Context(), d.Pool, params.ProjectID, uidStr)
	if err != nil {
		sendRPCError(w, req.ID, -32603, "internal error")
		return
	}
	if !exists || role == "" {
		sendRPCError(w, req.ID, -32600, "project not found or access denied")
		return
	}

	toolName := rpcMethodToTool(req.Method)
	if toolName == "" {
		sendRPCError(w, req.ID, -32601, "method not found: "+req.Method)
		return
	}

	pc := tools.ProjectCtx{
		Pool:       d.Pool,
		Storage:    d.Storage,
		ProjectID:  projectID,
		UserID:     uid,
		Role:       role,
		HTTPClient: http.DefaultClient,
	}

	result := tools.Execute(r.Context(), pc, toolName, req.Params)

	var resultVal any
	if isErrorPayload([]byte(result)) {
		var errMsg struct {
			Error string `json:"error"`
			Code  string `json:"code"`
		}
		if json.Unmarshal([]byte(result), &errMsg) == nil {
			sendRPCError(w, req.ID, -32603, errMsg.Error)
			return
		}
	}

	if err := json.Unmarshal([]byte(result), &resultVal); err != nil {
		resultVal = result
	}

	writeJSON(w, http.StatusOK, jsonRPCResponse{
		JSONRPC: "2.0",
		Result:  resultVal,
		ID:      req.ID,
	})
}

func sendRPCError(w http.ResponseWriter, id any, code int, message string) {
	writeJSON(w, http.StatusOK, jsonRPCResponse{
		JSONRPC: "2.0",
		Error:   &jsonRPCError{Code: code, Message: message},
		ID:      id,
	})
}

func rpcMethodToTool(method string) string {
	switch method {
	case "files.list":
		return "list_files"
	case "files.read":
		return "read_file"
	case "files.write":
		return "write_file"
	case "files.edit":
		return "edit_file"
	case "files.create":
		return "create_file"
	case "files.delete":
		return "delete_file"
	case "files.search":
		return "search_code"
	case "import_step":
		return "import_step"
	case "equations.read":
		return "read_equations"
	case "equations.set":
		return "set_equation"
	case "configurations.add":
		return "add_configuration"
	case "configurations.set_active":
		return "set_active_config"
	case "revisions.list":
		return "list_revisions"
	case "revisions.restore":
		return "restore_revision"
	case "docs.search":
		return "search_kerf_docs"
	default:
		return ""
	}
}

func isErrorPayload(b []byte) bool {
	var m map[string]any
	if json.Unmarshal(b, &m) != nil {
		return false
	}
	_, ok := m["error"]
	return ok
}
