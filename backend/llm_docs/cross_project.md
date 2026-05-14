# Cross-project parts (`external_ref`)

A mechanical Assembly Component can reference a file in a *different*
project via an `external_ref` slot. This is how a PCB project's
`board_3d` or `board_outline_2d` becomes a part inside a mechanical
assembly without copying source.

## Shape

```json
{
  "id": "comp-1",
  "name": "Main board",
  "external_ref": {
    "project_id": "<uuid>",
    "file_id":    "<uuid>",
    "kind":       "board_3d",
    "pin":        "tracking_latest",
    "last_seen_updated_at": "2026-05-09T22:31:00Z"
  }
}
```

When `external_ref` is present, the Component's local `file_id` is
ignored.

## `kind` values

- **`board_3d`** — The PCB rendered as a 3D mesh. Resolves through the
  source `.circuit.tsx`'s compile pipeline.
- **`board_outline_2d`** — The PCB outline as a 2D `.sketch` Geom2.
  Useful as a sketch to extrude / cut from inside the mechanical
  assembly. Helper `extractBoardOutline(circuitJson)` in
  `src/lib/circuitOutline.js` produces the outline.
- **`mesh`** — Any `kind='part'` file with a `model_3d` field, treated
  as a regular Part loader path.

## Pinning

- **`pin: "tracking_latest"`** — Always resolves the source file's
  HEAD content. The Update CTA uses `last_seen_updated_at` to flag
  stale references with an amber chip; click to acknowledge.
- **`pin: "<revision_uuid>"`** — Pins to a specific
  `file_revisions.id`. Source advances no longer trigger the stale
  indicator.

## LLM tool

`assembly_add_external_component(assembly_file_id, source_project_id,
source_file_id, kind, pin?)` validates source-project membership for
the caller (404 on no access) and splices a new Component with the
external_ref into the JSON.

## Resolution

`loadExternalParts(ref)` in `src/lib/assembly.js` dispatches by kind:

1. Optionally calls `library.lookupDerivedArtifact({projectId,
   fileId, derivedKind})` first (cache hit returns base64 payload).
2. On cache miss / 501, falls through to fetching the source file's
   content + recompiling.
3. The decoder is injected by the caller (`decodePayload(kind, bytes)
   → parts[]`) so `assembly.js` stays kernel-agnostic.

## Stale-indicator UX

`AssemblyEditor`'s `ExternalRefChips` renders one chip per
`tracking_latest` external ref:

- **Always:** emerald `↗ <project-name>` chip linking to the source
  project.
- **When source advanced:** amber "out of date" chip. Clicking calls
  `restampExternalRefSeen(rows, refId, liveUpdatedAt)` which updates
  `last_seen_updated_at` and clears the chip on next render.

## Known limits

- `external_ref.kind = "board_3d"` produces a JSCAD-evaluated mesh;
  STEP / IGES sources are out of scope.
- Stale-indicator click acknowledges only — there's no diff view yet.
- Cross-project membership is checked at resolve time; private source
  projects render an empty Component with a console warn.
