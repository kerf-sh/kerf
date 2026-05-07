package tessellate

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/imranp/kerf/backend/internal/config"
)

// NodeSidecarDriver implements Driver by spawning a Node subprocess per
// job. The protocol is JSON-over-stdio:
//
//	→ stdin  : {"step_b64": "<base64 STEP bytes>"}
//	← stdout : {"glb_b64": "<base64 GLB bytes>"} on success
//	← stdout : {"error":   "<message>"}          on parse failure
//
// The script is at scripts/step-tessellate.mjs and depends only on
// occt-import-js (already a project dep) — no extra npm install needed
// when the workspace's node_modules is present in the deploy.
//
// One process per job is intentional: occt-import-js leaks WASM heap
// across runs and the per-spawn cost (~80 ms) is rounding error compared
// to a typical OCCT parse. If startup ever becomes a bottleneck we can
// promote this to a long-lived sidecar with a per-job request id.
type NodeSidecarDriver struct {
	nodeBin string
	script  string
}

// NewNodeSidecarDriver builds a driver from config. Defaults: `node`
// from PATH, `./scripts/step-tessellate.mjs` relative to cwd.
func NewNodeSidecarDriver(cfg *config.Config) *NodeSidecarDriver {
	bin := cfg.StepTessellateNodeBin
	if bin == "" {
		bin = "node"
	}
	script := cfg.StepTessellateScript
	if script == "" {
		// The server is typically launched from the repo root or the
		// install prefix; both layouts have scripts/ alongside the
		// binary's working directory.
		script = filepath.Join("scripts", "step-tessellate.mjs")
	}
	return &NodeSidecarDriver{nodeBin: bin, script: script}
}

// sidecarRequest mirrors the JSON sent on stdin to the script.
type sidecarRequest struct {
	StepB64 string `json:"step_b64"`
}

// sidecarResponse mirrors the JSON received on stdout.
type sidecarResponse struct {
	GlbB64 string `json:"glb_b64,omitempty"`
	Error  string `json:"error,omitempty"`
}

// Tessellate runs the sidecar once and returns the .glb bytes.
func (d *NodeSidecarDriver) Tessellate(ctx context.Context, step []byte) ([]byte, error) {
	if len(step) == 0 {
		return nil, fmt.Errorf("empty step")
	}

	req := sidecarRequest{StepB64: base64.StdEncoding.EncodeToString(step)}
	reqJSON, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("encode request: %w", err)
	}

	cmd := exec.CommandContext(ctx, d.nodeBin, d.script)
	cmd.Stdin = bytes.NewReader(reqJSON)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		// Distinguish "node missing" from "script crashed" so the operator
		// gets a useful error in the jobs table.
		if execErr, ok := err.(*exec.Error); ok && execErr.Err == exec.ErrNotFound {
			return nil, fmt.Errorf("node binary not found: %q (set [limits].step_tessellate_node_bin in kerf.toml)", d.nodeBin)
		}
		stderrTail := tailString(stderr.String(), 800)
		if stderrTail != "" {
			return nil, fmt.Errorf("sidecar exit: %v: %s", err, stderrTail)
		}
		return nil, fmt.Errorf("sidecar exit: %v", err)
	}

	// The script may print log lines before its single JSON response;
	// extract the LAST non-empty line and decode that. Any earlier
	// output is treated as info-level chatter.
	last := lastJSONLine(stdout.Bytes())
	if last == nil {
		return nil, fmt.Errorf("sidecar produced no JSON output (stderr: %s)", tailString(stderr.String(), 400))
	}
	var resp sidecarResponse
	if err := json.Unmarshal(last, &resp); err != nil {
		return nil, fmt.Errorf("decode sidecar response: %w (raw: %s)", err, tailString(string(last), 400))
	}
	if resp.Error != "" {
		return nil, fmt.Errorf("sidecar reported: %s", resp.Error)
	}
	if resp.GlbB64 == "" {
		return nil, fmt.Errorf("sidecar returned no glb")
	}
	glb, err := base64.StdEncoding.DecodeString(resp.GlbB64)
	if err != nil {
		return nil, fmt.Errorf("decode glb_b64: %w", err)
	}
	return glb, nil
}

// lastJSONLine scans `out` for the last line that begins with '{' (after
// trimming whitespace) and returns its bytes (without the newline).
// Returns nil if no such line exists. We don't try to recover from
// embedded newlines inside JSON because the sidecar emits a one-line
// response.
func lastJSONLine(out []byte) []byte {
	lines := bytes.Split(out, []byte("\n"))
	for i := len(lines) - 1; i >= 0; i-- {
		l := bytes.TrimSpace(lines[i])
		if len(l) == 0 {
			continue
		}
		if l[0] == '{' {
			return l
		}
	}
	return nil
}

// tailString returns at most n trailing chars of s, prefixed with "..."
// when truncated. Used to keep error messages bounded so they fit in a
// jobs.error column without dragging in megabytes of stderr.
func tailString(s string, n int) string {
	s = strings.TrimSpace(s)
	if len(s) <= n {
		return s
	}
	return "..." + s[len(s)-n:]
}
