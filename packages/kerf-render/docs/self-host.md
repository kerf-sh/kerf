# Self-hosting the Kerf Cycles Worker

This page describes how to run the Blender Cycles render worker on your own
machine or GPU box, independently of Kerf Cloud.  Two paths are supported:

1. **Docker image** — bundles Blender 4.1; GPU-accelerated (CUDA) or CPU-only.
2. **BYO Blender** — point `KERF_BLENDER_PATH` at your existing Blender
   installation; no Docker required.

---

## Docker image

### Prerequisites

- Docker 24+
- For GPU acceleration: `nvidia-container-toolkit` installed and the Docker
  daemon configured to expose GPU devices (`--gpus all`).

### Build

From the repository root:

```sh
# GPU (CUDA runtime) — ~1.8 GB image
docker build \
    -f packages/kerf-render/Dockerfile.cycles-worker \
    --build-arg GPU=true \
    -t kerf/cycles-worker:gpu \
    .

# CPU-only — ~900 MB image
docker build \
    -f packages/kerf-render/Dockerfile.cycles-worker \
    --build-arg GPU=false \
    -t kerf/cycles-worker:cpu \
    .
```

The build downloads the official Blender 4.1.1 tarball from
`download.blender.org` during the image build.  Internet access is required
unless you pre-seed the layer cache.

#### Build arguments

| Argument | Default | Description |
|---|---|---|
| `GPU` | `true` | `true` uses `nvidia/cuda:12.3.0-runtime-ubuntu22.04` as base; `false` uses plain `ubuntu:22.04` |
| `BLENDER_VER` | `4.1.1` | Blender version to download |
| `BLENDER_SHA256` | `SKIP` | Optional sha256 checksum of the tarball. Set to the published value to verify integrity. |

### Run

```sh
docker run --gpus all \
    -e KERF_API_URL=https://my-kerf.example.com \
    -e KERF_API_TOKEN=<token> \
    -e KERF_WORKER_CONCURRENCY=1 \
    kerf/cycles-worker:gpu
```

For CPU-only (omit `--gpus all`):

```sh
docker run \
    -e KERF_API_URL=https://my-kerf.example.com \
    -e KERF_API_TOKEN=<token> \
    -e KERF_WORKER_CONCURRENCY=2 \
    kerf/cycles-worker:cpu
```

#### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `KERF_API_URL` | No | — | Base URL of your Kerf API server. Leave unset for standalone / offline testing. |
| `KERF_API_TOKEN` | No | — | Auth token issued by your Kerf server. Required when `KERF_API_URL` is set. |
| `KERF_WORKER_CONCURRENCY` | No | `1` | Parallel render slots. GPU: keep at `1`. CPU-only: `2`–`4` is typical. |
| `KERF_BLENDER_PATH` | No | — | Override the bundled Blender with a BYO binary (see below). |

---

## BYO Blender path

If you already have Blender installed, you do not need Docker.  Set
`KERF_BLENDER_PATH` to the full path of your Blender executable before
starting the worker:

```sh
# macOS (.app bundle)
export KERF_BLENDER_PATH="/Applications/Blender.app/Contents/MacOS/Blender"

# Linux (manual install)
export KERF_BLENDER_PATH="/opt/blender-4.1/blender"

# Windows (WSL or native)
export KERF_BLENDER_PATH="/mnt/c/Program Files/Blender Foundation/Blender 4.1/blender.exe"

python -m kerf_render.cycles_worker
```

`cycles_worker.resolve_blender_bin()` reads (in order):

1. `KERF_BLENDER_BIN` — exported by `scripts/entrypoint.sh` inside the
   container so the binary is resolved once at startup, not per-job.
2. `KERF_BLENDER_PATH` — operator-supplied BYO path.
3. `blender` — bare command resolved via `PATH`.

Empty values are ignored so an exported-but-empty variable does not shadow
the fallback.

### BYO with Docker (volume mount)

You can also skip the bundled Blender download and mount your own:

```sh
docker run \
    -v /host/path/to/blender-4.1:/opt/byo-blender:ro \
    -e KERF_BLENDER_PATH=/opt/byo-blender/blender \
    -e KERF_API_URL=https://my-kerf.example.com \
    kerf/cycles-worker:cpu
```

This is useful when you want the container isolation without the ~300 MB
Blender layer download.

---

## Concurrency and resource tuning

| Setup | Recommended `KERF_WORKER_CONCURRENCY` |
|---|---|
| Single NVIDIA GPU (≥8 GB VRAM) | `1` — VRAM contention limits benefit |
| Dual NVIDIA GPUs | `2` (one per GPU; requires per-job device pinning — coming in a later release) |
| CPU-only, 8-core box | `2` |
| CPU-only, 32-core box | `4`–`8` (memory-bound at high parallelism) |

---

## Health check

The image includes a `HEALTHCHECK` that confirms `kerf_render` is importable:

```
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python3 -c "import kerf_render; print('ok')" || exit 1
```

In a compose / Kubernetes deployment, wait for `healthy` before sending jobs.

---

## Upgrading Blender

To pin a different Blender version, rebuild with `--build-arg BLENDER_VER=4.2.0`
(adjust the URL path prefix in the Dockerfile if the release directory changes).
Verify the tarball checksum with `--build-arg BLENDER_SHA256=<hex>`.

---

## Related pages

- [docs/local-self-host.md](../../../../docs/local-self-host.md) — full
  self-host install guide (server + database + frontend)
- [packages/kerf-render/Dockerfile.cycles-worker](../Dockerfile.cycles-worker)
- [packages/kerf-render/scripts/entrypoint.sh](../scripts/entrypoint.sh)
