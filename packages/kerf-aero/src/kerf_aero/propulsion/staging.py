"""
Multi-stage rocket ΔV budgeting and optimal Δv-split optimisation.

The ideal rocket equation is applied stage-by-stage; structural fractions,
payload mass, and per-stage Isp are all configurable.

Functions
---------
multistage_delta_v   Total ΔV for a sequence of stage definitions.
optimal_delta_v_split   Optimise ΔV allocation across N stages of equal Isp.
stage_mass_ratio     Mass ratio for a single stage given ΔV and Isp.
gravity_loss_estimate   Simple gravity-loss estimate for a launch trajectory.

All functions return plain dicts and never raise.

References
----------
Sutton & Biblarz, "Rocket Propulsion Elements", 9th ed., Chap. 4.
Turner, "Rocket and Spacecraft Propulsion", 3rd ed., Chap. 2.
"""

from __future__ import annotations

import math
from typing import Any

G0: float = 9.80665  # m/s²


def stage_mass_ratio(delta_v_ms: float, isp: float) -> dict:
    """
    Mass ratio m0/mf for a single stage delivering delta_v [m/s] at Isp [s].
    """
    if isp <= 0:
        return {"ok": False, "reason": "Isp must be positive"}
    if delta_v_ms < 0:
        return {"ok": False, "reason": "ΔV must be non-negative"}
    ve = isp * G0
    mr = math.exp(delta_v_ms / ve)
    return {
        "ok": True,
        "mass_ratio": mr,
        "propellant_fraction": 1.0 - 1.0 / mr,
        "ve": ve,
        "delta_v_ms": delta_v_ms,
        "isp": isp,
    }


def multistage_delta_v(stages: list[dict[str, Any]]) -> dict:
    """
    Total ideal ΔV for a multi-stage rocket.

    Each stage dict must contain:
        isp        : specific impulse [s]
        m0         : initial mass of this stage (incl. all upper stages + payload) [kg]
        mf         : final mass after burnout (empty stage + upper stages + payload) [kg]

    Optionally:
        name       : stage label (string)

    The stages are evaluated in order from first-stage burn to last.

    Parameters
    ----------
    stages : list of stage dicts as described above

    Returns
    -------
    dict with:
        ok             True on success
        total_delta_v  [m/s]
        stage_results  list of per-stage ΔV and mass ratio dicts
        payload_mass   final mass after all stages [kg] (= last stage mf)
    """
    if not stages:
        return {"ok": False, "reason": "stages list is empty"}

    total_dv = 0.0
    results = []

    for i, stage in enumerate(stages):
        isp = stage.get("isp")
        m0 = stage.get("m0")
        mf = stage.get("mf")
        name = stage.get("name", f"Stage {i + 1}")

        if isp is None or m0 is None or mf is None:
            return {
                "ok": False,
                "reason": f"Stage {i + 1} ('{name}') missing isp/m0/mf",
            }
        if isp <= 0:
            return {"ok": False, "reason": f"Stage {i + 1}: Isp must be positive"}
        if m0 <= 0 or mf <= 0:
            return {"ok": False, "reason": f"Stage {i + 1}: masses must be positive"}
        if mf > m0:
            return {
                "ok": False,
                "reason": f"Stage {i + 1}: dry mass ({mf} kg) > wet mass ({m0} kg)",
            }

        ve = isp * G0
        mr = m0 / mf
        dv = ve * math.log(mr)
        total_dv += dv

        results.append({
            "stage": name,
            "isp": isp,
            "m0": m0,
            "mf": mf,
            "mass_ratio": mr,
            "delta_v_ms": dv,
            "delta_v_kms": dv / 1000.0,
            "propellant_fraction": (m0 - mf) / m0,
        })

    return {
        "ok": True,
        "total_delta_v_ms": total_dv,
        "total_delta_v_kms": total_dv / 1000.0,
        "n_stages": len(stages),
        "stage_results": results,
        "payload_mass": stages[-1]["mf"],
    }


