"""Automatic attribution / provenance extraction.

Every part Kerf ingests from an upstream open-source repository MUST carry,
*embedded in its own metadata*, who originally authored it — derived
automatically, never typed by hand. This module is the single, reusable,
unit-testable place that does that. Every adapter calls
:func:`build_attribution`; none of them parses ``git log`` themselves.

The authority order (a strict fallback chain — a blank author is a bug):

  1. **Per-source-file git history** (strongest "original author" signal):
     for the exact upstream file a part is derived from, scoped git log
     gives the file's *creating* commit author (``--diff-filter=A
     --follow``), the deduped set of everyone who touched it, and the last
     author/date.
  2. **Repo-level authorship**: copyright-holder lines parsed out of the
     clone's ``LICENSE`` / ``AUTHORS`` / ``CONTRIBUTORS`` files.
  3. **Manifest**: the ``parts-sources.toml`` ``source_project`` + ``license``
     with ``original_author = "unknown — see source repository"``.

Plus, when available, **in-file metadata** (e.g. a KiCad ``(generator ...)``
token) is recorded as an extra signal — never as the sole source.

Network-free: stdlib + ``subprocess`` git only. No new heavy deps.

Caveat — shallow clones: the fetcher clones with ``--depth 1``, which
truncates history so a per-file ``git log`` would only see the tip commit
and wrongly report the pinned-ref committer as the "original author". When
attribution is requested this module first calls :func:`ensure_full_history`
which runs ``git fetch --unshallow`` (falling back to repeated
``--deepen``); if the repo genuinely cannot be deepened (offline / already
truncated) the per-file result is flagged ``history_truncated = True`` and
the chain falls back to repo-level / manifest authorship rather than
emitting a misleading author.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

# Reuse the same thin git wrapper signature the fetcher uses so tests can
# inject a fake runner if they want; by default we shell out to real git
# against a real (tiny, tmp) repo, which keeps tests hermetic.
GitRunner = Callable[..., subprocess.CompletedProcess]


def run_git(args: list[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )


UNKNOWN_AUTHOR = "unknown — see source repository"


@dataclass
class FileHistory:
    """Authorship facts for one upstream file, from scoped ``git log``."""

    original_author: str = ""
    original_date: str = ""           # ISO-8601 (committer/author date, %aI)
    last_author: str = ""
    last_date: str = ""
    contributors: list[str] = field(default_factory=list)
    history_truncated: bool = False   # shallow clone we couldn't deepen
    found: bool = False               # the path had ANY history at all


# ---------------------------------------------------------------------------
# Low-level git probes
# ---------------------------------------------------------------------------

def repo_head(repo: Path, runner: GitRunner = run_git) -> str:
    """Resolved ``git rev-parse HEAD`` of the clone (the real upstream commit)."""
    cp = runner(["rev-parse", "HEAD"], cwd=repo)
    return cp.stdout.strip() if cp.returncode == 0 else ""


def repo_remote_url(repo: Path, runner: GitRunner = run_git) -> str:
    """``git remote get-url origin`` — the clone's actual remote."""
    cp = runner(["remote", "get-url", "origin"], cwd=repo)
    return cp.stdout.strip() if cp.returncode == 0 else ""


def is_shallow(repo: Path, runner: GitRunner = run_git) -> bool:
    cp = runner(["rev-parse", "--is-shallow-repository"], cwd=repo)
    return cp.returncode == 0 and cp.stdout.strip() == "true"


def is_own_git_root(repo: Path, runner: GitRunner = run_git) -> bool:
    """True only if *repo* IS a git work-tree root (not nested in an outer
    repo).

    The fetcher clones each source into its OWN repo at the cache dir root,
    so the clone's ``git rev-parse --show-toplevel`` equals the cache dir.
    The test KiCad fixtures, by contrast, live INSIDE the Kerf repo: there
    ``--show-toplevel`` would resolve to Kerf's root, not the fixtures dir.
    We must NOT attribute a part to whatever outer repo happens to enclose
    it — that would emit a wrong author/url. So provenance only trusts git
    history when the directory is its own toplevel; otherwise it falls
    through to repo-file / manifest authorship.
    """
    cp = runner(["rev-parse", "--show-toplevel"], cwd=repo)
    if cp.returncode != 0 or not cp.stdout.strip():
        return False
    try:
        return Path(cp.stdout.strip()).resolve() == Path(repo).resolve()
    except OSError:
        return False


