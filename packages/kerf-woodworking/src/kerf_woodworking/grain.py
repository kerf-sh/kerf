"""grain.py — grain-direction metadata and structural warnings for Kerf.

Wood grain runs along the long axis of the tree trunk. Parts cut or loaded
perpendicular to grain are significantly weaker in bending than parts loaded
parallel to grain.

This module provides:

    GrainDirection   — enum-like constants
    add_grain_meta   — annotate a joint dict with grain metadata
    check_grain      — return GrainWarning dicts for a joint

A ``GrainWarning`` is a plain dict with keys:
    kind          — always "grain_warning"
    severity      — "error" | "warning"
    message       — human-readable description
    joint_type    — the joint that triggered the warning
    direction     — the problematic grain direction
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class GrainDirection:
    """Grain-direction constants."""
    ALONG   = "along"    # load / cut parallel to grain (strong)
    ACROSS  = "across"   # load / cut perpendicular to grain (weak — cross-grain)
    DIAGONAL = "diagonal"  # 45° — intermediate strength
    ANY     = "any"      # no grain constraint declared


# ---------------------------------------------------------------------------
# Warning builders
# ---------------------------------------------------------------------------

def _make_warning(severity: str, message: str, joint_type: str, direction: str) -> dict:
    return {
        "kind":       "grain_warning",
        "severity":   severity,
        "message":    message,
        "joint_type": joint_type,
        "direction":  direction,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_grain(joint: dict[str, Any]) -> list[dict]:
    """Return a list of grain warnings for a joint descriptor.

    Currently checks:
    - Mortise-and-tenon: tenon shoulder cut across grain is a structural risk
      when the shoulder_grain is explicitly marked as "across".
    - Any joint: if ``grain_direction`` on the joint is "across", warn.
    - Pocket-screw: screwing into end grain is unreliable — warn.

    Args:
        joint: a joint descriptor dict as returned by the joinery constructors.

    Returns:
        List of GrainWarning dicts (may be empty).
    """
    warnings: list[dict] = []
    joint_type = joint.get("joint_type", "unknown")

    # Generic grain_direction field check
    grain = joint.get("grain_direction", GrainDirection.ALONG)
    if grain == GrainDirection.ACROSS:
        warnings.append(_make_warning(
            severity="warning",
            message=(
                f"Joint '{joint_type}' has grain_direction='across'. "
                "Cross-grain construction significantly reduces tensile and "
                "bending strength along the member."
            ),
            joint_type=joint_type,
            direction=GrainDirection.ACROSS,
        ))

    # Mortise-and-tenon specific: shoulder grain check
    if joint_type == "mortise_tenon":
        shoulder_grain = joint.get("shoulder_grain", GrainDirection.ALONG)
        if shoulder_grain == GrainDirection.ACROSS:
            warnings.append(_make_warning(
                severity="warning",
                message=(
                    "Mortise-and-tenon: tenon shoulder is perpendicular to grain "
                    "(shoulder_grain='across'). Under bending load the short-grain "
                    "shoulder may split. Orient the tenon so the shoulder runs "
                    "parallel to grain, or use breadboard construction."
                ),
                joint_type=joint_type,
                direction=GrainDirection.ACROSS,
            ))

    # Pocket-screw into end grain
    if joint_type == "pocket_screw":
        target_grain = joint.get("target_grain", GrainDirection.ALONG)
        if target_grain in (GrainDirection.ACROSS, "end"):
            warnings.append(_make_warning(
                severity="warning",
                message=(
                    "Pocket screw drives into end grain. End-grain screw holding "
                    "strength is roughly 25–40% of face-grain strength. Consider "
                    "using a face-grain target or adding glue."
                ),
                joint_type=joint_type,
                direction="end",
            ))

    # Dovetail: across-grain dovetail on narrow stock can split
    if joint_type == "dovetail":
        if joint.get("board_grain", GrainDirection.ALONG) == GrainDirection.ACROSS:
            warnings.append(_make_warning(
                severity="error",
                message=(
                    "Dovetail cut across grain on narrow stock will likely split "
                    "the board at the pins. Rotate the board so grain runs parallel "
                    "to the board length."
                ),
                joint_type=joint_type,
                direction=GrainDirection.ACROSS,
            ))

    return warnings


def add_grain_meta(
    joint: dict[str, Any],
    *,
    grain_direction: str = GrainDirection.ALONG,
    shoulder_grain: str | None = None,
    target_grain: str | None = None,
    board_grain: str | None = None,
) -> dict[str, Any]:
    """Annotate a joint descriptor with grain metadata and populate warnings.

    Mutates and returns the joint dict.  Also runs :func:`check_grain` and
    appends any new warnings to ``joint["warnings"]``.

    Args:
        joint:           joint descriptor dict.
        grain_direction: primary grain direction for this joint.
        shoulder_grain:  grain at the tenon shoulder (mortise-tenon only).
        target_grain:    grain of the receiving member (pocket-screw).
        board_grain:     grain running direction of the dovetail board.

    Returns:
        The mutated joint dict (same object).
    """
    joint["grain_direction"] = grain_direction
    if shoulder_grain is not None:
        joint["shoulder_grain"] = shoulder_grain
    if target_grain is not None:
        joint["target_grain"] = target_grain
    if board_grain is not None:
        joint["board_grain"] = board_grain

    new_warnings = check_grain(joint)
    existing = joint.setdefault("warnings", [])
    existing.extend(new_warnings)
    return joint
