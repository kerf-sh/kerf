# Jewelry metal weight & casting-cost estimator

Use the `jewelry_metal_cost` tool to estimate how much a jewelry part weighs
in a given metal, what gross metal you need to order for casting, and the
total cost breakdown.

## When to use

- A user asks "how much will this ring weigh in 18k gold?" or "compare the
  casting cost in platinum vs. sterling silver"
- After building a `.feature` file or `.jscad` model, the user wants a
  quick material cost before sending to a caster
- Helping pick a metal based on cost targets ("what's the cheapest metal
  option for this pendant that still looks fine?")

## Tool inputs

```json
{
  "volume_mm3": 300.0,          // required — part volume in mm³
  "metal": "18k_yellow",        // or density_g_cm3 for custom alloys
  "metal_price_per_gram": 38.0, // user supplies; no live feed
  "labor": 80.0,                // optional bench labor
  "finishing": 20.0,            // optional finishing/rhodium
  "casting_allowance_pct": 15,  // default 15; 10–25 typical range
  "compare_metals": ["14k_yellow", "sterling_925", "platinum_950"],
  "compare_prices": {
    "14k_yellow": 30.0,
    "sterling_925": 0.95,
    "platinum_950": 55.0
  }
}
```

Either `metal` or `density_g_cm3` must be provided; `density_g_cm3` takes
priority and lets you pass the density from a `.material` file:
```
density_g_cm3 = mat["physical"]["rho_kg_m3"] / 1000.0
```

## Metal density table (g/cm³)

Sources: World Gold Council Handbook on Gold Alloys, Legor Group data sheets
(2023), Platinum Guild International, Handy & Harman, NIST, CDA.

| Key               | Metal                     | g/cm³ |
|-------------------|---------------------------|-------|
| 10k_yellow        | 10k Yellow Gold           | 11.57 |
| 14k_yellow        | 14k Yellow Gold           | 13.07 |
| 18k_yellow        | 18k Yellow Gold           | 15.58 |
| 22k_yellow        | 22k Yellow Gold           | 17.80 |
| 24k_yellow        | 24k Yellow Gold (Fine)    | 19.32 |
| 10k_white         | 10k White Gold            | 11.61 |
| 14k_white         | 14k White Gold            | 13.25 |
| 18k_white         | 18k White Gold            | 15.60 |
| 10k_rose          | 10k Rose Gold             | 11.59 |
| 14k_rose          | 14k Rose Gold             | 13.20 |
| 18k_rose          | 18k Rose Gold             | 15.45 |
| platinum_950      | Platinum 950              | 21.40 |
| palladium_950     | Palladium 950             | 11.00 |
| sterling_925      | Sterling Silver 925       | 10.36 |
| fine_silver       | Fine Silver               | 10.49 |
| titanium          | Titanium Grade 2          |  4.51 |
| brass             | Brass 70/30 CuZn          |  8.53 |
| bronze            | Bronze 90/10 CuSn         |  8.78 |

## Formulas

### Volume → net weight

```
volume_cm3  = volume_mm3 / 1000
net_grams   = density_g_cm3 × volume_cm3
```

### Net weight → dwt / ozt

```
pennyweight (dwt) = grams / 1.55517384   (1 dwt = 1/20 ozt)
troy ounce (ozt)  = grams / 31.1034768   (NIST)
```

`20 dwt = 1 ozt` is the defining relationship.

### Casting gross weight

```
gross_grams     = net_grams × (1 + casting_allowance_pct / 100)
allowance_grams = gross_grams − net_grams
```

### Cost breakdown

```
metal_cost = gross_grams × metal_price_per_gram
total_cost = metal_cost + labor + finishing
```

## Casting allowance rationale

Lost-wax casting always produces more metal waste than the finished part:

- **Sprue**: the channel connecting the model to the sprue base; 8–12% of net
  weight for typical hollow shanks, more for thick or multi-gated pieces.
- **Button**: the disc of metal that solidifies in the flask button cup; 3–5%.
- **Flashing**: thin fins at parting lines; 1–3%.

The **default 15%** is the industry midpoint for single-gate vacuum–pressure
casting of rings and pendants. Use 10% for CNC-cut wax with optimised
spruing; use 20–25% for complex multi-piece or very thick castings.

The allowance covers gross metal to **purchase from your caster** — most
small casters sell you back the recycled button metal; check with your supplier.

## Unit conversion quick reference

| From | To | Formula |
|------|----|---------|
| grams | dwt | g / 1.55517384 |
| grams | ozt | g / 31.1034768 |
| dwt   | g   | dwt × 1.55517384 |
| ozt   | g   | ozt × 31.1034768 |
| dwt   | ozt | dwt / 20 |
| mm³   | cm³ | mm³ / 1000 |

## Worked example

A plain 2 mm shank ring, size 7 (US), with a cross-section profile extruded
into a torus. OCCT `GProp_GProps.Mass()` reports **300 mm³**.

```
volume_cm3  = 300 / 1000 = 0.3 cm³
net_grams   = 15.58 × 0.3 = 4.674 g  (18k yellow gold)
net_dwt     = 4.674 / 1.55517384 ≈ 3.004 dwt
net_ozt     = 4.674 / 31.1034768 ≈ 0.150 ozt

gross_grams = 4.674 × 1.15 = 5.375 g  (15% casting allowance)
metal_cost  = 5.375 × $38/g = $204.26 (at $38/g spot-equivalent for 18k)
total_cost  = $204.26 + $80 labor + $20 finishing = $304.26
```

## Notes on metal prices

There is **no live price feed** in Kerf. Ask the user to enter a current
price per gram. Common reference points (these change daily):

- **Fine gold spot** (~$60 USD/g at $1 900/ozt; $31.10/ozt/g × price/ozt)
- **18k yellow** ≈ 75% × fine gold spot + alloy cost, typically ~$42–50/g
- **Sterling silver** ≈ ~$0.80–1.10/g
- **Platinum 950** ≈ $30–60/g (historically 1–1.5× gold)
- **Palladium 950** ≈ $25–50/g

Always remind the user that casting-house prices include alloy preparation
and may differ from spot metal cost.

## Getting volume from a model

In the OCCT worker (JavaScript side):

```js
// After the feature tree has been evaluated and the solid is in `shape`:
const props = new OCC.GProp_GProps()
OCC.brepgprop.VolumeProperties(shape, props, 1e-5)
const volumeMm3 = props.Mass()  // mm³ when model units are mm (Kerf default)
```

In the Python pyworker (if you have the shape as TopoDS_Shape):

```python
from OCC.Core.BRepGProp import brepgprop
from OCC.Core.GProp import GProp_GProps
props = GProp_GProps()
brepgprop.VolumeProperties(shape, props)
volume_mm3 = props.Mass()  # mm³ in mm-unit model
```

Pass that value directly to `jewelry_metal_cost(volume_mm3=volume_mm3, metal=...)`.
