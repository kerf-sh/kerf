"""
Analytic oracles for the drape / cloth-simulation module.

DoD requirements covered
------------------------
1. Catenary sag oracle:
   A 1-D strip pinned at both ends (span < arc length) droops with a sag
   matching the analytic catenary formula to within 5%.  The comparison uses
   the ACTUAL measured arc length and span at equilibrium, so spring stretch
   is accounted for and any moderate stiffness works.

2. Drape-coefficient range:
   A circular cloth draped over a disc pedestal produces a DC in [0.30, 0.95].

3. Drape-coefficient monotonicity:
   DC increases (non-decreases) as bending stiffness increases — stiffer
   fabric drapes less (projects more area → higher DC).

4. Energy non-increasing oracle:
   Once the cloth has started to settle, sampled total energy is non-increasing
   (may plateau, must not grow by more than 1%).

5. Catenary helper:
   ``catenary_max_sag`` returns correct analytic values for known cases.
"""

from __future__ import annotations

import math
import pytest

from kerf_textiles.drape import drape_simulate, drape_on_disc, catenary_max_sag
from kerf_textiles.mass_spring import PlanePrimitive, _norm, _sub


# ---------------------------------------------------------------------------
# Helper: catenary analytic function
# ---------------------------------------------------------------------------

class TestCatenaryHelper:
    """Unit tests for the pure-math catenary_max_sag helper."""

    def test_taut_chain_no_sag(self):
        """A chain with arc length == span is taut — sag must be zero."""
        sag = catenary_max_sag(span=1.0, total_length=1.0)
        assert sag == pytest.approx(0.0, abs=1e-10)

    def test_known_catenary_deep(self):
        """
        For span=2, arc=3: sag is between 0.3 and 1.5 m (sanity check).
        """
        sag = catenary_max_sag(span=2.0, total_length=3.0)
        assert 0.3 < sag < 1.5

    def test_catenary_shallow(self):
        """
        Slight sag (L only slightly > S): sag > 0 and < 0.1 for S=1, L=1.001.
        """
        sag = catenary_max_sag(span=1.0, total_length=1.001)
        assert 0.01 < sag < 0.1

    def test_catenary_symmetry(self):
        """Doubling span and arc length should double the sag (scaling)."""
        sag1 = catenary_max_sag(span=1.0, total_length=1.5)
        sag2 = catenary_max_sag(span=2.0, total_length=3.0)
        assert sag2 == pytest.approx(2.0 * sag1, rel=1e-4)


# ---------------------------------------------------------------------------
# Oracle 1 — Catenary sag simulation
# ---------------------------------------------------------------------------

class TestCatenarySag:
    """
    Oracle: A cloth strip pinned at both ends sags with a profile matching
    the analytic catenary to within 5%.

    Setup
    -----
    * rows=N, cols=1: a single-column strip.
    * Pins placed with span < arc_length (90% of arc length).
    * Interior particles distributed linearly between pins.
    * Simulate to convergence.
    * Measure actual span and arc length at equilibrium.
    * Compare sim_sag to catenary_max_sag(measured_span, measured_arc).

    Using the ACTUAL measured arc (which includes spring stretch) makes this
    oracle independent of stiffness value.
    """

    def test_catenary_sag_within_5pct(self):
        """
        Simulated max sag within 5% of analytic catenary (measured arc/span).
        """
        n = 21
        arc_spacing = 0.055          # rest-length per spring
        arc_nominal = (n - 1) * arc_spacing   # = 1.1 m (nominal)
        span_target = 0.9 * arc_nominal        # = 0.99 m (creates sag)

        z0 = -span_target / 2.0
        zN = +span_target / 2.0

        result = drape_simulate(
            rows=n,
            cols=1,
            spacing=arc_spacing,
            mass=0.002,
            k_structural=200.0,
            k_shear=0.0,
            k_bend=0.0,
            velocity_damping=0.97,
            pin_indices=[(0, 0), (n - 1, 0)],
            pin_positions={(0, 0): (0.0, 0.0, z0), (n - 1, 0): (0.0, 0.0, zN)},
            steps=3000,
            dt=0.005,
            tol=5e-5,
        )

        pos = result.mesh.positions

        # Measured span (z-distance between pinned endpoints — unchanged)
        span_meas = abs(pos[n - 1][2] - pos[0][2])

        # Measured arc length (sum of consecutive distances — includes stretch)
        arc_meas = sum(
            math.sqrt(sum((pos[i + 1][k] - pos[i][k]) ** 2 for k in range(3)))
            for i in range(n - 1)
        )

        analytic_sag = catenary_max_sag(span=span_meas, total_length=arc_meas)
        sim_sag = result.max_sag

        assert analytic_sag > 1e-4, (
            f"Analytic sag too small ({analytic_sag:.6f} m) — "
            f"span={span_meas:.3f}, arc={arc_meas:.3f}"
        )
        rel_err = abs(sim_sag - analytic_sag) / analytic_sag
        assert rel_err < 0.05, (
            f"Simulated sag {sim_sag:.4f} m vs catenary {analytic_sag:.4f} m: "
            f"relative error {rel_err * 100:.1f}% > 5%"
        )

    def test_converges(self):
        """The strip should converge before reaching the step limit."""
        n = 15
        span_target = 0.9 * (n - 1) * 0.06  # 10% shorter than arc
        z0 = -span_target / 2.0
        zN = +span_target / 2.0

        result = drape_simulate(
            rows=n,
            cols=1,
            spacing=0.06,
            mass=0.002,
            k_structural=150.0,
            k_shear=0.0,
            k_bend=0.0,
            velocity_damping=0.96,
            pin_indices=[(0, 0), (n - 1, 0)],
            pin_positions={(0, 0): (0.0, 0.0, z0), (n - 1, 0): (0.0, 0.0, zN)},
            steps=4000,
            dt=0.005,
            tol=5e-5,
        )
        assert result.converged, (
            f"Cloth strip did not converge in {result.steps_taken} steps; "
            f"energy_history tail: {result.energy_history[-3:]}"
        )


