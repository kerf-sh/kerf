package tools

import (
	"context"
	"encoding/json"

	"github.com/imranp/kerf/backend/internal/fem"
	"github.com/imranp/kerf/backend/internal/llm"
)

var femRunSpec = llm.ToolSpec{
	Name:        "fem_run",
	Description: "Run a finite-element stress analysis on a STEP file. The file must be a STEP part or assembly. Returns max von-Mises stress, displacement, FoS, and modal frequencies. Requires material properties and boundary conditions.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"file_id": map[string]any{
				"type":        "string",
				"description": "UUID of the STEP file to analyse.",
			},
			"material_props": map[string]any{
				"type":        "object",
				"description": "Elastic material properties.",
				"properties": map[string]any{
					"E": map[string]any{
						"type":        "number",
						"description": "Young's modulus in Pa.",
					},
					"nu": map[string]any{
						"type":        "number",
						"description": "Poisson's ratio (dimensionless).",
					},
					"rho": map[string]any{
						"type":        "number",
						"description": "Density in kg/m³.",
					},
					"yield_strength": map[string]any{
						"type":        "number",
						"description": "Yield strength in Pa for FoS calculation.",
					},
				},
				"required": []string{"E", "nu", "rho", "yield_strength"},
			},
			"boundary_conditions": map[string]any{
				"type": "array",
				"items": map[string]any{
					"type": "object",
					"properties": map[string]any{
						"type": map[string]any{
							"type":        "string",
							"enum":        []string{"fixed", "displacement"},
							"description": "'fixed' = fully constrained; 'displacement' = prescribed UX/UY/UZ.",
						},
						"face_tags": map[string]any{
							"type":        "array",
							"items":       map[string]any{"type": "number"},
							"description": "Gmsh physical face tags to apply the BC.",
						},
						"ux": map[string]any{"type": "number"},
						"uy": map[string]any{"type": "number"},
						"uz": map[string]any{"type": "number"},
					},
					"required": []string{"type", "face_tags"},
				},
			},
			"loads": map[string]any{
				"type": "array",
				"items": map[string]any{
					"type": "object",
					"properties": map[string]any{
						"type": map[string]any{
							"type":        "string",
							"enum":        []string{"pressure", "force"},
							"description": "'pressure' = normal stress (Pa); 'force' = total force (N).",
						},
						"face_tags": map[string]any{
							"type":        "array",
							"items":       map[string]any{"type": "number"},
							"description": "Gmsh physical face tags to apply the load.",
						},
						"value": map[string]any{
							"type":        "number",
							"description": "Pressure in Pa or total force in N.",
						},
					},
					"required": []string{"type", "face_tags", "value"},
				},
			},
			"mesh_size": map[string]any{
				"type":        "number",
				"description": "Target element size in meters. Defaults to 0.01.",
			},
			"solver": map[string]any{
				"type":        "string",
				"enum":        []string{"fenicsx", "calculix"},
				"description": "Solver to use. Defaults to 'fenicsx'.",
			},
			"analysis_type": map[string]any{
				"type":        "string",
				"enum":        []string{"linear_static", "modal", "thermal"},
				"description": "Type of analysis to run. Defaults to 'linear_static'.",
			},
		},
		"required": []string{"file_id", "material_props", "boundary_conditions", "loads"},
	},
}

type femRunArgs struct {
	FileID              string             `json:"file_id"`
	MaterialProps       map[string]float64 `json:"material_props"`
	BoundaryConditions  []fem.BC           `json:"boundary_conditions"`
	Loads               []fem.Load         `json:"loads"`
	MeshSize            float64            `json:"mesh_size"`
	Solver              string             `json:"solver"`
	AnalysisType        string             `json:"analysis_type"`
}

func runFEMRun(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a femRunArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	if a.FileID == "" {
		return errPayload("file_id is required", "BAD_ARGS"), nil
	}
	if a.MaterialProps == nil {
		return errPayload("material_props is required", "BAD_ARGS"), nil
	}
	if len(a.BoundaryConditions) == 0 {
		return errPayload("at least one boundary_conditions entry is required", "BAD_ARGS"), nil
	}
	if len(a.Loads) == 0 {
		return errPayload("at least one load entry is required", "BAD_ARGS"), nil
	}

	spec := fem.InputSpec{
		MaterialProps:       a.MaterialProps,
		BoundaryConditions:  a.BoundaryConditions,
		Loads:               a.Loads,
		MeshSize:            a.MeshSize,
		Solver:              a.Solver,
		AnalysisType:        a.AnalysisType,
	}
	if spec.Solver == "" {
		spec.Solver = "fenicsx"
	}
	if spec.AnalysisType == "" {
		spec.AnalysisType = "linear_static"
	}

	specJSON, err := json.Marshal(spec)
	if err != nil {
		return "", err
	}

	var jobID string
	err = pc.Pool.QueryRow(ctx, `
		insert into fem_jobs (file_id, project_id, input_spec)
		values ($1, $2, $3)
		on conflict (file_id) where status in ('queued','running')
		do update set input_spec = $3, status = 'queued', error = null,
			started_at = null, finished_at = null
		returning id
	`, a.FileID, pc.ProjectID, specJSON).Scan(&jobID)
	if err != nil {
		return errPayload("failed to enqueue FEM job: "+err.Error(), "ERROR"), nil
	}

	return okPayload(map[string]any{
		"job_id": jobID,
		"status": "queued",
		"message": "FEM job enqueued. Poll fem_job_status(file_id) for results.",
	}), nil
}

var femJobStatusSpec = llm.ToolSpec{
	Name:        "fem_job_status",
	Description: "Poll the status of a FEM analysis job. Returns the job status, and when complete the result JSON (max von-Mises stress, displacement, FoS, frequencies).",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"file_id": map[string]any{
				"type":        "string",
				"description": "UUID of the file the FEM job was enqueued for.",
			},
		},
		"required": []string{"file_id"},
	},
}

type femJobStatusArgs struct {
	FileID string `json:"file_id"`
}

func runFEMJobStatus(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a femJobStatusArgs
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
		from fem_jobs
		where file_id = $1 and project_id = $2
		order by created_at desc
		limit 1
	`, a.FileID, pc.ProjectID).Scan(&status, &resultJSON, &errorText)
	if err != nil {
		return errPayload("fem job not found", "NOT_FOUND"), nil
	}

	resp := map[string]any{
		"file_id": a.FileID,
		"status":  status,
	}
	if status == "done" && resultJSON != nil {
		var result fem.Result
		if err := json.Unmarshal(resultJSON, &result); err == nil {
			resp["result"] = result
		}
	} else if status == "error" && errorText != nil {
		resp["error"] = *errorText
	}

	return okPayload(resp), nil
}