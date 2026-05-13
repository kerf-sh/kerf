package handlers

import (
	"encoding/json"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"

	"github.com/imranp/kerf/backend/internal/fem"
	"github.com/imranp/kerf/backend/internal/middleware"
)

func (d *Deps) RunFEM(w http.ResponseWriter, r *http.Request) {
	uid := middleware.UserID(r.Context())
	pid := chi.URLParam(r, "pid")
	fid := chi.URLParam(r, "fid")

	if requireMember(w, r, d.Pool, pid, uid) == "" {
		return
	}

	var spec fem.InputSpec
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
		insert into fem_jobs (file_id, project_id, input_spec)
		values ($1, $2, $3)
		on conflict (file_id) where status in ('queued','running')
		do update set input_spec = $3, status = 'queued', error = null,
			started_at = null, finished_at = null
		returning id
	`, fid, pid, specJSON).Scan(&jobID)
	if err != nil {
		if err == pgx.ErrNoRows {
			writeError(w, http.StatusConflict, "file already has an active FEM job")
			return
		}
		genericServerError(w, err)
		return
	}

	writeJSON(w, http.StatusAccepted, map[string]any{"job_id": jobID, "status": "queued"})
}