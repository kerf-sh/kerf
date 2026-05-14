import math
import sys
sys.path.insert(0, '/Users/pc/code/exo/kerf/backend-python')

from tools.tolerance import (
    worst_case, rss, monte_carlo, compute_histogram,
    grade_to_tolerance, IT_GRADE_TOLERANCES
)


def test_worst_case():
    dimensions = [
        {"nominal": 10.0, "plus": 0.1, "minus": 0.1},
        {"nominal": 5.0, "plus": 0.05, "minus": 0.05},
        {"nominal": 2.0, "plus": 0.02, "minus": 0.02},
    ]
    result = worst_case(dimensions)
    assert abs(result["nominal"] - 17.0) <= 0.001, f"nominal: {result['nominal']}"
    assert abs(result["max"] - 17.17) <= 0.01, f"max: {result['max']}"
    assert abs(result["min"] - 16.83) <= 0.01, f"min: {result['min']}"
    print("test_worst_case PASSED")


def test_rss():
    dimensions = [
        {"nominal": 10.0, "plus": 0.1, "minus": 0.1},
        {"nominal": 5.0, "plus": 0.05, "minus": 0.05},
        {"nominal": 2.0, "plus": 0.02, "minus": 0.02},
    ]
    result = rss(dimensions, rss_k=3.0)
    assert abs(result["nominal"] - 17.0) <= 0.001
    expected_rss_band = 3.0 * math.sqrt(0.1**2 + 0.05**2 + 0.02**2)
    assert abs(result["max"] - (result["nominal"] + expected_rss_band)) <= 0.01
    assert abs(result["min"] - (result["nominal"] - expected_rss_band)) <= 0.01
    print("test_rss PASSED")


def test_it_grade_lookup():
    assert abs(grade_to_tolerance("IT8") - 0.007) <= 0.0001
    assert abs(grade_to_tolerance("IT7") - 0.005) <= 0.0001
    assert abs(grade_to_tolerance("IT6") - 0.003) <= 0.0001
    assert grade_to_tolerance("IT99") == 0.0
    print("test_it_grade_lookup PASSED")


def test_it_grade_stack():
    dimensions = [
        {"nominal": 25.0, "grade": "IT8"},
        {"nominal": 10.0, "grade": "IT7"},
    ]
    result = worst_case(dimensions)
    assert abs(result["nominal"] - 35.0) <= 0.001
    print("test_it_grade_stack PASSED")


def test_upper_lower_form():
    dimensions = [
        {"nominal": 10.0, "upper": 10.1, "lower": 9.9},
        {"nominal": 5.0, "upper": 5.05, "lower": 4.95},
    ]
    result = worst_case(dimensions)
    assert abs(result["nominal"] - 15.0) <= 0.001
    assert abs(result["max"] - 15.15) <= 0.01
    assert abs(result["min"] - 14.85) <= 0.01
    print("test_upper_lower_form PASSED")


def test_monte_carlo():
    dimensions = [
        {"nominal": 10.0, "plus": 0.1, "minus": 0.1, "distribution": "normal"},
        {"nominal": 5.0, "plus": 0.05, "minus": 0.05, "distribution": "uniform"},
    ]
    result = monte_carlo(dimensions, samples=5000, seed=1)
    assert abs(result["p50"] - 15.0) <= 0.5, f"p50: {result['p50']}"
    assert len(result["histogram"]) > 0
    assert result["mean"] is not None
    assert result["std"] is not None
    print("test_monte_carlo PASSED")


def test_monte_carlo_with_seed():
    dimensions = [
        {"nominal": 10.0, "distribution": "normal"},
    ]
    result1 = monte_carlo(dimensions, samples=100, seed=42)
    result2 = monte_carlo(dimensions, samples=100, seed=42)
    assert result1["p50"] == result2["p50"]
    print("test_monte_carlo_with_seed PASSED")


def test_histogram():
    data = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0]
    hist, edges = compute_histogram(data, bins=5)
    assert len(hist) == 5
    assert len(edges) == 6
    assert sum(h["count"] for h in hist) == len(data)
    print("test_histogram PASSED")


def test_histogram_empty():
    hist, edges = compute_histogram([], bins=20)
    assert len(hist) == 0
    assert len(edges) == 0
    print("test_histogram_empty PASSED")


def main():
    test_worst_case()
    test_rss()
    test_it_grade_lookup()
    test_it_grade_stack()
    test_upper_lower_form()
    test_monte_carlo()
    test_monte_carlo_with_seed()
    test_histogram()
    test_histogram_empty()
    print("\nAll tests passed!")


if __name__ == "__main__":
    main()