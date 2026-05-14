from typing import Optional


class QuotaManager:
    def __init__(self, pool):
        self.pool = pool

    async def check_quota(self, workspace_id: str, resource: str) -> tuple[bool, int]:
        async with self.pool.acquire() as conn:
            if resource == "llm":
                row = await conn.fetchrow(
                    "SELECT credits_usd FROM cloud_user_balances WHERE user_id = $1",
                    workspace_id,
                )
                if not row:
                    return False, 0
                balance = row["credits_usd"]
                return balance > 0, int(balance * 100)

            elif resource == "storage":
                row = await conn.fetchrow(
                    """
                    SELECT COALESCE(SUM(bytes_delta), 0)::bigint as current_bytes
                    FROM usage_events
                    WHERE user_id = $1 AND kind = 'storage'
                    """,
                    workspace_id,
                )
                current_bytes = row["current_bytes"] if row else 0
                return True, current_bytes

            elif resource == "api_calls":
                row = await conn.fetchrow(
                    """
                    SELECT COUNT(*) as call_count
                    FROM usage_events
                    WHERE user_id = $1 AND kind = 'token'
                    AND created_at >= date_trunc('month', now())
                    """,
                    workspace_id,
                )
                call_count = row["call_count"] if row else 0
                return True, call_count

        return False, 0

    async def increment_usage(self, workspace_id: str, resource: str, amount: int) -> None:
        pass
