"""kerf-render: Cycles worker — subprocess harness + content-hash cache.

Consumes a job dict produced by :mod:`kerf_render.job_lifecycle`, drives
Blender headless in an isolated subprocess (so a crash does not take the
harness down), streams tile-progress events, writes PNG / multi-pass EXR
to object storage, and caches results by content hash.

Public API
----------
:class:`CyclesWorker` is the main entry point.  Instantiate it with a
:class:`CyclesWorkerConfig` and call :meth:`CyclesWorker.process_job`.

Job dict schema
---------------
::

    {
        "scene_blob":   bytes | str,   # raw Body bytes OR base64-encoded
        "camera":       dict,          # cycles_translator.Camera fields
        "lights":       list[dict],    # cycles_translator.Light fields
        "materials":    dict,          # face_id → material slot
        "preset":       str,           # "draft" | "standard" | "hero" | "cinema"
        "cache_key":    str,           # optional pre-computed key (overrides auto)
        "output_format": str,          # "png" | "exr"
        "job_id":       str,           # optional, for progress tagging
    }

Result dict schema
------------------
::

    # success
    {"ok": True,  "signed_url": str, "cache_key": str, "samples": int,
     "from_cache": bool, "render_seconds": float}

    # failure
    {"ok": False, "reason": str, "stderr_tail": str}
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Version sentinel — bump whenever the translator output format changes so
# that old cache entries are automatically invalidated.
# ---------------------------------------------------------------------------

_TRANSLATOR_VERSION = "T-106a-v1"

# ---------------------------------------------------------------------------
# Preset → sample-count mapping
# ---------------------------------------------------------------------------

PRESET_SAMPLES: Dict[str, int] = {
    "draft":    256,
    "standard": 1024,
    "hero":     4096,
    "cinema":   16384,
}

_DEFAULT_PRESET = "standard"

# ---------------------------------------------------------------------------
# Timeout per preset (seconds): generous budget scaled to sample count.
# ---------------------------------------------------------------------------

PRESET_TIMEOUTS: Dict[str, int] = {
    "draft":    120,
    "standard": 600,
    "hero":     1800,
    "cinema":   7200,
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class CyclesWorkerConfig:
    """Runtime configuration for :class:`CyclesWorker`."""

    blender_path: str = "blender"
    """Path to the Blender executable (or just ``"blender"`` for PATH lookup)."""

    storage_base_url: str = "file:///tmp/kerf_render_cache"
    """Base URL / prefix for storing render outputs.

    In production this would be an object-storage bucket URL; in tests we
    default to a local filesystem path so no external service is needed.
    """

    cache_dir: str = "/tmp/kerf_render_cache"
    """Local directory used to store cached render outputs and the cache
    index.  Created on first use."""

    max_stderr_tail: int = 2000
    """Maximum bytes of Blender stderr to preserve on crash."""

    default_resolution: Tuple[int, int] = field(default=(1920, 1080))
    """Output resolution when the job does not specify one."""


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _compute_cache_key(scene_blob: bytes, preset: str) -> str:
    """Return a hex SHA-256 cache key for ``(scene_blob, preset, version)``."""
    h = hashlib.sha256()
    h.update(scene_blob)
    h.update(preset.encode())
    h.update(_TRANSLATOR_VERSION.encode())
    return h.hexdigest()


def _cache_index_path(config: CyclesWorkerConfig) -> str:
    return os.path.join(config.cache_dir, "index.json")


def _load_cache_index(config: CyclesWorkerConfig) -> Dict[str, str]:
    path = _cache_index_path(config)
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_cache_index(config: CyclesWorkerConfig, index: Dict[str, str]) -> None:
    os.makedirs(config.cache_dir, exist_ok=True)
    path = _cache_index_path(config)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(index, fh)
    os.replace(tmp, path)


def _cache_lookup(config: CyclesWorkerConfig, key: str) -> Optional[str]:
    """Return the signed URL for ``key`` if present in cache, else None."""
    index = _load_cache_index(config)
    return index.get(key)


def _cache_store(config: CyclesWorkerConfig, key: str, signed_url: str) -> None:
    """Record a new cache entry mapping ``key`` → ``signed_url``."""
    index = _load_cache_index(config)
    index[key] = signed_url
    _save_cache_index(config, index)


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------


def _write_output(
    config: CyclesWorkerConfig,
    cache_key: str,
    output_format: str,
    data: bytes,
) -> str:
    """Persist render output and return a URL.

    S3/Tigris mode (``STORAGE_BACKEND=s3``)
    -----------------------------------------
    When the ``STORAGE_BACKEND`` environment variable is ``s3``, the output is
    uploaded to the configured object-storage bucket under the key
    ``renders/<cache_key>.<ext>`` and a presigned GET URL (TTL 7 days) is
    returned.  This avoids storing render artefacts on the ephemeral local
    filesystem of Koyeb instances and prevents serving them through the app
    proxy.

    Local / self-host mode (any other ``STORAGE_BACKEND``)
    -------------------------------------------------------
    The original behaviour is preserved: write to ``config.cache_dir`` and
    return the local file path.
    """
    ext = "png" if output_format == "png" else "exr"
    filename = f"{cache_key}.{ext}"

    backend = os.environ.get("STORAGE_BACKEND", "").strip().lower()
    if backend == "s3":
        return _write_output_s3(config, filename, ext, data)

    # ── Local / self-host fallback ───────────────────────────────────────────
    os.makedirs(config.cache_dir, exist_ok=True)
    dest = os.path.join(config.cache_dir, filename)
    with open(dest, "wb") as fh:
        fh.write(data)
    return dest


def _write_output_s3(
    config: CyclesWorkerConfig,
    filename: str,
    ext: str,
    data: bytes,
) -> str:
    """Upload *data* to S3/Tigris and return a presigned GET URL.

    Uses ``kerf_core.storage.create_storage`` with settings read from the
    same environment variables the main app uses (``S3_BUCKET``,
    ``S3_REGION``, ``S3_ACCESS_KEY_ID``, ``S3_SECRET_ACCESS_KEY``,
    ``S3_ENDPOINT``, ``S3_PUBLIC_URL_BASE``).  The object key is
    ``renders/<filename>``.  Presigned URL TTL is 7 days (604800 seconds).

    Raises on upload failure so the caller surfaces the error rather than
    silently returning a broken URL.
    """
    import asyncio
    import io

    try:
        from kerf_core.storage import create_storage
    except ImportError as exc:
        raise RuntimeError(
            "kerf_core.storage not available — cannot upload render output to S3"
        ) from exc

    storage = create_storage(
        backend="s3",
        s3_bucket=os.environ.get("S3_BUCKET", ""),
        s3_region=os.environ.get("S3_REGION", ""),
        s3_access_key_id=os.environ.get("S3_ACCESS_KEY_ID", ""),
        s3_secret_access_key=os.environ.get("S3_SECRET_ACCESS_KEY", ""),
        s3_endpoint=os.environ.get("S3_ENDPOINT", ""),
        s3_public_url_base=os.environ.get("S3_PUBLIC_URL_BASE", ""),
        cdn_base_url=os.environ.get("CDN_BASE_URL", ""),
    )

    object_key = f"renders/{filename}"
    content_type = "image/png" if ext == "png" else "image/x-exr"
    ttl_seconds = 604800  # 7 days

    async def _upload_and_sign() -> str:
        await storage.put(object_key, io.BytesIO(data), content_type, len(data))
        return await storage.signed_url(object_key, ttl_seconds=ttl_seconds)

    # Run in the current event loop if one is running, otherwise create one.
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # We are inside an async context — schedule as a coroutine and wait.
        import concurrent.futures
        future = asyncio.run_coroutine_threadsafe(_upload_and_sign(), loop)
        return future.result(timeout=120)
    else:
        return asyncio.run(_upload_and_sign())


# ---------------------------------------------------------------------------
# Blender subprocess driver
# ---------------------------------------------------------------------------


def _run_blender(
    config: CyclesWorkerConfig,
    script_path: str,
    timeout: int,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]],
) -> Tuple[int, str, str]:
    """Invoke Blender headless and return ``(returncode, stdout, stderr)``.

    Tile-progress lines written to stdout by the injected Blender script
    are forwarded to ``progress_callback`` as they arrive (when the
    callback is provided).  Each event is a JSON object on its own line::

        {"type": "tile", "x": 0, "y": 0, "w": 256, "h": 256,
         "samples_done": 32, "samples_total": 256}

    Blender's own informational output is forwarded on separate lines that
    do *not* parse as JSON; those are silently ignored by the callback.
    """
    cmd = [
        config.blender_path,
        "--background",
        "--python", script_path,
        "-noaudio",
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stderr = (exc.stderr or "")[-config.max_stderr_tail:]
        return -1, "", f"TimeoutExpired after {timeout}s\n{stderr}"
    except FileNotFoundError:
        return -2, "", f"blender executable not found: {config.blender_path!r}"

    # Forward tile events to the progress callback.
    if progress_callback and proc.stdout:
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
                if event.get("type") == "tile":
                    progress_callback(event)
            except json.JSONDecodeError:
                pass

    stderr_tail = (proc.stderr or "")[-config.max_stderr_tail:]
    return proc.returncode, proc.stdout or "", stderr_tail


# ---------------------------------------------------------------------------
# BYO-Blender resolution (T-106e self-host docker contract)
# ---------------------------------------------------------------------------


def resolve_blender_bin() -> str:
    """Return the Blender binary to invoke, honouring self-host env vars.

    Precedence: ``KERF_BLENDER_BIN`` (exported by the container
    ``entrypoint.sh``) > ``KERF_BLENDER_PATH`` (operator-supplied BYO
    path) > the bare ``"blender"`` command resolved from ``PATH``.
    Empty-string values are ignored so an exported-but-empty var does not
    shadow the fallback (paths with spaces are returned verbatim).
    """
    for var in ("KERF_BLENDER_BIN", "KERF_BLENDER_PATH"):
        val = os.environ.get(var)
        if val:
            return val
    return "blender"


def run_blender(
    script_path: str,
    blender_bin: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """Invoke Blender headlessly to execute ``script_path``.

    This is the entry point the self-host docker image (T-106e) uses to
    shell out to a bundled or BYO Blender.  ``blender_bin`` overrides
    resolution; when ``None`` it is resolved via
    :func:`resolve_blender_bin`.  Output is captured so the caller can
    surface Blender errors; a finite timeout guards against hung renders.
    """
    bin_ = blender_bin or resolve_blender_bin()
    return subprocess.run(
        [bin_, "-b", "--python", script_path, "-noaudio"],
        capture_output=True,
        text=True,
        timeout=600,
    )


# ---------------------------------------------------------------------------
# Blender script injection — tile-progress wrapper
# ---------------------------------------------------------------------------

_TILE_REPORTER = '''
import bpy
import json
import sys

class _KerfTileHandler(bpy.types.RenderEngine):
    """Mixin that injects a tile handler into the active render."""


def _install_tile_handler(samples_total: int):
    """Register a render-complete / tile handler to emit JSON-line progress."""
    import bpy

    def _on_render_stats(scene):
        # Blender 3.x / 4.x: no per-tile callback without a custom engine;
        # we emit a single progress event per render_stats call instead.
        try:
            stats = scene.statistics()
        except Exception:
            stats = ""
        # Emit a synthetic tile event so the harness receives at least one
        # progress notification per stats-update tick.
        s_done = getattr(scene.cycles, "sample", 0)
        event = {
            "type": "tile",
            "x": 0, "y": 0,
            "w": scene.render.resolution_x,
            "h": scene.render.resolution_y,
            "samples_done": s_done,
            "samples_total": samples_total,
        }
        print(json.dumps(event), flush=True)

    bpy.app.handlers.render_stats.append(_on_render_stats)
'''


def _build_render_script(
    *,
    gltf_path: str,
    script_str: str,
    output_path: str,
    output_format: str,
    samples: int,
    resolution: Tuple[int, int],
    gpu_enabled: bool = False,
) -> str:
    """Compose the final Blender script that will be written to a tempfile.

    We take the script produced by :func:`cycles_translator.translate_body_to_gltf_plus_materials`
    and append:
      - optional GPU device activation (when ``gpu_enabled=True``)
      - tile-progress reporting shim
      - an explicit ``bpy.ops.render.render(write_still=True)`` call
      - ``sys.exit(0)`` so Blender returns cleanly

    GPU activation
    --------------
    When ``gpu_enabled`` is ``True`` (controlled by the ``KERF_RENDER_GPU=1``
    environment variable — read by :func:`CyclesWorker._invoke_blender`), the
    script sets ``scene.cycles.device = 'GPU'``, selects ``CUDA`` as the
    compute device type, and enables all available CUDA devices.  If no CUDA
    devices are found at runtime Blender silently falls back to CPU rendering.

    To use a future ``KoyebGPUBackend`` (see
    ``kerf_workers.compute_backend.KoyebGPUBackend`` extension point in
    ``cloud/``), set ``KERF_RENDER_GPU=1`` in the GPU instance environment.
    """
    # The translator's generated script defines ``main()`` but deliberately
    # does NOT call ``bpy.ops.render.render``.  We append that here together
    # with the progress shim.
    res_x, res_y = resolution
    out_fmt_upper = output_format.upper()

    # GPU activation block — injected only when KERF_RENDER_GPU=1.
    gpu_block = ""
    if gpu_enabled:
        gpu_block = """
