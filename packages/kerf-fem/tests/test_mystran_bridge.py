"""
MYSTRAN subprocess bridge tests.

Test groups
-----------
1. BDF syntax tests (hermetic — no solver needed).
   Verify that the BDF generator produces syntactically valid bulk-data
   decks.  Checks: required section keywords, GRID/element counts,
   SPC1 presence, EIGRL presence for modal, ENDDATA terminator.

2. Leissa analytic oracle tests (hermetic — pure Python, no solver).
   Verify that ``leissa_plate_freq_hz`` and
   ``leissa_plate_first_three_modes`` return values consistent with the
   closed-form formula from Leissa (1969) NASA SP-160, Table 4.1.
   These tests are always run and can never be skipped.

3. MYSTRAN round-trip tests (skipped when ``mystran`` not on PATH).
   Run the SSSS plate corpus case through the live solver and assert
   that the first three natural frequencies fall within 3 % of the
   Leissa analytic oracle.

4. Pending-sentinel test.
   When ``shutil.which("mystran")`` is monkeypatched to return None,
   ``MystranBridge.solve`` must return ``status="pending"`` without
   raising.

References
----------
Leissa, A.W., "Vibration of Plates", NASA SP-160, 1969.
Blevins, R.D., "Formulas for Natural Frequency and Mode Shape", 1979.
"""

from __future__ import annotations

import math
import shutil
import re

import pytest

# ---------------------------------------------------------------------------
# Skip marker for tests that need the live mystran binary
# ---------------------------------------------------------------------------

