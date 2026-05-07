# Getting started

Install Kerf, create a project, edit a JSCAD file, see the model render.

## Install

Pick the path that suits you. Self-host needs a Postgres database; cloud is the
hosted version at kerf.app (no install).

### Homebrew (recommended)

```sh
brew install exolution/tap/kerf
```

This drops a single `kerf` binary on your `$PATH`. The frontend is embedded in
the binary.

### curl

```sh
curl -fsSL https://kerf.app/install.sh | sh
```

Same binary, downloaded straight from GitHub Releases.

### From source (dev mode)

```sh
git clone https://github.com/exolution/kerf
cd kerf
npm install
npm run init           # writes kerf.toml from kerf.example.toml
createdb kerf          # Postgres on localhost:5432
npm run migrate
npm run dev            # vite :5173 + go server :8080
```

Open <http://localhost:5173>.

## First-run config

Kerf reads a single `kerf.toml`. The `init` script writes one with defaults; at
minimum, set:

```toml
[auth]
optional = true            # single-user local mode — no signup screen

[llm.anthropic]
api_key = "sk-ant-..."     # or [llm.openai], [llm.gemini], [llm.moonshot]
```

`auth.optional = true` is for personal local installs only. For multi-user
deploys, leave it `false` and let users sign up.

The full schema lives in `kerf.example.toml` at the repo root.

## Create your first project

1. Open Kerf, click **New project**, name it `hello-cube`.
2. The default `main.jscad` opens with a starter cuboid. The 3D viewport on the
   right renders it as you type.

<!-- screenshot: editor with the default cuboid loaded -->

## Edit JSCAD

Replace the file content with:

```js
import { primitives, transforms, booleans } from '@jscad/modeling'

export default function () {
  const base   = primitives.cuboid({ size: [40, 40, 8] })
  const post   = transforms.translate(
    [0, 0, 12],
    primitives.cylinder({ radius: 6, height: 24 })
  )
  const body   = booleans.union(base, post)
  return [{ id: 'body', geom: body }]
}
```

Save (auto-saves on idle). The viewport re-renders within ~250 ms — Kerf
debounces re-evaluation based on file size, so a 5-line file feels instant and
a 5000-line one waits a beat.

<!-- screenshot: cube + cylinder rendered in viewport -->

## Click a part. Chat to refine.

1. Click anywhere on the rendered geometry. The clicked **Object** (here `body`)
   appears as a chip in the chat composer at the bottom right.
2. Type: *"add a 2 mm fillet around the top edge of the post"* and hit send.
3. The LLM edits `main.jscad` via the `edit_file` tool. The new revision lands
   in the file's history (Cmd+Z to undo).

If you don't have an LLM API key, that's fine — you can still hand-edit the
file; you just won't get the chat side of the loop.

## What's next

- Concepts behind Project / File / Object — see [concepts.md](./concepts.md).
- Drawing 2D sketches with constraints — see [sketching.md](./sketching.md).
- Building assemblies of multiple parts — see [assemblies.md](./assemblies.md).
- Producing dimensioned drawings — see [drawings.md](./drawings.md).

Next: [concepts.md](./concepts.md)
