# kerf-imports · iges_reader.py

> **Straggler — source not yet implemented.**
>
> A dedicated `packages/kerf-imports/src/kerf_imports/iges_reader.py` module
> does not exist on the `refactor` branch. IGES import is not yet supported
> in kerf-imports; it is a planned future addition.

## Planned interface

```python
from kerf_imports.iges_reader import parse_iges

result = parse_iges(iges_bytes)
# planned: {ok, entity_count, bodies, surfaces, curves, warnings}
```

## Standards reference

- ASME Y14.26M / IGES 5.3 (Initial Graphics Exchange Specification)
- Note: IGES was superseded by STEP (ISO 10303) for most new workflows;
  consider AP242 as the preferred exchange format.