_needs_mystran = pytest.mark.skipif(
    shutil.which("mystran") is None,
    reason="mystran not installed or not in PATH",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_bridge():
    from kerf_fem.mystran_bridge import MystranBridge
    return MystranBridge


def _load_corpus():
    from kerf_fem import mystran_corpus
    return mystran_corpus


# ===========================================================================
# 1. BDF syntax tests (hermetic)
# ===========================================================================


class TestBdfSyntax:
    """Verify the BDF deck writer produces valid bulk-data syntax."""

    def test_modal_deck_has_sol103(self):
        """SOL 103 must appear as the first executive control card."""
        corpus = _load_corpus()
        deck = corpus.ssss_plate_bdf()
        lines = deck.splitlines()
        assert lines[0].strip().startswith("SOL 103"), (
            f"Expected 'SOL 103' on line 1, got: {lines[0]!r}"
        )

    def test_modal_deck_has_cend(self):
        """CEND must terminate the executive control section."""
        corpus = _load_corpus()
        deck = corpus.ssss_plate_bdf()
        assert "CEND" in deck, "BDF deck missing CEND keyword"

    def test_modal_deck_has_begin_bulk(self):
        """BEGIN BULK must delimit the case control / bulk data boundary."""
        corpus = _load_corpus()
        deck = corpus.ssss_plate_bdf()
        assert "BEGIN BULK" in deck, "BDF deck missing BEGIN BULK"

    def test_modal_deck_has_enddata(self):
        """ENDDATA must terminate the bulk data section (required by NASTRAN)."""
        corpus = _load_corpus()
        deck = corpus.ssss_plate_bdf()
        lines = [ln.strip() for ln in deck.splitlines()]
        assert "ENDDATA" in lines, "BDF deck missing ENDDATA"

    def test_modal_deck_has_eigrl(self):
        """EIGRL card must be present for SOL 103 eigenvalue extraction."""
        corpus = _load_corpus()
        deck = corpus.ssss_plate_bdf()
        eigrl_lines = [ln for ln in deck.splitlines() if ln.startswith("EIGRL")]
        assert eigrl_lines, "BDF modal deck missing EIGRL card"

    def test_modal_deck_grid_count(self):
        """Number of GRID cards must match the mesh node count."""
        corpus = _load_corpus()
        case = corpus.build_corpus()[0]
        mesh = case.mesh

        deck = corpus.ssss_plate_bdf()
        grid_count = sum(1 for ln in deck.splitlines() if ln.startswith("GRID,"))
        expected = len(mesh["nodes"])
        assert grid_count == expected, (
            f"GRID card count {grid_count} != mesh node count {expected}"
        )

    def test_modal_deck_element_count(self):
        """Number of CQUAD4 cards must match the mesh element count."""
        corpus = _load_corpus()
        case = corpus.build_corpus()[0]
        mesh = case.mesh

        deck = corpus.ssss_plate_bdf()
        elem_count = sum(1 for ln in deck.splitlines() if ln.startswith("CQUAD4,"))
        expected = len(mesh["elements"])
        assert elem_count == expected, (
            f"CQUAD4 card count {elem_count} != mesh element count {expected}"
        )

    def test_modal_deck_has_pshell(self):
        """PSHELL property card must be present for shell elements."""
        corpus = _load_corpus()
        deck = corpus.ssss_plate_bdf()
        assert any(ln.startswith("PSHELL") for ln in deck.splitlines()), (
            "BDF modal deck missing PSHELL property card"
        )

    def test_modal_deck_has_mat1(self):
        """MAT1 isotropic material card must be present."""
        corpus = _load_corpus()
        deck = corpus.ssss_plate_bdf()
        assert any(ln.startswith("MAT1") for ln in deck.splitlines()), (
            "BDF modal deck missing MAT1 material card"
        )

    def test_modal_deck_has_spc1(self):
        """SPC1 boundary-condition card must be present."""
        corpus = _load_corpus()
        deck = corpus.ssss_plate_bdf()
        assert any(ln.startswith("SPC1") for ln in deck.splitlines()), (
            "BDF modal deck missing SPC1 constraint card"
        )

    def test_modal_deck_no_blank_card_name(self):
        """
        All non-comment bulk data cards must have a non-blank card name
        (i.e. no lines starting with a comma in the element/property section).
        """
        corpus = _load_corpus()
        deck = corpus.ssss_plate_bdf()
        bulk_start = deck.find("BEGIN BULK")
        bulk_end = deck.find("ENDDATA")
        bulk_section = deck[bulk_start:bulk_end]
        for line in bulk_section.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("$"):
                continue
            if stripped == "BEGIN BULK":
                continue
            # Free-field cards must not start with a comma
            assert not stripped.startswith(","), (
                f"Blank card name (leading comma) in bulk section: {line!r}"
            )

    def test_bdf_node_ids_are_positive_integers(self):
        """
        Every GRID card must reference a positive integer node ID as its
        first field (NASTRAN requires NID ≥ 1).
        """
        corpus = _load_corpus()
        deck = corpus.ssss_plate_bdf()
        for line in deck.splitlines():
            if not line.startswith("GRID,"):
                continue
            parts = line.split(",")
            assert len(parts) >= 2, f"Malformed GRID card: {line!r}"
            nid = int(parts[1])
            assert nid >= 1, f"Non-positive node ID in GRID card: {line!r}"

    def test_bdf_element_references_valid_nodes(self):
        """
        Every CQUAD4 element must reference node IDs that appear in the GRID
        cards (i.e. no dangling node references).
        """
        corpus = _load_corpus()
        deck = corpus.ssss_plate_bdf()
        lines = deck.splitlines()

        known_nids: set[int] = set()
        for line in lines:
            if line.startswith("GRID,"):
                parts = line.split(",")
                known_nids.add(int(parts[1]))

        for line in lines:
            if not line.startswith("CQUAD4,"):
                continue
            parts = line.split(",")
            # CQUAD4,EID,PID,G1,G2,G3,G4
            for nid_str in parts[3:]:
                nid_str = nid_str.strip()
                if nid_str:
                    nid = int(nid_str)
                    assert nid in known_nids, (
                        f"CQUAD4 references unknown node ID {nid}: {line!r}"
                    )

    def test_static_deck_has_sol101(self):
        """SOL 101 deck must have the correct solution sequence."""
        from kerf_fem.mystran_bridge import _write_bdf_static

        nodes = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)]
        elements = [(1, "CQUAD4", [1, 2, 3, 4])]
        materials = {"E": 200e9, "nu": 0.3, "rho": 7850.0}
        bcs = [{"type": "fixed", "node_ids": [1, 4]}]
        loads = [{"type": "force", "node_id": 2, "fx": 0.0, "fy": 0.0, "fz": -1000.0}]

        deck = _write_bdf_static(
            nodes, elements, materials, bcs, loads,
            shell_thickness=0.005,
        )
        assert deck.splitlines()[0].strip().startswith("SOL 101"), (
            "Static BDF deck must start with SOL 101"
        )
        assert "FORCE" in deck, "Static BDF deck missing FORCE card"
        assert "ENDDATA" in deck.splitlines()[-1] or "ENDDATA" in deck, (
            "Static BDF deck missing ENDDATA"
        )


