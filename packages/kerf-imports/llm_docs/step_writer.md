# kerf-imports · step_writer.py

> **Straggler — standalone source not yet implemented.**
>
> A dedicated `packages/kerf-imports/src/kerf_imports/step_writer.py` module
> does not exist on the `refactor` branch. STEP export is handled by the
> OCCT worker (`board_step` for PCB, OCCT `WriteSTEP` for mechanical parts).

## Planned interface

```python
from kerf_imports.step_writer import export_step

step_text = export_step(model, schema="AP242", units="mm")
```

## Standards reference

- ISO 10303-21: STEP physical file format
- ISO 10303-242: AP242 (preferred for new implementations)