def ensure_full_history(repo: Path, runner: GitRunner = run_git) -> bool:
    """Make per-file history meaningful on a ``--depth 1`` clone.

    Returns True if, after this call, the repo has full (or at least
    deepened) history; False if it is still shallow (offline / upstream
    refused). Callers must treat a False here as "per-file authorship may be
    truncated" and fall back accordingly — never emit a misleading author.
    """
    if not is_shallow(repo, runner):
        return True
    # Best: a single unshallow fetch.
    cp = runner(["fetch", "--unshallow"], cwd=repo)
    if cp.returncode == 0 and not is_shallow(repo, runner):
        return True
    # Fallback: progressively deepen (works even when --unshallow is refused
    # by some servers / partial clones).
    for depth in (256, 4096, 65536):
        cp = runner(["fetch", f"--deepen={depth}"], cwd=repo)
        if cp.returncode != 0:
            break
        if not is_shallow(repo, runner):
            return True
    return not is_shallow(repo, runner)


# ---------------------------------------------------------------------------
# Repo-level authorship — LICENSE / AUTHORS / CONTRIBUTORS
# ---------------------------------------------------------------------------

_COPYRIGHT_RE = re.compile(
    r"copyright\s*(?:\(c\)|©|&copy;)?\s*"
    r"(?:\d{4}(?:\s*[-,]\s*\d{4})*)?\s*[,]?\s*(.+)",
    re.IGNORECASE,
)
_AUTHOR_FILES = (
    "AUTHORS", "AUTHORS.md", "AUTHORS.txt",
    "CONTRIBUTORS", "CONTRIBUTORS.md", "CONTRIBUTORS.txt",
)
_LICENSE_FILES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "COPYING.txt")


def repo_authorship(repo: Path) -> list[str]:
    """Best-effort copyright holders parsed from LICENSE/AUTHORS/CONTRIBUTORS.

    Order: AUTHORS/CONTRIBUTORS first (those *are* an authorship list), then
    ``Copyright ... <holder>`` lines from the LICENSE/COPYING. Deduped,
    order-preserving. Returns [] if nothing usable is found.
    """
    holders: list[str] = []
    seen: set[str] = set()

    def _add(value: str) -> None:
        v = value.strip().strip(".").strip()
        # Strip a trailing "All rights reserved" tail and bracketed emails'
        # surrounding noise but keep "Name <email>".
        v = re.sub(r"\.?\s*all rights reserved\.?$", "", v, flags=re.IGNORECASE).strip()
        if v and len(v) <= 200 and v.lower() not in seen:
            seen.add(v.lower())
            holders.append(v)

    for fname in _AUTHOR_FILES:
        p = repo / fname
        if p.is_file():
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                s = line.strip().lstrip("*-#").strip()
                # Skip blanks, RST/markdown underline rules, and section
                # headings.
                if not s:
                    continue
                if not any(c.isalnum() for c in s):
                    continue  # "=====", "-----", "~~~~~" underline rules
                if s.lower().startswith(("authors", "contributors", "the ")):
                    continue
                _add(s)

    for fname in _LICENSE_FILES:
        p = repo / fname
        if p.is_file():
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                m = _COPYRIGHT_RE.search(line.strip())
                if m:
                    _add(m.group(1))

    return holders


# ---------------------------------------------------------------------------
# Per-source-file git history — the key "original author" signal
# ---------------------------------------------------------------------------

