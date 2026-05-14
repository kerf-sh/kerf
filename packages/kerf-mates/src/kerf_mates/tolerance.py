import json
import math
import random
from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx


IT_GRADE_TOLERANCES = {
    "IT01": 0.15,
    "IT0": 0.25,
    "IT1": 0.4,
    "IT2": 0.6,
    "IT3": 1.0,
    "IT4": 1.5,
    "IT5": 2.0,
    "IT6": 3.0,
    "IT7": 5.0,
    "IT8": 7.0,
    "IT9": 12.5,
    "IT10": 20.0,
    "IT11": 30.0,
    "IT12": 50.0,
    "IT13": 70.0,
    "IT14": 125.0,
    "IT15": 200.0,
    "IT16": 315.0,
}


def grade_to_tolerance(grade: str) -> float:
    if grade in IT_GRADE_TOLERANCES:
        return IT_GRADE_TOLERANCES[grade] / 1000.0
    return 0.0


def compute_histogram(data: list[float], bins: int = 20) -> tuple[list[dict], list[float]]:
    if not data:
        return [], []

    min_val = min(data)
    max_val = max(data)

    if max_val == min_val:
        max_val = min_val + 1

    bin_width = (max_val - min_val) / bins
    counts = [0] * bins
    edges = [min_val + i * bin_width for i in range(bins + 1)]

    for v in data:
        bin_idx = int((v - min_val) / bin_width)
        if bin_idx >= bins:
            bin_idx = bins - 1
        counts[bin_idx] += 1

    histogram = []
    for i in range(bins):
        histogram.append({
            "bin_start": edges[i],
            "bin_end": edges[i + 1],
            "count": counts[i],
        })

    return histogram, edges


tolerance_stack_spec = ToolSpec(
    name="tolerance_stack",
    description="Compute 1D worst-case and RSS tolerance stack-up for a chain of dimensions.",
    input_schema={
        "type": "object",
        "properties": {
            "tolerance_set_id": {"type": "string"},
            "file_id": {"type": "string"},
            "dimensions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "nominal": {"type": "number"},
                        "plus": {"type": "number"},
                        "minus": {"type": "number"},
                        "upper": {"type": "number"},
                        "lower": {"type": "number"},
                        "grade": {"type": "string"},
                        "id": {"type": "string"},
                        "unit": {"type": "string"},
                    },
                },
            },
            "unit": {"type": "string"},
            "rss_k": {"type": "number"},
        },
    },
)


@register(tolerance_stack_spec)
async def run_tolerance_stack(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    tolerance_set_id = a.get("tolerance_set_id", "")
    file_id = a.get("file_id", "")
    dimensions = a.get("dimensions", [])
    unit = a.get("unit", "mm")
    rss_k = a.get("rss_k", 3)

    if not tolerance_set_id and not dimensions:
        return err_payload("either tolerance_set_id or dimensions is required", "BAD_ARGS")

    if rss_k <= 0:
        rss_k = 3

    dims = []
    if tolerance_set_id and file_id:
        pass
    elif dimensions:
        for d in dimensions:
            nominal = d.get("nominal", 0)
            plus = d.get("plus", 0)
            minus = d.get("minus", 0)

            if "upper" in d and "plus" not in d:
                plus = d["upper"] - nominal
            if "lower" in d and "minus" not in d:
                minus = nominal - d["lower"]

            grade = d.get("grade", "")
            if grade:
                grade_tol = grade_to_tolerance(grade)
                if "plus" not in d and "upper" not in d:
                    plus = grade_tol
                if "minus" not in d and "lower" not in d:
                    minus = grade_tol

            dims.append({"nominal": nominal, "plus": plus, "minus": minus, "unit": d.get("unit", unit)})

    nominal = sum(d["nominal"] for d in dims)
    max_val = sum(d["nominal"] + d["plus"] for d in dims)
    min_val = sum(d["nominal"] - d["minus"] for d in dims)

    rss_band = 0.0
    for d in dims:
        half_span = (d["plus"] + d["minus"]) / 2
        rss_band += half_span * half_span
    rss_band = rss_k * math.sqrt(rss_band)

    return ok_payload({
        "method": "worst_case+rss",
        "nominal": nominal,
        "max": max_val,
        "min": min_val,
        "band": rss_band,
    })


tolerance_monte_carlo_spec = ToolSpec(
    name="tolerance_monte_carlo",
    description="Run a Monte-Carlo tolerance stack-up simulation (10k samples default).",
    input_schema={
        "type": "object",
        "properties": {
            "dimensions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "nominal": {"type": "number"},
                        "plus": {"type": "number"},
                        "minus": {"type": "number"},
                        "distribution": {"type": "string", "enum": ["normal", "uniform", "triangular"]},
                        "unit": {"type": "string"},
                    },
                    "required": ["nominal", "distribution"],
                },
            },
            "samples": {"type": "integer"},
            "unit": {"type": "string"},
        },
        "required": ["dimensions"],
    },
)


