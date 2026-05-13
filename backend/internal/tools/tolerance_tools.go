package tools

import (
	"context"
	"encoding/json"
	"math"
	"math/rand"

	"github.com/google/uuid"

	"github.com/imranp/kerf/backend/internal/llm"
)

type toleranceEntry struct {
	ID     string  `json:"id"`
	Nominal float64 `json:"nominal"`
	Plus   float64 `json:"plus"`
	Minus  float64 `json:"minus"`
	Unit   string  `json:"unit"`
}

type toleranceSet struct {
	ID        string          `json:"id"`
	Name      string          `json:"name"`
	Tolerances []toleranceEntry `json:"tolerances"`
}

type dimensionTolerance struct {
	Nominal float64 `json:"nominal"`
	Plus   float64 `json:"plus"`
	Minus  float64 `json:"minus"`
	Unit   string  `json:"unit"`
}

func (d dimensionTolerance) Upper() float64 { return d.Nominal + d.Plus }
func (d dimensionTolerance) Lower() float64 { return d.Nominal - d.Minus }
func (d dimensionTolerance) HalfSpan() float64 { return (d.Plus + d.Minus) / 2 }

type toleranceStackResult struct {
	Method  string  `json:"method"`
	Nominal float64 `json:"nominal"`
	Max     float64 `json:"max"`
	Min     float64 `json:"min"`
	Band    float64 `json:"band"`
}

type monteCarloResult struct {
	Method     string    `json:"method"`
	Samples    int       `json:"samples"`
	P01        float64   `json:"p01"`
	P50        float64   `json:"p50"`
	P99        float64   `json:"p99"`
	Mean       float64   `json:"mean"`
	StdDev     float64   `json:"std_dev"`
	Histogram  []int     `json:"histogram"`
	BinEdges   []float64 `json:"bin_edges"`
	Nominal    float64   `json:"nominal"`
}

var toleranceStackSpec = llm.ToolSpec{
	Name:        "tolerance_stack",
	Description: "Compute 1D worst-case and RSS tolerance stack-up for a chain of dimensions. Accepts named tolerance sets from a .tolerance file, a list of inline dimension objects, or dimension refs from a .sketch/.feature file. Returns nominal, max, min, and RSS band.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"tolerance_set_id": map[string]any{
				"type":        "string",
				"description": "ID of a tolerance set defined in a .tolerance file (mutually exclusive with dimensions).",
			},
			"file_id": map[string]any{
				"type":        "string",
				"description": "File UUID of the .tolerance file to load the named set from (required when tolerance_set_id is used).",
			},
			"dimensions": map[string]any{
				"type": "array",
				"description": "Inline list of dimensions, each as {nominal, plus, minus} or {nominal, upper, lower} or {nominal, grade}. At least one of tolerance_set_id or dimensions is required.",
				"items": map[string]any{
					"type": "object",
					"properties": map[string]any{
						"nominal":   map[string]any{"type": "number"},
						"plus":      map[string]any{"type": "number"},
						"minus":     map[string]any{"type": "number"},
						"upper":     map[string]any{"type": "number"},
						"lower":     map[string]any{"type": "number"},
						"grade":     map[string]any{"type": "string"},
						"id":        map[string]any{"type": "string"},
						"unit":      map[string]any{"type": "string"},
					},
				},
			},
			"unit": map[string]any{
				"type":        "string",
				"description": "Unit for inline dimensions when not specified per-dimension (mm | cm | inches). Defaults to mm.",
			},
			"rss_k": map[string]any{
				"type":        "number",
				"description": "Multiplier for RSS band. Use 3 for 99.73% (default), 2.45 for 99%, 1.96 for 95%.",
			},
		},
	},
}

type toleranceStackArgs struct {
	ToleranceSetID string                `json:"tolerance_set_id"`
	FileID         string                `json:"file_id"`
	Dimensions     []map[string]any      `json:"dimensions"`
	Unit           string                `json:"unit"`
	RSSK           float64               `json:"rss_k"`
}

