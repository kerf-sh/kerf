package scenarios

// Cross-project parts (PCB-as-part) scenario.
//
// Proves the end-to-end shape:
//   - User A registers, creates an electronics project with a basic
//     `.circuit.tsx` file.
//   - Same user creates a SECOND mechanical project under the same
//     workspace, an assembly file, and adds a Component with an
//     external_ref pointing at the circuit file via the
//     `assembly_add_external_component` LLM tool.
//   - GET on the assembly round-trips the external_ref shape verbatim.
//   - User B (different workspace, no membership on user A's projects)
//     can't read the assembly's source project at all (404 by design —
//     leaks no project existence). The cross-project ref is moot to B.
//   - The tool itself rejects an external_ref that B can't reach with a
//     FORBIDDEN code, even when B happens to know the assembly's id.

import (
	"context"
	"encoding/json"
	"strings"

	"github.com/google/uuid"

	"github.com/imranp/kerf/backend/cmd/test/runner"
	"github.com/imranp/kerf/backend/internal/tools"
)

// CrossProjectParts is registered in main.go's allScenarios.
func CrossProjectParts(s *runner.Suite, env *runner.Env) {
	c := env.Client
	ctx := context.Background()

	// --- 1. User A registers and gets a default workspace. ---
	alice, status, raw := registerWS(c, "cross-alice@example.com", "alicepass99hunter", "Cross Alice")
	if !s.Status("register alice", status, 201, raw) {
		return
	}
	if !s.True("alice default_workspace present", alice.DefaultWorkspace != nil,
		"expected default_workspace on register response") {
		return
	}

	// --- 2. Alice creates an ELECTRONICS project + a circuit file. ---
	type proj struct {
		ID string `json:"id"`
	}
	var elecProj proj
	status, raw, _ = c.DoJSON("POST", "/api/projects", map[string]any{
		"workspace_id": alice.DefaultWorkspace.ID,
		"name":         "Cross Project — PCB",
		"tags":         []string{"electronics", "pcb"},
		"starter":      "circuit",
	}, alice.AccessToken, &elecProj)
	if !s.Status("create electronics project", status, 201, raw) {
		return
	}
	elecPid := elecProj.ID

	// Minimal `.circuit.tsx` source. The body doesn't have to compile
	// successfully here — the backend stores it verbatim, and the
	// assembly_add_external_component tool only checks that the FILE
	// exists and the caller can read its workspace.
	circuitSrc := `import { Circuit } from "tscircuit"

export default (
  <board width="40mm" height="30mm">
    <resistor name="R1" resistance="1k" footprint="0402" pcbX="0" pcbY="0" />
  </board>
)
`
	var circuitRow struct {
		ID   string `json:"id"`
		Kind string `json:"kind"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+elecPid+"/files",
		map[string]any{
			"name":      "main.circuit.tsx",
			"kind":      "circuit",
			"parent_id": nil,
			"content":   circuitSrc,
		}, alice.AccessToken, &circuitRow)
	if !s.Status("create circuit file", status, 201, raw) {
		return
	}
	s.Equal("circuit.kind", circuitRow.Kind, "circuit")

	// --- 3. Alice creates a MECHANICAL project + an empty assembly file. ---
	var mechProj proj
	status, raw, _ = c.DoJSON("POST", "/api/projects", map[string]any{
		"workspace_id": alice.DefaultWorkspace.ID,
		"name":         "Cross Project — Enclosure",
		"tags":         []string{"mechanical"},
		"starter":      "jscad",
	}, alice.AccessToken, &mechProj)
	if !s.Status("create mechanical project", status, 201, raw) {
		return
	}
	mechPid := mechProj.ID

	var asmRow struct {
		ID   string `json:"id"`
		Kind string `json:"kind"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+mechPid+"/files",
		map[string]any{
			"name":      "main.assembly",
			"kind":      "assembly",
			"parent_id": nil,
			"content":   `{"components": []}`,
		}, alice.AccessToken, &asmRow)
	if !s.Status("create assembly", status, 201, raw) {
		return
	}
	s.Equal("assembly.kind", asmRow.Kind, "assembly")

	pcAlice := tools.ProjectCtx{
		Pool:      env.Pool,
		ProjectID: uuid.MustParse(mechPid),
		UserID:    uuid.MustParse(alice.User.ID),
		Role:      "owner",
	}

	// --- 4. assembly_add_external_component splices a cross-project ref. ---
	addOut := runTool(s, ctx, pcAlice, "assembly_add_external_component", map[string]any{
		"assembly_file_id":    asmRow.ID,
		"external_project_id": elecPid,
		"external_file_id":    circuitRow.ID,
		"kind":                "board_3d",
		"pin":                 "tracking_latest",
		"component_id":        "main-pcb",
	})
	if _, isErr := addOut["code"]; isErr {
		s.Fail("assembly_add_external_component",
			"expected success, got code="+asString(addOut["code"])+
				" error="+asString(addOut["error"]))
		return
	}
	s.Equal("add returned component_id", addOut["component_id"], "main-pcb")
	s.Equal("add echoed kind", addOut["kind"], "board_3d")
	s.Equal("add echoed pin", addOut["pin"], "tracking_latest")

	// --- 5. GET on the assembly round-trips the external_ref shape. ---
	var asmGet struct {
		Content string `json:"content"`
	}
	status, raw, _ = c.DoJSON("GET", "/api/projects/"+mechPid+"/files/"+asmRow.ID, nil,
		alice.AccessToken, &asmGet)
	if s.Status("get assembly after external ref", status, 200, raw) {
		s.Contains("assembly carries external_ref key", asmGet.Content, `"external_ref"`)
		s.Contains("assembly carries source project_id", asmGet.Content, elecPid)
		s.Contains("assembly carries source file_id", asmGet.Content, circuitRow.ID)
		s.Contains("assembly carries kind=board_3d", asmGet.Content, `"board_3d"`)
		s.Contains("assembly carries pin=tracking_latest", asmGet.Content, `"tracking_latest"`)
		s.Contains("assembly carries component id", asmGet.Content, `"main-pcb"`)
		// Round-trip via parse → re-marshal to confirm shape stability.
		var doc map[string]any
		if err := json.Unmarshal([]byte(asmGet.Content), &doc); s.NoError("parse assembly content", err) {
			comps, _ := doc["components"].([]any)
			s.Equal("assembly has 1 component", len(comps), 1)
			if len(comps) == 1 {
				entry, _ := comps[0].(map[string]any)
				ext, _ := entry["external_ref"].(map[string]any)
				s.Equal("ext.project_id", asString(ext["project_id"]), elecPid)
				s.Equal("ext.file_id", asString(ext["file_id"]), circuitRow.ID)
				s.Equal("ext.kind", asString(ext["kind"]), "board_3d")
				s.Equal("ext.pin", asString(ext["pin"]), "tracking_latest")
			}
		}
	}

	// --- 6. Bad ref: nonexistent file id → NOT_FOUND (not a 500). ---
	bogusOut := runTool(s, ctx, pcAlice, "assembly_add_external_component", map[string]any{
		"assembly_file_id":    asmRow.ID,
		"external_project_id": elecPid,
		"external_file_id":    uuid.New().String(),
		"kind":                "board_3d",
	})
	s.Equal("bogus file ref → NOT_FOUND", bogusOut["code"], "NOT_FOUND")

	// --- 7. Bad kind → BAD_ARGS. ---
	badKindOut := runTool(s, ctx, pcAlice, "assembly_add_external_component", map[string]any{
		"assembly_file_id":    asmRow.ID,
		"external_project_id": elecPid,
		"external_file_id":    circuitRow.ID,
		"kind":                "rocket-fuel",
	})
	s.Equal("bad kind → BAD_ARGS", badKindOut["code"], "BAD_ARGS")

	// --- 8. User B in a different workspace can't reach Alice's projects. ---
	bob, status, raw := registerWS(c, "cross-bob@example.com", "bobpass99hunter", "Cross Bob")
	if !s.Status("register bob", status, 201, raw) {
		return
	}

	// Bob CAN'T read Alice's electronics project at all (404 by design —
	// projects don't leak existence to non-members).
	status, raw, _ = c.Do("GET", "/api/projects/"+elecPid+"/files/"+circuitRow.ID, nil,
		bob.AccessToken)
	s.True("bob can't read alice's circuit",
		status == 404 || status == 403,
		"expected 403/404, got %d body=%s", status, string(raw))

	// Bob also can't read Alice's mechanical assembly — but if he COULD
	// somehow read it (e.g. the assembly were public), the resolver would
	// see external_ref and resolve geometry-empty rather than 500. We assert
	// the simpler invariant here: GET stays opaque.
	status, raw, _ = c.Do("GET", "/api/projects/"+mechPid+"/files/"+asmRow.ID, nil,
		bob.AccessToken)
	s.True("bob can't read alice's assembly",
		status == 404 || status == 403,
		"expected 403/404, got %d body=%s", status, string(raw))

	// --- 9. Bob's own assembly_add_external_component invocation against
	// Alice's circuit gets a FORBIDDEN code (Bob is not a member of Alice's
	// workspace). We pretend Bob has an assembly in his OWN project to
	// run the tool against. ---
	if !s.True("bob default_workspace present", bob.DefaultWorkspace != nil,
		"expected default_workspace on register response") {
		return
	}
	var bobProj proj
	status, raw, _ = c.DoJSON("POST", "/api/projects", map[string]any{
		"workspace_id": bob.DefaultWorkspace.ID,
		"name":         "Bob's project",
	}, bob.AccessToken, &bobProj)
	if !s.Status("bob creates project", status, 201, raw) {
		return
	}
	var bobAsm struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+bobProj.ID+"/files",
		map[string]any{
			"name":      "bob.assembly",
			"kind":      "assembly",
			"parent_id": nil,
			"content":   `{"components": []}`,
		}, bob.AccessToken, &bobAsm)
	if !s.Status("bob creates assembly", status, 201, raw) {
		return
	}
	pcBob := tools.ProjectCtx{
		Pool:      env.Pool,
		ProjectID: uuid.MustParse(bobProj.ID),
		UserID:    uuid.MustParse(bob.User.ID),
		Role:      "owner",
	}
	bobOut := runTool(s, ctx, pcBob, "assembly_add_external_component", map[string]any{
		"assembly_file_id":    bobAsm.ID,
		"external_project_id": elecPid,
		"external_file_id":    circuitRow.ID,
		"kind":                "board_3d",
	})
	s.Equal("bob's cross-project add → FORBIDDEN", bobOut["code"], "FORBIDDEN")

	// Sanity: bob's assembly was NOT mutated.
	var bobAsmAfter struct {
		Content string `json:"content"`
	}
	status, raw, _ = c.DoJSON("GET", "/api/projects/"+bobProj.ID+"/files/"+bobAsm.ID, nil,
		bob.AccessToken, &bobAsmAfter)
	if s.Status("get bob's assembly after rejected add", status, 200, raw) {
		s.True("bob's assembly stayed empty",
			!strings.Contains(bobAsmAfter.Content, "external_ref"),
			"expected no external_ref in bob's assembly, got %s", bobAsmAfter.Content)
	}
}
