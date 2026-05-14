# Authoring `.script.ts` files

A `.script.ts` file is a TypeScript automation script attached to a
project. It's the Phase 1 stub of the Scripting kind: the file
round-trips end-to-end (storage, history, mirror) and renders in a
read-only Monaco viewer, but no runtime executes it yet. The eventual
engine (esbuild-wasm bundler in a Web Worker, typed `kerf.*` API, fixed
backend RPC ops) lands in a follow-up slice.

The kind shipped to confirm the schema before the runtime is wired —
mirrors the `.simulation` "engine pending" pattern (see
`simulation.md`). When the user clicks any "Run script" affordance
today, nothing executes. The file's bytes are pure source.

## File shape

A `.script.ts` is a flat TypeScript source file — no JSON envelope, no
header. The backend treats it as `kind=script` with a `.script.ts` name
suffix. Example:

```ts
// Compute the volume of every Part in the assembly.
import { kerf } from 'kerf'

for (const f of kerf.project.files) {
  if (f.kind !== 'jscad') continue
  const v = await kerf.geom.volume(f.path)
  console.log(`${f.path}: ${v.toFixed(2)} mm^3`)
}
```

The script viewer (`src/components/ScriptEditor.jsx`) is **read-only**.
The LLM edits via `write_file` / `edit_file` like any other text file;
the user edits via a future inline editor that lands with the runtime.

## The `kerf.*` API (planned, not yet wired)

When the runtime ships, scripts will receive a single typed `kerf`
import. The shape is fixed so the LLM can write scripts today against a
contract that won't change:

```ts
kerf.project.files       // Array<{ id, path, kind, name }>
kerf.project.read(path)  // Promise<string>   — file contents
kerf.project.write(path, body) // Promise<void>

kerf.geom.translate(geom, [x, y, z])
kerf.geom.union(a, b, ...)
kerf.geom.subtract(a, b, ...)
kerf.geom.intersect(a, b, ...)
kerf.geom.volume(jscadPath)     // Promise<number>  — mm^3
kerf.geom.boundingBox(jscadPath)

kerf.run(opName, args)   // Promise<any> — RPC into a fixed
                         //   allowlist of backend ops
                         //   (e.g. 'export.stl', 'bom.compute').
```

`kerf.run` is the only escape hatch: a fixed allowlist of named
operations on the backend. Scripts cannot make arbitrary network calls,
read other users' files, or import packages — the bundler ships a
single virtual `kerf` module and refuses anything else.

## Common script patterns

These are the kinds of scripts we expect users (and the LLM) to ask
for. None run today — they're examples of the eventual contract:

### Compute the volume of every Part in the assembly

```ts
import { kerf } from 'kerf'

const parts = kerf.project.files.filter((f) => f.kind === 'jscad')
const rows = await Promise.all(
  parts.map(async (p) => ({
    path: p.path,
    volume_mm3: await kerf.geom.volume(p.path),
  }))
)
console.table(rows)
```

### Batch-export every Part to STL

```ts
import { kerf } from 'kerf'

for (const f of kerf.project.files) {
  if (f.kind !== 'jscad') continue
  const stl = await kerf.run('export.stl', { file_id: f.id })
  await kerf.project.write(`exports/${f.name}.stl`, stl)
}
```

### Re-stamp every assembly Component with a fresh transform

```ts
import { kerf } from 'kerf'

const asm = JSON.parse(await kerf.project.read('/main.assembly'))
asm.components = asm.components.map((c) => ({
  ...c,
  position: [Math.round(c.position[0]), Math.round(c.position[1]), Math.round(c.position[2])],
}))
await kerf.project.write('/main.assembly', JSON.stringify(asm, null, 2))
```

The assembly mutation pattern mirrors what `assembly.md` documents — a
script is just a way to apply that pattern in bulk.

## Authoring guidance

- **Imports.** Only `import { kerf } from 'kerf'` works. The bundler
  rejects `import fs from 'fs'`, npm packages, and HTTP imports. The
  one virtual module is enough: `kerf.project` exposes the file tree,
  `kerf.geom` exposes JSCAD primitives, `kerf.run` exposes the RPC
  allowlist.
- **Async.** Every `kerf.*` call that touches the project or runs a
  backend op is async — always `await` or `.then()`. The runtime will
  cancel a script that hangs on an unhandled promise.
- **Top-level await.** Allowed. The bundler emits an async IIFE.
- **Console.** `console.log` / `console.table` flow to the script
  output panel. There is no DOM, no `window`, no `document`.
- **Path style.** All `kerf.project.*` paths are leading-slash absolute
  (`/main.assembly`, `/parts/bracket.jscad`) — same convention as
  `read_file` / `write_file`.

## Known limits

- **Engine pending.** No runtime today. The Monaco viewer is read-only
  and the script never executes. The "engine pending" amber banner in
  the editor names the missing piece (esbuild-wasm). Feel free to
  author scripts now — they round-trip cleanly and will run the moment
  the runtime lands.
- **Read-only.** The frontend editor doesn't accept edits — the LLM
  (via `edit_file` / `write_file`) is the only writer today.
- **No schedules / triggers.** Scripts run on demand only. A future
  slice may add hooks (run-on-save, run-on-publish), but the v1 runtime
  is one-shot.
- **No streaming.** A script returns when its top-level promise
  resolves. `console.log` calls during execution flush at the end, not
  live.
- **Allowlisted RPC.** `kerf.run` only accepts ops from the fixed
  backend allowlist; arbitrary endpoints aren't reachable. The list
  starts small (`export.stl`, `bom.compute`, `geom.volume`) and grows
  per-slice.
