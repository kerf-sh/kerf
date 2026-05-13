package tools

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/imranp/kerf/backend/internal/llm"
)

var runRFStudySpec = llm.ToolSpec{
	Name:        "run_rf_study",
	Description: "Run an S-parameter analysis on a .rf-study file using scikit-rf. Performs Smith chart analysis, VSWR, return loss, and insertion loss on touchstone (.sNp) data.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"file_id": map[string]any{
				"type":        "string",
				"description": "UUID of the .rf-study file to analyze.",
			},
			"port_impedance": map[string]any{
				"type":        "number",
				"description": "Reference impedance in ohms for renormalization (default 50).",
			},
			"freq_unit": map[string]any{
				"type":        "string",
				"enum":        []string{"Hz", "kHz", "MHz", "GHz"},
				"description": "Frequency unit for output plots (default GHz).",
			},
		},
		"required": []string{"file_id"},
	},
}

type runRFStudyArgs struct {
	FileID         string  `json:"file_id"`
	PortImpedance  float64 `json:"port_impedance"`
	FreqUnit       string  `json:"freq_unit"`
}

func runRunRFStudy(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a runRFStudyArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	if a.FileID == "" {
		return errPayload("file_id is required", "BAD_ARGS"), nil
	}

	portZ := a.PortImpedance
	if portZ == 0 {
		portZ = 50.0
	}
	freqUnit := a.FreqUnit
	if freqUnit == "" {
		freqUnit = "GHz"
	}

	spec := map[string]any{
		"file_id":        a.FileID,
		"port_impedance": portZ,
		"freq_unit":      freqUnit,
	}
	specJSON, err := json.Marshal(spec)
	if err != nil {
		return "", err
	}

	var jobID string
	err = pc.Pool.QueryRow(ctx, `
		insert into rf_jobs (file_id, project_id, input_spec)
		values ($1, $2, $3)
		on conflict (file_id) where status in ('queued','running')
		do update set input_spec = $3, status = 'queued', error = null,
			started_at = null, finished_at = null
		returning id
	`, a.FileID, pc.ProjectID, specJSON).Scan(&jobID)
	if err != nil {
		return errPayload("failed to enqueue RF job: "+err.Error(), "ERROR"), nil
	}

	return okPayload(map[string]any{
		"job_id": jobID,
		"status": "queued",
		"message": "RF study job enqueued. Poll rf_job_status(file_id) for results.",
	}), nil
}

var rfJobStatusSpec = llm.ToolSpec{
	Name:        "rf_job_status",
	Description: "Poll the status of an RF study analysis job. Returns job status, and when complete the S-parameter analysis results including Smith chart SVG, VSWR, return loss, and insertion loss.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"file_id": map[string]any{
				"type":        "string",
				"description": "UUID of the .rf-study file the job was enqueued for.",
			},
		},
		"required": []string{"file_id"},
	},
}

type rfJobStatusArgs struct {
	FileID string `json:"file_id"`
}

type RFResult struct {
	Status               string    `json:"status"`
	FrequencyRange       []float64 `json:"frequency_range"`
	FrequencyUnit       string    `json:"frequency_unit"`
	PortImpedance       float64   `json:"port_impedance"`
	NumPorts            int        `json:"num_ports"`
	NumPoints           int        `json:"num_points"`
	VSWR                []float64 `json:"vswr"`
	ReturnLossDB        []float64 `json:"return_loss_db"`
	InsertionLossDB     []float64 `json:"insertion_loss_db"`
	SmithChartSVG       string    `json:"smith_chart_svg"`
	Warnings            []string  `json:"warnings"`
	Errors              []string  `json:"errors"`
}

func runRFJobStatus(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a rfJobStatusArgs
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
		from rf_jobs
		where file_id = $1 and project_id = $2
		order by created_at desc
		limit 1
	`, a.FileID, pc.ProjectID).Scan(&status, &resultJSON, &errorText)
	if err != nil {
		return errPayload("RF job not found", "NOT_FOUND"), nil
	}

	resp := map[string]any{
		"file_id": a.FileID,
		"status":  status,
	}
	if status == "done" && resultJSON != nil {
		var result RFResult
		if err := json.Unmarshal(resultJSON, &result); err == nil {
			resp["result"] = result
		}
	} else if status == "error" && errorText != nil {
		resp["error"] = *errorText
	}

	return okPayload(resp), nil
}

var importTouchstoneSpec = llm.ToolSpec{
	Name:        "import_touchstone",
	Description: "Import a Touchstone (.sNp) file and create a .rf-study file. Supports S1P, S2P, S3P, S4P formats with automatic renormalization to the specified port impedance.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"touchstone_file_id": map[string]any{
				"type":        "string",
				"description": "UUID of the uploaded Touchstone file.",
			},
			"name": map[string]any{
				"type":        "string",
				"description": "Name for the new .rf-study file (without extension).",
			},
			"port_impedance": map[string]any{
				"type":        "number",
				"description": "Reference impedance in ohms (default 50).",
			},
		},
		"required": []string{"touchstone_file_id", "name"},
	},
}

type importTouchstoneArgs struct {
	TouchstoneFileID string  `json:"touchstone_file_id"`
	Name             string  `json:"name"`
	PortImpedance    float64 `json:"port_impedance"`
}

func runImportTouchstone(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a importTouchstoneArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	if a.TouchstoneFileID == "" {
		return errPayload("touchstone_file_id is required", "BAD_ARGS"), nil
	}
	if a.Name == "" {
		return errPayload("name is required", "BAD_ARGS"), nil
	}

	portZ := a.PortImpedance
	if portZ == 0 {
		portZ = 50.0
	}

	var touchstoneData []byte
	var touchstoneFileName string
	err := pc.Pool.QueryRow(ctx, `
		select file_data, file_name from project_files
		where id = $1 and project_id = $2
	`, a.TouchstoneFileID, pc.ProjectID).Scan(&touchstoneData, &touchstoneFileName)
	if err != nil {
		return errPayload("Touchstone file not found", "NOT_FOUND"), nil
	}

	rfStudyDoc := map[string]any{
		"version": 1,
		"name":    a.Name,
		"source_file": touchstoneFileName,
		"port_impedance": portZ,
		"frequency_unit": "GHz",
		"touchstone_b64": fmt.Sprintf("%X", touchstoneData),
		"results": map[string]any{
			"status": "pending",
		},
	}

	rfStudyJSON, err := json.Marshal(rfStudyDoc)
	if err != nil {
		return errPayload("failed to create rf-study document: "+err.Error(), "ERROR"), nil
	}

	var newFileID string
	err = pc.Pool.QueryRow(ctx, `
		insert into project_files (project_id, file_name, file_data, content_type, file_kind, created_by)
		values ($1, $2, $3, 'application/json', 'rf-study', $4)
		returning id
	`, pc.ProjectID, a.Name+".rf-study", rfStudyJSON, pc.UserID).Scan(&newFileID)
	if err != nil {
		return errPayload("failed to create rf-study file: "+err.Error(), "ERROR"), nil
	}

	return okPayload(map[string]any{
		"file_id":   newFileID,
		"file_name": a.Name + ".rf-study",
		"status":    "created",
	}), nil
}