func runToleranceStack(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a toleranceStackArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}

	var dims []dimensionTolerance
	var unit string

	if a.ToleranceSetID != "" && a.FileID != "" {
		fid, err := uuid.Parse(a.FileID)
		if err != nil {
			return errPayload("file_id must be a uuid: "+err.Error(), "BAD_ARGS"), nil
		}
		content, err := loadFileContent(ctx, pc, fid)
		if err != nil {
			return errPayload("load tolerance file: "+err.Error(), "ERROR"), nil
		}
		var tset toleranceSet
		if err := json.Unmarshal([]byte(content), &tset); err != nil {
			return errPayload("parse tolerance file: "+err.Error(), "BAD_JSON"), nil
		}
		for _, t := range tset.Tolerances {
			if t.ID == a.ToleranceSetID {
				unit = t.Unit
				if unit == "" {
					unit = "mm"
				}
				dims = append(dims, dimensionTolerance{
					Nominal: t.Nominal,
					Plus:    t.Plus,
					Minus:   t.Minus,
					Unit:    unit,
				})
			}
		}
		if len(dims) == 0 {
			return errPayload("tolerance set '"+a.ToleranceSetID+"' not found", "NOT_FOUND"), nil
		}
	} else if len(a.Dimensions) > 0 {
		unit = a.Unit
		if unit == "" {
			unit = "mm"
		}
		for _, d := range a.Dimensions {
			tol := dimensionTolerance{Unit: unit}
			if u, ok := d["unit"].(string); ok && u != "" {
				tol.Unit = u
			}
			if n, ok := toFloat64(d["nominal"]); ok {
				tol.Nominal = n
			}
			if p, ok := toFloat64(d["plus"]); ok {
				tol.Plus = p
			}
			if m, ok := toFloat64(d["minus"]); ok {
				tol.Minus = m
			}
			if upper, ok := toFloat64(d["upper"]); ok {
				if _, hasPlus := toFloat64(d["plus"]); !hasPlus {
					tol.Plus = upper - tol.Nominal
				}
			}
			if lower, ok := toFloat64(d["lower"]); ok {
				if _, hasMinus := toFloat64(d["minus"]); !hasMinus {
					tol.Minus = tol.Nominal - lower
				}
			}
			if grade, ok := d["grade"].(string); ok {
				gradeTol := gradeToTolerance(grade)
				if _, hasPlus := toFloat64(d["plus"]); !hasPlus {
					if _, hasUpper := toFloat64(d["upper"]); !hasUpper {
						tol.Plus = gradeTol
					}
				}
				if _, hasMinus := toFloat64(d["minus"]); !hasMinus {
					if _, hasLower := toFloat64(d["lower"]); !hasLower {
						tol.Minus = gradeTol
					}
				}
			}
			dims = append(dims, tol)
		}
	} else {
		return errPayload("either tolerance_set_id or dimensions is required", "BAD_ARGS"), nil
	}

	k := a.RSSK
	if k == 0 {
		k = 3
	}

	nominal := 0.0
	var maxVal float64
	var minVal float64
	rssBand := 0.0

	for _, d := range dims {
		nominal += d.Nominal
		maxVal += d.Nominal + d.Plus
		minVal += d.Nominal - d.Minus
		halfSpan := (d.Plus + d.Minus) / 2
		rssBand += halfSpan * halfSpan
	}
	rssBand = k * math.Sqrt(rssBand)

	return okPayload(toleranceStackResult{
		Method:  "worst_case+rss",
		Nominal: nominal,
		Max:     maxVal,
		Min:     minVal,
		Band:    rssBand,
	}), nil
}

var toleranceMonteCarloSpec = llm.ToolSpec{
	Name:        "tolerance_monte_carlo",
	Description: "Run a Monte-Carlo tolerance stack-up simulation (10k samples default). Supports normal, uniform, and triangular distributions per dimension. Returns P01/P50/P99 percentiles, mean, std_dev, and a histogram of the result distribution.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"dimensions": map[string]any{
				"type": "array",
				"description": "List of dimensions with nominal, plus, minus, and distribution (normal|uniform|triangular).",
				"items": map[string]any{
					"type": "object",
					"properties": map[string]any{
						"nominal":      map[string]any{"type": "number"},
						"plus":         map[string]any{"type": "number"},
						"minus":        map[string]any{"type": "number"},
						"distribution": map[string]any{"type": "string", "enum": []string{"normal", "uniform", "triangular"}},
						"unit":         map[string]any{"type": "string"},
					},
					"required": []string{"nominal", "distribution"},
				},
			},
			"samples": map[string]any{
				"type":        "number",
				"description": "Number of Monte-Carlo samples. Default 10000.",
			},
			"unit": map[string]any{
				"type":        "string",
				"description": "Default unit when not specified per-dimension (mm | cm | inches). Defaults to mm.",
			},
		},
		"required": []string{"dimensions"},
	},
}

type toleranceMonteCarloArgs struct {
	Dimensions []map[string]any `json:"dimensions"`
	Samples    int               `json:"samples"`
	Unit       string            `json:"unit"`
}

