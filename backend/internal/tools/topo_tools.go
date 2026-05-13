package tools

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"

	"github.com/imranp/kerf/backend/internal/llm"
)

type topoDoc struct {
	Version                int         `json:"version"`
	DesignSpaceFeaturePath string      `json:"design_space_feature_path"`
	MaterialPath           string      `json:"material_path"`
	VolumeFraction         float64     `json:"volume_fraction"`
	PenalizationPower      int         `json:"penalization_power"`
	FilterRadiusMM         float64     `json:"filter_radius_mm"`
	MaxIterations          int         `json:"max_iterations"`
	ConvergenceTolerance   float64     `json:"convergence_tolerance"`
	Results                topoResults `json:"results"`
}

type topoResults struct {
	Status               string   `json:"status"`
	Iterations          int      `json:"iterations"`
	FinalCompliance     *float64 `json:"final_compliance"`
	FinalVolumeFraction *float64 `json:"final_volume_fraction"`
	Warnings            []string `json:"warnings"`
	Errors              []string `json:"errors"`
	OutputMeshFileID    string   `json:"output_mesh_file_id"`
}

func parseTopoContent(s string) topoDoc {
	var d topoDoc
	if strings.TrimSpace(s) != "" {
		_ = json.Unmarshal([]byte(s), &d)
	}
	if d.Version == 0 {
		d.Version = 1
	}
	if d.MaxIterations == 0 {
		d.MaxIterations = 200
	}
	if d.PenalizationPower == 0 {
		d.PenalizationPower = 3
	}
	if d.FilterRadiusMM == 0 {
		d.FilterRadiusMM = 1.5
	}
	if d.ConvergenceTolerance == 0 {
		d.ConvergenceTolerance = 1e-4
	}
	if d.VolumeFraction == 0 {
		d.VolumeFraction = 0.3
	}
	if d.Results.Warnings == nil {
		d.Results.Warnings = []string{}
	}
	if d.Results.Errors == nil {
		d.Results.Errors = []string{}
	}
	return d
}

func serializeTopoContent(d topoDoc) (string, error) {
	if d.Version == 0 {
		d.Version = 1
	}
	if d.Results.Warnings == nil {
		d.Results.Warnings = []string{}
	}
	if d.Results.Errors == nil {
		d.Results.Errors = []string{}
	}
	b, err := json.MarshalIndent(d, "", "  ")
	if err != nil {
		return "", err
	}
	return string(b), nil
}

var topoRunSpec = llm.ToolSpec{
	Name:        "topo_run",
	Description: "Submit a topology-optimization (SIMP via FEniCSx) job for a .topo file. Reads design_space_feature_path, material_path, volume_fraction, penalization_power, filter_radius_mm, max_iterations, and convergence_tolerance from the .topo file, then POSTs to the pyworker /run-topo endpoint. On engine-pending the .topo file is updated with an 'Engine pending' warning.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"topo_path": map[string]any{
				"type":        "string",
				"description": "Absolute path of the .topo SIMP specification file.",
			},
		},
		"required": []string{"topo_path"},
	},
}

type topoRunArgs struct {
	TopoPath string `json:"topo_path"`
}

