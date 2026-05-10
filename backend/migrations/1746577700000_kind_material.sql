-- Add 'material' to the files.kind enumeration so engineering material
-- definitions (.material, JSON) can live alongside the rest of the
-- project tree. A 'material' file holds a JSON document of the shape:
--
--   { "version": 1, "name": "AISI 1018 Steel",
--     "category": "metal/steel/carbon",
--     "mechanical": { "E_GPa": 205, "nu": 0.29, "yield_MPa": 370, ... },
--     "thermal":    { "alpha_per_K": 11.7e-6, "k_W_mK": 51.9, ... },
--     "physical":   { "rho_kg_m3": 7870 },
--     "callout":    "AISI 1018",
--     "notes":      "..." }
--
-- Consumed downstream by FEM, tolerance studies, drawing callouts, and
-- Part defaults (a Part may carry a `material_path` pointer to one of
-- these files). See backend/internal/llm/docs/material.md.

alter table files drop constraint if exists files_kind_check;
alter table files add constraint files_kind_check check (
    kind in ('file','folder','assembly','step','drawing','sketch','part','feature','circuit','equations','material')
);
