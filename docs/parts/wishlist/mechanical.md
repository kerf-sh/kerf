# Mechanical standard-parts wishlist

Human-owned. One row per part **family** (never per size). The
`kerf-partsgen` script reads this file but **never writes to it**.

- `- [ ]` — pending: `kerf-partsgen author <family_id>` then
  `kerf-partsgen enumerate` will (re)generate it into `.parts-out/`.
- `- [x]` — **you** reviewed `.parts-out/<domain>/<family>/` by hand and
  approve it. `enumerate` skips `[x]`; `seed` promotes `[x]` into the
  library. Flipping `[ ]`→`[x]` and committing that one line **is** the
  human review record.

`family_id` is the slug of the family name — text before the first dash,
lower-cased, non-alphanumerics → `_` (e.g. *ISO 7089 flat washer* →
`iso_7089_flat_washer`), or an explicit `id:<slug>` token. It maps to
`packages/kerf-partsgen/src/kerf_partsgen/generators/<family_id>.py`.

> The two `[x]` rows below ship with a committed, human-written reference
> generator + frozen dimension table and enumerate clean today. Every
> `[ ]` row is a real wishlist target with no generator yet — `author` it.

## Fasteners

- [x] ISO 4017 hex head bolt — sizes M3–M24 — ref ISO 4017
- [ ] ISO 4762 socket-head cap screw — sizes M3–M24 — ref ISO 4762
- [ ] ISO 4014 hex bolt partial thread — sizes M5–M24 — ref ISO 4014
- [ ] ISO 7380 button-head socket screw — sizes M3–M16 — ref ISO 7380
- [ ] ISO 10642 countersunk socket screw — sizes M3–M20 — ref ISO 10642
- [ ] ISO 1207 slotted cheese-head screw — sizes M1.6–M10 — ref ISO 1207
- [ ] ISO 7045 cross-recess pan-head screw — sizes M2–M10 — ref ISO 7045
- [ ] ISO 4026 hex socket set screw flat point — sizes M3–M16 — ref ISO 4026
- [ ] ISO 2009 slotted countersunk screw — sizes M2–M12 — ref ISO 2009
- [ ] DIN 571 hex lag screw — sizes 6–16 mm — ref DIN 571
- [ ] ISO 4753 metric stud bolt — sizes M5–M24 — ref ISO 4753

## Nuts

- [ ] ISO 4032 hex nut style 1 — sizes M3–M24 — ref ISO 4032
- [ ] ISO 4035 chamfered thin hex nut — sizes M3–M24 — ref ISO 4035
- [ ] ISO 7040 nylon-insert lock nut — sizes M3–M20 — ref ISO 7040
- [ ] ISO 4161 hex flange nut — sizes M5–M20 — ref ISO 4161
- [ ] DIN 1587 dome cap nut — sizes M3–M16 — ref DIN 1587
- [ ] ISO 4034 hex nut grade C — sizes M5–M36 — ref ISO 4034
- [ ] ISO 10511 prevailing-torque thin nut — sizes M3–M20 — ref ISO 10511

## Washers

- [x] ISO 7089 flat washer — sizes M3–M24 — ref ISO 7089
- [ ] ISO 7090 chamfered plain washer — sizes M3–M24 — ref ISO 7090
- [ ] ISO 7093 large series plain washer — sizes M3–M24 — ref ISO 7093
- [ ] DIN 127B split spring lock washer — sizes M3–M24 — ref DIN 127
- [ ] DIN 6798-A external-tooth lock washer — sizes M3–M16 — ref DIN 6798
- [ ] DIN 125-A plain washer — sizes M3–M24 — ref DIN 125

## Bearings

- [ ] ISO 15 deep-groove ball bearing — sizes 6000–6210 — ref ISO 15
- [ ] ISO 104 thrust ball bearing — sizes 51100–51110 — ref ISO 104
- [ ] ISO 4379 flanged sleeve bushing — sizes 6–25 mm bore — ref ISO 4379
- [ ] LM-series linear ball bushing — sizes LM6–LM30 — ref manufacturer-neutral LM

## Pins & keys

- [ ] ISO 2338 parallel dowel pin — sizes Ø1–Ø20 — ref ISO 2338
- [ ] ISO 8752 heavy spring roll pin — sizes Ø2–Ø16 — ref ISO 8752
- [ ] ISO 1234 split cotter pin — sizes Ø1–Ø10 — ref ISO 1234
- [ ] DIN 6885-A parallel drive key — sizes 2×2–25×14 — ref DIN 6885

## Profiles, seals & misc

- [ ] T-slot aluminium extrusion — sizes 2020–4040 — ref manufacturer-neutral
- [ ] AS568 nitrile O-ring — sizes -006 to -150 — ref SAE AS568
- [ ] Metric O-ring G-series — sizes 3×1.5–50×3 — ref ISO 3601
- [ ] DIN 471 external retaining ring — sizes Ø3–Ø40 — ref DIN 471
- [ ] DIN 472 internal retaining ring — sizes Ø8–Ø50 — ref DIN 472
- [ ] Ball-stud gas-strut mount — sizes M6–M10 — ref manufacturer-neutral
