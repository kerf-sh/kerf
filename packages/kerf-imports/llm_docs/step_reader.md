# kerf-imports · step_reader.py

> **Straggler — standalone source not yet implemented.**
>
> A dedicated `packages/kerf-imports/src/kerf_imports/step_reader.py` module
> does not exist on the `refactor` branch. STEP AP242 metadata extraction is
> available via `kerf_imports.heal.step_ap242_metadata()`. Full STEP geometry
> import (B-rep topology + OCCT shape reconstruction) is handled by the
> OCCT worker, not by a Python-side reader.

## Available now

```python
from kerf_imports.heal import step_ap242_metadata

meta = step_ap242_metadata(step_text)
# Returns: {file_schema, products, geometric_tolerances, pmi_items,
#           assembly_usages, warnings}
```

## Planned interface

```python
from kerf_imports.step_reader import parse_step

result = parse_step(step_bytes)
# planned: {ok, product_count, shape_count, bodies, assembly_tree, warnings}
```

## Standards reference

- ISO 10303-21: STEP physical file format
- ISO 10303-214: AP214 automotive design data
- ISO 10303-242: AP242 managed model-based 3D engineering
