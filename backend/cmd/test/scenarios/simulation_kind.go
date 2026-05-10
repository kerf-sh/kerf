package scenarios

// SimulationKind scenario — exercises the `.simulation` file kind end-to-end:
//   - kind='simulation' is accepted by POST /files (added in
//     1746577900000_kind_simulation migration + the handlers.CreateFile
//     validator).
//   - kind='not_a_real_kind' is rejected at the handler validator with a 400.
//   - GET round-trips kind + JSON content byte-identical.
//
// The simulation file is a permissive JSON envelope written by the (still
// deferred) ngspice-wasm engine. Today the kind is just a shape gate so
// runs are queryable, restorable via file_revisions, and shareable on
// Workshop. Editor view + LLM tool + engine all live in separate slices.
// Mirrors materials.go for register/setup conventions.

import (
	"github.com/imranp/kerf/backend/cmd/test/runner"
)

// SimulationKind drives the .simulation file kind. Registered in main.go's
// allScenarios.
func SimulationKind(s *runner.Suite, env *runner.Env) {
	c := env.Client

	owner, status, raw := registerWS(c, "sim-owner@example.com", "simpass99hunter", "Sim Owner")
	if !s.Status("register sim owner", status, 201, raw) {
		return
	}
	if !s.True("sim owner default_workspace present", owner.DefaultWorkspace != nil,
		"expected default_workspace on register response") {
		return
	}

	// Holding project.
	var proj struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects", map[string]any{
		"workspace_id": owner.DefaultWorkspace.ID,
		"name":         "Simulation project",
		"tags":         []string{"electronics"},
	}, owner.AccessToken, &proj)
	if !s.Status("create simulation project", status, 201, raw) {
		return
	}
	pid := proj.ID

	// --- 1. kind validator: 'simulation' is accepted ---------------------
	// Pretend the engine wrote this — the shape is intentionally
	// permissive (TBD as the engine lands). The circuit_file_id is a
	// throw-away UUID; nothing dereferences it server-side today.
	simJSON := `{"version":1,"circuit_file_id":"00000000-0000-0000-0000-000000000000","analysis":{"type":"transient","tstep":"1us","tstop":"10ms"},"probes":[],"results":{"waveforms":[],"warnings":[],"errors":[]}}`
	var simRow struct {
		ID   string `json:"id"`
		Kind string `json:"kind"`
		Name string `json:"name"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{
			"name":      "run-001.simulation",
			"kind":      "simulation",
			"parent_id": nil,
			"content":   simJSON,
		}, owner.AccessToken, &simRow)
	if !s.Status("create simulation file", status, 201, raw) {
		return
	}
	s.Equal("simulation.kind echoed", simRow.Kind, "simulation")
	s.Equal("simulation.name echoed", simRow.Name, "run-001.simulation")
	s.NotEmpty("simulation.id", simRow.ID)

	// --- 2. GET round-trips kind + content byte-identical ----------------
	var simGet struct {
		Kind    string `json:"kind"`
		Content string `json:"content"`
	}
	status, raw, _ = c.DoJSON("GET", "/api/projects/"+pid+"/files/"+simRow.ID, nil,
		owner.AccessToken, &simGet)
	if s.Status("get simulation file", status, 200, raw) {
		s.Equal("simulation.kind round-trip", simGet.Kind, "simulation")
		s.Equal("simulation.content round-trip byte-identical", simGet.Content, simJSON)
	}

	// --- 3. kind validator rejects an unknown kind ----------------------
	// The handler's createFileReq validator lists allowed kinds and
	// surfaces the rejection as 400 (NOT a DB integrity-violation 500).
	// If a future refactor moves the gate to the DB the constraint check
	// would also reject — but the contract stays "do NOT silently
	// succeed".
	var badRow struct {
		ID   string `json:"id"`
		Kind string `json:"kind"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{
			"name":      "wat.junk",
			"kind":      "not_a_real_kind",
			"parent_id": nil,
			"content":   "",
		}, owner.AccessToken, &badRow)
	s.Equal("invalid kind rejected with 400", status, 400)
	s.True("invalid kind did NOT silently succeed (no id assigned)",
		badRow.ID == "", "got id=%q", badRow.ID)
}
