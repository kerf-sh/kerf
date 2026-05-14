import json
import uuid
from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx


validate_jscad_spec = ToolSpec(
    name="validate_jscad",
    description="Stub: returns ok=true. Real validation runs in the browser.",
    input_schema={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
)


@register(validate_jscad_spec)
async def run_validate_jscad(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    return ok_payload({
        "path": a.get("path", ""),
        "ok": True,
        "checked": False,
        "note": "client-side validation",
    })


generate_bom_spec = ToolSpec(
    name="generate_bom",
    description="Generate a Bill of Materials for the current project. Walks every assembly file, recursively resolves nested assemblies, and aggregates leaf Part references by MPN (or by file id when MPN is missing). Returns rows with quantity, unit price (from the Part's first distributor with a price), and total price.",
    input_schema={"type": "object", "properties": {}},
)


def parse_part_content(content: str) -> dict:
    if not content or not content.strip():
        return {"version": 1, "distributors": []}
    try:
        doc = json.loads(content)
    except Exception:
        return {"version": 1, "distributors": []}
    if doc.get("version", 0) == 0:
        doc["version"] = 1
    if "distributors" not in doc or doc["distributors"] is None:
        doc["distributors"] = []
    return doc


def parse_bom_components(content: str) -> list:
    if not content or not content.strip():
        return []
    try:
        d = json.loads(content)
    except Exception:
        return []
    if d.get("components"):
        return d["components"]
    if d.get("children"):
        return d["children"]
    return []


@register(generate_bom_spec)
async def run_generate_bom(ctx: ProjectCtx, args: bytes) -> str:
    rows = await ctx.pool.fetch(
        "SELECT id, parent_id, name, kind, content FROM files "
        "WHERE project_id = $1 AND deleted_at IS NULL "
        "AND kind IN ('assembly', 'part', 'folder', 'file', 'step', 'drawing', 'sketch')",
        ctx.project_id,
    )

    by_id = {}
    files = []
    for row in rows:
        f = {
            "id": row["id"],
            "parent_id": row["parent_id"],
            "name": row["name"],
            "kind": row["kind"],
            "content": row["content"] or "",
        }
        files.append(f)
        by_id[f["id"]] = f

    paths = {}
    for f in files:
        parts = [f["name"]]
        cur = f["parent_id"]
        for _ in range(64):
            if cur is None:
                break
            p = by_id.get(cur)
            if not p:
                break
            parts.insert(0, p["name"])
            cur = p["parent_id"]
        paths[f["id"]] = "/" + "/".join(parts)

    aggregates = {}

    def resolve_active_config(doc: dict, pinned: str) -> str:
        configs = doc.get("configurations", [])
        if not configs:
            return ""
        if pinned:
            for c in configs:
                if c.get("id") == pinned:
                    return c.get("id", "")
        default = doc.get("default_config", "").strip()
        if default:
            for c in configs:
                if c.get("id") == default:
                    return c.get("id", "")
        return configs[0].get("id", "") if configs else ""

    def add_part(part_file: dict, quantity: int, config_id: str):
        doc = parse_part_content(part_file["content"])
        mpn = doc.get("mpn", "").strip()
        if not mpn:
            base = f"fid:{part_file['id']}"
        else:
            base = mpn
        key = base
        if config_id:
            key = base + "|cfg=" + config_id
        if key not in aggregates:
            aggregates[key] = {
                "count": 0,
                "file_id": part_file["id"],
                "file_row": part_file,
                "config_id": config_id,
            }
        elif aggregates[key]["file_id"] != part_file["id"] and mpn:
            pass
        aggregates[key]["count"] += quantity

    async def walk(fid: uuid.UUID, multiplier: int, config_hint: str, visited: dict):
        f = by_id.get(fid)
        if f is None:
            return
        if f["kind"] == "part":
            doc = parse_part_content(f["content"])
            cfg_id = resolve_active_config(doc, config_hint)
            add_part(f, multiplier, cfg_id)
            return
        if f["kind"] != "assembly":
            return
        if fid in visited:
            return
        visited[fid] = True

        for c in parse_bom_components(f["content"]):
            file_id_str = c.get("file_id", "")
            if not file_id_str:
                continue
            try:
                cid = uuid.UUID(file_id_str)
            except Exception:
                continue
            q = 1
            if c.get("quantity") and c["quantity"] > 0:
                q = c["quantity"]
            next_hint = config_hint
            if c.get("config_id"):
                next_hint = c["config_id"]
            await walk(cid, multiplier * q, next_hint, visited)

    for f in files:
        if f["kind"] == "assembly":
            visited = {}
            await walk(f["id"], 1, "", visited)

    out = []
    grand_total = 0.0
    has_any_price = False
    warnings = []

    for key, a in aggregates.items():
        doc = parse_part_content(a["file_row"]["content"])
        row = {
            "part": doc,
            "file_id": str(a["file_id"]),
            "path": paths.get(a["file_id"], ""),
            "count": a["count"],
            "material_path": doc.get("material_path", ""),
        }
        if a["config_id"]:
            row["config_id"] = a["config_id"]
            for c in doc.get("configurations", []):
                if c.get("id") == a["config_id"]:
                    row["config_label"] = c.get("label") or c.get("id", "")
                    break
        unit_price = None
        primary_dist = None
        for dist in doc.get("distributors", []):
            if dist.get("price_usd") is not None:
                unit_price = dist["price_usd"]
                primary_dist = {
                    "name": dist.get("name", ""),
                    "url": dist.get("url", ""),
                    "sku": dist.get("sku", ""),
                }
                break
        if primary_dist is None and doc.get("distributors"):
            d0 = doc["distributors"][0]
            primary_dist = {
                "name": d0.get("name", ""),
                "url": d0.get("url", ""),
                "sku": d0.get("sku", ""),
            }
        if unit_price is not None:
            row["unit_price_usd"] = unit_price
            tot = unit_price * a["count"]
            row["total_price_usd"] = tot
            grand_total += tot
            has_any_price = True
        if not doc.get("mpn"):
            warnings.append(f'Part "{doc.get("name", "")}" has no MPN')
        out.append(row)

    out.sort(key=lambda r: (r["part"].get("name", ""), r.get("config_id", ""), r["path"]))

    total_ptr = None
    if has_any_price:
        total_ptr = grand_total

    return ok_payload({
        "rows": out,
        "total_price_usd": total_ptr,
        "warnings": warnings,
    })