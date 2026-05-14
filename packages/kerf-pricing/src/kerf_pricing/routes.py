"""Admin HTTP surface for the pricing table.

GET  /admin/pricing             — list all current prices
POST /admin/pricing/refresh     — trigger an immediate LiteLLM refresh

Both routes require ``account_role='admin'`` (or system).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from kerf_core.db.connection import get_pool_required
from kerf_core.dependencies import require_auth

from kerf_pricing.queries import list_all_prices
from kerf_pricing.refresh import refresh_model_prices


logger = logging.getLogger(__name__)
router = APIRouter()


async def _require_admin(payload: dict) -> str:
    """Resolve the caller's role; 403 unless admin/system."""
    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="unauthorized")
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT account_role FROM users WHERE id = $1", uid,
        )
    if not row:
        raise HTTPException(status_code=403, detail="admin only")
    role = row["account_role"]
    if role not in ("admin", "system"):
        raise HTTPException(status_code=403, detail="admin only")
    return uid


@router.get("/admin/pricing")
async def get_pricing(payload: dict = Depends(require_auth)):
    await _require_admin(payload)
    pool = await get_pool_required()
    rows = await list_all_prices(pool)
    return {"prices": rows}


@router.post("/admin/pricing/refresh")
async def post_pricing_refresh(payload: dict = Depends(require_auth)):
    await _require_admin(payload)
    pool = await get_pool_required()
    n = await refresh_model_prices(pool)
    return {"refreshed": n}
