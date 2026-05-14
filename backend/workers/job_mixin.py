import json
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ClaimedJob:
    id: str
    file_id: str
    project_id: str
    storage_key: str
    input_spec: dict


class JobMixin:
    async def claim_next_job(
        self,
        tx,
        table: str,
        file_ref_table: str,
    ) -> Optional[ClaimedJob]:
        row = await tx.fetchrow(
            f"""
            SELECT j.id, j.file_id, f.project_id, f.storage_key, j.input_spec
            FROM {table} j
            JOIN {file_ref_table} f ON f.id = j.file_id
            WHERE j.status = 'queued' AND f.deleted_at IS NULL
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

        input_spec = {}
        if row["input_spec"]:
            try:
                input_spec = json.loads(row["input_spec"]) if isinstance(row["input_spec"], str) else row["input_spec"]
            except (json.JSONDecodeError, TypeError):
                input_spec = {}

        return ClaimedJob(
            id=str(job_id),
            file_id=str(row["file_id"]),
            project_id=str(row["project_id"]),
            storage_key=storage_key,
            input_spec=input_spec,
        )

    def parse_input_spec(self, raw_spec: Any) -> dict:
        if not raw_spec:
            return {}
        if isinstance(raw_spec, dict):
            return raw_spec
        if isinstance(raw_spec, str):
            try:
                return json.loads(raw_spec)
            except json.JSONDecodeError:
                return {}
        return {}

    async def update_job_status(
        self,
        tx,
        table: str,
        job_id: str,
        status: str,
        result_json: Optional[dict] = None,
        error: Optional[str] = None,
    ):
        if status == "error":
            await tx.execute(
                f"""
                UPDATE {table}
                SET status='error', error=$2, finished_at=now()
                WHERE id = $1
                """,
                job_id,
                error[:800] if error and len(error) > 800 else error,
            )
        elif status == "done":
            await tx.execute(
                f"""
                UPDATE {table}
                SET status='done', result_json=$2, finished_at=now(), error=null
                WHERE id = $1
                """,
                job_id,
                result_json,
            )