def sample_dimension(rng: random.Random, nominal: float, half_plus: float, half_minus: float, distribution: str) -> float:
    if distribution == "uniform":
        lo = nominal - half_minus
        hi = nominal + half_plus
        return lo + rng.random() * (hi - lo)
    elif distribution == "triangular":
        lo = nominal - half_minus
        hi = nominal + half_plus
        mode = (lo + hi) / 2
        u = rng.random()
        sqrt_u = math.sqrt(u)
        if u < (hi - mode) / (hi - lo):
            return lo + sqrt_u * (mode - lo)
        else:
            return hi - sqrt_u * (hi - mode)
    else:
        span = half_plus + half_minus
        return nominal + (rng.random() * 2 - 1) * span


@register(tolerance_monte_carlo_spec)
async def run_tolerance_monte_carlo(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    dimensions = a.get("dimensions", [])
    samples = a.get("samples", 10000)
    unit = a.get("unit", "mm")

    if not dimensions:
        return err_payload("at least one dimension is required", "BAD_ARGS")

    if samples <= 0:
        samples = 10000
    if samples > 1000000:
        samples = 1000000

    rng = random.Random(1)
    results = []

    for _ in range(samples):
        v = 0.0
        for d in dimensions:
            nominal = d.get("nominal", 0)
            half_plus = d.get("plus", 0) / 2
            half_minus = d.get("minus", 0) / 2
            dist = d.get("distribution", "normal")
            v += sample_dimension(rng, nominal, half_plus, half_minus, dist)
        results.append(v)

    mean = sum(results) / len(results)
    m2 = sum((v - mean) ** 2 for v in results)
    std_dev = math.sqrt(m2 / len(results))

    results_sorted = sorted(results)
    p01 = results_sorted[int(len(results) * 0.01)]
    p50 = results_sorted[int(len(results) * 0.50)]
    p99 = results_sorted[int(len(results) * 0.99)]

    hist, edges = compute_histogram(results, 20)

    return ok_payload({
        "method": "monte_carlo",
        "samples": samples,
        "p01": p01,
        "p50": p50,
        "p99": p99,
        "mean": mean,
        "std_dev": std_dev,
        "histogram": hist,
        "bin_edges": edges,
        "nominal": sum(d.get("nominal", 0) for d in dimensions),
    })


def worst_case(dimensions: list[dict]) -> dict:
    dims = []
    for d in dimensions:
        nominal = d.get("nominal", 0)
        plus = d.get("plus", 0)
        minus = d.get("minus", 0)

        if "upper" in d and "plus" not in d:
            plus = d["upper"] - nominal
        if "lower" in d and "minus" not in d:
            minus = nominal - d["lower"]

        grade = d.get("grade", "")
        if grade:
            grade_tol = grade_to_tolerance(grade)
            if "plus" not in d and "upper" not in d:
                plus = grade_tol
            if "minus" not in d and "lower" not in d:
                minus = grade_tol

        dims.append({"nominal": nominal, "plus": plus, "minus": minus})

    nominal = sum(d["nominal"] for d in dims)
    max_val = sum(d["nominal"] + d["plus"] for d in dims)
    min_val = sum(d["nominal"] - d["minus"] for d in dims)
    return {
        "nominal": nominal,
        "max": max_val,
        "min": min_val,
        "worst_case_range": max_val - min_val,
    }


def rss(dimensions: list[dict], rss_k: float = 3.0) -> dict:
    dims = []
    for d in dimensions:
        nominal = d.get("nominal", 0)
        plus = d.get("plus", 0)
        minus = d.get("minus", 0)

        if "upper" in d and "plus" not in d:
            plus = d["upper"] - nominal
        if "lower" in d and "minus" not in d:
            minus = nominal - d["lower"]

        grade = d.get("grade", "")
        if grade:
            grade_tol = grade_to_tolerance(grade)
            if "plus" not in d and "upper" not in d:
                plus = grade_tol
            if "minus" not in d and "lower" not in d:
                minus = grade_tol

        dims.append({"nominal": nominal, "plus": plus, "minus": minus})

    nominal = sum(d["nominal"] for d in dims)
    rss_band = 0.0
    for d in dims:
        half_span = (d["plus"] + d["minus"]) / 2
        rss_band += half_span * half_span
    rss_band = rss_k * math.sqrt(rss_band)
    return {
        "nominal": nominal,
        "max": nominal + rss_band,
        "min": nominal - rss_band,
        "rss_range": 2 * rss_band,
    }


def monte_carlo(dimensions: list[dict], samples: int = 5000, seed: int = None) -> dict:
    if seed is None:
        seed = 1
    rng = random.Random(seed)
    results = []

    for _ in range(samples):
        v = 0.0
        for d in dimensions:
            nominal = d.get("nominal", 0)
            half_plus = d.get("plus", 0) / 2
            half_minus = d.get("minus", 0) / 2
            dist = d.get("distribution", "normal")
            v += sample_dimension(rng, nominal, half_plus, half_minus, dist)
        results.append(v)

    mean = sum(results) / len(results)
    m2 = sum((v - mean) ** 2 for v in results)
    std_dev = math.sqrt(m2 / len(results))

    results_sorted = sorted(results)
    p50 = results_sorted[int(len(results) * 0.50)]
    p95 = results_sorted[int(len(results) * 0.95)]
    p99 = results_sorted[int(len(results) * 0.99)]

    hist, _ = compute_histogram(results, 20)

    return {
        "p50": p50,
        "p95": p95,
        "p99": p99,
        "histogram": hist,
        "mean": mean,
        "std": std_dev,
    }