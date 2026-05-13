package handlers

import (
	"encoding/json"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"

	"github.com/imranp/kerf/backend/internal/sim"
	"github.com/imranp/kerf/backend/internal/middleware"
)

func (d *Deps) RunSim(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	fid := chi.URLParam(r, "fid")

	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}

	var spec sim.InputSpec
	if err := json.NewDecoder(r.Body).Decode(&spec); err != nil {
		writeError(w, http.StatusBadRequest, "invalid input_spec: "+err.Error())
		return
	}

	specJSON, err := json.Marshal(spec)
	if err != nil {
		genericServerError(w, err)
		return
	}

	var jobID string
	err = d.Pool.QueryRow(r.Context(), `
		insert into sim_jobs (file_id, project_id, input_spec)
		values ($1, $2, $3)
		on conflict (file_id) where status in ('queued','running')
		do update set input_spec = $3, status = 'queued', error = null,
			started_at = null, finished_at = null
		returning id
	`, fid, pid, specJSON).Scan(&jobID)
	if err != nil {
		if err == pgx.ErrNoRows {
			writeError(w, http.StatusConflict, "file already has an active sim job")
			return
		}
		genericServerError(w, err)
		return
	}

	writeJSON(w, http.StatusAccepted, map[string]any{"job_id": jobID, "status": "queued"})
}

func (d *Deps) SimJobStatus(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	fid := chi.URLParam(r, "fid")

	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}

	var status string
	var resultJSON []byte
	var errorText *string
	err := d.Pool.QueryRow(r.Context(), `
		select status, result_json, error
		from sim_jobs
		where file_id = $1 and project_id = $2
		order by created_at desc
		limit 1
	`, fid, pid).Scan(&status, &resultJSON, &errorText)
	if err != nil {
		if err == pgx.ErrNoRows {
			writeError(w, http.StatusNotFound, "sim job not found")
			return
		}
		genericServerError(w, err)
		return
	}

	resp := map[string]any{
		"file_id": fid,
		"status":  status,
	}
	if status == "done" && resultJSON != nil {
		var result sim.Result
		if err := json.Unmarshal(resultJSON, &result); err == nil {
			resp["result"] = result
		}
	} else if status == "error" && errorText != nil {
		resp["error"] = *errorText
	}

	writeJSON(w, http.StatusOK, resp)
}