# ---------------------------------------------------------------------------
# Oracle 2 — Drape coefficient in [0.30, 0.95]
# ---------------------------------------------------------------------------

class TestDrapeCoefficient:
    """
    A circular cloth (14 cm radius) draped over a disc pedestal (7 cm radius)
    must produce a drape coefficient in the published range [0.30, 0.95].
    """

    def test_dc_in_published_range(self):
        result = drape_on_disc(
            cloth_radius=0.14,
            disc_radius=0.07,
            spacing=0.03,
            mass=0.002,
            k_structural=5.0,
            k_shear=2.5,
            k_bend=0.5,
            velocity_damping=0.97,
            steps=2000,
            dt=0.005,
            tol=1e-4,
        )
        assert result.drape_coefficient is not None
        dc = result.drape_coefficient
        assert 0.30 <= dc <= 0.95, (
            f"Drape coefficient {dc:.3f} is outside the published range [0.30, 0.95]"
        )

    def test_dc_is_dimensionless_fraction(self):
        """DC must always be in [0, 1]."""
        result = drape_on_disc(
            cloth_radius=0.14,
            disc_radius=0.07,
            spacing=0.03,
            mass=0.002,
            k_structural=3.0,
            k_shear=1.5,
            k_bend=0.2,
            velocity_damping=0.97,
            steps=1500,
            dt=0.005,
            tol=1e-4,
        )
        assert result.drape_coefficient is not None
        assert 0.0 <= result.drape_coefficient <= 1.0


# ---------------------------------------------------------------------------
# Oracle 3 — Drape coefficient monotonicity
# ---------------------------------------------------------------------------

class TestDrapeCoefficientMonotonicity:
    """
    DC INCREASES with bending stiffness.

    Physical reasoning:
    * Stiff fabric → outer ring barely droops → projects nearly original area → DC → 1.
    * Limp fabric → outer ring hangs vertically → projects only disc area → DC → 0.

    Oracle: DC(k_bend=low) <= DC(k_bend=high) + tolerance.
    """

    def _dc(self, k_bend: float) -> float:
        result = drape_on_disc(
            cloth_radius=0.14,
            disc_radius=0.07,
            spacing=0.03,
            mass=0.002,
            k_structural=5.0,
            k_shear=2.5,
            k_bend=k_bend,
            velocity_damping=0.97,
            steps=2000,
            dt=0.005,
            tol=1e-4,
        )
        assert result.drape_coefficient is not None
        return result.drape_coefficient

    def test_dc_increases_with_bend_stiffness(self):
        """
        DC(k_bend=0.1) <= DC(k_bend=50) — stiffer fabric projects more area.
        Tolerance 0.03 for numerical noise.
        """
        dc_limp = self._dc(k_bend=0.1)
        dc_stiff = self._dc(k_bend=50.0)
        assert dc_stiff >= dc_limp - 0.03, (
            f"Monotonicity violation: DC(limp={dc_limp:.3f}) > DC(stiff={dc_stiff:.3f}) "
            f"by more than tolerance"
        )


