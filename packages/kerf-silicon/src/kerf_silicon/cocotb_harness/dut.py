"""
kerf_silicon.cocotb_harness.dut
================================

DUT — Design-Under-Test signal proxy.

Usage
-----
::

    dut = DUT({"clk": 0, "rst_n": 0, "data_in": 0, "data_out": 0})
    dut.clk.value = 1
    assert dut.clk.value == 1

The ``DUT`` class provides attribute-style access to a set of named signals
whose values are backed by a plain Python dict (the *shadow dict*).  When a
real simulator is attached (via ``runner.run``), signal writes are forwarded
to the simulator's native handle; in pure-Python / pytest mode they stay in
the shadow dict.

Public API (mirrors cocotb.handle.*):
  ``DUT(signal_map)``          — construct from {name: initial_value}
  ``dut.<signal>.value``       — read current value
  ``dut.<signal>.value = x``   — write (updates shadow + optional sim handle)
  ``dut._signals``             — dict of all signal proxies
"""

from __future__ import annotations

from typing import Any


class Signal:
    """A single named signal on a DUT."""

    def __init__(self, name: str, initial: Any = 0) -> None:
        self._name = name
        self._value = initial
        # Optional real-simulator handle (set by runner when available)
        self._sim_handle: Any = None

    # ------------------------------------------------------------------
    # cocotb-compatible .value property
    # ------------------------------------------------------------------

    @property
    def value(self) -> Any:
        if self._sim_handle is not None:
            return self._sim_handle.value
        return self._value

    @value.setter
    def value(self, val: Any) -> None:
        self._value = val
        if self._sim_handle is not None:
            self._sim_handle.value = val

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"Signal({self._name!r}, value={self._value!r})"

    def __int__(self) -> int:
        return int(self._value)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Signal):
            return self._value == other._value
        return self._value == other


class DUT:
    """
    Design-Under-Test proxy.

    Parameters
    ----------
    signal_map : dict[str, Any]
        Mapping of signal name → initial value.

    Examples
    --------
    ::

        dut = DUT({"clk": 0, "rst_n": 1, "q": 0})
        dut.clk.value = 1
        assert dut.clk.value == 1
    """

    def __init__(self, signal_map: dict[str, Any]) -> None:
        # Store signals privately to avoid __getattr__ recursion
        object.__setattr__(self, "_signals", {
            name: Signal(name, initial)
            for name, initial in signal_map.items()
        })

    # ------------------------------------------------------------------
    # Attribute access → Signal proxy
    # ------------------------------------------------------------------

    def __getattr__(self, name: str) -> Signal:
        signals = object.__getattribute__(self, "_signals")
        if name in signals:
            return signals[name]
        raise AttributeError(
            f"DUT has no signal {name!r}. "
            f"Available: {list(signals.keys())}"
        )

    def __setattr__(self, name: str, val: Any) -> None:
        signals = object.__getattribute__(self, "_signals")
        if name in signals:
            signals[name].value = val
        else:
            object.__setattr__(self, name, val)

    # ------------------------------------------------------------------
    # Iteration / repr
    # ------------------------------------------------------------------

    def __iter__(self):
        return iter(object.__getattribute__(self, "_signals").values())

    def __repr__(self) -> str:  # pragma: no cover
        signals = object.__getattribute__(self, "_signals")
        pairs = ", ".join(f"{k}={v.value!r}" for k, v in signals.items())
        return f"DUT({pairs})"
