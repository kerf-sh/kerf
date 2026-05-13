package tools

import (
	"context"
	"encoding/json"

	"github.com/imranp/kerf/backend/internal/llm"
	"github.com/imranp/kerf/backend/internal/sim"
)

var runSimulationSpec = llm.ToolSpec{
	Name:        "run_simulation",
	Description: "Run a SPICE simulation on a circuit file. The circuit file must be a .circuit.tsx file containing tscircuit JSON. Returns job ID for polling.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"circuit_file_id": map[string]any{
				"type":        "string",
				"description": "UUID of the circuit file to simulate.",
			},
			"analysis": map[string]any{
				"type": "object",
				"description": "Analysis specification.",
				"properties": map[string]any{
					"type": map[string]any{
						"type":        "string",
						"enum":        []string{"tran", "dc", "ac", "op"},
						"description": "Analysis type: tran (transient), dc (DC sweep), ac (AC analysis), op (operating point).",
					},
					"tstep": map[string]any{
						"type":        "string",
						"description": "Transient time step (e.g. '1us').",
					},
					"tstop": map[string]any{
						"type":        "string",
						"description": "Transient stop time (e.g. '10ms').",
					},
					"vstart": map[string]any{
						"type":        "number",
						"description": "DC sweep start voltage.",
					},
					"vstop": map[string]any{
						"type":        "number",
						"description": "DC sweep stop voltage.",
					},
					"vstep": map[string]any{
						"type":        "number",
						"description": "DC sweep voltage step.",
					},
					"fstart": map[string]any{
						"type":        "number",
						"description": "AC sweep start frequency in Hz.",
					},
					"fstop": map[string]any{
						"type":        "number",
						"description": "AC sweep stop frequency in Hz.",
					},
					"points": map[string]any{
						"type":        "number",
						"description": "Number of frequency points for AC analysis.",
					},
				},
				"required": []string{"type"},
			},
		},
		"required": []string{"circuit_file_id", "analysis"},
	},
}

type runSimulationArgs struct {
	CircuitFileID string        `json:"circuit_file_id"`
	Analysis     sim.InputSpec `json:"analysis"`
}

func runSimulation(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a runSimulationArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	if a.CircuitFileID == "" {
		return errPayload("circuit_file_id is required", "BAD_ARGS"), nil
	}
	if a.Analysis.Type == "" {
		return errPayload("analysis.type is required", "BAD_ARGS"), nil
	}

	spec := a.Analysis

	specJSON, err := json.Marshal(spec)
	if err != nil {
		return "", err
	}

	var jobID string
	err = pc.Pool.QueryRow(ctx, `
		insert into sim_jobs (file_id, project_id, input_spec)
		values ($1, $2, $3)
		on conflict (file_id) where status in ('queued','running')
		do update set input_spec = $3, status = 'queued', error = null,
			started_at = null, finished_at = null
		returning id
	`, a.CircuitFileID, pc.ProjectID, specJSON).Scan(&jobID)
	if err != nil {
		return errPayload("failed to enqueue sim job: "+err.Error(), "ERROR"), nil
	}

	return okPayload(map[string]any{
		"job_id":       jobID,
		"status":       "queued",
		"message":      "Simulation job enqueued. Poll sim_job_status(file_id) for results.",
		"circuit_file_id": a.CircuitFileID,
	}), nil
}

var simJobStatusSpec = llm.ToolSpec{
	Name:        "sim_job_status",
	Description: "Poll the status of a SPICE simulation job. Returns job status, and when complete the waveform results.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"file_id": map[string]any{
				"type":        "string",
				"description": "UUID of the file the simulation job was enqueued for.",
			},
		},
		"required": []string{"file_id"},
	},
}

type simJobStatusArgs struct {
	FileID string `json:"file_id"`
}

func runSimJobStatus(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a simJobStatusArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	if a.FileID == "" {
		return errPayload("file_id is required", "BAD_ARGS"), nil
	}

	var status string
	var resultJSON []byte
	var errorText *string
	err := pc.Pool.QueryRow(ctx, `
		select status, result_json, error
		from sim_jobs
		where file_id = $1 and project_id = $2
		order by created_at desc
		limit 1
	`, a.FileID, pc.ProjectID).Scan(&status, &resultJSON, &errorText)
	if err != nil {
		return errPayload("sim job not found", "NOT_FOUND"), nil
	}

	resp := map[string]any{
		"file_id": a.FileID,
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

	return okPayload(resp), nil
}