# ===========================================================================
# 2. Leissa analytic oracle tests (hermetic — always run)
# ===========================================================================


class TestLeissaOracle:
    """
    Verify the Leissa (1969) plate frequency oracle.

    These tests never require MYSTRAN and must always pass.  They serve both
    as a regression guard on the analytic formula and as documentation of the
    expected numerical values for the corpus reference case.
    """

    # Steel plate parameters matching the corpus case
    _E = 200e9
    _nu = 0.3
    _rho = 7850.0
    _h = 0.002    # 2 mm
    _a = 0.4      # m
    _b = 0.3      # m

    def _f(self, m: int, n: int) -> float:
        corpus = _load_corpus()
        return corpus.leissa_plate_freq_hz(
            self._E, self._nu, self._rho, self._h, self._a, self._b, m, n
        )

    def test_mode_11_positive(self):
        """Fundamental frequency (1,1) must be positive."""
        assert self._f(1, 1) > 0.0

    def test_mode_11_formula(self):
        """
        Manual cross-check of the (1,1) frequency against the formula:

            D = E h³ / (12 (1 − ν²))
            ω₁₁ = π² (1/a² + 1/b²) √(D / (ρ h))
            f₁₁ = ω₁₁ / (2π)

        Result must match to machine precision (same formula, different code path).
        """
        E, nu, rho, h, a, b = self._E, self._nu, self._rho, self._h, self._a, self._b
        D = E * h ** 3 / (12.0 * (1.0 - nu ** 2))
        omega = math.pi ** 2 * (1 / a ** 2 + 1 / b ** 2) * math.sqrt(D / (rho * h))
        f_expected = omega / (2.0 * math.pi)
        f_actual = self._f(1, 1)
        assert abs(f_actual - f_expected) < 1e-6, (
            f"leissa_plate_freq_hz(1,1) = {f_actual:.6f} Hz, "
            f"expected {f_expected:.6f} Hz"
        )

    def test_mode_frequencies_ascending(self):
        """
        Modal frequencies must increase as mode indices increase along the
        same axis: f(1,1) < f(2,1) < f(3,1).
        """
        f11 = self._f(1, 1)
        f21 = self._f(2, 1)
        f31 = self._f(3, 1)
        assert f11 < f21, f"f(1,1)={f11:.2f} not < f(2,1)={f21:.2f}"
        assert f21 < f31, f"f(2,1)={f21:.2f} not < f(3,1)={f31:.2f}"

    def test_mode_12_vs_21_symmetry(self):
        """
        For a 0.4×0.3 plate, f(1,2) ≠ f(2,1) because a ≠ b.  This test
        documents that the formula is NOT degenerate for the non-square case.
        """
        f12 = self._f(1, 2)
        f21 = self._f(2, 1)
        assert abs(f12 - f21) > 1.0, (
            f"Expected f(1,2) ≠ f(2,1) for non-square plate, "
            f"got {f12:.2f} vs {f21:.2f} Hz"
        )

    def test_square_plate_degeneracy(self):
        """
        For a square plate (a = b), modes (1,2) and (2,1) are degenerate
        (same frequency, confirmed by the symmetric formula).
        """
        corpus = _load_corpus()
        a = b = 0.4
        f12 = corpus.leissa_plate_freq_hz(self._E, self._nu, self._rho, self._h, a, b, 1, 2)
        f21 = corpus.leissa_plate_freq_hz(self._E, self._nu, self._rho, self._h, a, b, 2, 1)
        assert abs(f12 - f21) < 1e-6, (
            f"Square plate modes (1,2) and (2,1) should be degenerate, "
            f"got {f12:.6f} vs {f21:.6f} Hz"
        )

    def test_first_three_modes_length(self):
        """leissa_plate_first_three_modes must return exactly 3 values."""
        corpus = _load_corpus()
        modes = corpus.leissa_plate_first_three_modes(
            self._E, self._nu, self._rho, self._h, self._a, self._b
        )
        assert len(modes) == 3, f"Expected 3 modes, got {len(modes)}: {modes}"

    def test_first_three_modes_ascending(self):
        """The three returned frequencies must be in ascending order."""
        corpus = _load_corpus()
        modes = corpus.leissa_plate_first_three_modes(
            self._E, self._nu, self._rho, self._h, self._a, self._b
        )
        assert modes[0] < modes[1] < modes[2], (
            f"Modes not ascending: {modes}"
        )

    def test_first_three_modes_first_is_f11(self):
        """The lowest mode must equal f(1,1)."""
        corpus = _load_corpus()
        modes = corpus.leissa_plate_first_three_modes(
            self._E, self._nu, self._rho, self._h, self._a, self._b
        )
        f11 = self._f(1, 1)
        assert abs(modes[0] - f11) / f11 < 1e-6, (
            f"Lowest mode {modes[0]:.4f} Hz != f(1,1)={f11:.4f} Hz"
        )

    def test_increasing_thickness_raises_frequency(self):
        """
        Thicker plate → higher bending rigidity D per unit mass:
        f ∝ √(D / (ρ h)) = √(E h² / (12 (1−ν²) ρ)) → f ∝ h.
        So f increases with thickness.
        """
        corpus = _load_corpus()
        f_thin = corpus.leissa_plate_freq_hz(
            self._E, self._nu, self._rho, 0.001, self._a, self._b
        )
        f_thick = corpus.leissa_plate_freq_hz(
            self._E, self._nu, self._rho, 0.004, self._a, self._b
        )
        assert f_thick > f_thin, (
            f"Expected thicker plate to have higher frequency: "
            f"h=1mm → {f_thin:.2f} Hz, h=4mm → {f_thick:.2f} Hz"
        )

    def test_invalid_geometry_raises(self):
        """Zero plate dimensions must raise ValueError."""
        corpus = _load_corpus()
        with pytest.raises(ValueError):
            corpus.leissa_plate_freq_hz(
                self._E, self._nu, self._rho, 0.0, self._a, self._b
            )

    def test_corpus_case_leissa_reference(self):
        """
        The corpus case expected_frequencies_hz must match the direct oracle
        call to machine precision (sanity-check corpus consistency).
        """
        corpus = _load_corpus()
        cases = corpus.build_corpus()
        ssss_case = next(c for c in cases if c.name == "ssss_plate_modal")
        expected = ssss_case.expected_frequencies_hz

        direct = corpus.leissa_plate_first_three_modes(
            ssss_case.materials["E"],
            ssss_case.materials["nu"],
            ssss_case.materials["rho"],
            ssss_case.mesh["shell_thickness"],
            0.4,  # a
            0.3,  # b
        )
        for i, (ef, df) in enumerate(zip(expected, direct)):
            assert abs(ef - df) / df < 1e-6, (
                f"Corpus mode {i+1}: stored {ef:.4f} Hz != direct oracle {df:.4f} Hz"
            )


