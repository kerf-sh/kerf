# jewelry_templates — Jewelry Preset / Template Library

## Overview

Two LLM tools for dropping a complete jewelry piece into the scene from a
single chat prompt.

| Tool | Purpose |
|------|---------|
| `list_jewelry_templates` | Return the full template catalog, optionally filtered by category |
| `instantiate_jewelry_template` | Resolve a template into a parametric recipe dict with optional overrides |

---

## Quick start

```
User: "make me a solitaire engagement ring"
Agent: list_jewelry_templates → filter by rings
Agent: instantiate_jewelry_template(template_id="ring_solitaire_round")
Agent: execute each component recipe step (jewelry_create_ring_shank, jewelry_create_prong_head, …)
```

---

## Categories and template IDs

### Rings (10)

| Template ID | Name |
|-------------|------|
| `ring_solitaire_round` | Solitaire Ring — Round Brilliant |
| `ring_solitaire_oval` | Solitaire Ring — Oval Cut |
| `ring_solitaire_cushion` | Solitaire Ring — Cushion Cut |
| `ring_solitaire_emerald` | Solitaire Ring — Emerald Cut |
| `ring_three_stone` | Three-Stone Ring |
| `ring_halo` | Halo Engagement Ring |
| `ring_eternity` | Full Eternity Band |
| `ring_signet` | Classic Signet Ring |
| `ring_mens_band` | Men's Comfort-Fit Band |
| `ring_tension` | Tension-Set Ring |
| `ring_pave_band` | Pavé Band |

### Earrings (5)

| Template ID | Name |
|-------------|------|
| `earring_stud` | Diamond Stud Earrings |
| `earring_drop` | Drop Earrings |
| `earring_hoop` | Classic Hoop Earrings |
| `earring_chandelier` | Chandelier Earrings |
| `earring_huggie` | Huggie Hoop Earrings |

### Pendants (5)

| Template ID | Name |
|-------------|------|
| `pendant_solitaire` | Solitaire Pendant |
| `pendant_halo` | Halo Pendant |
| `pendant_locket` | Classic Round Locket |
| `pendant_bar` | Bar Pendant |
| `pendant_cross` | Cross Pendant |

### Bracelets (5)

| Template ID | Name |
|-------------|------|
| `bracelet_tennis` | Tennis Bracelet |
| `bracelet_charm` | Charm Bracelet |
| `bracelet_bangle` | Plain Bangle |
| `bracelet_cuff` | Wide Cuff Bracelet |
| `bracelet_link` | Curb Link Bracelet |

### Misc (5)

| Template ID | Name |
|-------------|------|
| `misc_brooch` | Oval Brooch |
| `misc_cufflink` | Round Cufflinks |
| `misc_tie_pin` | Tie Pin (Stick Pin) |
| `misc_lapel_pin` | Lapel Pin |
| `misc_signet_pendant` | Signet Pendant |

---

## Recipe schema

Each recipe dict returned by `instantiate_jewelry_template` has:

```json
{
  "template_id": "ring_solitaire_round",
  "name": "Solitaire Ring — Round Brilliant",
  "category": "rings",
  "description": "...",
  "metal": "18k_white",
  "components": [
    {
      "tool": "jewelry_create_ring_shank",
      "role": "shank",
      "params": { "ring_size": 7, "system": "US", ... }
    },
    ...
  ],
  "tags": ["engagement", "solitaire", "round", "classic", "six-prong"]
}
```

Execute each component in order: call `tool` with its `params` to append nodes
to the active `.feature` file.

---

## Overrides

The `overrides` arg lets callers customise the recipe without editing templates:

```json
{
  "metal": "14k_yellow",
  "components": [
    { "index": 0, "params": { "ring_size": 8 } }
  ]
}
```

- Top-level fields (`metal`, `name`) replace values directly.
- `components` is a list of `{"index": int, "params": dict}` patch objects;
  the patch is merged (not replaced) into the component params at that index.

---

## Valid metals and cuts

All `metal` values must be valid keys in `METAL_DENSITY_G_CM3`
(kerf_cad_core.jewelry.metal_cost).  Common choices:

| Key | Label |
|-----|-------|
| `18k_yellow` | 18k Yellow Gold |
| `18k_white` | 18k White Gold |
| `18k_rose` | 18k Rose Gold |
| `14k_yellow` | 14k Yellow Gold |
| `14k_white` | 14k White Gold |
| `platinum_950` | Platinum 950 |
| `sterling_925` | Sterling Silver 925 |

All `cut` values must be members of `GEMSTONE_CUTS`
(kerf_cad_core.jewelry.gemstones).  Common choices: `round_brilliant`,
`oval`, `cushion`, `emerald`, `princess`, `pear`, `marquise`.
