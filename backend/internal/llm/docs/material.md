# Authoring `.material` files

A `.material` file declares one engineering material — Young's modulus,
density, thermal expansion, yield strength, etc. The same file is
consumed by FEM (mech + thermal), tolerance stack-up, drawing callouts,
Part defaults, and the architecture project type (building materials).

> **Tooling note:** Use `read_material` to inspect a material,
> `find_material_by_name` to fuzzy-search the project for one, and
> `set_part_material` to attach a material to a `.part` file. To create
> or hand-edit the JSON, use the standard `create_file` (kind="material")
> + `write_file` / `edit_file` after consulting this page.

## File shape

```json
{
  "version": 1,
  "name": "AISI 1018 Steel",
  "category": "metal/steel/carbon",
  "common_names": ["mild steel", "low-carbon steel"],
  "color_hex": "#7d8088",

  "mechanical": {
    "E_GPa": 205,
    "G_GPa": 80,
    "nu": 0.29,
    "yield_MPa": 370,
    "ultimate_MPa": 440,
    "elongation_pct": 15
  },

  "thermal": {
    "alpha_per_K": 11.7e-6,
    "k_W_mK": 51.9,
    "cp_J_kgK": 486,
    "T_min_C": -40,
    "T_max_C": 250
  },

  "physical": {
    "rho_kg_m3": 7870
  },

  "callout": "AISI 1018",
  "notes": "General-purpose mild steel. Source: MatWeb."
}
```

## Field rules

- `version` must be `1`.
- `name` is required and is the canonical display label
  (e.g. "AISI 1018 Steel"). It's also the BOM material aggregation key.
- `category` is a slash-delimited taxonomy path
  (`metal/steel/carbon`, `polymer/thermoplastic/abs`, …). Free-form;
  consumers can render any prefix.
- `common_names` is an array of synonyms used by `find_material_by_name`
  fuzzy search.
- `color_hex` is a CSS-style `#rrggbb` used for renderer tinting and
  drawing-shading defaults. Optional.
- All numeric fields use **SI base units**: GPa for moduli, MPa for
  strengths, kg/m³ for density, 1/K for thermal expansion, W/m·K for
  conductivity, J/kg·K for specific heat, °C for temperature limits.
- Use **`null`** for unknown / unmeasured numeric values rather than
  omitting them. Consumers render `null` as "—" instead of guessing
  zero.
- `callout` is the short label drawing tools stamp on title blocks
  (e.g. `"AISI 1018"`, `"6061-T6"`).
- `notes` is freeform; cite a handbook (MatWeb, ASM, MIL-HDBK-5) when
  possible so downstream FEM users can verify.

## Properties (v1)

| Group        | Field            | Symbol | Unit    | Notes                              |
|--------------|------------------|--------|---------|------------------------------------|
| mechanical   | `E_GPa`          | E      | GPa     | Young's modulus                    |
| mechanical   | `G_GPa`          | G      | GPa     | Shear modulus                      |
| mechanical   | `nu`             | ν      | —       | Poisson's ratio (0 ≤ ν < 0.5)      |
| mechanical   | `yield_MPa`      | σ_y    | MPa     | Yield strength                     |
| mechanical   | `ultimate_MPa`   | σ_u    | MPa     | Ultimate tensile strength          |
| mechanical   | `elongation_pct` |        | %       | Elongation at break                |
| thermal      | `alpha_per_K`    | α      | 1/K     | Linear thermal expansion           |
| thermal      | `k_W_mK`         | k      | W/m·K   | Thermal conductivity               |
| thermal      | `cp_J_kgK`       | cₚ     | J/kg·K  | Specific heat (constant pressure)  |
| thermal      | `T_min_C`        |        | °C      | Min service temp                   |
| thermal      | `T_max_C`        |        | °C      | Max service temp                   |
| physical     | `rho_kg_m3`      | ρ      | kg/m³   | Density                            |

S-N curves, stress-strain curves, and anisotropic moduli will land in
v2 — for now those are out-of-scope.

## Referencing a material from a Part

A Part file can carry an optional `material_path` field pointing at a
`.material` file's absolute path. Consumers (FEM, BOM material column,
drawing callouts) read it via the file API and look up the properties
they need.

```json
{
  "version": 1,
  "name": "Bracket, M3 mounting",
  "mpn": "BRK-M3",
  "material_path": "/library/materials/aluminum-6061-t6.material"
}
```

To attach a material to a Part, prefer the `set_part_material` tool —
it validates the path resolves to a kind='material' file before
writing. Direct `edit_file` works too if you already have the path.

## Where these come from

The hosted Kerf cluster seeds a `kerf-system/materials` Library
project with ~20 representative materials (steels, aluminums,
plastics, brass, copper, titanium). Operators run the seed once per
cluster:

```sh
npm run seed:materials
```

The seed is idempotent — re-running it skips any (project, name)
collisions, so it's safe to run after upgrades.

For materials not in the seed, drop a `.material` file into your
project library or send a PR to `seed/materials/` upstream so the
next release ships it for everyone.
