# kerf-partsgen

A **token-frugal, contributor-run** pipeline that builds an original (MIT)
parametric **standard-parts library** for the Kerf Workshop / library —
starting with mechanical standard parts (fasteners, washers, nuts, bearings,
profiles, seals…).

The expensive mistake would be calling an LLM once per *part* (per SKU).
Standard parts have *tabulated* dimensions; an LLM transcribing them per-size
hallucinates and wastes tokens. `kerf-partsgen` instead spends a tiny,
bounded amount of LLM budget **once per part family** to author a reviewable
parametric generator, then enumerates every size **deterministically with
zero tokens**.

## The two phases

### 1. `author` — the ONLY token spend (≈ once per family)

The LLM authors a **parametric generator** for a family (e.g. *ISO 4762
socket-head cap screw*) as committed, reviewable MIT Python. The generator:

* freezes the family's **authoritative standard dimension table**
  (`SIZES` — real per-size dimensions transcribed once from the standard;
  see `LICENSES.md` on why dimensions are uncopyrightable facts), and
* builds geometry by **composing Kerf's OCCT kernel facade**
  (`kerf_partsgen.kernel`) — `sketch → pad/revolve`, `box`/`cylinder`/
  `hex_prism`, `union`/`cut`/`intersect`, chamfer. It **never** freehands a
  mesh.

A bounded repair budget applies: if the authored generator fails the local
verification gate, the failure is fed back to the LLM **at most 2 times**,
then the family is marked `FAILED` and skipped. **Never an unbounded loop.**

The human reviews the generator + table **in the PR diff** — that diff *is*
the correctness audit.

### 2. `enumerate` — ZERO LLM tokens (deterministic)

For each authored generator, loop its `SIZES` table → `build(row)` →
**verification gate** → emit artifacts. Re-runs cost **zero tokens**. This
is where all the parts come from.

## Verification gate

A green checkbox must never mean "the LLM replied". For every enumerated
variant the gate **re-measures the solid off the OCCT kernel** and requires:

1. **Valid / watertight solid** — `Shape.isValid()` true, strictly positive
   volume, and a successful STEP round-trip (the same STEP `import_step`
   ingests).
2. **Bounding-box sanity** — each axis within **±20 %** of the row's
   declared `expect.bbox_mm` (axes sorted, so build orientation is
   irrelevant).
3. **Volume sanity** — within **±50 %** of `expect.volume_mm3` when the row
   declares one (rows may set it `null`; bbox + watertight still gate them).

Tolerances are loose on purpose: the table holds *nominal* catalogue
numbers, the generator adds real features (chamfers, reliefs) the nominal
numbers omit. The gate catches gross blunders (wrong magnitude, mm/inch
slip, a non-solid), not sub-micron accuracy. Tolerances live in
`verify.py` (`BBOX_TOL`, `VOLUME_TOL`).

## Commands

Run from anywhere inside the repo (repo root auto-detected).

```bash
# install the contributor toolchain (OCCT kernel via cadquery)
pip install -e 'packages/kerf-partsgen[kernel]'

# see the wishlist + per-family state + kernel backend
kerf-partsgen list

# author ONE family (the only step that needs a key + spends tokens)
export ANTHROPIC_API_KEY=sk-...                 # contributor BYO key
pip install -e 'packages/kerf-partsgen[author]' # adds the anthropic client
kerf-partsgen author iso_4762_socket_head_cap_screw

# enumerate every [ ] family — NO key, ZERO tokens — into .parts-out/
kerf-partsgen enumerate
kerf-partsgen enumerate --only iso_7089_flat_washer   # one family

# promote every [x]-approved family into Kerf's publisher seed
kerf-partsgen seed
```

`enumerate` exits non-zero if any variant FAILed, so it drops into CI.

## Token model in practice

| phase       | LLM calls                              | needs API key |
|-------------|----------------------------------------|---------------|
| `author`    | 1 per family + ≤ 2 repairs (then FAIL) | yes           |
| `enumerate` | **0**                                  | no            |
| `seed`      | **0**                                  | no            |
| any re-run  | **0**                                  | no            |

Model defaults to `claude-opus-4-7` (correctness matters; bounded so cost is
fine); override with `KERF_PARTSGEN_MODEL`. The key is read from
`ANTHROPIC_API_KEY` — never hardcoded or committed. The `author` phase
reuses Kerf's existing LLM client (`kerf_chat.llm.AnthropicProvider`) when
importable, otherwise a thin direct `anthropic` call.

## The human-tick workflow (the script never edits tracked files)

1. Wishlist `docs/parts/wishlist/mechanical.md` is **human-owned**. One row
   per family. `- [ ]` = (re)generate; `- [x]` = reviewed & approved.
2. `kerf-partsgen enumerate` writes **only** into the **gitignored**
   `.parts-out/<domain>/<family>/<size>/` (`part.step` + `meta.json` +
   `RESULT`). It prints a summary and **modifies no tracked file** and
   **never touches the markdown**.
3. The contributor eyeballs `.parts-out/`, then **by hand** flips that
   family's `- [ ]` → `- [x]` and commits that one-line change. **That tick
   is the human review record.**
4. `kerf-partsgen seed` reads `[x]` families, enumerates them, and writes
   `PartDoc` JSON into `seed/publishers/parts/` (Kerf's existing
   first-party publisher seed location — see `seed/publishers/README.md`).
   It writes *new* files for the human to review + `git add`; it never
   rewrites a tracked file itself. Loading those into the running DB is done
   by Kerf's own publishers seeder (idempotent, upsert by
   `(project, name)` into the `Common Components` project of the
   `kerf-system` workspace). No new DB schema — reuses the existing
   `kind='part'` library row.

## How to add a family

1. Add one row to `docs/parts/wishlist/mechanical.md`:
   `- [ ] my_family_id — Human Name — sizes … — ref STD 1234`.
2. `kerf-partsgen author my_family_id` (with a key) — or hand-write
   `src/kerf_partsgen/generators/my_family_id.py` following the
   `FAMILY` / `SIZES` / `build(row)` contract in
   `kerf_partsgen/spec.py` and the two committed reference generators
   (`iso_7089_flat_washer.py`, `iso_4017_hex_head_bolt.py`).
3. `kerf-partsgen enumerate --only my_family_id`, eyeball `.parts-out/`.
4. Flip the row to `- [x]`, commit the generator + that one-line tick.

## Render / thumbnail approach

Kerf's only render path is Blender Cycles (`kerf-render`) — a heavy system
binary, not contributor-hermetic. `kerf-partsgen` therefore emits a
**deterministic lightweight artifact** per variant instead of a Cycles
render: `meta.json` (declared vs **kernel-measured** bbox + volume + gate
reasons) plus the real `part.step` solid. A true textured thumbnail can be
produced later by feeding `part.step` to `kerf-render` / `import_step` in a
full Kerf env; the pipeline does not block on rendering. This is a
deliberate, documented limitation.

## Status of the committed generators

| generator                       | state                                   |
|---------------------------------|-----------------------------------------|
| `iso_7089_flat_washer.py`       | **real** — committed, 10/10 sizes PASS  |
| `iso_4017_hex_head_bolt.py`     | **real** — committed, 10/10 sizes PASS  |
| every other wishlist row        | wishlist only — `author` it             |

See `LICENSES.md` for the full licensing + token-hygiene statement.
