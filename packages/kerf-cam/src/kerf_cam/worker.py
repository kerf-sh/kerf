import asyncio
import json
import logging
from typing import Optional

import asyncpg

try:
    from workers.base import BaseWorker
except ImportError:
    from kerf_cam._compat import BaseWorker

logger = logging.getLogger(__name__)


class CAMInputSpec:
    def __init__(
        self,
        operation: str = "profile",
        tool_diameter: float = 3.0,
        step_over: float = 0.5,
        step_down: float = 0.5,
        feed_rate: float = 1000.0,
        spindle_speed: float = 10000.0,
        coolant: bool = True,
    ):
        self.operation = operation
        self.tool_diameter = tool_diameter
        self.step_over = step_over
        self.step_down = step_down
        self.feed_rate = feed_rate
        self.spindle_speed = spindle_speed
        self.coolant = coolant

    @classmethod
    def from_dict(cls, d: dict) -> "CAMInputSpec":
        return cls(
            operation=d.get("operation", "profile"),
            tool_diameter=d.get("tool_diameter", 3.0),
            step_over=d.get("step_over", 0.5),
            step_down=d.get("step_down", 0.5),
            feed_rate=d.get("feed_rate", 1000.0),
            spindle_speed=d.get("spindle_speed", 10000.0),
            coolant=d.get("coolant", True),
        )

    def to_dict(self) -> dict:
        return {
            "operation": self.operation,
            "tool_diameter": self.tool_diameter,
            "step_over": self.step_over,
            "step_down": self.step_down,
            "feed_rate": self.feed_rate,
            "spindle_speed": self.spindle_speed,
            "coolant": self.coolant,
        }


class CAMResult:
    def __init__(
        self,
        output_key: str = "",
        toolpath_length: float = 0.0,
        estimated_time: float = 0.0,
        warnings: Optional[list] = None,
        errors: Optional[list] = None,
    ):
        self.output_key = output_key
        self.toolpath_length = toolpath_length
        self.estimated_time = estimated_time
        self.warnings = warnings or []
        self.errors = errors or []

    def to_dict(self) -> dict:
        return {
            "output_key": self.output_key,
            "toolpath_length": self.toolpath_length,
            "estimated_time": self.estimated_time,
            "warnings": self.warnings,
            "errors": self.errors,
        }


class CAMDriver:
    def __init__(self, pyworker_url: str = "http://localhost:8090", timeout: int = 300):
        self.pyworker_url = pyworker_url
        self.timeout = timeout

    async def run_cam(self, step_bytes: bytes, spec: CAMInputSpec) -> CAMResult:
        import aiohttp
        import base64

        req = {
            "step_b64": base64.b64encode(step_bytes).decode(),
            "input_spec": spec.to_dict(),
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.pyworker_url}/run-cam",
                json=req,
                timeout=aiohttp.ClientTimeout(total=self.timeout + 30),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"pyworker status {resp.status}: {body}")

                data = await resp.json()

                if data.get("error"):
                    raise RuntimeError(f"pyworker error: {data['error']}")

                return CAMResult(
                    output_key=data.get("output_key", ""),
                    toolpath_length=data.get("toolpath_length", 0.0),
                    estimated_time=data.get("estimated_time", 0.0),
                    warnings=data.get("warnings", []),
                    errors=data.get("errors", []),
                )


class CAMWorker(BaseWorker):
    def __init__(
        self,
        pool: asyncpg.Pool,
        storage_getter,
        pyworker_url: str = "http://localhost:8090",
        poll_interval: float = 5.0,
        timeout: int = 300,
    ):
        super().__init__("cam", pool, poll_interval)
        self.storage_getter = storage_getter
        self.driver = CAMDriver(pyworker_url=pyworker_url, timeout=timeout)
        self.timeout = timeout

    async def run_one(self) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                job = await self.claim_job(conn, "cam_jobs", "files")
                if job is None:
                    return False

                job_id = job["id"]
                file_id = job["file_id"]
                storage_key = job["storage_key"]
                input_spec_raw = job["input_spec"]

                input_spec = CAMInputSpec.from_dict(
                    input_spec_raw if isinstance(input_spec_raw, dict)
                    else json.loads(input_spec_raw) if input_spec_raw else {}
                )

        storage = self.storage_getter()
        try:
            rc = await storage.get(storage_key)
            step_bytes = await rc.read()
            await rc.close()
        except Exception as e:
            logger.error(f"cam: download step failed (job={job_id}): {e}")
            await self.mark_error("cam_jobs", job_id, f"download step: {e}")
            return True

        if not step_bytes:
            await self.mark_error("cam_jobs", job_id, "empty step file")
            return True

        try:
            async with asyncio.timeout(self.timeout):
                result = await self.driver.run_cam(step_bytes, input_spec)
        except asyncio.TimeoutError:
            await self.mark_error("cam_jobs", job_id, "cam computation timeout")
            return True
        except Exception as e:
            logger.error(f"cam: job={job_id} failed: {e}")
            await self.mark_error("cam_jobs", job_id, str(e))
            return True

        await self.mark_done("cam_jobs", job_id, result.to_dict())
        logger.info(f"cam: job={job_id} file={file_id} done")
        return True
