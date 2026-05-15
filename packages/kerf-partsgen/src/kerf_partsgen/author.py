"""The ``author`` phase — the ONLY place tokens are ever spent.

Cost model (also in README):

  * 1 author call per part FAMILY (never per part / per SKU), plus
  * at most ``MAX_REPAIRS`` (= 2) repair calls if the authored generator
    fails the local verification gate.

After ``1 + MAX_REPAIRS`` attempts the family is marked ``FAILED`` and we
move on — there is no unbounded loop, ever.  ``enumerate`` / ``seed`` and all
re-runs spend zero tokens.

The LLM never sees per-size dimensions and is never called per size.  It
authors *one parametric Python module* that (a) freezes the family's
authoritative dimension table and (b) builds geometry by composing
:mod:`kerf_partsgen.kernel` (Kerf's OCCT facade) — committed, human-reviewed
MIT code.  The committed diff IS the correctness audit.

LLM plumbing: we reuse Kerf's existing client
(``kerf_chat.llm.AnthropicProvider`` + ``CompleteRequest`` / ``Message``)
when importable, else a minimal direct ``anthropic`` call.  Key + model come
from the environment (``ANTHROPIC_API_KEY``, ``KERF_PARTSGEN_MODEL``) —
contributor BYO, never hardcoded.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass

from kerf_partsgen.enumerate import enumerate_family
from kerf_partsgen.loader import generator_path
from kerf_partsgen.spec import FamilyResult

MAX_REPAIRS = 2
DEFAULT_MODEL = "claude-opus-4-7"  # correctness matters; bounded so cost is fine

_CODE_FENCE_RE = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL)


@dataclass
class AuthorOutcome:
    family_id: str
    status: str          # "AUTHORED" | "FAILED"
    attempts: int        # LLM calls actually made (1 + repairs)
    generator_path: str
    detail: str = ""


# ── prompt ─────────────────────────────────────────────────────────────────

_SYSTEM = """You author ONE parametric generator module for a single \
standard-parts family for the Kerf CAD library. You are called ONCE per \
family (never per size). Output a complete Python module, nothing else.

Hard requirements:
- Expose exactly: FAMILY (dict), SIZES (list[dict]), build(row) (function).
- FAMILY keys: family_id, name, standard, domain, category, units="mm".
- SIZES: one dict per catalogued size from the cited standard's OWN
  dimension table. Transcribe the REAL tabulated dimensions (these are
  uncopyrightable facts). Each row: {"size": "<label>", "params": {...mm...},
  "expect": {"bbox_mm": [x,y,z], "volume_mm3": <approx float or null>}}.
  bbox_mm is the nominal overall bounding box; volume_mm3 may be null when
  awkward to hand-figure (bbox + watertight still gate it).
- build(row) is PURE: read row["params"], compose ONLY the kernel facade
  below, return its GeneratedPart. No I/O, no network, no globals, no mesh
  freehanding, no extra imports beyond `from kerf_partsgen import kernel`.

kernel facade (the ONLY geometry API you may call):
  kernel.box(length,width,height) -> GeneratedPart
  kernel.cylinder(radius,height) -> GeneratedPart
  kernel.hex_prism(across_flats,height) -> GeneratedPart   # by wrench size
  kernel.sketch_circle(diameter).pad(distance) / .revolve(angle_deg)
  kernel.sketch_polygon([(x,y),...]).pad(distance) / .revolve(angle_deg)
  kernel.sketch_regular_polygon(n,across_flats).pad(distance)
  kernel.union(a,b) / kernel.cut(a,b) / kernel.intersect(a,b)
  kernel.translate(p,dx,dy,dz)
  kernel.chamfer_top_edge(p,length)