# ===========================================================================
# 3. MYSTRAN round-trip tests (skipped when mystran not on PATH)
# ===========================================================================


@_needs_mystran
class TestMystranRoundTrip:
    """
    Live MYSTRAN solver validation tests.

    Skipped automatically when ``mystran`` is not installed.  When the solver
    is available, these tests run the SSSS plate corpus case end-to-end and
    assert that the computed frequencies fall within 3 % of the Leissa analytic
    oracle values.
    """

    def test_mystran_binary_is_executable(self):
        """mystran must be found on PATH and must exit successfully on --help."""
        import subprocess
        result = subprocess.run(
            ["mystran", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Most solvers exit 0 or 1 on --help; the key check is that it runs.
        assert result.returncode in (0, 1), (
            f"mystran --help exited with unexpected code {result.returncode}"
        )

    def test_ssss_plate_modal_first_three_frequencies(self):
        """
        SSSS plate modal analysis: first 3 frequencies within 3% of
        Leissa (1969) NASA SP-160, Table 4.1 analytic oracle.
        """
        corpus = _load_corpus()
        cases = corpus.build_corpus()
        case = next(c for c in cases if c.name == "ssss_plate_modal")

        MystranBridge = _load_bridge()
        bridge = MystranBridge()

        # Translate SSSS BCs (DOF 3 only) for the bridge — the bridge
        # currently uses the "fixed" type for the BDF writer path.
        # For a live SSSS run we supply the correct DOF mask via a custom
        # BC that the bridge's _write_bdf_modal handles.
        bcs = [
            {
                "type": "fixed",
                "node_ids": case.boundary_conditions[0]["node_ids"],
            }
        ]

        result = bridge.solve(
            mesh=case.mesh,
            materials=case.materials,
            boundary_conditions=bcs,
            analysis_type="modal",
        )

        assert result.ok, (
            f"MystranBridge.solve returned ok=False: {result.errors}"
        )
        assert result.status != "pending", "Unexpected pending result with mystran on PATH"

        freqs = result.frequencies
        assert len(freqs) >= 3, (
            f"Expected at least 3 frequencies; got {len(freqs)}: {freqs}"
        )

        oracle = case.expected_frequencies_hz
        tol = case.tolerance
        for i in range(3):
            f_fem = freqs[i]
            f_ref = oracle[i]
            rel_err = abs(f_fem - f_ref) / f_ref
            assert rel_err <= tol, (
                f"Mode {i+1}: FEM {f_fem:.2f} Hz deviates {rel_err*100:.1f}% "
                f"from Leissa oracle {f_ref:.2f} Hz "
                f"(tolerance {tol*100:.0f}%)"
            )

    def test_result_has_eigenvalues(self):
        """
        Eigenvalues (rad²/s²) must be present, positive, and consistent
        with the returned frequencies: ω = 2π f, eigenvalue ≈ ω².
        """
        corpus = _load_corpus()
        cases = corpus.build_corpus()
        case = next(c for c in cases if c.name == "ssss_plate_modal")

        MystranBridge = _load_bridge()
        bridge = MystranBridge()
        bcs = [{"type": "fixed", "node_ids": case.boundary_conditions[0]["node_ids"]}]

        result = bridge.solve(mesh=case.mesh, materials=case.materials,
                              boundary_conditions=bcs, analysis_type="modal")
        assert result.ok

        evs = result.eigenvalues
        freqs = result.frequencies
        assert len(evs) == len(freqs), (
            f"eigenvalues length {len(evs)} != frequencies length {len(freqs)}"
        )
        for ev, f in zip(evs, freqs):
            assert ev > 0, f"Non-positive eigenvalue: {ev}"
            omega_from_ev = math.sqrt(ev)
            omega_from_f = 2.0 * math.pi * f
            rel = abs(omega_from_ev - omega_from_f) / omega_from_f
            assert rel < 0.01, (
                f"Inconsistency: √(eigenvalue)={omega_from_ev:.4f} rad/s "
                f"vs 2πf={omega_from_f:.4f} rad/s (1% tolerance)"
            )


# ===========================================================================
# 4. Pending-sentinel test (monkeypatch — always run)
# ===========================================================================


class TestPendingSentinel:
    """
    When mystran is not on PATH, MystranBridge.solve must return a pending
    sentinel without raising, suitable for graceful degradation.
    """

    def test_pending_when_mystran_absent(self, monkeypatch):
        """solve() returns status='pending' when mystran binary is absent."""
        import kerf_fem.mystran_bridge as mb
        monkeypatch.setattr(shutil, "which", lambda _: None)
        mb._MYSTRAN_AVAILABLE = None  # reset cache

        MystranBridge = _load_bridge()
        bridge = MystranBridge()

        result = bridge.solve(
            mesh={"nodes": [(0, 0, 0)], "elements": []},
            materials={"E": 200e9, "nu": 0.3, "rho": 7850.0},
            boundary_conditions=[],
            analysis_type="modal",
        )

        assert result.status == "pending", (
            f"Expected status='pending', got {result.status!r}"
        )
        assert not result.ok, "ok must be False when status='pending'"
        assert any(
            "mystran" in w.lower() or "path" in w.lower()
            for w in result.warnings
        ), f"Warning must mention mystran or PATH: {result.warnings}"

    def test_pending_for_linear_static_when_absent(self, monkeypatch):
        """Pending sentinel applies to all analysis_types, not just modal."""
        import kerf_fem.mystran_bridge as mb
        monkeypatch.setattr(shutil, "which", lambda _: None)
        mb._MYSTRAN_AVAILABLE = None

        MystranBridge = _load_bridge()
        bridge = MystranBridge()

        result = bridge.solve(
            mesh={"nodes": [(0, 0, 0)], "elements": []},
            materials={"E": 200e9, "nu": 0.3, "rho": 7850.0},
            boundary_conditions=[],
            analysis_type="linear_static",
        )
        assert result.status == "pending"

    def test_unsupported_analysis_type_fails(self, monkeypatch):
        """
        Unknown analysis_type should return status='failed' with a descriptive
        error (not raise).  This is tested without monkeypatching mystran so
        it exercises the type-dispatch code path when the solver IS on PATH
        — OR we patch it to be available.
        """
        import kerf_fem.mystran_bridge as mb
        # Force the solver to appear available so the code reaches type dispatch.
        monkeypatch.setattr(mb, "_MYSTRAN_AVAILABLE", True)

        MystranBridge = _load_bridge()
        bridge = MystranBridge()

        result = bridge.solve(
            mesh={"nodes": [(0, 0, 0)], "elements": []},
            materials={},
            boundary_conditions=[],
            analysis_type="nonlinear_contact",
        )
        assert result.status == "failed", (
            f"Expected status='failed' for unknown analysis_type, got {result.status!r}"
        )
        assert not result.ok

    def test_to_dict_serialisable(self, monkeypatch):
        """MystranResult.to_dict() must return a plain dict (JSON-serialisable)."""
        import json
        import kerf_fem.mystran_bridge as mb
        monkeypatch.setattr(shutil, "which", lambda _: None)
        mb._MYSTRAN_AVAILABLE = None

        MystranBridge = _load_bridge()
        result = MystranBridge().solve(
            mesh={}, materials={}, boundary_conditions=[],
            analysis_type="modal",
        )
        d = result.to_dict()
        assert isinstance(d, dict)
        # Must be JSON-serialisable
        json.dumps(d)