func runTopoRun(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a topoRunArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	if strings.TrimSpace(a.TopoPath) == "" {
		return errPayload("topo_path is required", "BAD_ARGS"), nil
	}

	rp, err := resolvePath(ctx, pc, a.TopoPath)
	if err != nil || !rp.Exists {
		return errPayload("file not found: "+a.TopoPath, "NOT_FOUND"), nil
	}
	if rp.Kind != "topo" {
		return errPayload("path is not a .topo file (kind="+rp.Kind+")", "BAD_KIND"), nil
	}

	var content string
	if err := pc.Pool.QueryRow(ctx,
		`select content from files where id = $1 and project_id = $2`,
		rp.ID, pc.ProjectID).Scan(&content); err != nil {
		return "", err
	}

	doc := parseTopoContent(content)

	if strings.TrimSpace(doc.DesignSpaceFeaturePath) == "" {
		return errPayload("topo file is missing design_space_feature_path", "BAD_TOPO"), nil
	}
	if strings.TrimSpace(doc.MaterialPath) == "" {
		return errPayload("topo file is missing material_path", "BAD_TOPO"), nil
	}
	if doc.VolumeFraction <= 0 || doc.VolumeFraction >= 1 {
		return errPayload("volume_fraction must be in (0, 1)", "BAD_TOPO"), nil
	}
	if doc.MaxIterations <= 0 {
		return errPayload("max_iterations must be > 0", "BAD_TOPO"), nil
	}

	featureRP, err := resolvePath(ctx, pc, doc.DesignSpaceFeaturePath)
	if err != nil || !featureRP.Exists {
		return errPayload("design_space_feature_path not found: "+doc.DesignSpaceFeaturePath, "NOT_FOUND"), nil
	}
	if featureRP.Kind != "feature" {
		return errPayload("design_space_feature_path is not a .feature file", "BAD_TOPO"), nil
	}

	matRP, err := resolvePath(ctx, pc, doc.MaterialPath)
	if err != nil || !matRP.Exists {
		return errPayload("material_path not found: "+doc.MaterialPath, "NOT_FOUND"), nil
	}
	if matRP.Kind != "material" {
		return errPayload("material_path is not a .material file", "BAD_TOPO"), nil
	}

	payload := map[string]any{
		"project_id":             pc.ProjectID.String(),
		"topo_file_id":           rp.ID.String(),
		"feature_file_id":        featureRP.ID.String(),
		"material_file_id":       matRP.ID.String(),
		"volume_fraction":       doc.VolumeFraction,
		"penalization_power":    doc.PenalizationPower,
		"filter_radius_mm":      doc.FilterRadiusMM,
		"max_iterations":        doc.MaxIterations,
		"convergence_tolerance": doc.ConvergenceTolerance,
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return errPayload("encode payload: "+err.Error(), "ERROR"), nil
	}

	reqURL := "http://localhost:9090/run-topo"
	req, err := http.NewRequestWithContext(ctx, "POST", reqURL, strings.NewReader(string(body)))
	if err != nil {
		return errPayload("create request: "+err.Error(), "ERROR"), nil
	}
	req.Header.Set("content-type", "application/json")

	resp, err := pc.HTTPClient.Do(req)
	if err != nil {
		doc.Results.Status = "pending"
		doc.Results.Warnings = append(doc.Results.Warnings, "Engine pending — FEniCSx not yet deployed.")
		outBody, _ := serializeTopoContent(doc)
		pc.Pool.Exec(ctx,
			`update files set content = $1, updated_at = now() where id = $2 and project_id = $3`,
			string(outBody), rp.ID, pc.ProjectID)
		_ = recordRevisionForFile(ctx, pc, rp.ID, string(outBody), "tool")
		return okPayload(map[string]any{
			"status":              "pending",
			"topo_path":           a.TopoPath,
			"warning":             "Engine pending — FEniCSx not yet deployed.",
			"output_mesh_file_id": "",
		}), nil
	}
	defer resp.Body.Close()

	var engineResp struct {
		Status               string  `json:"status"`
		OutputMeshFileID     string  `json:"output_mesh_file_id"`
		FinalCompliance     float64 `json:"final_compliance"`
		FinalVolumeFraction float64 `json:"final_volume_fraction"`
		Iterations          int     `json:"iterations"`
		Error               string  `json:"error,omitempty"`
		Warnings            []string `json:"warnings,omitempty"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&engineResp); err != nil {
		return errPayload("decode engine response: "+err.Error(), "ERROR"), nil
	}

	if engineResp.Status == "" {
		engineResp.Status = "pending"
	}
	if engineResp.Warnings == nil {
		engineResp.Warnings = []string{}
	}

	doc.Results.Status = engineResp.Status
	doc.Results.Iterations = engineResp.Iterations
	doc.Results.OutputMeshFileID = engineResp.OutputMeshFileID
	if engineResp.FinalCompliance != 0 {
		fc := engineResp.FinalCompliance
		doc.Results.FinalCompliance = &fc
	}
	if engineResp.FinalVolumeFraction != 0 {
		fvf := engineResp.FinalVolumeFraction
		doc.Results.FinalVolumeFraction = &fvf
	}
	for _, w := range engineResp.Warnings {
		if w != "" {
			doc.Results.Warnings = append(doc.Results.Warnings, w)
		}
	}
	if engineResp.Error != "" {
		doc.Results.Errors = append(doc.Results.Errors, engineResp.Error)
	}

	outBody, err := serializeTopoContent(doc)
	if err != nil {
		return errPayload("encode result: "+err.Error(), "ERROR"), nil
	}
	pc.Pool.Exec(ctx,
		`update files set content = $1, updated_at = now() where id = $2 and project_id = $3`,
		string(outBody), rp.ID, pc.ProjectID)
	_ = recordRevisionForFile(ctx, pc, rp.ID, string(outBody), "tool")

	return okPayload(map[string]any{
		"status":                engineResp.Status,
		"topo_path":             a.TopoPath,
		"output_mesh_file_id":   engineResp.OutputMeshFileID,
		"final_compliance":       engineResp.FinalCompliance,
		"final_volume_fraction": engineResp.FinalVolumeFraction,
		"iterations":            engineResp.Iterations,
		"errors":                doc.Results.Errors,
	}), nil
}