All units mm. Threads are modelled as the plain cylindrical shank at the
nominal major diameter (libraries do not cut real helical threads).
Output ONLY the module (optionally in one ```python fence)."""


def _build_user_prompt(family_label: str, standard_hint: str,
                        domain: str, prior_error: str | None) -> str:
    base = (
        f"Family: {family_label}\n"
        f"Referenced standard: {standard_hint}\n"
        f"Wishlist domain: {domain}\n"
        f"Author the generator module now. Use the standard's own size table."
    )
    if prior_error:
        base += (
            "\n\nYOUR PREVIOUS MODULE FAILED THE LOCAL VERIFICATION GATE. "
            "Fix it and resend the FULL corrected module. Failure detail:\n"
            f"{prior_error}"
        )
    return base


def _extract_module(text: str) -> str:
    m = _CODE_FENCE_RE.search(text)
    return (m.group(1) if m else text).strip() + "\n"


# ── LLM call (reuse Kerf's client; fall back to a thin direct client) ──────


def _resolve_model() -> str:
    return os.environ.get("KERF_PARTSGEN_MODEL", DEFAULT_MODEL)


def _call_llm(system: str, user: str, model: str, api_key: str) -> str:
    """Single completion. Prefers kerf_chat.llm; else minimal anthropic."""
    try:
        from kerf_chat.llm import (  # type: ignore
            AnthropicProvider,
            CompleteRequest,
            Message,
        )

        provider = AnthropicProvider(api_key)
        resp = provider.complete(
            CompleteRequest(
                model=model,
                system=system,
                messages=[Message(role="user", content=user)],
                max_tokens=8192,
                temperature=0.0,
            )
        )
        return resp.content
    except ImportError:
        import anthropic  # thin fallback; same env key

        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model,
            system=system,
            max_tokens=8192,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            b.text for b in resp.content if getattr(b, "type", "") == "text"
        )


# ── author with bounded repair ────────────────────────────────────────────


def _gate_failure_text(fr: FamilyResult) -> str | None:
    if fr.error:
        return fr.error
    fails = [v for v in fr.variants if v.status == "FAIL"]
    if not fails:
        return None
    lines = [f"{len(fails)}/{len(fr.variants)} sizes FAILED the gate:"]
    for v in fails[:5]:
        lines.append(f"- size {v.size}: " + "; ".join(v.reasons))
    return "\n".join(lines)


def author_family(
    family_id: str,
    family_label: str,
    standard_hint: str,
    repo_root: str,
    *,
    domain: str = "mechanical",
    gen_dir: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    llm_call=_call_llm,
) -> AuthorOutcome:
    """Author one family with a bounded repair budget.

    ``llm_call(system, user, model, api_key) -> str`` is injectable so tests
    mock it (no network, no live LLM). On success the generator file is
    written and validated by a real local ``enumerate`` of its own table.
    """
    key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return AuthorOutcome(
            family_id=family_id, status="FAILED", attempts=0,
            generator_path=generator_path(family_id, gen_dir),
            detail="no ANTHROPIC_API_KEY (author is the only phase needing one)",
        )
    mdl = model or _resolve_model()
    dest = generator_path(family_id, gen_dir)
    os.makedirs(os.path.dirname(dest), exist_ok=True)

    prior_error: str | None = None
    attempts = 0
    for attempt in range(1 + MAX_REPAIRS):
        attempts += 1
        user = _build_user_prompt(family_label, standard_hint, domain, prior_error)
        raw = llm_call(_SYSTEM, user, mdl, key)
        module_src = _extract_module(raw)

        # write to a temp file, validate by loading + enumerating its OWN
        # table through the real gate before committing it to gen_dir.
        tmp_dir = tempfile.mkdtemp(prefix="kpg_author_")
        tmp_path = os.path.join(tmp_dir, f"{family_id}.py")
        with open(tmp_path, "w", encoding="utf-8") as fh:
            fh.write(module_src)

        fr = enumerate_family(
            family_id, repo_root, gen_dir=tmp_dir, domain=domain
        )
        failure = _gate_failure_text(fr)
        if failure is None and fr.variants:
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(module_src)
            return AuthorOutcome(
                family_id=family_id, status="AUTHORED", attempts=attempts,
                generator_path=dest,
                detail=f"{fr.passed} sizes pass the gate",
            )
        prior_error = failure or "generator produced no variants"

    return AuthorOutcome(
        family_id=family_id, status="FAILED", attempts=attempts,
        generator_path=dest,
        detail=f"gate still failing after {attempts} attempts: {prior_error}",
    )
