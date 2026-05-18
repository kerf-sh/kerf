"""VCD (Value Change Dump) writer for VHDL simulation waveform output.

Produces IEEE 1364-2001 compliant VCD text that can be opened in GTKWave
and other waveform viewers.

VCD format overview
-------------------
The file begins with a header section:
  $timescale 1ps $end
  $scope module top $end
  $var wire 1 ! signal_name $end
  ...
  $upscope $end
  $enddefinitions $end

Followed by an initial dump:
  $dumpvars
  xsignal_name
  $end

Then timestamped value-change records:
  #100
  1!
  0"
  #200
  ...
"""
from __future__ import annotations

import io
from typing import TextIO

_STD_LOGIC_VCD = {
    "U": "x",
    "X": "x",
    "0": "0",
    "1": "1",
    "Z": "z",
    "W": "x",
    "L": "0",
    "H": "1",
    "-": "x",
}


class VCDWriter:
    """Emits VCD waveform data to a file-like object.

    Usage::

        buf = io.StringIO()
        writer = VCDWriter(buf, timescale="1ps")
        with writer:
            a_id = writer.register_var("top", "a", "wire", 1)
            b_id = writer.register_var("top", "b", "wire", 1)
            writer.change(a_id, 0, "0")
            writer.change(b_id, 0, "1")
            writer.change(a_id, 100, "1")
        vcd_text = buf.getvalue()
    """

    def __init__(
        self,
        file: TextIO | None = None,
        timescale: str = "1ps",
        comment: str = "",
    ) -> None:
        self._file: TextIO = file if file is not None else io.StringIO()
        self._timescale = timescale
        self._comment = comment
        self._vars: dict[str, tuple[str, str, str, int]] = {}
        # id_code -> (scope, name, var_type, width)
        self._id_counter = 0
        self._current_time: int = -1
        self._header_written = False
        self._closed = False
        # Buffer value changes until flush/close
        self._changes: list[tuple[int, str, str]] = []  # (time, id_code, value)

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "VCDWriter":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Variable registration
    # ------------------------------------------------------------------

    def register_var(
        self,
        scope: str,
        name: str,
        var_type: str = "wire",
        size: int = 1,
    ) -> str:
        """Register a signal variable and return its VCD id_code."""
        id_code = _id_code(self._id_counter)
        self._id_counter += 1
        self._vars[id_code] = (scope, name, var_type, size)
        return id_code

    # ------------------------------------------------------------------
    # Recording changes
    # ------------------------------------------------------------------

    def change(self, id_code: str, time_ps: int, value: str) -> None:
        """Record a value change for *id_code* at *time_ps* picoseconds.

        *value* should be a single std_logic character (e.g. "0", "1", "X").
        """
        if self._closed:
            raise RuntimeError("VCDWriter is already closed")
        vcd_val = _STD_LOGIC_VCD.get(value, "x")
        self._changes.append((time_ps, id_code, vcd_val))

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def get_text(self) -> str:
        """Return all buffered VCD text as a string.

        Flushes the writer (writes headers + all changes) without closing.
        """
        self._flush_to_file()
        pos = self._file.tell()
        self._file.seek(0)
        text = self._file.read()
        self._file.seek(pos)
        return text

    def close(self) -> None:
        """Flush remaining output and mark the writer as closed."""
        if self._closed:
            return
        self._flush_to_file()
        self._closed = True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _flush_to_file(self) -> None:
        """Write header (once) and all pending changes to the file."""
        if not self._header_written:
            self._write_header()
            self._header_written = True

        # Sort changes by time then id_code for deterministic output
        self._changes.sort(key=lambda c: (c[0], c[1]))

        for time_ps, id_code, vcd_val in self._changes:
            if time_ps != self._current_time:
                self._current_time = time_ps
                self._file.write(f"#{time_ps}\n")
            # 1-bit signals: "0!" or "1!" format
            self._file.write(f"{vcd_val}{id_code}\n")
        self._changes.clear()

    def _write_header(self) -> None:
        f = self._file

        if self._comment:
            f.write(f"$comment {self._comment} $end\n")

        f.write(f"$timescale {self._timescale} $end\n")

        # Group variables by scope
        scopes: dict[str, list[tuple[str, str, str, int, str]]] = {}
        for id_code, (scope, name, var_type, width) in self._vars.items():
            scopes.setdefault(scope, []).append((scope, name, var_type, width, id_code))

        for scope, vars_in_scope in scopes.items():
            f.write(f"$scope module {scope} $end\n")
            for _scope, name, var_type, width, id_code in vars_in_scope:
                f.write(f"$var {var_type} {width} {id_code} {name} $end\n")
            f.write("$upscope $end\n")

        f.write("$enddefinitions $end\n")

        # Initial dump — all vars as 'x' unless a change at T=0 exists
        t0_changes = {id_code: vcd_val for t, id_code, vcd_val in self._changes if t == 0}
        f.write("$dumpvars\n")
        for id_code in self._vars:
            val = t0_changes.get(id_code, "x")
            f.write(f"{val}{id_code}\n")
        f.write("$end\n")


def _id_code(n: int) -> str:
    """Generate a compact printable VCD id_code from an integer index.

    VCD id_codes use printable ASCII characters 33-126 (! through ~).
    This encodes the integer in base 94.
    """
    chars = []
    base = 94
    offset = 33  # '!'
    if n == 0:
        return chr(offset)
    while n > 0:
        chars.append(chr(n % base + offset))
        n //= base
    return "".join(reversed(chars))


def write_vcd(
    signals: dict[str, list[tuple[int, str]]],
    timescale: str = "1ps",
    scope: str = "top",
) -> str:
    """Convenience function: convert a dict of signal traces to VCD text.

    Parameters
    ----------
    signals:
        ``{signal_name: [(time_ps, value), ...]}``
    timescale:
        VCD timescale string (default ``"1ps"``).
    scope:
        Module scope name (default ``"top"``).

    Returns
    -------
    str
        Complete VCD text starting with ``$timescale``.
    """
    buf = io.StringIO()
    with VCDWriter(buf, timescale=timescale) as writer:
        ids = {name: writer.register_var(scope, name) for name in signals}
        for name, trace in signals.items():
            for time_ps, value in trace:
                writer.change(ids[name], time_ps, value)
    buf.seek(0)
    return buf.read()
