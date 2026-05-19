"""info_yaml.py — Build and parse the ``info.yaml`` file required by Tiny Tapeout.

The info.yaml schema (TT10 / current) contains at minimum:
  - project.title
  - project.author
  - project.description
  - project.top_module
  - project.language (Verilog / VHDL / …)
  - project.tiles (e.g. "1x1")
  - documentation.{what_it_does, how_it_works, how_to_test}

This module intentionally avoids any third-party YAML library so it can be
imported without extras.  It uses Python's stdlib ``json`` for the round-trip
test (JSON is valid YAML for simple key/value structures) and a hand-rolled
serialiser for the full file.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Required top-level keys (flat access via dot notation is checked below)
# ---------------------------------------------------------------------------

_REQUIRED_KEYS: list[tuple[str, str]] = [
    ("project", "title"),
    ("project", "author"),
    ("project", "description"),
    ("project", "top_module"),
    ("project", "language"),
    ("project", "tiles"),
]

_VALID_LANGUAGES = {"Verilog", "SystemVerilog", "VHDL", "Chisel", "Mixed"}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def build_info_dict(
    *,
    title: str,
    author: str,
    description: str,
    top_module: str,
    language: str = "Verilog",
    tiles: str = "1x1",
    what_it_does: str = "",
    how_it_works: str = "",
    how_to_test: str = "",
    extra_project: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a structured dict that maps 1-to-1 with the info.yaml schema."""
    doc = {
        "what_it_does": what_it_does,
        "how_it_works": how_it_works,
        "how_to_test": how_to_test,
    }
    proj: dict[str, Any] = {
        "title": title,
        "author": author,
        "description": description,
        "top_module": top_module,
        "language": language,
        "tiles": tiles,
    }
    if extra_project:
        proj.update(extra_project)
    return {"project": proj, "documentation": doc}


def validate_info_dict(info: dict[str, Any]) -> None:
    """Raise ``ValueError`` for any missing or malformed field in *info*."""
    for section, key in _REQUIRED_KEYS:
        section_data = info.get(section)
        if not isinstance(section_data, dict) or key not in section_data:
            raise ValueError(f"info_dict missing required field: {section}.{key}")

    lang = info["project"]["language"]
    if lang not in _VALID_LANGUAGES:
        raise ValueError(
            f"Unknown language {lang!r}. Expected one of {sorted(_VALID_LANGUAGES)}"
        )


def dump_yaml(info: dict[str, Any]) -> str:
    """Serialise *info* to a YAML string (no third-party deps)."""
    lines: list[str] = ["---"]

    def _scalar(v: Any) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        s = str(v)
        # Quote if contains special chars or is empty
        if not s or re.search(r'[:#\[\]{},&*!|>\'"\n]', s) or s.strip() != s:
            escaped = s.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return s

    def _render(obj: Any, indent: int = 0) -> list[str]:
        pad = "  " * indent
        result: list[str] = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, dict):
                    result.append(f"{pad}{k}:")
                    result.extend(_render(v, indent + 1))
                elif isinstance(v, list):
                    result.append(f"{pad}{k}:")
                    for item in v:
                        result.append(f"{pad}  - {_scalar(item)}")
                else:
                    result.append(f"{pad}{k}: {_scalar(v)}")
        return result

    lines.extend(_render(info))
    lines.append("")  # trailing newline
    return "\n".join(lines)


def load_yaml(text: str) -> dict[str, Any]:
    """Parse a simple YAML document produced by :func:`dump_yaml`.

    Supports only the subset we write: nested mappings and scalar values.
    Lists are supported at one level of indentation under a key.
    """
    # Collect non-empty, non-comment lines with their indent level
    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        stripped = raw.rstrip()
        if not stripped or stripped.lstrip().startswith("#") or stripped.strip() == "---":
            continue
        indent = len(stripped) - len(stripped.lstrip())
        lines.append((indent, stripped.lstrip()))

    def _parse_block(pos: int, min_indent: int) -> tuple[dict[str, Any], int]:
        """Parse a mapping block starting at *pos* with items at *min_indent*."""
        result: dict[str, Any] = {}
        while pos < len(lines):
            indent, content = lines[pos]
            if indent < min_indent:
                break  # back to parent
            if indent > min_indent:
                # Shouldn't happen at block entry; skip
                pos += 1
                continue

            if ":" not in content:
                pos += 1
                continue

            key, _, rest = content.partition(":")
            key = key.strip()
            rest = rest.strip()

            pos += 1
            if rest == "":
                # Value is a nested block — peek at next line's indent
                if pos < len(lines) and lines[pos][0] > indent:
                    child_indent = lines[pos][0]
                    # Check if it's a list
                    if lines[pos][1].startswith("- "):
                        items: list[Any] = []
                        while pos < len(lines) and lines[pos][0] == child_indent and lines[pos][1].startswith("- "):
                            items.append(_parse_scalar(lines[pos][1][2:]))
                            pos += 1
                        result[key] = items
                    else:
                        child, pos = _parse_block(pos, child_indent)
                        result[key] = child
                else:
                    result[key] = {}
            else:
                result[key] = _parse_scalar(rest)

        return result, pos

    if not lines:
        return {}

    root_indent = lines[0][0]
    result, _ = _parse_block(0, root_indent)
    return result


def _parse_scalar(s: str) -> Any:
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s
