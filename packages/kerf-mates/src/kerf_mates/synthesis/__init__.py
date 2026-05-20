"""
kerf_mates.synthesis — mechanism synthesis (inverse kinematics / motion spec → mechanism).

Sub-modules
-----------
fourbar     — 4-bar linkage synthesis from a 3-point coupler-curve spec (Burmester theory)
cam         — cam-profile synthesis from follower motion laws (cycloidal, polynomial, harmonic)
gear_train  — gear-train synthesis: target ratio → spur configuration

Usage
-----
    from kerf_mates.synthesis import fourbar, cam, gear_train

    result = fourbar.synthesise_four_bar(points)
    profile = cam.synthesise_cam(law="cycloidal", h=10.0, beta_deg=120.0)
    config  = gear_train.synthesise_gear_train(target_ratio=5.0)
"""

from kerf_mates.synthesis import fourbar, cam, gear_train

__all__ = ["fourbar", "cam", "gear_train"]
