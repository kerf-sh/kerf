"""bdd.py — Binary Decision Diagram engine.

Tries to import pyeda; if unavailable, falls back to an in-house
Shannon-cofactor BDD that is sufficient for small combinational netlists
(half-adder scale, ≤ 20 gates).

Public API
----------
BDDEngine  — factory / context; use ``BDDEngine()`` to create.
  .var(name)       → BDDNode   primary-input variable
  .const(value)    → BDDNode   constant 0 or 1
  .apply_and(a, b) → BDDNode
  .apply_or(a, b)  → BDDNode
  .apply_xor(a, b) → BDDNode
  .apply_not(a)    → BDDNode
  .apply_nand(a, b)→ BDDNode
  .apply_nor(a, b) → BDDNode
  .equivalent(a, b)→ bool      — True iff BDD(a) ≡ BDD(b) for all inputs
  .satisfying_assignment(a)     → dict[str,int] | None  (None iff a == FALSE)
  .counterexample(a, b)         → dict[str,int] | None  (None iff a ≡ b)
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Try pyeda first
# ---------------------------------------------------------------------------

try:
    from pyeda.inter import exprvar, And, Or, Xor, Not, expr
    from pyeda.boolalg.expr import Expression

    _PYEDA_AVAILABLE = True
    log.debug("formal.bdd: using pyeda backend")

except ImportError:  # pragma: no cover — covered by fallback path in CI
    _PYEDA_AVAILABLE = False
    log.info(
        "formal.bdd: pyeda not available; using built-in Shannon-cofactor BDD"
    )


# ===========================================================================
# Hand-rolled BDD (ROBDD via Shannon expansion, reduced & ordered)
# ===========================================================================
#
# Representation: a node is one of
#   • Const(val)          — terminal node, val ∈ {0, 1}
#   • ITE(var, hi, lo)    — if var then hi else lo
#
# We use a unique-table (dict) so structurally equal nodes are shared.
# The ``apply`` operations recurse and memoize with the standard BDD
# cofactor reduction rules.
#
# Variable order is fixed to the declaration order (call order of ``var()``).
# For the half-adder, order doesn't matter — there are only 2 inputs.
# ===========================================================================


class _Const:
    """Terminal BDD node (0 or 1)."""

    __slots__ = ("val",)

    def __init__(self, val: int) -> None:
        self.val = val  # 0 or 1

    def __repr__(self) -> str:
        return f"Const({self.val})"

    def __hash__(self) -> int:
        return hash(self.val)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Const) and other.val == self.val


class _ITE:
    """Non-terminal BDD node: if var_index then hi else lo."""

    __slots__ = ("var_index", "hi", "lo")

    def __init__(self, var_index: int, hi: Any, lo: Any) -> None:
        self.var_index = var_index
        self.hi = hi
        self.lo = lo

    def __repr__(self) -> str:
        return f"ITE(x{self.var_index}, {self.hi!r}, {self.lo!r})"

    def __hash__(self) -> int:
        return hash((self.var_index, id(self.hi), id(self.lo)))

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, _ITE)
            and other.var_index == self.var_index
            and other.hi is self.hi
            and other.lo is self.lo
        )


_BDDNode = _Const | _ITE


class _InHouseBDDEngine:
    """Minimal reduced-ordered BDD engine (Shannon-cofactor style)."""

    def __init__(self) -> None:
        self._vars: list[str] = []          # ordered variable names
        self._var_index: dict[str, int] = {}
        self._false = _Const(0)
        self._true = _Const(1)
        # unique table: (var_index, id(hi), id(lo)) → _ITE
        self._unique: dict[tuple[int, int, int], _ITE] = {}
        # apply cache: (op, id(a), id(b)) → node
        self._apply_cache: dict[tuple[str, int, int], _BDDNode] = {}

    # ------------------------------------------------------------------ #
    # Unique table                                                         #
    # ------------------------------------------------------------------ #

    def _make(self, var_index: int, hi: _BDDNode, lo: _BDDNode) -> _BDDNode:
        """Return the canonical node for (var_index, hi, lo), merging if hi==lo."""
        if hi is lo:
            return hi  # reduced: both branches identical
        key = (var_index, id(hi), id(lo))
        node = self._unique.get(key)
        if node is None:
            node = _ITE(var_index, hi, lo)
            self._unique[key] = node
        return node

    # ------------------------------------------------------------------ #
    # Public API expected by BDDEngine wrapper below                       #
    # ------------------------------------------------------------------ #

    def var(self, name: str) -> _BDDNode:
        if name not in self._var_index:
            idx = len(self._vars)
            self._vars.append(name)
            self._var_index[name] = idx
        idx = self._var_index[name]
        return self._make(idx, self._true, self._false)

    def const(self, value: int) -> _BDDNode:
        return self._true if value else self._false

    # ------------------------------------------------------------------ #
    # BDD apply (two-argument Shannon expansion)                           #
    # ------------------------------------------------------------------ #

    def _top_var(self, a: _BDDNode, b: _BDDNode) -> int | None:
        """Return index of the top (lowest-order) variable in {a, b}."""
        ai = a.var_index if isinstance(a, _ITE) else None
        bi = b.var_index if isinstance(b, _ITE) else None
        if ai is None and bi is None:
            return None
        if ai is None:
            return bi
        if bi is None:
            return ai
        return min(ai, bi)

    def _hi(self, node: _BDDNode, idx: int) -> _BDDNode:
        """Cofactor of node when variable idx = 1."""
        if isinstance(node, _ITE) and node.var_index == idx:
            return node.hi
        return node

    def _lo(self, node: _BDDNode, idx: int) -> _BDDNode:
        """Cofactor of node when variable idx = 0."""
        if isinstance(node, _ITE) and node.var_index == idx:
            return node.lo
        return node

    def _apply(self, op: str, a: _BDDNode, b: _BDDNode) -> _BDDNode:
        cache_key = (op, id(a), id(b))
        cached = self._apply_cache.get(cache_key)
        if cached is not None:
            return cached

        result: _BDDNode

        # Terminal cases
        if isinstance(a, _Const) and isinstance(b, _Const):
            av, bv = a.val, b.val
            if op == "and":
                result = self._true if av and bv else self._false
            elif op == "or":
                result = self._true if av or bv else self._false
            elif op == "xor":
                result = self._true if av ^ bv else self._false
            else:
                raise ValueError(f"Unknown op: {op}")
        else:
            top = self._top_var(a, b)
            assert top is not None
            hi = self._apply(op, self._hi(a, top), self._hi(b, top))
            lo = self._apply(op, self._lo(a, top), self._lo(b, top))
            result = self._make(top, hi, lo)

        self._apply_cache[cache_key] = result
        return result

    def _apply_not(self, a: _BDDNode) -> _BDDNode:
        cache_key = ("not", id(a), id(a))
        cached = self._apply_cache.get(cache_key)
        if cached is not None:
            return cached
        if isinstance(a, _Const):
            result: _BDDNode = self._false if a.val else self._true
        else:
            hi = self._apply_not(a.hi)
            lo = self._apply_not(a.lo)
            result = self._make(a.var_index, hi, lo)
        self._apply_cache[cache_key] = result
        return result

    def apply_and(self, a: _BDDNode, b: _BDDNode) -> _BDDNode:
        return self._apply("and", a, b)

    def apply_or(self, a: _BDDNode, b: _BDDNode) -> _BDDNode:
        return self._apply("or", a, b)

    def apply_xor(self, a: _BDDNode, b: _BDDNode) -> _BDDNode:
        return self._apply("xor", a, b)

    def apply_not(self, a: _BDDNode) -> _BDDNode:
        return self._apply_not(a)

    def apply_nand(self, a: _BDDNode, b: _BDDNode) -> _BDDNode:
        return self._apply_not(self._apply("and", a, b))

    def apply_nor(self, a: _BDDNode, b: _BDDNode) -> _BDDNode:
        return self._apply_not(self._apply("or", a, b))

    # ------------------------------------------------------------------ #
    # Equivalence + satisfying assignment                                  #
    # ------------------------------------------------------------------ #

    def equivalent(self, a: _BDDNode, b: _BDDNode) -> bool:
        """True iff BDD(a) ≡ BDD(b) for all input assignments."""
        # After ROBDD reduction, two equivalent functions share the same node.
        # But since we index by memory identity (id()), we need the XOR check.
        diff = self._apply("xor", a, b)
        return isinstance(diff, _Const) and diff.val == 0

    def satisfying_assignment(self, node: _BDDNode) -> dict[str, int] | None:
        """Return any input assignment that makes node = 1, or None if unsatisfiable."""
        assignment: dict[int, int] = {}

        def _sat(n: _BDDNode) -> bool:
            if isinstance(n, _Const):
                return n.val == 1
            # try hi branch (var=1) first
            assignment[n.var_index] = 1
            if _sat(n.hi):
                return True
            assignment[n.var_index] = 0
            return _sat(n.lo)

        if not _sat(node):
            return None
        return {self._vars[i]: v for i, v in assignment.items()}

    def counterexample(self, a: _BDDNode, b: _BDDNode) -> dict[str, int] | None:
        """Return an input assignment where a ≠ b, or None if they are equivalent."""
        diff = self._apply("xor", a, b)
        if isinstance(diff, _Const) and diff.val == 0:
            return None
        return self.satisfying_assignment(diff)


# ===========================================================================
# pyeda-backed engine (same interface)
# ===========================================================================


class _PyedaBDDEngine:  # pragma: no cover — only used when pyeda is installed
    """Thin wrapper around pyeda's BDD/expression interface."""

    def __init__(self) -> None:
        # pyeda expressions are symbolic; equivalence via DPLL/BDD internally.
        self._vars: dict[str, Any] = {}

    def var(self, name: str) -> Any:
        if name not in self._vars:
            self._vars[name] = exprvar(name)
        return self._vars[name]

    def const(self, value: int) -> Any:
        from pyeda.inter import Zero, One  # type: ignore[import]
        return One if value else Zero

    def apply_and(self, a: Any, b: Any) -> Any:
        return And(a, b)

    def apply_or(self, a: Any, b: Any) -> Any:
        return Or(a, b)

    def apply_xor(self, a: Any, b: Any) -> Any:
        return Xor(a, b)

    def apply_not(self, a: Any) -> Any:
        return Not(a)

    def apply_nand(self, a: Any, b: Any) -> Any:
        return Not(And(a, b))

    def apply_nor(self, a: Any, b: Any) -> Any:
        return Not(Or(a, b))

    def equivalent(self, a: Any, b: Any) -> bool:
        diff = Xor(a, b)
        # If Xor simplifies to Zero, they are equivalent.
        from pyeda.inter import Zero  # type: ignore[import]
        simplified = diff.simplify()
        if simplified == Zero:
            return True
        # Check for satisfiability of the diff — if UNSAT, equivalent.
        pt = simplified.satisfy_one()
        return pt is None

    def satisfying_assignment(self, node: Any) -> dict[str, int] | None:
        pt = node.satisfy_one()
        if pt is None:
            return None
        return {str(k): int(v) for k, v in pt.items()}

    def counterexample(self, a: Any, b: Any) -> dict[str, int] | None:
        diff = Xor(a, b)
        pt = diff.satisfy_one()
        if pt is None:
            return None
        return {str(k): int(v) for k, v in pt.items()}


