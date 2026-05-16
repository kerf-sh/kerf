"""
kerf_cad_core.robotics — serial robot-arm kinematics.

Public API (re-exported for convenience):

    from kerf_cad_core.robotics import (
        dh_matrix,
        fk_chain,
        end_effector_pose,
        ik_2r_planar,
        ik_3r_planar,
        geometric_jacobian,
        manipulability,
        workspace_radius,
        joint_trajectory_trapezoidal,
    )

Distinct from kerf_cad_core.kinematics (planar linkages/cams).
This module covers Denavit-Hartenberg serial arm kinematics.

References
----------
Craig, J.J. "Introduction to Robotics: Mechanics and Control", 3rd ed.
Spong, M.W., Hutchinson, S., Vidyasagar, M. "Robot Modeling and Control", 2006.
Siciliano, B. et al. "Robotics: Modelling, Planning and Control", 2009.

Author: imranparuk
"""

from kerf_cad_core.robotics.arm import (
    dh_matrix,
    fk_chain,
    end_effector_pose,
    ik_2r_planar,
    ik_3r_planar,
    geometric_jacobian,
    manipulability,
    workspace_radius,
    joint_trajectory_trapezoidal,
)

__all__ = [
    "dh_matrix",
    "fk_chain",
    "end_effector_pose",
    "ik_2r_planar",
    "ik_3r_planar",
    "geometric_jacobian",
    "manipulability",
    "workspace_radius",
    "joint_trajectory_trapezoidal",
]
