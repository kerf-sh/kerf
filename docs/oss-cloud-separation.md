# OSS ↔ Cloud Separation — the canonical model

Status: canonical. Audited against refactor branch commit `7b139c0`
(2026-05-15). This document is the source of truth for *why* the
open-core split exists and *where exactly* the line is drawn. If code and
this document disagree, the code has a bug — file a task, do not silently
widen the line.

---

## 1. The simple-separation principle

**The only difference between self-hosted Kerf and Kerf Cloud is the
billing/metering layer plus hosted convenience. No product feature is ever
gated behind cloud or billing.**

Cloud's value proposition is, verbatim:

> "We already ran the work, we host it for you, and we meter the LLM."

It is **never**:

> "Here are features you don't get unless you pay."

Concretely:

- Every CAD operation, sketcher, OCCT kernel op, the pure-Python B-rep
  kernel (`kerf-cad-core/geom/` — valid topology, booleans, fillets,
  closest-point, SSI, parametric feature DAG, persistent face naming),
  assembly/mate, drawing, electronics/PCB, FEM, CAM, slicing,
  topology-optimization tool, LLM agent tool, file storage, version
  history, and the **parts library capability** is present and fully
  functional in the MIT self-hosted install.
- The cloud bundle adds: usage metering + three-bucket billing
  (Paystack), the hosted Workshop (public multi-user project sharing),
  hosted git + GitHub sync, the operator-run distributor sync, hosted
  transactional email, the pricing table refresh, and operator-side
  pre-computation workers (e.g. STEP pre-tessellation). None of these
  *remove* a design capability from self-host; they are either a
  metering concern or a hosted-by-nature surface (see §5).

A change that makes a self-hosted user *unable to do something a cloud
user can do — where that something is a design capability rather than
"someone else paid/hosted/metered it"* — is a **separation leak** and a
release blocker.

---

## 2. Architecture of the split

### 2.1 Dual license

- **MIT** (`/LICENSE`) covers the entire repo *except* the cloud bundle.
- **Proprietary** (`/LICENSE-CLOUD`) covers the cloud bundle: it must
  enumerate the cloud-only Python packages and the cloud frontend
  directory.

The cloud bundle is:

| Path | Role | License intent |
| --- | --- | --- |
| `packages/kerf-billing/` | Paystack payments, three-bucket spend/quota | LICENSE-CLOUD |
| `packages/kerf-cloud/` | Workshop, git, GitHub sync, email, distributor sync | LICENSE-CLOUD |
| `packages/kerf-pricing/` | LLM-cost pricing table + refresh worker | LICENSE-CLOUD |
| `src/cloud/` | Billing/Workshop/git/email/pricing React UI | LICENSE-CLOUD |

Everything else — `packages/kerf-{core,api,auth,cad-core,electronics,
fem,cam,slicing,topo,tess,imports,mates,bim,plc,wiring,chat,render,
parts,partsgen,sdk*,v1,workers}/` and all of `src/` outside `src/cloud/`
— is MIT.

> Audit note (2026-05-15): `LICENSE-CLOUD` currently scopes itself to the
> *retired* `cloud/**` and `backend/cloud/**` paths and to `src/cloud/**`,
> and never names the live `packages/kerf-{billing,cloud,pricing}/`
> packages. `kerf-billing/pyproject.toml` and `kerf-cloud/pyproject.toml`
> additionally declare `license = { text = "MIT" }`. Only
> `kerf-pricing/pyproject.toml` correctly declares
> `LicenseRef-Kerf-Cloud`. This is a licensing-scope gap, not a runtime
> leak — see the findings report. The model *intent* is the table above.

### 2.2 The dormant-manifest mechanism (the runtime gate)

Cloud Python packages are normal installable packages, but their plugin
`register()` entry-point **early-returns an empty `PluginManifest` when
`ctx.cloud_enabled` is False** and mounts no routes / starts no workers:

- `packages/kerf-billing/src/kerf_billing/plugin.py:16-23`
- `packages/kerf-cloud/src/kerf_cloud/plugin.py:16-23`
- `packages/kerf-pricing/src/kerf_pricing/plugin.py:19-26`

So even if a cloud package is physically installed, with
`cloud_enabled=False` it is inert: `provides=[]`, zero routes, zero
workers. `cloud_enabled` is config-driven (`kerf-core/config.py:64`,
default `False`), and `cloud_enabled=True` force-disables `local_mode`
(`config.py:80-84`).

OSS packages must **never** import `kerf_billing` / `kerf_cloud` /
`kerf_pricing` at module scope. The two intentional consumption points in
`kerf-api` (`routes.py:2460,2587` billing; `routes.py:4358,4438` cloud
distributors) use **lazy, function-local imports guarded by a runtime
flag** (`settings.usage_enabled`) or a None-registry guard
(`get_registry()` is only populated by the cloud plugin). With cloud off
the import line is never reached. This is a deliberate, contained seam,
not a leak — but it is the kind of seam that needs a CI guard so it
cannot silently grow (see findings).

