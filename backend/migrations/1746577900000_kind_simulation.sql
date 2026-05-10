-- Add 'simulation' to the files.kind enumeration so SPICE simulation runs
-- (.simulation, JSON) can live alongside the .circuit.tsx that produced
-- them. A 'simulation' file holds a JSON document of the (currently
-- permissive) shape:
--
--   { "version": 1,
--     "circuit_file_id": "<uuid>",
--     "analysis": { "type": "transient", "tstep": "1us", "tstop": "10ms" },
--     "probes": [...],
--     "results": { "waveforms": [...], "warnings": [...], "errors": [...] } }
--
-- The exact result shape is intentionally not pinned here — the engine
-- (ngspice-wasm) is still a separate slice. Storing runs as a file kind
-- (rather than a companion table) makes them queryable, restorable via
-- file_revisions, and shareable on Workshop. If indexing-heavy queries
-- emerge later we can add a sidecar table; for now content lives in
-- files.content.

alter table files drop constraint if exists files_kind_check;
alter table files add constraint files_kind_check check (
    kind in ('file','folder','assembly','step','drawing','sketch','part','feature','circuit','equations','material','simulation')
);
