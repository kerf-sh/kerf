package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/google/uuid"

	"github.com/imranp/kerf/backend/internal/llm"
)

var autorouteCircuitSpec = llm.ToolSpec{
	Name:        "autoroute_circuit",
	Description: "Autoroute PCB traces for a `.circuit.tsx` file using FreeRouting. Exports the board to Specctra DSN, runs the FreeRouting JAR, parses the SES session, and updates the circuit file with routed trace geometry. Requires the board to have at least two components and one net.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"circuit_file_id": map[string]any{
				"type":        "string",
				"description": "UUID of the `.circuit.tsx` file (kind='circuit') to autoroute.",
			},
			"trace_width_microns": map[string]any{
				"type":        "number",
				"description": "Trace width in microns (default 200µm = 0.2mm, suitable for 2A current).",
			},
			"via_diameter_microns": map[string]any{
				"type":        "number",
				"description": "Via barrel diameter in microns (default 600µm).",
			},
			"via_drill_microns": map[string]any{
				"type":        "number",
				"description": "Via drill (hole) diameter in microns (default 300µm).",
			},
			"route_layers": map[string]any{
				"type":        "string",
				"description": "Comma-separated layer spec for routing (default '1top,16bot' for 2-layer; '1top,2mid1,3mid2,16bot' for 4-layer). FreeRouting interprets layer numbers per the DSN layer_map.",
			},
			"clearance_microns": map[string]any{
				"type":        "number",
				"description": "Copper-to-copper clearance in microns (default 200µm).",
			},
		},
		"required": []string{"circuit_file_id"},
	},
}

type autorouteCircuitArgs struct {
	CircuitFileID       string  `json:"circuit_file_id"`
	TraceWidthMicrons   float64 `json:"trace_width_microns"`
	ViaDiameterMicrons  float64 `json:"via_diameter_microns"`
	ViaDrillMicrons     float64 `json:"via_drill_microns"`
	RouteLayers         string  `json:"route_layers"`
	ClearanceMicrons    float64 `json:"clearance_microns"`
}

type autorouteCircuitResult struct {
	OK                    bool     `json:"ok"`
	FileID                string   `json:"file_id"`
	RouteLayerCount       int      `json:"route_layer_count"`
	TotalSegmentsRouted   int      `json:"total_segments_routed"`
	TotalViasPlaced       int      `json:"total_vias_placed"`
	NetCount              int      `json:"net_count"`
	UnroutedNetCount      int      `json:"unrouted_net_count"`
	Warnings              []string `json:"warnings"`
}

func runAutorouteCircuit(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a autorouteCircuitArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	if strings.TrimSpace(a.CircuitFileID) == "" {
		return errPayload("circuit_file_id is required", "BAD_ARGS"), nil
	}
	fileID, err := uuid.Parse(a.CircuitFileID)
	if err != nil {
		return errPayload("circuit_file_id must be a uuid: "+err.Error(), "BAD_ARGS"), nil
	}

	var fname, kind, content string
	err = pc.Pool.QueryRow(ctx,
		`select name, kind, content from files
		 where id = $1 and project_id = $2 and deleted_at is null`,
		fileID, pc.ProjectID).Scan(&fname, &kind, &content)
	if err != nil {
		return errPayload("circuit file not found", "NOT_FOUND"), nil
	}
	if kind != "circuit" {
		return errPayload("file kind "+kind+" is not a .circuit.tsx file", "BAD_ARGS"), nil
	}

	if pc.HTTPClient == nil {
		pc.HTTPClient = &http.Client{Timeout: 30 * time.Second}
	}

	circuitJSON, err := compileCircuitToJSON(ctx, pc, content)
	if err != nil {
		return errPayload("failed to compile circuit: "+err.Error(), "COMPILE_ERROR"), nil
	}

	traceWidth := a.TraceWidthMicrons
	if traceWidth <= 0 {
		traceWidth = 200
	}
	viaDia := a.ViaDiameterMicrons
	if viaDia <= 0 {
		viaDia = 600
	}
	viaDrill := a.ViaDrillMicrons
	if viaDrill <= 0 {
		viaDrill = 300
	}
	clearance := a.ClearanceMicrons
	if clearance <= 0 {
		clearance = 200
	}
	routeLayers := a.RouteLayers
	if strings.TrimSpace(routeLayers) == "" {
		routeLayers = "1top,16bot"
	}

	pyworkerURL := getPyworkerURL() + "/autoroute"
	reqBody := map[string]any{
		"circuit_json":          circuitJSON,
		"trace_width_microns":   traceWidth,
		"via_diameter_microns":  viaDia,
		"via_drill_microns":     viaDrill,
		"route_layers":          routeLayers,
		"clearance_microns":     clearance,
	}
	reqBodyBytes, _ := json.Marshal(reqBody)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, pyworkerURL, strings.NewReader(string(reqBodyBytes)))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := pc.HTTPClient.Do(req)
	if err != nil {
		return errPayload("autoroute worker unavailable: "+err.Error(), "WORKER_ERROR"), nil
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return errPayload(fmt.Sprintf("autoroute worker returned status %d", resp.StatusCode), "WORKER_ERROR"), nil
	}

	var workerResp struct {
		UpdatedCircuit string   `json:"updated_circuit"`
		Warnings       []string `json:"warnings"`
		Segments       int      `json:"segments_routed"`
		Vias           int      `json:"vias_placed"`
		Nets           int      `json:"nets_routed"`
		Unrouted       int      `json:"nets_unrouted"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&workerResp); err != nil {
		return errPayload("failed to decode autoroute response: "+err.Error(), "WORKER_ERROR"), nil
	}

	if _, err := pc.Pool.Exec(ctx,
		`update files set content = $1, updated_at = now()
		 where id = $2 and project_id = $3`,
		workerResp.UpdatedCircuit, fileID, pc.ProjectID); err != nil {
		return "", err
	}
	_ = recordRevisionForFile(ctx, pc, fileID, workerResp.UpdatedCircuit, "tool")

	return okPayload(autorouteCircuitResult{
		OK:                  true,
		FileID:              fileID.String(),
		RouteLayerCount:     len(strings.Split(routeLayers, ",")),
		TotalSegmentsRouted: workerResp.Segments,
		TotalViasPlaced:     workerResp.Vias,
		NetCount:            workerResp.Nets,
		UnroutedNetCount:    workerResp.Unrouted,
		Warnings:            workerResp.Warnings,
	}), nil
}

func getPyworkerURL() string {
	if u := os.Getenv("PYWORKER_URL"); strings.TrimSpace(u) != "" {
		return u
	}
	return "http://localhost:3001"
}

func compileCircuitToJSON(ctx context.Context, pc ProjectCtx, tsxContent string) ([]byte, error) {
	return nil, fmt.Errorf("compileCircuitToJSON not yet implemented — circuitWorker runs in the frontend")
}