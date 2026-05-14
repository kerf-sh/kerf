import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

STALE_PART_AGE = timedelta(hours=24)
SWEEP_INTERVAL = timedelta(hours=6)


def is_stale(part_json: str) -> bool:
    try:
        d = json.loads(part_json)
    except json.JSONDecodeError:
        return False

    dists = d.get("distributors", [])
    if not dists:
        return False

    now = datetime.utcnow()
    for e in dists:
        fetched_at_str = e.get("fetched_at", "")
        if not fetched_at_str:
            return True
        try:
            fetched_at = datetime.fromisoformat(fetched_at_str.replace("Z", "+00:00"))
            if fetched_at.tzinfo:
                fetched_at = fetched_at.replace(tzinfo=None)
            if now - fetched_at > STALE_PART_AGE:
                return True
        except (ValueError, TypeError):
            return True

    return False


async def refresh_part(ctx_pool, registry, part_json: str) -> tuple[str, int, None]:
    if not registry or not part_json or not part_json.strip():
        return part_json, 0, None

    try:
        doc = json.loads(part_json)
    except json.JSONDecodeError:
        return part_json, 0, None

    raw_dist = doc.get("distributors")
    if not raw_dist:
        return part_json, 0, None

    try:
        dists = json.loads(raw_dist) if isinstance(raw_dist, str) else raw_dist
    except json.JSONDecodeError:
        return part_json, 0, None

    if not dists:
        return part_json, 0, None

    mpn = ""
    manufacturer = ""
    name = ""
    if "mpn" in doc:
        try:
            mpn = json.loads(doc["mpn"]) if isinstance(doc["mpn"], str) else doc["mpn"]
        except (json.JSONDecodeError, TypeError):
            mpn = str(doc.get("mpn", ""))
    if "manufacturer" in doc:
        try:
            manufacturer = json.loads(doc["manufacturer"]) if isinstance(doc["manufacturer"], str) else doc.get("manufacturer", "")
        except (json.JSONDecodeError, TypeError):
            manufacturer = str(doc.get("manufacturer", ""))
    if "name" in doc:
        try:
            name = json.loads(doc["name"]) if isinstance(doc["name"], str) else doc.get("name", "")
        except (json.JSONDecodeError, TypeError):
            name = str(doc.get("name", ""))

    updated = 0
    for entry in dists:
        entry_name = entry.get("name", "")
        if not registry.has(entry_name):
            continue

        try:
            svc = await registry.acquire(entry_name)
        except Exception as e:
            logger.warning(f"distributors: acquire {entry_name} for sku {entry.get('sku', '')}: {e}")
            continue

        result = None
        sku = entry.get("sku", "")
        try:
            if sku:
                result = await svc.lookup(ctx_pool, sku)
            else:
                fallback = mpn
                if not fallback:
                    fallback = f"{manufacturer} {name}".strip()
                if fallback:
                    results = await svc.search(ctx_pool, fallback, 1)
                    if results:
                        result = results[0]
        except Exception as e:
            logger.warning(f"distributors: lookup {entry_name}/{sku}: {e}")
            continue

        if not result:
            continue

        try:
            await registry.mark_used(entry_name)
        except Exception:
            pass

        if result.url:
            entry["url"] = result.url
        if result.sku:
            entry["sku"] = result.sku
        if result.price_usd is not None:
            entry["price_usd"] = result.price_usd
        if result.stock is not None:
            entry["stock"] = result.stock
        entry["fetched_at"] = datetime.utcnow().isoformat() + "Z"

        updated += 1

    if updated == 0:
        return part_json, 0, None

    doc["distributors"] = dists
    try:
        out = json.dumps(doc, indent=2)
    except json.JSONEncodeError:
        return part_json, updated, None

    return out, updated, None


async def refresh_all_parts(pool, registry) -> int:
    if not registry or not registry.enabled_names():
        return 0

    rows = await pool.fetch(
        """
        select id, content
        from files
        where kind = 'part' and deleted_at is null
        order by updated_at desc
        limit 500
        """
    )

    pending = []
    for row in rows:
        content = row["content"]
        if is_stale(content):
            pending.append({"id": row["id"], "content": content})

    updated = 0
    for item in pending:
        new_content, n, _ = await refresh_part(pool, registry, item["content"])
        if n > 0:
            async with pool.acquire() as conn:
                await conn.execute(
                    "update files set content = $2, updated_at = now() where id = $1 and deleted_at is null",
                    item["id"],
                    new_content,
                )
            updated += 1

    return updated


async def _sweep_loop(pool, registry) -> None:
    await asyncio.sleep(30)

    n = await refresh_all_parts(pool, registry)
    if n > 0:
        logger.info(f"distributors: initial sweep refreshed {n} part(s)")

    while True:
        await asyncio.sleep(SWEEP_INTERVAL.total_seconds())
        n = await refresh_all_parts(pool, registry)
        if n > 0:
            logger.info(f"distributors: sweep refreshed {n} part(s)")


def start_sweep(pool, registry) -> asyncio.Task:
    return asyncio.create_task(_sweep_loop(pool, registry))
