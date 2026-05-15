"""The ``enumerate`` phase — ZERO LLM tokens, fully deterministic.

For each ``[ ]`` (un-approved) family in the wishlist:

  * load its authored generator,
  * loop the committed size table,
  * call ``build(row)`` (composes :mod:`kerf_partsgen.kernel`),
  * run the verification gate,
  * emit artifacts into the **gitignored** ``<repo>/.parts-out/<domain>/
    <family>/<size>/`` : ``part.step`` + ``meta.json`` + ``RESULT`` (PASS/FAIL).

It writes ONLY under ``.parts-out/``.  It never touches a tracked file and
never touches the wishlist markdown — the contributor reviews ``.parts-out/``
and ticks ``[x]`` by hand.

Re-running this costs zero tokens.  This is where ALL the parts come from.
"""

from __future__ import annotations

import json
import os
import traceback

from kerf_partsgen import kernel
from kerf_partsgen.loader import generator_path, load_generator
from kerf_partsgen.spec import FamilyResult, VariantResult
from kerf_partsgen.verify import verify_variant
from kerf_partsgen.wishlist import WishlistRow, parse_wishlist_file


def parts_out_root(repo_root: str) -> str:
    return os.path.join(repo_root, ".parts-out")


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in str(s))


def _write_variant_artifacts(
    out_dir: str, family, row: dict, result: VariantResult
) -> None:
    os.makedirs(out_dir, exist_ok=True)
    meta = {
        "family_id": family.family_id,
        "family_name": family.name,
        "standard": family.standard,
        "size": result.size,
        "status": result.status,
        "reasons": result.reasons,
        "measured_bbox_mm": (
            list(result.measured_bbox_mm) if result.measured_bbox_mm else None
        ),
        "measured_volume_mm3": result.measured_volume_mm3,
        "declared": row.get("expect"),
        "params": row.get("params", {}),
    }
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, sort_keys=True)
    with open(os.path.join(out_dir, "RESULT"), "w", encoding="utf-8") as fh:
        fh.write(result.status + "\n")
        for r in result.reasons:
            fh.write(f"- {r}\n")


def enumerate_family(
    family_id: str,
    repo_root: str,
    *,
    gen_dir: str | None = None,
    domain: str = "mechanical",
    out_root: str | None = None,
) -> FamilyResult:
    """Enumerate one family. Deterministic, no network, no LLM.

    Artifacts go under ``<out_root or repo_root>/.parts-out/`` — always a
    gitignored tree; ``out_root`` lets callers (and tests) redirect them
    away from the working copy without affecting wishlist/generator lookup.
    """
    path = generator_path(family_id, gen_dir)
    if not os.path.isfile(path):
        return FamilyResult(
            family_id=family_id, name=family_id, standard="",
            error=f"no generator yet — run `kerf-partsgen author {family_id}`",
        )
    try:
        family = load_generator(path)
    except Exception as exc:
        return FamilyResult(
            family_id=family_id, name=family_id, standard="",
            error=f"generator invalid: {exc}",
        )

    fr = FamilyResult(
        family_id=family.family_id, name=family.name, standard=family.standard
    )
    fam_dir = os.path.join(
        parts_out_root(out_root or repo_root), domain, _slug(family.family_id)
    )

    for row in family.sizes:
        size = str(row.get("size"))
        out_dir = os.path.join(fam_dir, _slug(size))
        try:
            built = family.build(row)
        except kernel.KernelUnavailable as exc:
            vr = VariantResult(
                family_id=family.family_id, size=size, status="FAIL",
                reasons=[f"OCCT kernel unavailable: {exc}"],
            )
            vr.artifact_dir = out_dir
            _write_variant_artifacts(out_dir, family, row, vr)
            fr.variants.append(vr)
            continue
        except Exception:
            vr = VariantResult(
                family_id=family.family_id, size=size, status="FAIL",
                reasons=[
                    "build() raised:\n" + traceback.format_exc(limit=4)
                ],
            )
            vr.artifact_dir = out_dir
            _write_variant_artifacts(out_dir, family, row, vr)
            fr.variants.append(vr)
            continue

        vr = verify_variant(family.family_id, size, row, built)
        vr.artifact_dir = out_dir
        os.makedirs(out_dir, exist_ok=True)
        if vr.status == "PASS":
            try:
                built.export_step(os.path.join(out_dir, "part.step"))
            except Exception as exc:  # pragma: no cover
                vr.status = "FAIL"
                vr.reasons.append(f"STEP write failed: {exc}")
        _write_variant_artifacts(out_dir, family, row, vr)
        fr.variants.append(vr)

    return fr


def select_families(rows: list[WishlistRow], *, only: str | None) -> list[WishlistRow]:
    """``[ ]`` rows are work; ``[x]`` are skipped (already human-approved).
    ``only`` restricts to a single family_id (still must be un-approved)."""
    todo = [r for r in rows if not r.approved]
    if only:
        todo = [r for r in todo if r.family_id == only]
    return todo


def enumerate_wishlist(
    repo_root: str,
    *,
    domain: str = "mechanical",
    only: str | None = None,
    gen_dir: str | None = None,
    wishlist_path: str | None = None,
) -> list[FamilyResult]:
    wl_path = wishlist_path or os.path.join(
        repo_root, "docs", "parts", "wishlist", f"{domain}.md"
    )
    rows = parse_wishlist_file(wl_path)
    results: list[FamilyResult] = []
    for row in select_families(rows, only=only):
        results.append(
            enumerate_family(
                row.family_id, repo_root, gen_dir=gen_dir, domain=domain
            )
        )
    return results


def summarize(results: list[FamilyResult]) -> str:
    lines = []
    total_p = total_f = 0
    for fr in results:
        if fr.error:
            lines.append(f"  {fr.family_id:<34} ERROR  {fr.error}")
            continue
        total_p += fr.passed
        total_f += fr.failed
        flag = "ok " if fr.failed == 0 else "!! "
        lines.append(
            f"  {flag}{fr.family_id:<32} {fr.passed:>3} PASS / "
            f"{fr.failed:>3} FAIL  ({fr.standard})"
        )
    head = (
        f"enumerate: {len(results)} families, "
        f"{total_p} PASS / {total_f} FAIL"
    )
    return head + "\n" + "\n".join(lines) if lines else head
