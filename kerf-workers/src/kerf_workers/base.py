import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class BaseWorker(ABC):
    def __init__(
        self,
        name: str,
        pool,
        poll_interval: float = 5.0,
        error_delay: float = 2.0,
    ):
        self.name = name
        self.pool = pool
        self.poll_interval = poll_interval
        self.error_delay = error_delay
        self._shutdown = False

    async def run(self, ctx: asyncio.TaskGroup):
        task = ctx.create_task(self._loop())
        try:
            await task
        except asyncio.CancelledError:
            self._shutdown = True
            logger.info(f"{self.name}: worker shutdown")

    def stop(self):
        self._shutdown = True

    async def _loop(self):
        while not self._shutdown:
            try:
                ran = await self.run_one()
                if not ran:
                    await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception(f"{self.name}: runOne error")
                await asyncio.sleep(self.error_delay)

    @abstractmethod
    async def run_one(self) -> bool:
        pass

    async def claim_job(
        self,
        tx,
        table: str,
        file_ref_table: str,
        status_col: str = "status",
    ):
        row = await tx.fetchrow(
            f"""
            SELECT j.id, j.file_id, f.project_id, f.storage_key, j.input_spec
            FROM {table} j
            JOIN {file_ref_table} f ON f.id = j.file_id
            WHERE j.{status_col} = 'queued' AND f.deleted_at IS NULL
            ORDER BY j.created_at ASC
            FOR UPDATE OF j SKIP LOCKED
            LIMIT 1
            """
        )
        if row is None:
            return None

        job_id = row["id"]
        storage_key = row["storage_key"]

        if not storage_key:
            await tx.execute(
                f"""
                UPDATE {table}
                SET status='error', error='file has no storage_key', finished_at=now()
                WHERE id = $1
                """,
                job_id,
            )
            return None

        await tx.execute(
            f"""
            UPDATE {table}
            SET status='running', started_at=now()
            WHERE id = $1
            """,
            job_id,
        )

        return row

    async def mark_error(self, table: str, job_id: str, error: str):
        try:
            await self.pool.execute(
                f"""
                UPDATE {table}
                SET status = 'error', error = $2, finished_at = now()
                WHERE id = $1
                """,
                job_id,
                error[:800] if len(error) > 800 else error,
            )
        except Exception:
            logger.exception(f"{self.name}: mark error failed (job={job_id})")

    async def mark_done(self, table: str, job_id: str, result_json: dict):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    f"""
                    UPDATE {table}
                    SET status='done', result_json=$2, finished_at=now(), error=null
                    WHERE id = $1
                    """,
                    job_id,
                    result_json,
                )

    def truncate_error(self, err: str, max_len: int = 800) -> str:
        if len(err) <= max_len:
            return err
        return err[:max_len] + "..."
