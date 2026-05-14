import asyncio
import json
import logging
from typing import Optional

import asyncpg

from kerf_workers.base import BaseWorker

logger = logging.getLogger(__name__)


class TessInputSpec:
    def __init__(
        self,
        resolution: int = 50000,
        export_format: str = "glb",
        scale: float = 1.0,
    ):
        self.resolution = resolution
        self.export_format = export_format
        self.scale = scale

    @classmethod
    def from_dict(cls, d: dict) -> "TessInputSpec":
        return cls(
            resolution=d.get("resolution", 50000),
            export_format=d.get("export_format", "glb"),
            scale=d.get("scale", 1.0),
        )

    def to_dict(self) -> dict:
        return {
            "resolution": self.resolution,
            "export_format": self.export_format,
            "scale": self.scale,
        }


class TessResult:
    def __init__(
        self,
        output_key: str = "",
        warnings: Optional[list] = None,
        errors: Optional[list] = None,
    ):
        self.output_key = output_key
        self.warnings = warnings or []
        self.errors = errors or []

    def to_dict(self) -> dict:
        return {
            "output_key": self.output_key,
            "warnings": self.warnings,
            "errors": self.errors,
        }


class TessDriver:
    def __init__(self, pyworker_url: str = "http://localhost:8090", timeout: int = 300):
        self.pyworker_url = pyworker_url
        self.timeout = timeout

    async def run_tess(self, step_bytes: bytes, spec: TessInputSpec) -> TessResult:
        import aiohttp
        import base64

        req = {
            "step_b64": base64.b64encode(step_bytes).decode(),
            "input_spec": spec.to_dict(),
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.pyworker_url}/run-tess",
                json=req,
                timeout=aiohttp.ClientTimeout(total=self.timeout + 30),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"pyworker status {resp.status}: {body}")

                data = await resp.json()

                if data.get("error"):
                    raise RuntimeError(f"pyworker error: {data['error']}")

                return TessResult(
                    output_key=data.get("output_key", ""),
                    warnings=data.get("warnings", []),
                    errors=data.get("errors", []),
                )


class TessWorker(BaseWorker):
    def __init__(
        self,
        pool: asyncpg.Pool,
        storage_getter,
        pyworker_url: str = "http://localhost:8090",
        poll_interval: float = 5.0,
        timeout: int = 300,
    ):
        super().__init__("tess", pool, poll_interval)
        self.storage_getter = storage_getter
        self.driver = TessDriver(pyworker_url=pyworker_url, timeout=timeout)
        self.timeout = timeout

    async def run_one(self) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                job = await self.claim_job(conn, "step_tessellation_jobs", "files")
                if job is None:
                    return False

                job_id = job["id"]
                file_id = job["file_id"]
                storage_key = job["storage_key"]
                input_spec_raw = job["input_spec"]

                input_spec = TessInputSpec.from_dict(
                    input_spec_raw if isinstance(input_spec_raw, dict)
                    else json.loads(input_spec_raw) if input_spec_raw else {}
                )

        storage = self.storage_getter()
        try:
            rc = await storage.get(storage_key)
            step_bytes = await rc.read()
            await rc.close()
        except Exception as e:
            logger.error(f"tess: download step failed (job={job_id}): {e}")
            await self.mark_error("step_tessellation_jobs", job_id, f"download step: {e}")
            return True

        if not step_bytes:
            await self.mark_error("step_tessellation_jobs", job_id, "empty step file")
            return True

        try:
            async with asyncio.timeout(self.timeout):
                result = await self.driver.run_tess(step_bytes, input_spec)
        except asyncio.TimeoutError:
            await self.mark_error("step_tessellation_jobs", job_id, "tessellation timeout")
            return True
        except Exception as e:
            logger.error(f"tess: job={job_id} failed: {e}")
            await self.mark_error("step_tessellation_jobs", job_id, str(e))
            return True

        mesh_key = result.output_key or ""
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        """
                        UPDATE step_tessellation_jobs
                        SET status='done', mesh_storage_key=$2, finished_at=now(), error=null
                        WHERE id = $1
                        """,
                        job_id,
                        mesh_key,
                    )
                    if mesh_key:
                        await conn.execute(
                            "UPDATE files SET mesh_storage_key = $2 WHERE id = $1",
                            file_id,
                            mesh_key,
                        )
        except Exception as e:
            logger.exception(f"tess: mark-done failed (job={job_id}): {e}")
            await self.mark_error("step_tessellation_jobs", job_id, f"mark done: {e}")
            return True

        logger.info(f"tess: job={job_id} file={file_id} done mesh={mesh_key}")
        return True
