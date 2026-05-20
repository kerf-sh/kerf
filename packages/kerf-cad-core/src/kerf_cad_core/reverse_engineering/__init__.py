"""
kerf_cad_core.reverse_engineering — Reverse-engineering pipeline (v1).

Converts a point cloud (from a 3-D scanner or synthetic source) into a
parametric feature tree that can be re-evaluated to produce a solid model.

Pipeline
--------
1. **Import** — parse ``.pcd`` / ``.ply`` files into numpy-free Python lists of
   ``[x, y, z]`` floats using pure-Python parsers (``io`` sub-module).

2. **Segmentation** — sequential RANSAC: fit the best primitive to the remaining
   cloud, remove its inliers, repeat.  Supported primitives (v1):

   - Plane   → mapped to an extrude feature
   - Cylinder→ mapped to a revolve feature
   - Sphere  → mapped to a sphere primitive feature
   - Cone    → mapped to a cone primitive feature

3. **Feature mapping** — each fitted segment is converted to a ``.feature``-
   style dict node (``feature_map`` sub-module).  The mapping is intentionally
   simple:

   +-----------+--------------+----------------------------------+
   | Primitive | Feature op   | Key parameters                   |
   +===========+==============+==================================+
   | plane     | extrude      | normal, d, extent (bbox depth)   |
   +-----------+--------------+----------------------------------+
   | cylinder  | revolve      | axis, axis_point, radius, height |
   +-----------+--------------+----------------------------------+
   | sphere    | sphere       | centre, radius                   |
   +-----------+--------------+----------------------------------+
   | cone      | cone         | apex, axis, half_angle, height   |
   +-----------+--------------+----------------------------------+

4. **Feature tree** — a ``FeatureTree`` (a list of feature-node dicts) is
   returned by ``pipeline.recognize()``.  Each node has an ``id`` (e.g.
   ``"plane-0"``, ``"cylinder-0"``), an ``op``, and fit-specific params.

5. **Re-evaluation + Hausdorff check** — ``pipeline.sample_feature_tree()``
   re-samples the fitted shapes to a point cloud and
   ``pipeline.hausdorff_distance()`` computes the max-min distance between two
   clouds.  The round-trip oracle passes when ``hausdorff_distance ≤ 1e-3``
   (for noise-free synthetic inputs).

Known limits / deferred to v2
------------------------------
- **Freeform / Class-A surfaces** (NURBS patches, subdivision surfaces) — not
  recognised.  Points not claimed by any primitive are reported in
  ``unassigned_points``.
- **Real scanner noise** — RANSAC thresholds tuned for low noise (≤ 0.5 % of
  model extent); high-noise scans should pre-filter (outlier removal,
  bilateral smoothing) before feeding this pipeline.
- **Topology / feature ordering** — features are listed in fit order (dominant
  primitive first).  Full constructive history reconstruction (which feature
  was added vs. subtracted) is deferred to T-332b.
- **Cone / torus in mixed clouds** — cone RANSAC degrades when the apex is far
  outside the sampled region; a partial-cone heuristic is planned for v2.
- **File I/O — binary PLY** — only ASCII PLY is supported in v1; binary-LE and
  binary-BE variants raise ``UnsupportedFormatError``.

Sub-modules
-----------
io              — .pcd / .ply parsers
segmentation    — sequential RANSAC (plane/cylinder/sphere/cone)
feature_map     — segment dict → feature node dict
pipeline        — top-level recognize(), sample_feature_tree(), hausdorff_distance()

Author: imranparuk
"""
from __future__ import annotations

from kerf_cad_core.reverse_engineering.io import (
    UnsupportedFormatError,
    load_pcd,
    load_ply,
    load_point_cloud,
)
from kerf_cad_core.reverse_engineering.segmentation import (
    sequential_ransac,
)
from kerf_cad_core.reverse_engineering.feature_map import (
    segment_to_feature,
)
from kerf_cad_core.reverse_engineering.pipeline import (
    FeatureTree,
    recognize,
    sample_feature_tree,
    hausdorff_distance,
    max_point_to_surface_distance,
)

__all__ = [
    # io
    "UnsupportedFormatError",
    "load_pcd",
    "load_ply",
    "load_point_cloud",
    # segmentation
    "sequential_ransac",
    # feature_map
    "segment_to_feature",
    # pipeline
    "FeatureTree",
    "recognize",
    "sample_feature_tree",
    "hausdorff_distance",
    "max_point_to_surface_distance",
]
