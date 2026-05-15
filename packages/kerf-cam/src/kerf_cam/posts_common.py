"""
Shared helpers for 3-axis post-processors.

Provides:
  PostOpts3        — dataclass shared across all 3-axis posts.
  apply_tool_defaults3 — fills feed/RPM/plunge from a Tool when the
                         caller left them at sentinel values.
  tool_comment_line    — formats a tool-comment G-code line for a given
                         dialect (semicolon for LinuxCNC/GRBL,
                         parentheses for Fanuc/Mach3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from kerf_cam.tool_db import Tool


# ---------------------------------------------------------------------------
# Sentinel defaults — used by apply_tool_defaults3() to detect "not set".
# Values deliberately differ from common operator choices so an explicit
# override of 1000 mm/min is still respected.
# ---------------------------------------------------------------------------

_DEFAULT_FEED_CUT = 1000.0      # mm/min
_DEFAULT_FEED_RAPID = 5000.0    # mm/min
_DEFAULT_FEED_PLUNGE = 300.0    # mm/min
_DEFAULT_SPINDLE_RPM = 10000    # RPM


# ---------------------------------------------------------------------------
# PostOpts3
# ---------------------------------------------------------------------------

@dataclass
class PostOpts3:
    """Configuration shared across all 3-axis post-processors.

    When a ``tool`` is attached and ``apply_tool_defaults()`` is called,
    the tool's feeds/speeds backfill any field that was left at its
    default sentinel value.  PostOpts caller-supplied overrides always win.

    Dialect notes
    -------------
    linuxcnc  — ``;`` comments, ``%`` tape markers, G-code body unchanged.
    grbl      — same as linuxcnc but no ``M6`` tool-change (GRBL has no
                automatic tool changer); a ``(M6 T<n>)`` comment is
                emitted instead so the operator knows which tool to fit.
    fanuc     — N-number sequence, parenthetical ``(...)`` comments.
                ``no_n_numbers=True`` suppresses N-numbers for older
                Fanuc variants that don't accept them.
    mach3     — parenthetical comments, no ``%`` tape markers, ``M6 T<n>``
                with a separate T-call on the preceding line.
    """

    tool_number: int = 1
    feed_rapid_mm_min: float = _DEFAULT_FEED_RAPID
    feed_cut_mm_min: float = _DEFAULT_FEED_CUT
    feed_plunge_mm_min: float = _DEFAULT_FEED_PLUNGE
    spindle_rpm: int = _DEFAULT_SPINDLE_RPM
    coolant: str = "flood"          # "flood" | "mist" | "off"
    no_n_numbers: bool = False       # Fanuc only — suppress N-numbers

    # Optional resolved tool (T7 integration).
    tool: Optional["Tool"] = field(default=None, repr=False)

    def apply_tool_defaults(self) -> None:
        """Back-fill feeds/RPM from the attached Tool.

        Only fields that are still at their sentinel (default) values are
        overridden — explicit caller values are preserved.
        """
        if self.tool is None:
            return
        t = self.tool
        if self.feed_cut_mm_min == _DEFAULT_FEED_CUT and t.feed_rate_mm_min is not None:
            self.feed_cut_mm_min = t.feed_rate_mm_min
        if self.feed_plunge_mm_min == _DEFAULT_FEED_PLUNGE and t.plunge_rate_mm_min is not None:
            self.feed_plunge_mm_min = t.plunge_rate_mm_min
        if self.spindle_rpm == _DEFAULT_SPINDLE_RPM and t.effective_spindle_rpm is not None:
            self.spindle_rpm = int(t.effective_spindle_rpm)


# ---------------------------------------------------------------------------
# tool_comment_line
# ---------------------------------------------------------------------------

def tool_comment_line(tool: "Tool", dialect: str) -> str:
    """Return a single G-code comment line describing the tool.

    Parameters
    ----------
    tool    : Tool instance (T7 dataclass).
    dialect : ``"semicolon"`` → ``; tool: …``
              ``"paren"``     → ``(TOOL: …)``
    """
    body = tool.to_comment()
    if dialect == "semicolon":
        return f"; {body}"
    else:
        # Parenthetical — Fanuc/Mach3 style; upper-case by convention.
        return f"({body.upper()})"
