# Kerf Documentation

Welcome to the Kerf docs. Use the sidebar to browse topics, or search with **Ctrl+K**.

## Getting Started
- [Getting Started](getting-started) — install, first project, keyboard shortcuts
- [Concepts](concepts) — files, features, assemblies, the LLM-tool loop

## Modeling
- [Sketching](sketching) — constraints, tools, the planegcs solver
- [Assemblies](assemblies) — mates, external components, BOM
- [Drawings](drawings) — multi-sheet, GD&T, title block
- [Parametric stack](parametric) — equations, features, graph

## Domains
- [Electronics](electronics) — tscircuit, PCB, SPICE, RF, autoroute
- [Importing](imports) — KiCad, OpenSCAD, Rhino 3DM, STEP, DXF

## Reference
- [Architecture](architecture) — plugin loader, PluginContext, monorepo layout
- [Capabilities](capabilities) — every plugin's `provides=[...]` tags + personas
- [LLM Tools](llm-tools) — full tool catalogue with input/output schema
- [v1 JSON-RPC](v1-rpc) — unified RPC endpoint
- [Contributing](contributing) — dev setup, migrations, PR checklist

## Cloud
- [Cloud features](cloud) — git sync, storage, billing, workspaces
- [Cloud operator guide](cloud-operator) — deploy, migrate, secrets, email

## What's New
- [Recent releases](whats-new) — shipped features this sprint

## Plans (in design)
- [FreeCAD sketch → 3D shortcuts](plans/freecad-sketch-shortcuts) — five PartDesign-parity tools
- [Sketch → JSCAD workflow](plans/sketch-to-jscad) — mesh-side analog of `.feature`

## Legal
- [License](license) — MIT (root) + proprietary (cloud plugins)
- [Terms](terms)
- [Privacy](privacy)
