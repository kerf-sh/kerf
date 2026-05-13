package scenarios

import (
	"context"

	"github.com/google/uuid"

	"github.com/imranp/kerf/backend/cmd/test/runner"
	"github.com/imranp/kerf/backend/internal/tools"
)

func ToleranceStackup(s *runner.Suite, env *runner.Env) {
	c := env.Client
	ctx := context.Background()

	owner, status, raw := register(c, "tol-owner@example.com", "tolpass1", "Tolerance Owner")
	if !s.Status("register tolerance owner", status, 201, raw) {
		return
	}
	var proj struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects",
		map[string]string{"name": "Tolerance Stack-up Project", "workspace_id": owner.DefaultWorkspace.ID}, owner.AccessToken, &proj)
	if !s.Status("create tolerance project", status, 201, raw) {
		return
	}
	pid := proj.ID
	pc := tools.ProjectCtx{
		Pool:      env.Pool,
		ProjectID: uuid.MustParse(pid),
		UserID:    uuid.MustParse(owner.User.ID),
		Role:      "owner",
	}

	_ = ctx

	// --- tolerance_stack: inline dimensions (worst-case + RSS) ---
	tolResult := runTool(s, ctx, pc, "tolerance_stack", map[string]any{
		"dimensions": []map[string]any{
			{"nominal": 10.0, "plus": 0.1, "minus": 0.1},
			{"nominal": 5.0, "plus": 0.05, "minus": 0.05},
			{"nominal": 2.0, "plus": 0.02, "minus": 0.02},
		},
		"rss_k": 3.0,
		"unit":  "mm",
	})
	s.NotEmpty("tolerance_stack result", tolResult["method"].(string))
	s.Equal("tolerance_stack method", tolResult["method"], "worst_case+rss")
	nominal, _ := tolResult["nominal"].(float64)
	s.True("tolerance_stack nominal", abs(nominal-17.0) <= 0.001, "expected ~17.0, got %v", nominal)
	max, _ := tolResult["max"].(float64)
	s.True("tolerance_stack max", abs(max-17.17) <= 0.01, "expected ~17.17, got %v", max)
	min, _ := tolResult["min"].(float64)
	s.True("tolerance_stack min", abs(min-16.83) <= 0.01, "expected ~16.83, got %v", min)

	// --- tolerance_stack: IT grade ---
	gradeResult := runTool(s, ctx, pc, "tolerance_stack", map[string]any{
		"dimensions": []map[string]any{
			{"nominal": 25.0, "grade": "IT8"},
			{"nominal": 10.0, "grade": "IT7"},
		},
		"unit": "mm",
	})
	s.Equal("grade stack method", gradeResult["method"], "worst_case+rss")
	gradeNom, _ := gradeResult["nominal"].(float64)
	s.True("grade stack nominal", abs(gradeNom-35.0) <= 0.001, "expected ~35.0, got %v", gradeNom)

	// --- tolerance_stack: upper/lower form ---
	ulResult := runTool(s, ctx, pc, "tolerance_stack", map[string]any{
		"dimensions": []map[string]any{
			{"nominal": 10.0, "upper": 10.1, "lower": 9.9},
			{"nominal": 5.0, "upper": 5.05, "lower": 4.95},
		},
	})
	ulNom, _ := ulResult["nominal"].(float64)
	s.True("upper/lower nominal", abs(ulNom-15.0) <= 0.001, "expected ~15.0, got %v", ulNom)

	// --- tolerance_stack: requires dimensions or set_id ---
	emptyResult := runTool(s, ctx, pc, "tolerance_stack", map[string]any{})
	s.Equal("empty stack code", emptyResult["code"], "BAD_ARGS")

	// --- tolerance_monte_carlo: basic ---
	mcResult := runTool(s, ctx, pc, "tolerance_monte_carlo", map[string]any{
		"dimensions": []map[string]any{
			{"nominal": 10.0, "plus": 0.1, "minus": 0.1, "distribution": "normal"},
			{"nominal": 5.0, "plus": 0.05, "minus": 0.05, "distribution": "uniform"},
		},
		"samples": 5000,
		"unit":    "mm",
	})
	s.Equal("monte_carlo method", mcResult["method"], "monte_carlo")
	s.Equal("monte_carlo samples", mcResult["samples"], 5000)
	mcP50, _ := mcResult["p50"].(float64)
	s.True("monte_carlo p50", abs(mcP50-15.0) <= 0.5, "expected ~15.0, got %v", mcP50)
	mcHist, _ := mcResult["histogram"].([]any)
	s.True("monte_carlo histogram has bins", len(mcHist) > 0, "histogram is empty")

	// --- tolerance_monte_carlo: requires at least one dimension ---
	mcEmpty := runTool(s, ctx, pc, "tolerance_monte_carlo", map[string]any{
		"dimensions": []map[string]any{},
	})
	s.Equal("mc empty code", mcEmpty["code"], "BAD_ARGS")

	// --- tolerance_monte_carlo: default samples cap ---
	mcLarge := runTool(s, ctx, pc, "tolerance_monte_carlo", map[string]any{
		"dimensions": []map[string]any{
			{"nominal": 10.0, "distribution": "normal"},
		},
		"samples": 99999999,
	})
	s.Equal("mc cap method", mcLarge["method"], "monte_carlo")
}

func abs(x float64) float64 {
	if x < 0 {
		return -x
	}
	return x
}
