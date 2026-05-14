import asyncio
import json
import logging
from typing import Optional

import aiohttp
import asyncpg

from kerf_workers.base import BaseWorker

logger = logging.getLogger(__name__)


class SPICEInputSpec:
    def __init__(
        self,
        type: str = "transient",
        tstep: Optional[str] = None,
        tstop: Optional[str] = None,
        vstart: float = 0.0,
        vstop: float = 0.0,
        vstep: float = 0.0,
        fstart: float = 0.0,
        fstop: float = 0.0,
        points: int = 0,
    ):
        self.type = type
        self.tstep = tstep
        self.tstop = tstop
        self.vstart = vstart
        self.vstop = vstop
        self.vstep = vstep
        self.fstart = fstart
        self.fstop = fstop
        self.points = points

    @classmethod
    def from_dict(cls, d: dict) -> "SPICEInputSpec":
        return cls(
            type=d.get("type", "transient"),
            tstep=d.get("tstep"),
            tstop=d.get("tstop"),
            vstart=d.get("vstart", 0.0),
            vstop=d.get("vstop", 0.0),
            vstep=d.get("vstep", 0.0),
            fstart=d.get("fstart", 0.0),
            fstop=d.get("fstop", 0.0),
            points=d.get("points", 0),
        )

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "tstep": self.tstep,
            "tstop": self.tstop,
            "vstart": self.vstart,
            "vstop": self.vstop,
            "vstep": self.vstep,
            "fstart": self.fstart,
            "fstop": self.fstop,
            "points": self.points,
        }


class Waveform:
    def __init__(
        self,
        name: str = "",
        kind: str = "",
        x_unit: str = "",
        y_unit: str = "",
        x: Optional[list] = None,
        y: Optional[list] = None,
    ):
        self.name = name
        self.kind = kind
        self.x_unit = x_unit
        self.y_unit = y_unit
        self.x = x or []
        self.y = y or []

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "xUnit": self.x_unit,
            "yUnit": self.y_unit,
            "x": self.x,
            "y": self.y,
        }


class SPICEResult:
    def __init__(
        self,
        waveforms: Optional[list] = None,
        warnings: Optional[list] = None,
        errors: Optional[list] = None,
    ):
        self.waveforms = waveforms or []
        self.warnings = warnings or []
        self.errors = errors or []

    @classmethod
    def from_dict(cls, d: dict) -> "SPICEResult":
        waveforms = [
            Waveform(
                name=w.get("name", ""),
                kind=w.get("kind", ""),
                x_unit=w.get("xUnit", ""),
                y_unit=w.get("yUnit", ""),
                x=w.get("x", []),
                y=w.get("y", []),
            ).to_dict()
            for w in d.get("waveforms", [])
        ]
        return cls(
            waveforms=waveforms,
            warnings=d.get("warnings", []),
            errors=d.get("errors", []),
        )

    def to_dict(self) -> dict:
        return {
            "waveforms": self.waveforms,
            "warnings": self.warnings,
            "errors": self.errors,
        }


class SPICEDriver:
    def __init__(self, pyworker_url: str = "http://localhost:8090", timeout: int = 300):
        self.pyworker_url = pyworker_url
        self.timeout = timeout

    async def run_spice(self, netlist: str, spec: SPICEInputSpec) -> SPICEResult:
        req = {
            "netlist": netlist,
            "analysis": spec.to_dict(),
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.pyworker_url}/run-spice",
                json=req,
                timeout=aiohttp.ClientTimeout(total=self.timeout + 30),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"pyworker status {resp.status}: {body}")

                data = await resp.json()

                if data.get("error"):
                    raise RuntimeError(f"pyworker error: {data['error']}")

                return SPICEResult.from_dict(data)


class SPICEWorker(BaseWorker):
    def __init__(
        self,
        pool: asyncpg.Pool,
        storage_getter,
        pyworker_url: str = "http://localhost:8090",
        poll_interval: float = 5.0,
        timeout: int = 300,
    ):
        super().__init__("spice", pool, poll_interval)
        self.storage_getter = storage_getter
        self.driver = SPICEDriver(pyworker_url=pyworker_url, timeout=timeout)
        self.timeout = timeout

    async def run_one(self) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                job = await self.claim_job(conn, "sim_jobs", "files")
                if job is None:
                    return False

                job_id = job["id"]
                file_id = job["file_id"]
                storage_key = job["storage_key"]
                input_spec_raw = job["input_spec"]

                input_spec_dict = (
                    input_spec_raw if isinstance(input_spec_raw, dict)
                    else json.loads(input_spec_raw) if input_spec_raw else {}
                )
                netlist = input_spec_dict.get("netlist")
                analysis_dict = input_spec_dict.get("analysis", {})

                if not netlist:
                    storage = self.storage_getter()
                    try:
                        rc = await storage.get(storage_key)
                        netlist_bytes = await rc.read()
                        await rc.close()
                        netlist = netlist_bytes.decode("utf-8")
                    except Exception as e:
                        logger.error(f"spice: download netlist failed (job={job_id}): {e}")
                        await self.mark_error("sim_jobs", job_id, f"download netlist: {e}")
                        return True

                if not netlist.strip():
                    await self.mark_error("sim_jobs", job_id, "empty netlist file")
                    return True

                input_spec = SPICEInputSpec.from_dict(analysis_dict)

        try:
            async with asyncio.timeout(self.timeout):
                result = await self.driver.run_spice(netlist, input_spec)
        except asyncio.TimeoutError:
            await self.mark_error("sim_jobs", job_id, "spice computation timeout")
            return True
        except Exception as e:
            logger.error(f"spice: job={job_id} failed: {e}")
            await self.mark_error("sim_jobs", job_id, str(e))
            return True

        await self.mark_done("sim_jobs", job_id, result.to_dict())
        logger.info(f"spice: job={job_id} file={file_id} done")
        return True
