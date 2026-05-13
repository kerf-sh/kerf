package scenarios

import (
	"context"
	"strings"

	"github.com/google/uuid"

	"github.com/imranp/kerf/backend/cmd/test/runner"
	"github.com/imranp/kerf/backend/internal/tools"
)

func TopoStudy(s *runner.Suite, env *runner.Env) {
	c := env.Client
	ctx := context.Background()

	owner, status, raw := registerWS(c, "topo-owner@example.com", "topopass99hunter", "Topo Owner")
	if !s.Status("register topo owner", status, 201, raw) {
		return
	}
	if !s.True("topo owner default_workspace present", owner.DefaultWorkspace != nil,
		"expected default_workspace on register response") {
		return
	}

	var proj struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects", map[string]any{
		"workspace_id": owner.DefaultWorkspace.ID,
		"name":         "Topo project",
		"tags":         []string{"topology", "optimization"},
	}, owner.AccessToken, &proj)
	if !s.Status("create topo project", status, 201, raw) {
		return
	}
	pid := proj.ID

	pc := tools.ProjectCtx{
		Pool:      env.Pool,
		ProjectID: uuid.MustParse(pid),
		UserID:    uuid.MustParse(owner.User.ID),
		Role:      "owner",
	}

	createFeature := runTool(s, ctx, pc, "create_feature", map[string]any{
		"path": "/bracket.feature",
		"name": "Bracket design space",
	})
	featID, _ := createFeature["id"].(string)
	if !s.NotEmpty("create_feature returned id", featID) {
		return
	}

	matJSON := `{
  "version": 1,
  "name": "AISI 1018 Steel",
  "category": "metal/steel/carbon",
  "common_names": ["mild steel"],
  "mechanical": { "E_GPa": 205, "G_GPa": 80, "nu": 0.29 },
  "physical": { "rho_kg_m3": 7870 }
}`
	var matRow struct {
		ID   string `json:"id"`
		Kind string `json:"kind"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{
			"name":    "aisi-1018.material",
			"kind":    "material",
			"content": matJSON,
		}, owner.AccessToken, &matRow)
	s.Status("create material file", status, 201, raw)

	topoJSON := `{
  "version": 1,
  "design_space_feature_path": "/bracket.feature",
  "material_path": "/aisi-1018.material",
  "volume_fraction": 0.3,
  "penalization_power": 3,
  "filter_radius_mm": 1.5,
  "max_iterations": 200,
  "convergence_tolerance": 1e-4,
  "results": {
    "status": "pending",
    "iterations": 0,
    "warnings": [],
    "errors": []
  }
}`
	var topoRow struct {
		ID   string `json:"id"`
		Kind string `json:"kind"`
		Name string `json:"name"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{
			"name":    "run-001.topo",
			"kind":    "topo",
			"content": topoJSON,
		}, owner.AccessToken, &topoRow)
	if !s.Status("create topo file", status, 201, raw) {
		return
	}
	s.Equal("topo.kind echoed", topoRow.Kind, "topo")
	s.NotEmpty("topo.id", topoRow.ID)

	var topoGet struct {
		Kind    string `json:"kind"`
		Content string `json:"content"`
	}
	status, raw, _ = c.DoJSON("GET", "/api/projects/"+pid+"/files/"+topoRow.ID, nil,
		owner.AccessToken, &topoGet)
	if s.Status("get topo file", status, 200, raw) {
		s.Equal("topo.kind round-trip", topoGet.Kind, "topo")
		s.Equal("topo.content round-trip byte-identical", topoGet.Content, topoJSON)
	}

	topoRunOut := runTool(s, ctx, pc, "topo_run", map[string]any{
		"topo_path": "/run-001.topo",
	})
	outStatus, _ := topoRunOut["status"].(string)
	s.Equal("topo_run engine pending status", outStatus, "pending")

	warning, _ := topoRunOut["warning"].(string)
	s.Equal("topo_run engine pending warning", warning, "Engine pending — FEniCSx not yet deployed.")

	badTopo := runTool(s, ctx, pc, "topo_run", map[string]any{
		"topo_path": "/does-not-exist.topo",
	})
	s.Equal("topo_run missing file → NOT_FOUND", badTopo["code"], "NOT_FOUND")

	badKind := runTool(s, ctx, pc, "topo_run", map[string]any{
		"topo_path": "/aisi-1018.material",
	})
	s.Equal("topo_run wrong kind → BAD_KIND", badKind["code"], "BAD_KIND")

	topoMissingDS := `{
  "version": 1,
  "design_space_feature_path": "",
  "material_path": "/aisi-1018.material",
  "volume_fraction": 0.3,
  "penalization_power": 3,
  "filter_radius_mm": 1.5,
  "max_iterations": 200,
  "convergence_tolerance": 1e-4,
  "results": { "status": "pending", "warnings": [], "errors": [] }
}`
	var badDSRow struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{
			"name":    "bad-design.topo",
			"kind":    "topo",
			"content": topoMissingDS,
		}, owner.AccessToken, &badDSRow)
	s.Status("create bad-ds topo file", status, 201, raw)

	badRun := runTool(s, ctx, pc, "topo_run", map[string]any{
		"topo_path": "/bad-design.topo",
	})
	s.Equal("topo_run missing design_space_feature_path → BAD_TOPO", badRun["code"], "BAD_TOPO")

	badVF := strings.Replace(topoJSON, `"volume_fraction": 0.3`, `"volume_fraction": 1.5`, 1)
	var badVFRow struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{
			"name":    "bad-vf.topo",
			"kind":    "topo",
			"content": badVF,
		}, owner.AccessToken, &badVFRow)
	s.Status("create bad-vf topo file", status, 201, raw)

	badVFRun := runTool(s, ctx, pc, "topo_run", map[string]any{
		"topo_path": "/bad-vf.topo",
	})
	s.Equal("topo_run invalid volume_fraction → BAD_TOPO", badVFRun["code"], "BAD_TOPO")
}