def optimal_delta_v_split(
    total_delta_v: float,
    n_stages: int,
    isp_per_stage: list[float] | float,
    mass_ratio_per_stage: list[float] | float | None = None,
    structural_fraction_per_stage: list[float] | float = 0.1,
    payload_mass: float = 1000.0,
    *,
    tol: float = 1e-8,
    max_iter: int = 1000,
) -> dict:
    """
    Optimal ΔV split across N stages for maximum payload fraction.

    When all stages have the same Isp and same structural fraction (ε), the
    optimal split is equal ΔV per stage (Lagrange multiplier result).  This
    function supports unequal Isp per stage and solves the optimum
    numerically via gradient-free search.

    The mass model per stage is:

        m_propellant = m0_stage · (1 − 1/MR_stage)
        m_structure  = ε · m_propellant
        m_upper      = m0_stage / MR_stage      (upper stages + payload)

    where MR_stage = exp(ΔV_stage / ve_stage).

    Parameters
    ----------
    total_delta_v         : total mission ΔV [m/s]
    n_stages              : number of stages
    isp_per_stage         : Isp [s] per stage (scalar → same for all)
    mass_ratio_per_stage  : if given, overrides structural_fraction (unused here)
    structural_fraction_per_stage : ε per stage (scalar → same for all)
    payload_mass          : final payload mass [kg]
    tol                   : convergence tolerance
    max_iter              : maximum optimisation iterations

    Returns
    -------
    dict with:
        ok              True on success
        optimal_delta_v_split   list of ΔV per stage [m/s]
        stage_mass_ratios       list of m0/mf per stage
        payload_fraction        payload / initial total wet mass
        total_wet_mass          initial total wet mass [kg]
        stage_results           per-stage mass breakdown
    """
    if n_stages < 1:
        return {"ok": False, "reason": "n_stages must be ≥ 1"}
    if total_delta_v <= 0:
        return {"ok": False, "reason": "total_delta_v must be positive"}
    if payload_mass <= 0:
        return {"ok": False, "reason": "payload_mass must be positive"}

    # Broadcast scalars
    if isinstance(isp_per_stage, (int, float)):
        isps = [float(isp_per_stage)] * n_stages
    else:
        isps = list(isp_per_stage)
        if len(isps) != n_stages:
            return {"ok": False, "reason": "isp_per_stage length mismatch"}

    if isinstance(structural_fraction_per_stage, (int, float)):
        epsilons = [float(structural_fraction_per_stage)] * n_stages
    else:
        epsilons = list(structural_fraction_per_stage)
        if len(epsilons) != n_stages:
            return {"ok": False, "reason": "structural_fraction_per_stage length mismatch"}

    for i, (isp, eps) in enumerate(zip(isps, epsilons)):
        if isp <= 0:
            return {"ok": False, "reason": f"Stage {i + 1}: Isp must be positive"}
        if not (0.0 <= eps < 1.0):
            return {"ok": False, "reason": f"Stage {i + 1}: structural fraction must be in [0,1)"}

    def _payload_fraction(dv_split: list[float]) -> float:
        """Compute payload / initial total wet mass for a ΔV allocation."""
        # Work backwards from payload: given upper stages, compute each stage m0
        m_upper = payload_mass
        total_m0 = None
        for stage_idx in range(n_stages - 1, -1, -1):
            dv_s = dv_split[stage_idx]
            isp_s = isps[stage_idx]
            eps_s = epsilons[stage_idx]
            ve_s = isp_s * G0
            mr_s = math.exp(dv_s / ve_s)
            # m0_stage / mf_stage = mr_s
            # mf_stage = m_upper + m_structure
            # m_structure = eps_s * m_propellant = eps_s * (m0_stage - mf_stage)
            # Let m0 = x:
            #   mf = m_upper + eps_s * (x - mf)
            #   mf(1 + eps_s) = m_upper + eps_s * x   ... (A)
            #   x / mf = mr_s  → mf = x / mr_s        ... (B)
            # Sub (B) into (A):
            #   x / mr_s * (1 + eps_s) = m_upper + eps_s * x
            #   x (1 + eps_s) / mr_s - eps_s * x = m_upper
            #   x [(1 + eps_s)/mr_s - eps_s] = m_upper
            denom = (1.0 + eps_s) / mr_s - eps_s
            if denom <= 0:
                return 0.0  # infeasible
            m0_stage = m_upper / denom
            if total_m0 is None:
                total_m0 = m0_stage  # we only want stage-1 m0 for denominator
                # Actually we want the outermost (first) stage m0
            m_upper = m0_stage
        # total_m0 = first stage initial wet mass (outermost stage)
        total_m0 = m_upper  # outermost stage
        return payload_mass / total_m0 if total_m0 > 0 else 0.0

    # -----------------------------------------------------------------------
    # Equal-split starting point
    # -----------------------------------------------------------------------
    dv_split = [total_delta_v / n_stages] * n_stages

    if n_stages == 1:
        # Trivial
        isp = isps[0]
        eps = epsilons[0]
        ve = isp * G0
        mr = math.exp(total_delta_v / ve)
        denom = (1.0 + eps) / mr - eps
        if denom <= 0:
            return {"ok": False, "reason": "Single stage: structural fraction too high for given ΔV"}
        m0 = payload_mass / denom
        mf = m0 / mr
        pf = payload_mass / m0
        return {
            "ok": True,
            "optimal_delta_v_split": [total_delta_v],
            "stage_mass_ratios": [mr],
            "payload_fraction": pf,
            "total_wet_mass": m0,
            "stage_results": [{
                "stage": "Stage 1",
                "delta_v_ms": total_delta_v,
                "mass_ratio": mr,
                "m0": m0,
                "mf": mf,
                "isp": isp,
            }],
            "equal_split": True,
        }

    # For equal Isp all stages: analytic optimal = equal ΔV per stage
    # For unequal Isp: use gradient-free search (coordinate descent)
    same_isp = all(abs(isps[i] - isps[0]) < 1e-6 for i in range(n_stages))
    same_eps = all(abs(epsilons[i] - epsilons[0]) < 1e-6 for i in range(n_stages))

    if not same_isp or not same_eps:
        # Coordinate descent optimisation
        dv_split = [total_delta_v / n_stages] * n_stages
        best_pf = _payload_fraction(dv_split)
        step = total_delta_v * 0.05

        for _iteration in range(max_iter):
            improved = False
            for i in range(n_stages):
                for direction in (+1, -1):
                    candidate = dv_split[:]
                    delta = direction * step
                    # Transfer ΔV from stage i to stage (i+1) % n_stages
                    j = (i + 1) % n_stages
                    if candidate[i] + delta > tol and candidate[j] - delta > tol:
                        candidate[i] += delta
                        candidate[j] -= delta
                        pf = _payload_fraction(candidate)
                        if pf > best_pf + tol:
                            best_pf = pf
                            dv_split = candidate[:]
                            improved = True
            if not improved:
                step *= 0.5
                if step < tol:
                    break

    # Build output
    stage_results = []
    m_upper = payload_mass
    stage_m0s = []
    for stage_idx in range(n_stages - 1, -1, -1):
        dv_s = dv_split[stage_idx]
        isp_s = isps[stage_idx]
        eps_s = epsilons[stage_idx]
        ve_s = isp_s * G0
        mr_s = math.exp(dv_s / ve_s)
        denom = (1.0 + eps_s) / mr_s - eps_s
        if denom <= 0:
            return {"ok": False, "reason": f"Stage {stage_idx + 1}: infeasible (ε too high or ΔV too large)"}
        m0_s = m_upper / denom
        mf_s = m0_s / mr_s
        stage_m0s.insert(0, m0_s)
        m_upper = m0_s

    total_m0 = stage_m0s[0]
    pf = payload_mass / total_m0

    m_upper = payload_mass
    for stage_idx in range(n_stages - 1, -1, -1):
        dv_s = dv_split[stage_idx]
        isp_s = isps[stage_idx]
        eps_s = epsilons[stage_idx]
        ve_s = isp_s * G0
        mr_s = math.exp(dv_s / ve_s)
        denom = (1.0 + eps_s) / mr_s - eps_s
        m0_s = m_upper / denom
        mf_s = m0_s / mr_s
        stage_results.insert(0, {
            "stage": f"Stage {stage_idx + 1}",
            "delta_v_ms": dv_s,
            "delta_v_kms": dv_s / 1000.0,
            "mass_ratio": mr_s,
            "m0": m0_s,
            "mf": mf_s,
            "isp": isp_s,
            "structural_fraction": eps_s,
        })
        m_upper = m0_s

    return {
        "ok": True,
        "optimal_delta_v_split": dv_split,
        "stage_mass_ratios": [math.exp(dv / (isps[i] * G0)) for i, dv in enumerate(dv_split)],
        "payload_fraction": pf,
        "total_wet_mass": total_m0,
        "stage_results": stage_results,
        "equal_split": same_isp and same_eps,
    }