### 2.3 `VITE_CLOUD` / `cloudEnabled` (the frontend gate)

The frontend learns its mode once, at boot, from `GET /api/config` via
`src/cloud/useCloudConfig.js` (`cloudEnabled`, `localMode`). Components
read `useCloudConfig()` and hide cloud-only UI when `cloudEnabled` is
false. This flag must **only** toggle:

- billing/pricing UI (`/billing`, `/pricing`, Paystack widgets)
- Workshop public-sharing UI (`/workshop`, `/workshop/:slug`, Publish)
- hosted git/GitHub UI (GitPanel, CommitDialog, MergeDialog)
- operator admin UI that is meaningless self-hosted (`/admin/email` SES)

It must **never** gate a design feature. (Audit finding: today it *also*
gates the parts-library catalog UI — see the findings report. That is a
leak to fix, not the intended model.)

---

## 3. Parts-library access model

The parts **library capability is identical** in cloud and self-hosted.
What differs is *who fetches the data and who carries attribution*.

### 3.1 Cloud (hosted)

The operator pre-populates and hosts the library — including KiCad and
other 3rd-party sources — and carries the CC-BY-SA attribution at serve
time. Attribution is automatic: the `kerf-parts` pipeline emits an
`ATTRIBUTION-NOTICE.txt` into its generated output, which the operator
serves alongside the catalog.

### 3.2 Local / self-hosted

Identical library *capability*: the same `/api/library/parts` endpoint
(served by the **MIT** `kerf-api`, mounted unconditionally —
`kerf-api/src/kerf_api/routes.py:5043`), the same DB schema, the same
seed pipeline. The difference: **the user fetches the data themselves.
Nothing auto-downloads.**

- `kerf-parts` is a **contributor-run CLI pipeline**, deliberately *not*
  a `kerf.plugins` runtime entry point
  (`packages/kerf-parts/pyproject.toml:22`). It exposes only console
  scripts (`kerf-parts-fetch`, `kerf-seed-parts`). Importing the package
  or booting Kerf does **not** fetch anything.
- KiCad / 3rd-party libraries **must never auto-populate locally and are
  never redistributed by Kerf.** They are CC-BY-SA-4.0 *with the KiCad
  Library Exception* (and LGPL/CC0 for BOLTS/FreeCAD-library). The
  Exception permits *using* them in designs but is **not** a grant to
  bundle the library data into an MIT repo. So Kerf only ever
  *fetches* them, per user, into a gitignored cache.

### 3.3 The legal line (memorize this)