func runToleranceMonteCarlo(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a toleranceMonteCarloArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}

	if len(a.Dimensions) == 0 {
		return errPayload("at least one dimension is required", "BAD_ARGS"), nil
	}

	samples := a.Samples
	if samples <= 0 {
		samples = 10000
	}
	if samples > 1000000 {
		samples = 1000000
	}

	unit := a.Unit
	if unit == "" {
		unit = "mm"
	}

	type dimSim struct {
		nominal     float64
		halfPlus    float64
		halfMinus   float64
		distribution string
	}
	sims := make([]dimSim, len(a.Dimensions))
	for i, d := range a.Dimensions {
		s := dimSim{distribution: "normal"}
		if n, ok := toFloat64(d["nominal"]); ok {
			s.nominal = n
		}
		if p, ok := toFloat64(d["plus"]); ok {
			s.halfPlus = p / 2
		}
		if m, ok := toFloat64(d["minus"]); ok {
			s.halfMinus = m / 2
		}
		if dist, ok := d["distribution"].(string); ok {
			s.distribution = dist
		}
		sims[i] = s
	}

	rng := rand.New(rand.NewSource(1))
	results := make([]float64, samples)
	sum := 0.0

	for i := 0; i < samples; i++ {
		v := 0.0
		for _, s := range sims {
			v += sampleDimension(rng, s.nominal, s.halfPlus, s.halfMinus, s.distribution)
		}
		results[i] = v
		sum += v
	}

	nominal := 0.0
	for _, s := range sims {
		nominal += s.nominal
	}

	mean := sum / float64(samples)

	var m2 float64
	for _, v := range results {
		d := v - mean
		m2 += d * d
	}
	stdDev := math.Sqrt(m2 / float64(samples))

	percentiles(results, []float64{0.01, 0.50, 0.99})
	p01 := results[int(float64(samples)*0.01)]
	p50 := results[int(float64(samples)*0.50)]
	p99 := results[int(float64(samples)*0.99)]

	hist, edges := histogram(results, 20)

	return okPayload(monteCarloResult{
		Method:    "monte_carlo",
		Samples:   samples,
		P01:       p01,
		P50:       p50,
		P99:       p99,
		Mean:      mean,
		StdDev:    stdDev,
		Histogram: hist,
		BinEdges:  edges,
		Nominal:   nominal,
	}), nil
}

func sampleDimension(rng *rand.Rand, nominal, halfPlus, halfMinus float64, distribution string) float64 {
	switch distribution {
	case "uniform":
		lo := nominal - halfMinus
		hi := nominal + halfPlus
		return lo + rng.Float64()*(hi-lo)
	case "triangular":
		lo := nominal - halfMinus
		hi := nominal + halfPlus
		mode := (lo + hi) / 2
		u := rng.Float64()
		sqrtU := math.Sqrt(u)
		if u < (hi-mode)/(hi-lo) {
			return lo + sqrtU*(mode-lo)
		}
		return hi - sqrtU*(hi-mode)
	default:
		span := halfPlus + halfMinus
		return nominal + (rng.Float64()*2-1)*span
	}
}

func percentiles(arr []float64, qs []float64) {
	for _, q := range qs {
		n := int(float64(len(arr)) * q)
		if n >= len(arr) {
			n = len(arr) - 1
		}
		quickSelect(arr, n)
	}
}

func quickSelect(arr []float64, k int) {
	low := 0
	high := len(arr) - 1
	for low < high {
		pivot := partition(arr, low, high)
		if k == pivot {
			return
		} else if k < pivot {
			high = pivot - 1
		} else {
			low = pivot + 1
		}
	}
}

func partition(arr []float64, low, high int) int {
	pivot := arr[high]
	i := low
	for j := low; j < high; j++ {
		if arr[j] < pivot {
			arr[i], arr[j] = arr[j], arr[i]
			i++
		}
	}
	arr[i], arr[high] = arr[high], arr[i]
	return i
}

func histogram(values []float64, bins int) ([]int, []float64) {
	min := values[0]
	max := values[0]
	for _, v := range values {
		if v < min {
			min = v
		}
		if v > max {
			max = v
		}
	}
	if max == min {
		max = min + 1
	}
	binWidth := (max - min) / float64(bins)
	counts := make([]int, bins)
	for _, v := range values {
		bin := int((v - min) / binWidth)
		if bin >= bins {
			bin = bins - 1
		}
		counts[bin]++
	}
	edges := make([]float64, bins+1)
	for i := 0; i <= bins; i++ {
		edges[i] = min + float64(i)*binWidth
	}
	return counts, edges
}

var gradeIT = map[string]float64{
	"IT01": 0.15, "IT0": 0.25, "IT1": 0.4, "IT2": 0.6, "IT3": 1.0, "IT4": 1.5,
	"IT5": 2.0, "IT6": 3.0, "IT7": 5.0, "IT8": 7.0, "IT9": 12.5, "IT10": 20.0,
	"IT11": 30.0, "IT12": 50.0, "IT13": 70.0, "IT14": 125.0, "IT15": 200.0,
	"IT16": 315.0,
}

func gradeToTolerance(grade string) float64 {
	if t, ok := gradeIT[grade]; ok {
		return t / 1000.0
	}
	return 0
}

func toFloat64(v any) (float64, bool) {
	switch n := v.(type) {
	case float64:
		return n, true
	case float32:
		return float64(n), true
	case int:
		return float64(n), true
	case int64:
		return float64(n), true
	}
	return 0, false
}

func loadFileContent(ctx context.Context, pc ProjectCtx, fid uuid.UUID) (string, error) {
	var content string
	err := pc.Pool.QueryRow(ctx,
		`select content from files where id = $1 and project_id = $2 and deleted_at is null`,
		fid, pc.ProjectID).Scan(&content)
	return content, err
}