# ===========================================================================
# Public facade
# ===========================================================================


class BDDEngine:
    """Create a new BDD engine context.

    Automatically selects pyeda (if available) or the built-in
    Shannon-cofactor BDD.
    """

    def __init__(self) -> None:
        if _PYEDA_AVAILABLE:  # pragma: no cover
            self._impl: _InHouseBDDEngine | _PyedaBDDEngine = _PyedaBDDEngine()
        else:
            self._impl = _InHouseBDDEngine()

    # Delegate everything to the implementation.

    def var(self, name: str) -> Any:
        """Create or look up a primary-input variable by name."""
        return self._impl.var(name)

    def const(self, value: int) -> Any:
        """Return a constant BDD node (0 or 1)."""
        return self._impl.const(value)

    def apply_and(self, a: Any, b: Any) -> Any:
        return self._impl.apply_and(a, b)

    def apply_or(self, a: Any, b: Any) -> Any:
        return self._impl.apply_or(a, b)

    def apply_xor(self, a: Any, b: Any) -> Any:
        return self._impl.apply_xor(a, b)

    def apply_not(self, a: Any) -> Any:
        return self._impl.apply_not(a)

    def apply_nand(self, a: Any, b: Any) -> Any:
        return self._impl.apply_nand(a, b)

    def apply_nor(self, a: Any, b: Any) -> Any:
        return self._impl.apply_nor(a, b)

    def equivalent(self, a: Any, b: Any) -> bool:
        """True iff the two BDD nodes represent the same Boolean function."""
        return self._impl.equivalent(a, b)

    def satisfying_assignment(self, node: Any) -> dict[str, int] | None:
        """Any assignment making node = 1; None if unsatisfiable."""
        return self._impl.satisfying_assignment(node)

    def counterexample(self, a: Any, b: Any) -> dict[str, int] | None:
        """An assignment where a ≠ b; None if they are equivalent."""
        return self._impl.counterexample(a, b)
