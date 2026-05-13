package fem

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/imranp/kerf/backend/internal/config"
)

const pyworkerAddr = "http://localhost:8090"

type InputSpec struct {
	MaterialProps    map[string]float64 `json:"material_props"`
	BoundaryConditions []BC             `json:"boundary_conditions"`
	Loads             []Load            `json:"loads"`
	MeshSize          float64           `json:"mesh_size"`
	Solver            string            `json:"solver"`          // "fenicsx" | "calculix"
	AnalysisType      string            `json:"analysis_type"`  // "linear_static" | "modal" | "thermal"
}

type BC struct {
	Type     string  `json:"type"` // "fixed" | "displacement"
	FaceTags []int   `json:"face_tags"`
	UX       float64 `json:"ux"`
	UY       float64 `json:"uy"`
	UZ       float64 `json:"uz"`
}

type Load struct {
	Type     string  `json:"type"` // "pressure" | "force"
	FaceTags []int   `json:"face_tags"`
	Value    float64 `json:"value"`
}

type Result struct {
	MaxVonMisesStress float64           `json:"max_vonmises_stress"`
	MaxDisplacement   float64           `json:"max_displacement"`
	Displacement      map[string]float64 `json:"displacement"`
	FoS               float64           `json:"fos"`
	Frequencies       []float64         `json:"frequencies"`
	ModeShapes        [][]float64       `json:"mode_shapes"`
	Temperatures      []float64         `json:"temperatures"`
	Warnings          []string          `json:"warnings"`
	Errors            []string          `json:"errors"`
}

type driverRequest struct {
	StepB64   string     `json:"step_b64"`
	InputSpec InputSpec  `json:"input_spec"`
}

type driverResponse struct {
	ResultB64 string `json:"result_b64,omitempty"`
	Error     string `json:"error,omitempty"`
}

type Driver struct {
	addr    string
	timeout time.Duration
	httpClient *http.Client
}

func NewDriver(cfg *config.Config) *Driver {
	timeout := time.Duration(cfg.FEMTimeoutSec) * time.Second
	if timeout <= 0 {
		timeout = 5 * time.Minute
	}
	return &Driver{
		addr:    pyworkerAddr,
		timeout: timeout,
		httpClient: &http.Client{Timeout: timeout + 30*time.Second},
	}
}

func (d *Driver) RunFEM(ctx context.Context, step []byte, spec InputSpec) (*Result, error) {
	if len(step) == 0 {
		return nil, fmt.Errorf("empty step")
	}

	req := driverRequest{
		StepB64:   base64.StdEncoding.EncodeToString(step),
		InputSpec: spec,
	}
	reqJSON, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("encode request: %w", err)
	}

	ctx, cancel := context.WithTimeout(ctx, d.timeout+30*time.Second)
	defer cancel()

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, d.addr+"/run-fem", bytes.NewReader(reqJSON))
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := d.httpClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("pyworker request: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err != nil {
		return nil, fmt.Errorf("read response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("pyworker status %d: %s", resp.StatusCode, string(body))
	}

	var dr driverResponse
	if err := json.Unmarshal(body, &dr); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}
	if dr.Error != "" {
		return nil, fmt.Errorf("pyworker error: %s", dr.Error)
	}
	if dr.ResultB64 == "" {
		return nil, fmt.Errorf("pyworker returned no result")
	}

	resultBytes, err := base64.StdEncoding.DecodeString(dr.ResultB64)
	if err != nil {
		return nil, fmt.Errorf("decode result_b64: %w", err)
	}

	var result Result
	if err := json.Unmarshal(resultBytes, &result); err != nil {
		return nil, fmt.Errorf("decode result JSON: %w", err)
	}

	return &result, nil
}