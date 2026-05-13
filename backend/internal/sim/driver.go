package sim

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/imranp/kerf/backend/internal/config"
)

const pyworkerAddr = "http://localhost:8090"

type InputSpec struct {
	Type  string `json:"type"`
	Tstep string `json:"tstep,omitempty"`
	Tstop string `json:"tstop,omitempty"`
	Vstart float64 `json:"vstart,omitempty"`
	Vstop  float64 `json:"vstop,omitempty"`
	Vstep  float64 `json:"vstep,omitempty"`
	Fstart float64 `json:"fstart,omitempty"`
	Fstop  float64 `json:"fstop,omitempty"`
	Points int     `json:"points,omitempty"`
}

type Waveform struct {
	Name string   `json:"name"`
	Kind string   `json:"kind"`
	XUnit string  `json:"xUnit"`
	YUnit string  `json:"yUnit"`
	X     []float64 `json:"x"`
	Y     []float64 `json:"y"`
}

type Result struct {
	Waveforms []Waveform `json:"waveforms"`
	Warnings  []string   `json:"warnings"`
	Errors    []string   `json:"errors"`
}

type driverRequest struct {
	Netlist  string     `json:"netlist"`
	Analysis InputSpec  `json:"analysis"`
}

type Driver struct {
	addr       string
	timeout    time.Duration
	httpClient *http.Client
}

func NewDriver(cfg *config.Config) *Driver {
	timeout := time.Duration(cfg.SIMTimeoutSec) * time.Second
	if timeout <= 0 {
		timeout = 5 * time.Minute
	}
	return &Driver{
		addr:    pyworkerAddr,
		timeout: timeout,
		httpClient: &http.Client{Timeout: timeout + 30*time.Second},
	}
}

func (d *Driver) RunSpice(ctx context.Context, netlist string, spec InputSpec) (*Result, error) {
	if netlist == "" {
		return nil, fmt.Errorf("empty netlist")
	}

	req := driverRequest{
		Netlist:  netlist,
		Analysis: spec,
	}
	reqJSON, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("encode request: %w", err)
	}

	ctx, cancel := context.WithTimeout(ctx, d.timeout+30*time.Second)
	defer cancel()

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, d.addr+"/run-spice", bytes.NewReader(reqJSON))
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

	var result Result
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("decode response: %w", err)
	}

	return &result, nil
}