def gravity_loss_estimate(
    delta_v_ideal: float,
    burn_time: float,
    average_pitch_deg: float = 45.0,
    g0: float = G0,
) -> dict:
    """
    Simple estimate of gravity-drag loss during a launch burn.

    Δv_gravity ≈ g0 · t_burn · sin(θ_avg)

    where θ_avg is the average pitch angle above horizontal.

    This is a first-order approximation.  For a vertical launch followed by
    gravity turn, a typical value is 50–150 m/s for an orbital mission.

    Parameters
    ----------
    delta_v_ideal    : ideal (vacuum, no-gravity) ΔV [m/s]
    burn_time        : total powered-flight time [s]
    average_pitch_deg: average flight-path angle above horizontal [°]
    g0               : gravitational acceleration [m/s²]

    Returns
    -------
    dict with gravity_loss [m/s], drag_fraction, effective_delta_v [m/s]
    """
    if burn_time < 0:
        return {"ok": False, "reason": "burn_time must be ≥ 0"}
    if delta_v_ideal < 0:
        return {"ok": False, "reason": "delta_v_ideal must be ≥ 0"}

    pitch_rad = math.radians(average_pitch_deg)
    grav_loss = g0 * burn_time * math.sin(pitch_rad)
    eff_dv = delta_v_ideal - grav_loss

    return {
        "ok": True,
        "gravity_loss_ms": grav_loss,
        "effective_delta_v_ms": eff_dv,
        "gravity_fraction": grav_loss / delta_v_ideal if delta_v_ideal > 0 else 0.0,
        "burn_time": burn_time,
        "average_pitch_deg": average_pitch_deg,
    }
