# kerf-optics · paraxial lens design (ABCD matrix)

Optical design plugin implementing the paraxial ray-transfer matrix (ABCD)
formalism for multi-element thin-lens systems.

## Quick start

```python
from kerf_optics.lens_system import LensSystem, ThinLens, FreeSpace

# Single converging lens — 100 mm focal length, object at 200 mm
f = 0.1      # metres
do = 0.2
di = 1.0 / (1.0/f - 1.0/do)   # thin-lens equation → di = 0.2 m

system = LensSystem([FreeSpace(do), ThinLens(f), FreeSpace(di)])
print(system.efl())          # 0.1 m
print(system.image_distance(do))  # 0.2 m
```

## Supported element types

| Type               | Parameters                          | Description                  |
|--------------------|-------------------------------------|------------------------------|
| `ThinLens`         | `f` (m)                             | Thin lens, f > 0 converging  |
| `FreeSpace`        | `d` (m), `n` (default 1.0)          | Free-space propagation       |
| `CurvedInterface`  | `R` (m), `n1`, `n2`                 | Spherical refraction surface |
| `Mirror`           | `R` (m)                             | Spherical mirror (R > 0 concave) |
| `Aperture`         | `diameter` (m)                      | Thin aperture stop (identity) |
| `Detector`         | —                                   | Image plane (identity)       |

## ray_transfer.py — elementary ABCD matrices

```python
from kerf_optics.ray_transfer import (
    M_free, M_thin_lens, M_refraction, M_mirror, M_identity,
    system_matrix, focal_length, image_distance, trace_ray, seidel_thin_lens,
)

# Free-space propagation 100 mm in air
M = M_free(0.1, n=1.0)   # [[1, 0.1], [0, 1]]

# Thin lens f = 50 mm
M = M_thin_lens(0.05)    # [[1, 0], [-20, 1]]

# Compose a system (order: first element first)
M_sys = system_matrix([M_free(0.2), M_thin_lens(0.1), M_free(0.2)])
print(focal_length(M_sys))   # 0.1 m

# Trace a single ray (y=0.001 m, nu=0)
states = trace_ray(0.001, 0.0, [M_free(0.2), M_thin_lens(0.1), M_free(0.2)])
# states[0] = input, states[-1] = exit
```

## lens_system.py — data model

### `LensSystem`

```python
system = LensSystem()
system.append(FreeSpace(0.5))
system.append(ThinLens(0.1))

# First-order properties
print(system.efl())                          # effective focal length
print(system.image_distance(object_dist))   # image distance
print(system.back_focal_distance())         # BFD

# Ray tracing
states = system.trace(y0=0.001, u0=0.0)
spot   = system.spot_diagram(n_rays=9)

# Summary dict
info = system.summary()
```

### Factory constructors

```python
# Single thin lens (do=200 mm, f=100 mm, di=200 mm)
s = LensSystem.thin_lens(f=0.1, object_distance=0.2, image_distance=0.2)

# Two-lens telephoto
s = LensSystem.telephoto(f1=0.15, f2=-0.05, separation=0.1, object_distance=0.5)
```

## LLM tools

### `optics_trace_ray`

Trace a ray bundle through a JSON-described element list.

```json
{
  "elements": [
    {"type": "free_space", "d": 0.2},
    {"type": "thin_lens",  "f": 0.1},
    {"type": "free_space", "d": 0.2}
  ],
  "rays": [[0.001, 0.0], [0.002, 0.001]]
}
```

Returns `{efl, system_matrix:{A,B,C,D}, rays:[{y0,nu0,surfaces,final_height}], spot:{rms_spot_m}}`.

### `optics_lens_design`

First-order design from target EFL and conjugate distances.

```json
{
  "target_efl": 0.1,
  "object_distance": 0.2,
  "design_type": "single"
}
```

Returns element list + achieved EFL + image distance.

## Seidel aberration coefficients

```python
from kerf_optics.ray_transfer import seidel_thin_lens

coefs = seidel_thin_lens(
    f=0.1, n=1.5, object_distance=0.2,
    y_marginal=0.01, shape_factor=0.0,
)
print(coefs["spherical"])     # W040
print(coefs["coma"])          # W131
print(coefs["field_curvature"])  # W220
```

## Reference identities

- Thin-lens equation: `1/f = 1/di + 1/do` (real object, real image both positive)
- Two-lens EFL: `1/EFL = 1/f1 + 1/f2 - d/(f1*f2)` where d = separation
- ABCD determinant: `det(M) = n_in / n_out` (= 1 for same medium)
- Image distance from system matrix: `di = -(A*do + B) / (C*do + D)`