# ---------------------------------------------------------------------------
# Oracle 4 — Energy non-increasing after settling begins
# ---------------------------------------------------------------------------

class TestEnergyNonIncreasing:
    """
    Once the cloth has started settling, the sampled total energy history
    should be non-increasing (may plateau, must not grow by more than 1%).
    """

    def test_energy_non_increasing(self):
        result = drape_simulate(
            rows=10,
            cols=10,
            spacing=0.05,
            mass=0.004,
            k_structural=60.0,
            k_shear=30.0,
            k_bend=8.0,
            velocity_damping=0.98,
            pin_indices=[(0, 0), (0, 9)],
            colliders=[PlanePrimitive(height=-1.0)],
            steps=2000,
            dt=0.005,
            tol=5e-5,
            energy_sample_interval=100,
        )
        history = result.energy_history
        assert len(history) >= 5, "Need at least 5 energy samples"

        # Skip first 2 samples (initial transient) and check tail
        tail = history[2:]
        violations = 0
        for i in range(1, len(tail)):
            if tail[i] > tail[i - 1] * 1.01:
                violations += 1

        assert violations == 0, (
            f"Energy increased at {violations} sample(s) in the settling tail: "
            f"{tail}"
        )

    def test_energy_history_sampled(self):
        """energy_history is populated at the expected interval."""
        result = drape_simulate(
            rows=6, cols=6, spacing=0.05, mass=0.004,
            k_structural=60.0, k_shear=30.0, k_bend=8.0,
            velocity_damping=0.98,
            pin_indices=[(0, 0), (0, 5)],
            steps=400, dt=0.005,
            tol=1e-3,
            energy_sample_interval=50,
        )
        assert len(result.energy_history) >= 1


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------

class TestDrapeSmoke:
    def test_simulate_runs_and_returns_result(self):
        result = drape_simulate(
            rows=5, cols=5, spacing=0.1, mass=0.01,
            k_structural=30.0, k_shear=15.0, k_bend=4.0,
            velocity_damping=0.98,
            steps=100, dt=0.005,
        )
        assert result.mesh is not None
        assert isinstance(result.max_sag, float)
        assert result.max_sag >= 0.0
        assert result.steps_taken > 0

    def test_pinned_particles_do_not_move(self):
        n = 5
        result = drape_simulate(
            rows=n, cols=n, spacing=0.05, mass=0.01,
            k_structural=50.0, k_shear=25.0, k_bend=6.0,
            velocity_damping=0.98,
            pin_indices=[(0, 0), (0, n - 1)],
            steps=200, dt=0.005,
        )
        mesh = result.mesh
        # (row=0, col=0) → index 0;  (row=0, col=n-1) → index n-1
        assert mesh.positions[0][1] == pytest.approx(0.0, abs=1e-10), \
            "Pinned particle (0,0) moved!"
        assert mesh.positions[n - 1][1] == pytest.approx(0.0, abs=1e-10), \
            "Pinned particle (0,n-1) moved!"

    def test_sphere_collision(self):
        """Cloth particles should not penetrate the sphere."""
        from kerf_textiles.mass_spring import SpherePrimitive

        sphere = SpherePrimitive(centre=(0.0, -0.3, 0.0), radius=0.2)
        result = drape_simulate(
            rows=8, cols=8, spacing=0.05, mass=0.004,
            k_structural=50.0, k_shear=25.0, k_bend=5.0,
            velocity_damping=0.98,
            colliders=[sphere],
            steps=1200, dt=0.005,
        )
        for p in result.mesh.positions:
            dist = math.sqrt(sum((p[k] - sphere.centre[k]) ** 2 for k in range(3)))
            assert dist >= sphere.radius * 0.98, (
                f"Particle penetrated sphere: dist={dist:.4f} < radius={sphere.radius}"
            )

    def test_drape_on_disc_smoke(self):
        result = drape_on_disc(
            cloth_radius=0.12,
            disc_radius=0.06,
            spacing=0.025,
            mass=0.002,
            k_structural=4.0,
            k_shear=2.0,
            k_bend=0.3,
            velocity_damping=0.97,
            steps=1200,
            dt=0.005,
        )
        assert result.drape_coefficient is not None
        assert 0.0 <= result.drape_coefficient <= 1.0
        assert result.max_sag >= 0.0
