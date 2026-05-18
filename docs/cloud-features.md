# Cloud features

How Kerf Cloud and a self-hosted Kerf install differ — and where they are identical.

See [oss-cloud-separation.md](./oss-cloud-separation.md) for the canonical model and the invariants that enforce it.

---

## The simple separation principle

**Every design capability is available in both the hosted and self-hosted builds.** The difference is who runs the infrastructure, who pays the LLM bill, and which hosted-by-nature surfaces exist.

Kerf Cloud's value proposition is:

> "We already ran the work, we host it for you, and we meter the LLM."

It is never:

> "Here are features you don't get unless you pay."

---

## What is cloud-only by nature

These surfaces presuppose a hosted, multi-tenant server. They have no meaningful self-hosted equivalent.

| Surface | Why it's cloud-only |
|---|---|
| Billing and usage metering (`/billing`, `/pricing`) | A single-tenant self-host has nothing to meter or settle. Self-hosters use their own API keys directly. |
| [Workshop](./workshop.md) public project catalog | Requires a hosted server with anonymous visitors. The *capability* — your files, sharing them — is fully present locally; only the public, operator-run catalog is cloud. |
| Hosted git + GitHub sync | Additive managed convenience on top of the local version history that every install already has. See [file-revisions.md](./file-revisions.md) and [github-sync.md](./github-sync.md). |
| Operator distributor sweep | Polls DigiKey / Mouser / LCSC with operator-owned credentials. Self-hosters can configure their own credentials and run the same sweep. |
| Pre-computation workers (STEP pre-tessellation, pricing refresh) | Operator-side convenience. Self-host tessellates locally in-browser; STEP imports still work. |
| Transactional email | System emails (welcome, password reset, billing receipts). Not meaningful for a single-user local install. |
| Kerf Cloud GPU Cycles worker | Operator-run GPU farm metered against kerf_paid credits. Self-hosters run their own cycles-worker Docker image on their own GPU box, or point `KERF_BLENDER_PATH` at a local Blender install. The in-browser `three-gpu-pathtracer` fallback works on both — it requires no server at all. See [local-self-host.md §Hero Render](./local-self-host.md#hero-render--gpu-cycles-worker-t-106e). |

---

## What is never gated

No matter which tier or whether you are on Kerf Cloud or self-hosting:

- Every CAD operation: sketcher, OCCT B-rep, feature DAG, JSCAD
- Assembly, mates, drawings, GD&T
- Electronics / PCB design and DRC
- FEM, CAM, slicing, topology optimisation
- All LLM agent tools (~150 tools across 19 plugins)
- [File revision history and undo](./file-revisions.md)
- The parts library capability (browse, search, insert) — see [oss-cloud-separation.md §3](./oss-cloud-separation.md)
- The parts library backend (`/api/library/parts`) — MIT, mounted unconditionally

---

## Feature matrix

| Feature | Self-hosted (MIT) | Kerf Cloud (any tier) |
|---|---|---|
| All CAD / EDA tools | Yes | Yes |
| File revision history | Yes | Yes |
| Parts library (populate + use) | Yes — you fetch the data | Yes — operator-hosted |
| Workshop public gallery | No — no audience | Yes |
| Hosted git + GitHub sync | No — not applicable | Yes |
| Usage metering / billing | No | Yes |
| Pre-computation workers | Local fallback | Operator-run |
| Transactional email | No | Yes |
| Hero Render in-browser fallback (`three-gpu-pathtracer`) | Yes — no server needed | Yes — also available offline |
| Hero Render Blender Cycles (server-side) | Yes — BYO Blender or self-hosted Docker worker | Yes — Kerf Cloud GPU farm (kerf_paid credits) |

---

## Related pages

- [oss-cloud-separation.md](./oss-cloud-separation.md) — canonical model, invariants, audit notes
- [billing-and-credits.md](./billing-and-credits.md) — three-bucket billing, plan tiers
- [workshop.md](./workshop.md) — Workshop hub overview
- [github-sync.md](./github-sync.md) — hosted git and GitHub sync
- [file-revisions.md](./file-revisions.md) — OSS revision history
- [local-self-host.md](./local-self-host.md) — self-hosting guide