| Pipeline | Output origin | License | May Kerf redistribute / pip-bundle it? |
| --- | --- | --- | --- |
| `kerf-partsgen` | **Original**, human-written generators; dimension tables are uncopyrightable engineering *facts* (ISO/DIN numbers cited for traceability, no standard's prose/drawings copied) | **MIT** | **Yes** — redistributable; suitable for a pip-installable pre-generated standard-parts package |
| `kerf-parts` | **Fetched** 3rd-party data (KiCad, BOLTS, FreeCAD-library) converted locally | CC-BY-SA-4.0+Exception / LGPL / CC0 (mixed) | **No** — fetch-only, never committed, never bundled, never auto-fetched. User pulls it from upstream via the CLI. |

The repo enforces this: `/.parts-cache/` and `/.parts-out/` are
gitignored (`/.gitignore:55,59`); no fetched/generated data is committed;
only `kerf-parts` code + `parts-sources.toml` + `LICENSES.md`, and (for
`kerf-partsgen`) code + metadata-only `PartDoc` JSON under
`seed/publishers/parts/`, are tracked.

---

## 4. How to get the library when self-hosting

You have two independent, complementary routes. Both populate the same
`/api/library/parts` catalog the UI reads.

### 4.1 Original standard parts (`kerf-partsgen`) — MIT, zero 3rd-party data

`kerf-partsgen` generates standard mechanical parts (ISO bolts, washers,
brackets, …) from original MIT generators. No network, no 3rd-party data,
no tokens at enumerate/seed time.

```sh
# from the repo root, in your Kerf venv
pip install -e packages/kerf-partsgen
python -m kerf_partsgen.cli enumerate         # build geometry into ./.parts-out/ (gitignored)
python -m kerf_partsgen.cli seed              # upsert into the system "Parts Library" project
```

> Recommended future convenience (spec only — not yet built): publish a
> **pip-installable pre-generated `kerf-partsgen` package** (e.g.
> `kerf-standard-parts`) that ships the already-enumerated solids +
> metadata so self-host users get standard parts with
> `pip install kerf-standard-parts && kerf-seed-standard-parts` and never
> need to run generation or bring an API key. This is legally clean
> because `kerf-partsgen` output is original/MIT. See the findings report
> for the task spec.

### 4.2 3rd-party libraries (`kerf-parts`) — you fetch them yourself

`kerf-parts` clones the pinned upstream repos in `parts-sources.toml`
(KiCad symbols/footprints/3D, BOLTS, FreeCAD-library) into a gitignored
cache *on your machine* and converts them locally. Kerf never ships this
data and never auto-fetches it.

```sh
pip install -e "packages/kerf-parts[seed]"

# fetch the pinned upstream sources into <repo_root>/.parts-cache/ (gitignored).
# KiCad packages3D is multi-GB and opt-in via --heavy.
kerf-parts-fetch                 # light sources (symbols, footprints, BOLTS, freecad-library)
kerf-parts-fetch --heavy         # also pull kicad-packages3D (large)

# convert + upsert into the system "Parts Library" project.
# An ATTRIBUTION-NOTICE.txt is written into the gitignored generated dir;
# if you operate this for others you must serve that notice (CC-BY-SA).
kerf-seed-parts
```

The result is the *same* searchable library a cloud user sees — only the
fetch + attribution responsibility moved to you, which is exactly the CC-
BY-SA + KiCad-Library-Exception requirement.

---

## 5. Cloud-only-by-nature vs never-gated (the honest accounting)

**Legitimately cloud-only by nature** (no meaning self-hosted; gating
them is correct, not a feature gate):

- **Billing / Paystack / pricing UI** (`/billing`, `/pricing`,
  `kerf-billing`, `kerf-pricing`). A single-tenant self-host has no
  metering, no ZAR settlement, no markup — there is literally nothing to
  bill. Self-host uses its own provider API keys directly.
- **Workshop public project sharing** (`/workshop`, `/workshop/:slug`,
  Publish — `kerf-cloud`). "Public, browsable, multi-user project
  sharing" presupposes a hosted multi-tenant server with anonymous
  visitors. A single-user/self-hosted instance has no audience to share
  *to*; the concept doesn't reduce to a local feature. This is **not** a
  feature gate — it is a surface that has no self-host meaning. (The
  underlying capability — your project, its files, exporting/sharing them
  — is fully present locally; only the *operator-run public catalog* is
  cloud.)
- **Hosted git + GitHub sync** (`kerf-cloud`). The OSS install already
  has full local version history (`file_revisions`). The cloud git layer
  is the hosted convenience of a managed git remote + GitHub OAuth; it is
  additive, not a replacement, and self-host loses no version-control
  *capability*.
- **Operator distributor sync** (`kerf-cloud/distributors`,
  `kerf-cloud/email`, pricing refresh worker, STEP pre-tessellation
  `AutoTessWorker`). These are operator-side pre-computation/credential-
  bearing services. Self-host keeps the *capability* (e.g.
  `kerf-tess`'s `/run-tess` route is mounted unconditionally —
  `kerf-tess/plugin.py:59-61`; the browser tessellates locally). Only
  the "we already ran it for you" worker is cloud.

**Never legitimately gated** (gating these *is* a leak):

- The **parts-library catalog** (browse/search/insert seeded library
  parts). The backend (`/api/library/parts`) is MIT and works self-
  hosted; `kerf-parts`/`kerf-partsgen` exist specifically so self-host
  users can populate it. Hiding the catalog UI behind `cloudEnabled` is a
  feature gate and contradicts §1 and §3. (Audit found this is currently
  the case — see findings report.)
- Any CAD/sketcher/assembly/drawing/electronics/FEM/CAM/topo/LLM-tool
  capability. None are gated today (verified) and none ever may be.

---

## 6. Invariants (turn these into CI/tests)

1. No OSS package imports `kerf_billing` / `kerf_cloud` / `kerf_pricing`
   at module scope; the only allowed consumption is lazy, runtime-flag-
   guarded, function-local imports in `kerf-api`.
2. `kerf-billing`, `kerf-cloud`, `kerf-pricing` `register()` return an
   empty manifest and mount nothing when `cloud_enabled=False`.
3. `kerf-parts` never fetches at import/boot/first-run — CLI invocation
   only. KiCad/3rd-party data is never committed and never auto-fetched.
4. `kerf-partsgen` commits no mesh/geometry and no copied 3rd-party
   text/drawings — code + uncopyrightable dimension tables + metadata
   JSON only.
5. `VITE_CLOUD`/`cloudEnabled` toggles only billing/Workshop/git/email/
   pricing UI — never a design feature, **including the parts library**.
6. `LICENSE-CLOUD` scope + every cloud package's `pyproject.toml`
   `license` field name the live `packages/kerf-{billing,cloud,pricing}/`
   + `src/cloud/` paths and nothing else.
