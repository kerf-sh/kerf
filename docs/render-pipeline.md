# Render pipeline

Kerf has a two-tier render path: a **backend render** for high-fidelity hero
images and a **browser path tracer** for real-time previews and offline use.

**Status:** In progress — see tasks T-106a through T-106f in `tasks.md` for
the detailed implementation plan.

---

## Tier 1 — Current viewport (shipped)

The Three.js viewport already delivers production-quality real-time rendering:

- **PBR materials** — physically-based roughness/metalness material model for
  metals, dielectrics, and gemstones; used by the jewelry PBR gem/metal
  viewport materials (task #151).
- **PMREM / HDRI environment** — pre-filtered mipmapped radiance environment
  maps for accurate ambient and specular lighting.
- **ACES tonemap + bloom** — the ACES film-like tonemapper and a selective
  bloom post-process give the viewport an output-referred, cinematic look.
- **BVH raycaster** with frustum culling and `InstancedMesh` batching for
  interactive frame rates on assemblies with hundreds of identical components.

These deliver the "hero-shot" quality you see in project thumbnails and the
Workshop gallery. For most workflows this tier is sufficient.

---

## Tier 2 — Backend Cycles renderer (in progress, T-106a..f)

For presentation-quality caustics, dispersion, and full global illumination —
needed for jewelry (gem sparkle), architecture (daylighting), and automotive
(paint flake / clearcoat) — the backend tier delegates to a headless renderer
via the `kerf-render` plugin.

### T-106a — Scene translator (planned)

Translates a Kerf B-rep / mesh scene into the backend renderer format: maps
Kerf PBR material parameters (roughness, metalness, IOR, transmission) to
the backend shader graph and writes the scene to a temporary file for import.

### T-106b — Render worker (planned)

Subprocess harness inside `kerf-render` that:

1. Accepts a render job from the job queue.
2. Spawns a headless render process with the translated scene.
3. Polls for completion; cancels on timeout.
4. Stores the output image as a derived artifact on the file.

Job lifecycle: `queued → running → done | error`. Cached by scene hash so
re-renders of unchanged scenes return the stored artifact immediately.

### T-106c — Hero-render UX panel (planned)

Browser-side panel to configure and trigger a render job:

- Resolution preset (1 K / 2 K / 4 K)
- Sample count (fast preview / production)
- Environment HDR selection
- Start / cancel / download controls

Status polling uses the `/api/projects/:pid/files/:fid/render/status` endpoint.

### T-106d — Pricing meter (planned, cloud only)

Cloud installs meter render jobs in GPU-seconds and debit the `kerf_paid`
bucket at cost + markup. Self-hosted installs run the same render worker at
no metering cost — you pay only for your own compute.

See [billing-and-credits.md](./billing-and-credits.md) for the three-bucket
model; render job pricing sits inside the existing `kerf_paid` bucket.

### T-106e — Self-host Docker image + BYO path (planned)

A `Dockerfile.render` variant that bundles the renderer. Self-hosters who
want the backend tier point `[render].backend_path` in `kerf.toml` at the
executable. The self-host path mirrors the cloud path exactly — no feature
difference, no metering.

### T-106f — In-browser path tracer fallback (planned)

A `three-gpu-pathtracer`-based in-browser path tracer built on top of the
existing Three.js scene graph. It reuses the T-106a material mapping so
the in-browser result matches the backend output as closely as Web GPU
constraints allow. Progressive rendering: a noisy preview appears immediately
and refines toward the final image.

Key properties:

- Works **offline** and with self-hosted installs that have no backend renderer.
- No GPU-seconds billing (the browser tab pays).
- Resolution is capped by WebGL/WebGPU limits (typically 4 K).
- Caustics and dispersion are approximated via path tracing rather than
  full spectral transport — acceptable for most use cases.

---

## Choosing the right tier

| Scenario | Recommended tier |
|---|---|
| Interactive design review | Tier 1 — Three.js viewport |
| Workshop hero image, PDF export | Tier 1 (existing) or Tier 2 once landed |
| Jewelry caustics / sparkle | Tier 2 backend or Tier 2 browser path tracer |
| Architecture daylighting study | Tier 2 backend |
| No internet / self-hosted | Tier 1 always; Tier 2 browser if path tracer landed |

---

## Current file kind: `.render`

The `.render` file kind stores a render scene configuration (camera, environment
HDR, override materials, output resolution). The LLM can scaffold it via
`search_kerf_docs("render")`.

```json
{
  "version": 1,
  "camera": { "position": [0, 0.2, 0.5], "target": [0, 0, 0], "fov_deg": 45 },
  "environment": { "hdri": "studio_small", "intensity": 1.0, "rotation_deg": 0 },
  "resolution": [1920, 1080],
  "samples": 256
}
```

The `kerf-render` plugin owns this kind and registers the `render_scene` LLM
tool that triggers a render job.

---

## Related pages

- [architecture.md](./architecture.md) — plugin architecture; `kerf-render` plugin
- [workshop.md](./workshop.md) — hero cover images on publish
- [jewelry-workflow.md](./jewelry-workflow.md) — gem/metal PBR materials
- [billing-and-credits.md](./billing-and-credits.md) — render credit metering (cloud)
- [local-self-host.md](./local-self-host.md) — BYO render path for self-hosters
