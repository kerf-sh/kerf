"""kerf_core.classify — file-kind detection by extension (T-321).

``kind_for_name`` is the canonical predicate used to assign a files.kind
value when creating or uploading a plain text / source-code file.

Supported output kinds (subset relevant to this module):
  'text'    — common text / source / config files (the new kind added in T-321)
  None      — extension is not in the text list; caller should use its own logic
              or fall back to 'file'.

The mapping intentionally mirrors the EXTENSION_TO_MODE table in
src/lib/editorModes.js (frontend Monaco language-ID map) so every
extension that gets syntax highlighting also gets kind='text' in the DB.
"""

from __future__ import annotations

# All lowercase dot-prefixed extensions that should be stored as kind='text'.
TEXT_EXTENSIONS: frozenset[str] = frozenset(
    {
        # Plain text / documentation
        ".txt",
        ".md",
        ".markdown",
        ".rst",
        # Web / scripting
        ".js",
        ".mjs",
        ".cjs",
        ".ts",
        ".mts",
        ".jsx",
        ".tsx",
        ".html",
        ".htm",
        ".css",
        ".scss",
        ".less",
        # Python
        ".py",
        ".pyw",
        # C / C++ / embedded
        ".c",
        ".h",
        ".cpp",
        ".cxx",
        ".cc",
        ".hpp",
        ".hh",
        ".hxx",
        ".ino",  # Arduino sketch
        ".uno",  # ESP32/Uno variant
        # Linker scripts & hardware description
        ".ld",
        ".v",
        ".vhd",
        ".vhdl",
        # Data / config
        ".json",
        ".jsonc",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".env",
        # Shell
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        ".bat",
        ".cmd",
        ".ps1",
        # Build / make
        ".makefile",
        ".mk",
        # Ruby / Lua
        ".rb",
        ".lua",
        # SQL
        ".sql",
        # XML / SVG
        ".xml",
        ".svg",
        ".xsd",
        # Rust / Go / Java / Kotlin / Swift / Dart
        ".rs",
        ".go",
        ".java",
        ".kt",
        ".kts",
        ".swift",
        ".dart",
        # Other common text
        ".csv",
        ".log",
        ".diff",
        ".patch",
        ".dockerfile",
        ".graphql",
        ".gql",
        ".proto",
    }
)

# Dedicated Kerf file kinds that should NOT be overridden to 'text' even if
# their extension happens to appear in TEXT_EXTENSIONS (e.g. .json is text,
# but *.family.json and *.schedule.json have dedicated editor components).
# These are checked via suffix so multi-part names like 'main.assembly' work.
_DEDICATED_SUFFIXES: tuple[str, ...] = (
    ".jscad",
    ".assembly",
    ".drawing",
    ".sketch",
    ".feature",
    ".part",
    ".equations",
    ".tolerance",
    ".topo",
    ".subd",
    ".mesh",
    ".render",
    ".fem",
    ".section",
    ".family.json",
    ".schedule.json",
    ".view.json",
    ".sheet.json",
    ".duct.json",
    ".pipe.json",
    ".conduit.json",
    ".stair.json",
    ".railing.json",
    ".plc.st",
    ".quadmesh",
    ".print",
)


def kind_for_name(name: str) -> str | None:
    """Return the appropriate files.kind for a text/source file, or None.

    Args:
        name: File name or relative path (only the basename / extension matters).

    Returns:
        ``'text'``  if the file extension is a known text/source extension and
                    the file does not have a dedicated Kerf editor suffix.
        ``None``    otherwise (caller decides the kind; typical fallback is
                    ``'file'``).
    """
    if not name:
        return None

    lower = name.lower()

    # Dedicated Kerf types take priority — do not tag them as 'text'.
    for suffix in _DEDICATED_SUFFIXES:
        if lower.endswith(suffix):
            return None

    # Extension-less basenames that are well-known text files.
    base = lower.rsplit("/", 1)[-1]
    if base in ("makefile", "dockerfile", "gemfile", "rakefile", "cmakelists.txt", ".gitignore", ".gitattributes"):
        return "text"

    # Walk candidate extensions from longest to shortest (multi-part support).
    dot_idx = lower.find(".")
    if dot_idx != -1:
        start = dot_idx
        while start != -1:
            candidate = lower[start:]
            if candidate in TEXT_EXTENSIONS:
                return "text"
            start = lower.find(".", start + 1)

    return None