def _dedupe(seq: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for x in seq:
        x = x.strip()
        if x and x.lower() not in seen:
            seen.add(x.lower())
            out.append(x)
    return out


def file_history(
    repo: Path,
    rel_path: str,
    *,
    runner: GitRunner = run_git,
    deepen: bool = True,
) -> FileHistory:
    """Scoped ``git log`` authorship for *rel_path* inside *repo*.

    - original author/date: the file's CREATING commit
      (``git log --diff-filter=A --follow --format=%an <%ae>|%aI -- path``,
      last line == oldest add).
    - contributors: every distinct ``%an <%ae>`` that touched the path.
    - last author/date: the most recent commit for the path.

    ``deepen``: if the clone is shallow, try to unshallow first so the
    creating commit is actually visible (see :func:`ensure_full_history`).
    On an un-deepenable shallow clone the result is flagged
    ``history_truncated`` and ``found`` reflects only the tip — callers fall
    back to repo/manifest authorship instead of trusting a wrong author.
    """
    hist = FileHistory()
    rp = rel_path.replace("\\", "/").lstrip("/")
    if not rp:
        return hist

    truncated = False
    if deepen and is_shallow(repo, runner):
        truncated = not ensure_full_history(repo, runner)
    hist.history_truncated = truncated

    # All commits touching the path, newest first: "%an <%ae>|%aI".
    cp = runner(
        ["log", "--follow", "--format=%an <%ae>|%aI", "--", rp],
        cwd=repo,
    )
    lines = [ln for ln in cp.stdout.splitlines() if ln.strip()] if cp.returncode == 0 else []
    if lines:
        hist.found = True
        first_author, _, first_date = lines[0].partition("|")
        hist.last_author = first_author.strip()
        hist.last_date = first_date.strip()
        hist.contributors = _dedupe([ln.split("|", 1)[0] for ln in lines])

    # The creating commit specifically (oldest "A" against the path).
    cp_add = runner(
        ["log", "--diff-filter=A", "--follow", "--format=%an <%ae>|%aI", "--", rp],
        cwd=repo,
    )
    add_lines = (
        [ln for ln in cp_add.stdout.splitlines() if ln.strip()]
        if cp_add.returncode == 0 else []
    )
    if add_lines:
        # Multiple adds can show with --follow across renames; the LAST is
        # the original creation.
        orig_author, _, orig_date = add_lines[-1].partition("|")
        hist.original_author = orig_author.strip()
        hist.original_date = orig_date.strip()
    elif lines:
        # No explicit "A" visible (e.g. shallow tip only): the oldest commit
        # we *can* see is the best original-author proxy, but mark truncated.
        last_seen = lines[-1]
        a, _, d = last_seen.partition("|")
        hist.original_author = a.strip()
        hist.original_date = d.strip()
        if truncated or is_shallow(repo, runner):
            hist.history_truncated = True

    return hist


# ---------------------------------------------------------------------------
# Public: assemble the embedded attribution block
# ---------------------------------------------------------------------------

def _short_sha(sha: str) -> str:
    return sha[:12] if sha else ""


def _license_url(license_id: str) -> str:
    """Best-effort canonical license URL from an SPDX-ish id. No network."""
    lic = (license_id or "").strip()
    if not lic:
        return ""
    head = re.split(r"\s+(?:WITH|with)\s+|/|\+", lic)[0].strip()
    table = {
        "CC-BY-SA-4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
        "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
        "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
        "MIT": "https://opensource.org/license/mit",
        "Apache-2.0": "https://www.apache.org/licenses/LICENSE-2.0",
        "LGPL-2.1-or-later": "https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html",
        "LGPL-2.1-only": "https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html",
        "GPL-3.0-or-later": "https://www.gnu.org/licenses/gpl-3.0.html",
        "GPL-2.0-or-later": "https://www.gnu.org/licenses/old-licenses/gpl-2.0.html",
    }
    if head in table:
        return table[head]
    if head.startswith("CC-"):
        return "https://spdx.org/licenses/" + head + ".html"
    return ""


def build_attribution(
    source,  # kerf_parts.manifest.Source — typed loosely to avoid a cycle
    repo: Path,
    source_file_rel: str,
    *,
    in_file_meta: Optional[dict] = None,
    runner: GitRunner = run_git,
    retrieved_at: Optional[str] = None,
) -> dict:
    """Build the embedded ``attribution`` block for ONE part.

    This is the single entrypoint every adapter uses. It runs the full
    fallback chain and *guarantees* a non-empty ``original_author`` and
    ``source_url``. ``source_file_rel`` is the part's originating file path
    RELATIVE to the clone root (e.g. ``Device.kicad_sym`` or
    ``Resistor_SMD.pretty/R_0805_2012Metric.kicad_mod``).

    *repo* may be a non-git directory (e.g. the test KiCad fixtures dir): in
    that case the git probes return empties and the chain falls straight
    through to repo-file / manifest authorship — still never blank.
    """
    repo = Path(repo)
    when = retrieved_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest_url = getattr(source, "git_url", "") or ""
    manifest_project = getattr(source, "name", "") or ""
    manifest_license = getattr(source, "license", "") or ""
    manifest_ref = getattr(source, "ref", "") or ""

    # Only trust git history if *repo* is its OWN clone root — never an
    # outer repo that merely encloses the directory (see is_own_git_root).
    own_root = is_own_git_root(repo, runner)
    if own_root:
        head = repo_head(repo, runner)
        remote = repo_remote_url(repo, runner)
        hist = file_history(repo, source_file_rel, runner=runner)
    else:
        head = ""
        remote = ""
        hist = FileHistory()
    repo_holders = repo_authorship(repo)

    # ---- fallback chain for the original author -----------------------
    original_author = ""
    author_source = ""
    if hist.found and hist.original_author and not hist.history_truncated:
        original_author = hist.original_author
        author_source = "git-file-history"
    elif hist.found and hist.original_author and hist.history_truncated:
        # We have *an* author but only from a truncated clone — usable as a
        # weak signal, but prefer a clean repo-level holder if present.
        if repo_holders:
            original_author = repo_holders[0]
            author_source = "repo-authors-file"
        else:
            original_author = hist.original_author
            author_source = "git-file-history-truncated"
    elif repo_holders:
        original_author = repo_holders[0]
        author_source = "repo-authors-file"
    else:
        original_author = UNKNOWN_AUTHOR
        author_source = "manifest-fallback"

    # contributors: git first, else repo holders, else the chosen author.
    if hist.contributors:
        contributors = list(hist.contributors)
    elif repo_holders:
        contributors = list(repo_holders)
    else:
        contributors = [original_author] if original_author != UNKNOWN_AUTHOR else []

    upstream_commit = head or manifest_ref
    source_url = remote or manifest_url
    license_url = _license_url(manifest_license)

    attribution = {
        "source_project": manifest_project,
        "source_url": source_url,
        "manifest_url": manifest_url,
        "upstream_ref": manifest_ref,
        "upstream_commit": upstream_commit,
        "license": manifest_license,
        "license_url": license_url,
        "source_file": source_file_rel,
        "original_author": original_author,
        "original_author_date": hist.original_date,
        "contributors": contributors,
        "last_author": hist.last_author,
        "last_author_date": hist.last_date,
        "author_source": author_source,
        "history_truncated": hist.history_truncated,
        "retrieved_at": when,
    }
    if in_file_meta:
        # Recorded as an EXTRA signal only — never the sole author source.
        attribution["in_file_metadata"] = {
            k: v for k, v in in_file_meta.items() if v
        }

    attribution["attribution_text"] = _attribution_text(attribution)
    return attribution


def attach_attribution(
    source,
    repo: Path,
    part,  # kerf_parts.model.KerfPart — typed loosely to avoid a cycle
    source_file_rel: str,
    *,
    in_file_meta: Optional[dict] = None,
    runner: GitRunner = run_git,
) -> None:
    """Stamp the embedded ``attribution`` block onto *part*'s metadata.

    The ONE call every adapter (real or scaffold) uses so attribution is
    automatic and uniform: the moment an adapter constructs a KerfPart it
    calls this and the part can never leave without provenance. Keeps the
    legacy flat ``source``/``upstream_*`` keys for back-compat and sets the
    canonical structured ``attribution`` + ``attribution_text``.
    """
    attribution = build_attribution(
        source, repo, source_file_rel, in_file_meta=in_file_meta, runner=runner
    )
    md = getattr(part, "metadata", None)
    if md is None:
        md = {}
        part.metadata = md
    md.setdefault("source", getattr(source, "name", ""))
    md.setdefault("upstream_url", getattr(source, "git_url", ""))
    md.setdefault("upstream_ref", getattr(source, "ref", ""))
    md.setdefault("upstream_license", getattr(source, "license", ""))
    md["attribution"] = attribution
    md["attribution_text"] = attribution["attribution_text"]


def _attribution_text(a: dict) -> str:
    """A human one-liner that travels with the part into Workshop/BOM."""
    project = a.get("source_project") or "upstream"
    sha = _short_sha(a.get("upstream_commit", "")) or a.get("upstream_ref", "")
    lic = a.get("license") or "see source"
    author = a.get("original_author") or UNKNOWN_AUTHOR
    n = len(a.get("contributors") or [])
    at = f" @ {sha}" if sha else ""
    txt = (
        f"Part from {project}{at} ({lic}); "
        f"original author: {author}; contributors: {n}"
    )
    if a.get("history_truncated"):
        txt += " [history truncated — shallow clone]"
    return txt


# ---------------------------------------------------------------------------
# NOTICE regeneration from the SAME structured data (so they never diverge)
# ---------------------------------------------------------------------------

def notice_lines_for_parts(attributions: list[dict]) -> list[str]:
    """Render the per-part attribution section of the NOTICE from the exact
    same structured blocks embedded in the parts (single source of truth).
    """
    lines: list[str] = []
    by_project: dict[str, list[dict]] = {}
    for a in attributions:
        by_project.setdefault(a.get("source_project", "?"), []).append(a)
    for project, items in sorted(by_project.items()):
        authors = _dedupe(
            [i.get("original_author", "") for i in items if i.get("original_author")]
        )
        lic = next((i.get("license") for i in items if i.get("license")), "")
        url = next((i.get("source_url") for i in items if i.get("source_url")), "")
        sha = next(
            (i.get("upstream_commit") for i in items if i.get("upstream_commit")), ""
        )
        lines += [
            f"* {project}  ({len(items)} part(s))",
            f"    upstream : {url}",
            f"    commit   : {sha}",
            f"    license  : {lic}",
            f"    original authors ({len(authors)}):",
        ]
        for au in authors[:50]:
            lines.append(f"      - {au}")
        if len(authors) > 50:
            lines.append(f"      ... and {len(authors) - 50} more")
        lines.append("")
    return lines
