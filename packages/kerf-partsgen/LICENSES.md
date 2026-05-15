# Licensing & token hygiene — kerf-partsgen

## The code is MIT and original

Everything under `packages/kerf-partsgen/` — the pipeline **and** every
authored generator under `src/kerf_partsgen/generators/` — is original work
licensed **MIT**, the same as the Kerf repo root (`/LICENSE`).

## Standard dimensions are facts, not copyrightable

A generator's `SIZES` table holds the *tabulated dimensions* of a
standardised part (e.g. ISO 7089 outer Ø / thickness per metric size).
Dimensional facts of a public engineering standard are **not
copyrightable** — only a particular creative *expression* (the standard
document's prose, typesetting, drawings) is. The generators do not copy any
standard's text, drawings, or layout; they encode the bare numeric facts and
build geometry with original code. Cite the standard number (`ISO 7089`) for
traceability; that is a factual reference, not a reproduction.

We deliberately do **not** vendor or scrape any standards body's PDF, any
manufacturer CAD file, or any third-party parts catalogue. (Third-party
fetch/convert lives in the separate `kerf-parts` package and is out of
scope here.)

## Generated part data is never committed

The `enumerate` / `seed` phases write solids (`.step`), thumbnails and
metadata into the repo-root `.parts-out/` directory, which is **gitignored**
(`/.parts-out/` in `/.gitignore`). Generated geometry is reproducible at any
time from the committed generator + table with **zero tokens**, so there is
no reason to commit it and every reason not to (bloat, churn, review noise).

The only part data that *is* committed is the small `PartDoc` JSON the
`seed` step emits into Kerf's existing `seed/publishers/parts/` location —
metadata only (name / category / measured bbox+volume / which generator
reproduces it), no mesh, reviewed and committed by a human.

## Token model (also in README.md)

Tokens are spent **only** in the `author` phase, **only once per part
family**: 1 author call + at most 2 bounded repair calls, then the family is
marked `FAILED` and skipped. There is no per-part / per-SKU LLM call and no
unbounded loop. `enumerate`, `seed`, and every re-run cost **zero tokens**.
The contributor brings their own API key (`ANTHROPIC_API_KEY`); no secret is
ever hardcoded or committed.