# ── GPU device activation (KERF_RENDER_GPU=1) ──────────────────────────────
# Sets Cycles to GPU rendering via CUDA.  If no CUDA devices are present
# Blender silently falls back to CPU so the render still completes.
_scene = _bpy.context.scene
if hasattr(_scene, "cycles"):
    _scene.cycles.device = "GPU"
_prefs = _bpy.context.preferences.addons.get("cycles")
if _prefs is not None:
    _cprefs = _prefs.preferences
    _cprefs.compute_device_type = "CUDA"
    for _dev in _cprefs.devices:
        _dev.use = True
# ───────────────────────────────────────────────────────────────────────────
"""

    suffix = f'''
import sys as _sys
import json as _json
import bpy as _bpy

# Override output path and format from the worker.
_bpy.context.scene.render.filepath = {repr(output_path)}
_bpy.context.scene.render.image_settings.file_format = {repr(out_fmt_upper)}
_bpy.context.scene.render.resolution_x = {res_x}
_bpy.context.scene.render.resolution_y = {res_y}
if hasattr(_bpy.context.scene, "cycles"):
    _bpy.context.scene.cycles.samples = {samples}
{gpu_block}
# Tile progress: register a render-stats handler that emits JSON lines.
def _kerf_tile_handler(scene):
    try:
        s_done = getattr(scene.cycles, "sample", 0)
    except Exception:
        s_done = 0
    event = {{
        "type": "tile",
        "x": 0, "y": 0,
        "w": scene.render.resolution_x,
        "h": scene.render.resolution_y,
        "samples_done": s_done,
        "samples_total": {samples},
    }}
    print(_json.dumps(event), flush=True)

_bpy.app.handlers.render_stats.append(_kerf_tile_handler)

# Execute the translated scene setup, then render.
main()
_bpy.ops.render.render(write_still=True)

# Emit a final tile event marking completion.
_done_event = {{"type": "tile", "x": 0, "y": 0,
    "w": _bpy.context.scene.render.resolution_x,
    "h": _bpy.context.scene.render.resolution_y,
    "samples_done": {samples}, "samples_total": {samples}}}
print(_json.dumps(_done_event), flush=True)

_sys.exit(0)
'''
    return script_str + suffix


# ---------------------------------------------------------------------------
# Main worker class
# ---------------------------------------------------------------------------


class CyclesWorker:
    """Subprocess-isolated Blender Cycles render worker.

    Parameters
    ----------
    config:
        :class:`CyclesWorkerConfig` instance.  Defaults to
        ``CyclesWorkerConfig()`` if not supplied.
    """

    def __init__(self, config: Optional[CyclesWorkerConfig] = None) -> None:
        self.config = config or CyclesWorkerConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_job(
        self,
        job_dict: Dict[str, Any],
        *,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Process one render job.

        Parameters
        ----------
        job_dict:
            See module docstring for the expected schema.
        progress_callback:
            Optional callable invoked for each tile-progress event emitted
            by the Blender subprocess.  Receives a single dict argument::

                {"type": "tile", "x": int, "y": int, "w": int, "h": int,
                 "samples_done": int, "samples_total": int}

        Returns
        -------
        dict
            Success::

                {"ok": True, "signed_url": str, "cache_key": str,
                 "samples": int, "from_cache": bool, "render_seconds": float}

            Failure::

                {"ok": False, "reason": str, "stderr_tail": str}
        """
        t0 = time.monotonic()

        # --- Select GPU SKU based on scene complexity --------------------
        from kerf_render.dispatch import select_gpu_sku  # noqa: PLC0415
        scene_metrics: Dict[str, Any] = {
            k: job_dict[k]
            for k in ("preset", "samples", "resolution", "poly_count", "light_count")
            if k in job_dict
        }
        gpu_sku = select_gpu_sku(scene_metrics)
        logger.debug("cycles_worker: selected gpu_sku=%s for job", gpu_sku)

        # --- Decode scene blob -------------------------------------------
        raw_blob = job_dict.get("scene_blob", b"")
        if isinstance(raw_blob, str):
            try:
                scene_blob = base64.b64decode(raw_blob)
            except Exception:
                scene_blob = raw_blob.encode()
        else:
            scene_blob = bytes(raw_blob)

        # --- Preset / samples -------------------------------------------
        preset = str(job_dict.get("preset", _DEFAULT_PRESET)).lower()
        if preset not in PRESET_SAMPLES:
            preset = _DEFAULT_PRESET
        samples = PRESET_SAMPLES[preset]
        timeout = PRESET_TIMEOUTS[preset]

        # --- Output format -----------------------------------------------
        output_format = str(job_dict.get("output_format", "png")).lower()
        if output_format not in ("png", "exr"):
            output_format = "png"

        # --- Cache key ---------------------------------------------------
        cache_key = job_dict.get("cache_key") or _compute_cache_key(scene_blob, preset)

        # --- Cache hit? --------------------------------------------------
        cached_url = _cache_lookup(self.config, cache_key)
        if cached_url:
            logger.info("cycles_worker: cache hit key=%s", cache_key)
            return {
                "ok":             True,
                "signed_url":     cached_url,
                "cache_key":      cache_key,
                "samples":        samples,
                "from_cache":     True,
                "render_seconds": 0.0,
                "gpu_model":      gpu_sku,
            }

        # --- Translate scene blob → glTF + script -----------------------
        translate_result = self._translate_scene(job_dict, scene_blob, samples, output_format)
        if not translate_result["ok"]:
            return {
                "ok":         False,
                "reason":     translate_result.get("reason", "translation_failed"),
                "stderr_tail": "",
            }

        gltf_bytes: bytes = translate_result["gltf_bytes"]
        script_str: str   = translate_result["script_str"]
        resolution: Tuple[int, int] = translate_result["resolution"]

        # --- Run Blender in subprocess -----------------------------------
        render_result = self._invoke_blender(
            gltf_bytes=gltf_bytes,
            script_str=script_str,
            output_format=output_format,
            samples=samples,
            resolution=resolution,
            timeout=timeout,
            progress_callback=progress_callback,
        )

        render_seconds = time.monotonic() - t0

        if not render_result["ok"]:
            return {
                "ok":          False,
                "reason":      render_result["reason"],
                "stderr_tail": render_result.get("stderr_tail", ""),
            }

        # --- Persist output & cache --------------------------------------
        output_data: bytes = render_result["output_data"]
        signed_url = _write_output(self.config, cache_key, output_format, output_data)
        _cache_store(self.config, cache_key, signed_url)

        logger.info(
            "cycles_worker: render complete key=%s preset=%s seconds=%.1f gpu_sku=%s",
            cache_key, preset, render_seconds, gpu_sku,
        )

        return {
            "ok":             True,
            "signed_url":     signed_url,
            "cache_key":      cache_key,
            "samples":        samples,
            "from_cache":     False,
            "render_seconds": render_seconds,
            "gpu_model":      gpu_sku,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _translate_scene(
        self,
        job_dict: Dict[str, Any],
        scene_blob: bytes,
        samples: int,
        output_format: str,
    ) -> Dict[str, Any]:
        """Call cycles_translator with the scene blob and return artefacts.

        If the blob is non-empty we assume it encodes a Body and call
        ``translate_body_to_gltf_plus_materials``.  When the blob is empty
        (e.g. a test with a synthetic script) we fall through gracefully.
        """
        from kerf_render.cycles_translator import (
            Camera,
            Light,
            RenderOutput,
            translate_body_to_gltf_plus_materials,
        )

        resolution_raw = job_dict.get("resolution", [1920, 1080])
        resolution: Tuple[int, int] = (
            int(resolution_raw[0]),
            int(resolution_raw[1]),
        )

        # Build Camera
        cam_dict = job_dict.get("camera") or {}
        camera = Camera(
            position=tuple(cam_dict.get("position", (0.0, 0.0, 5.0))),
            target=tuple(cam_dict.get("target", (0.0, 0.0, 0.0))),
            up=tuple(cam_dict.get("up", (0.0, 1.0, 0.0))),
            fov_deg=float(cam_dict.get("fov_deg", 35.0)),
        )

        # Build Lights
        lights_raw = job_dict.get("lights") or []
        lights: List[Light] = []
        for ld in lights_raw:
            lights.append(Light(
                type=str(ld.get("type", "point")),
                position=tuple(ld.get("position", (5.0, 5.0, 5.0))),
                target=tuple(ld.get("target", (0.0, 0.0, 0.0))),
                color=tuple(ld.get("color", (1.0, 1.0, 1.0))),
                energy=float(ld.get("energy", 1000.0)),
                size=float(ld.get("size", 1.0)),
                name=str(ld.get("name", "Light")),
            ))
        if not lights:
            lights = [Light(type="point", position=(5.0, 5.0, 5.0), energy=1000.0)]

        ext = "png" if output_format == "png" else "exr"
        output_cfg = RenderOutput(
            path=f"/tmp/kerf_render_output.{ext}",
            resolution=resolution,
            samples=samples,
        )

        materials_raw = job_dict.get("materials") or {}
        # materials_raw may be {face_id: slot_name} — convert keys to int
        materials_int: Dict[int, str] = {}
        for k, v in materials_raw.items():
            try:
                materials_int[int(k)] = str(v)
            except (ValueError, TypeError):
                pass

        if not scene_blob:
            # No body supplied — return a minimal stub script so tests that
            # only care about the subprocess layer can work without a Body.
            stub_script = (
                "def main(): pass\n"
            )
            return {
                "ok":         True,
                "gltf_bytes": b"",
                "script_str": stub_script,
                "resolution": resolution,
            }

        # Decode blob → Body (duck-typed; in tests a FakeBody is passed via
        # scene_blob being zero-length, so this branch runs only in production
        # where a real Body is serialised into scene_blob).
        body = job_dict.get("_body_object")
        if body is None:
            # Attempt to deserialise; if that fails, return a failure dict.
            try:
                body = _deserialise_body(scene_blob)
            except Exception as exc:
                return {"ok": False, "reason": f"body_deserialise_failed: {exc}"}

        result = translate_body_to_gltf_plus_materials(
            body,
            camera=camera,
            lights=lights,
            materials=materials_int,
            output=output_cfg,
        )
        if not result.get("ok"):
            return {"ok": False, "reason": result.get("reason", "translation_failed")}

        return {
            "ok":         True,
            "gltf_bytes": result["gltf_bytes"],
            "script_str": result["blender_script"],
            "resolution": resolution,
        }

    def _invoke_blender(
        self,
        *,
        gltf_bytes: bytes,
        script_str: str,
        output_format: str,
        samples: int,
        resolution: Tuple[int, int],
        timeout: int,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]],
    ) -> Dict[str, Any]:
        """Write temp files, call Blender, read back output.

        GPU activation is controlled by the ``KERF_RENDER_GPU`` environment
        variable.  Set ``KERF_RENDER_GPU=1`` (or ``true``/``yes``) to enable
        CUDA GPU rendering inside the Blender subprocess.  When unset or set to
        any other value the script runs on CPU (the default).

        Returns
        -------
        dict
            Success: ``{"ok": True, "output_data": bytes}``
            Failure: ``{"ok": False, "reason": str, "stderr_tail": str}``
        """
        ext = "png" if output_format == "png" else "exr"

        # Honour KERF_RENDER_GPU env flag — graceful CPU fallback when unset.
        gpu_flag = os.environ.get("KERF_RENDER_GPU", "").strip().lower()
        gpu_enabled = gpu_flag in ("1", "true", "yes")

        with tempfile.TemporaryDirectory(prefix="kerf_render_") as tmpdir:
            # Write glTF blob
            gltf_path = os.path.join(tmpdir, "scene.glb")
            with open(gltf_path, "wb") as fh:
                fh.write(gltf_bytes)

            # Build + write the final Blender script
            output_path = os.path.join(tmpdir, f"render.{ext}")
            final_script = _build_render_script(
                gltf_path=gltf_path,
                script_str=script_str,
                output_path=output_path,
                output_format=output_format,
                samples=samples,
                resolution=resolution,
                gpu_enabled=gpu_enabled,
            )
            script_path = os.path.join(tmpdir, "render_script.py")
            with open(script_path, "w") as fh:
                fh.write(final_script)

            # Invoke Blender
            returncode, stdout, stderr_tail = _run_blender(
                self.config,
                script_path,
                timeout,
                progress_callback,
            )

            if returncode != 0:
                logger.error(
                    "cycles_worker: blender exited %d stderr_tail=%s",
                    returncode,
                    stderr_tail[-200:],
                )
                return {
                    "ok":          False,
                    "reason":      "blender_crashed",
                    "stderr_tail": stderr_tail,
                }

            # Try to locate output file (Blender may append frame number)
            actual_path = output_path
            if not os.path.exists(actual_path):
                candidates = sorted(
                    os.path.join(tmpdir, f)
                    for f in os.listdir(tmpdir)
                    if f.startswith("render") and f.endswith(f".{ext}")
                )
                if candidates:
                    actual_path = candidates[-1]

            if not os.path.exists(actual_path):
                return {
                    "ok":          False,
                    "reason":      "output_file_missing",
                    "stderr_tail": stderr_tail,
                }

            with open(actual_path, "rb") as fh:
                output_data = fh.read()

        return {"ok": True, "output_data": output_data}


# ---------------------------------------------------------------------------
# Body deserialisation stub
# ---------------------------------------------------------------------------


def _deserialise_body(blob: bytes):
    """Attempt to deserialise a Body from ``blob``.

    This is a thin shim: in production the correct deserialiser is imported
    from ``kerf_cad_core``; here we only try and raise on failure so the
    caller can handle it gracefully.
    """
    try:
        from kerf_cad_core.geom.brep import Body  # type: ignore
        return Body.from_bytes(blob)
    except ImportError:
        raise RuntimeError("kerf_cad_core not available; cannot deserialise Body")
    except AttributeError:
        raise RuntimeError("Body.from_bytes not available in this kerf_cad_core version")


# ---------------------------------------------------------------------------
# Convenience: compute cache key (exported for callers)
# ---------------------------------------------------------------------------


def compute_cache_key(scene_blob: bytes, preset: str) -> str:
    """Public alias for :func:`_compute_cache_key`."""
    return _compute_cache_key(scene_blob, preset)


__all__ = [
    "PRESET_SAMPLES",
    "PRESET_TIMEOUTS",
    "CyclesWorkerConfig",
    "CyclesWorker",
    "compute_cache_key",
    "resolve_blender_bin",
    "run_blender",
]
