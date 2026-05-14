import json
import uuid
from fastapi import APIRouter, HTTPException, status, Request, Depends

from kerf_core.db.connection import get_pool_required
from kerf_core.dependencies import require_auth
from tools import ProjectCtx, specs, execute as execute_tool, err_payload


router = APIRouter()


async def get_user_workspace_role(conn, workspace_id: str, user_id: str):
    row = await conn.fetchrow(
        "SELECT role FROM workspace_members WHERE workspace_id = $1 AND user_id = $2",
        workspace_id, user_id,
    )
    return row["role"] if row else None


METHOD_TO_TOOL = {
    "files.list": "list_files",
    "files.read": "read_file",
    "files.write": "write_file",
    "files.edit": "edit_file",
    "files.create": "create_file",
    "files.delete": "delete_file",
    "files.search": "search_code",
    "import_step": "import_step",
    "equations.read": "read_equations",
    "equations.set": "set_equation",
    "configurations.add": "add_configuration",
    "configurations.set_active": "set_active_config",
    "revisions.list": "list_revisions",
    "revisions.restore": "restore_revision",
    "docs.search": "search_kerf_docs",
}


def send_rpc_error(code: int, message: str, rpc_id: any = None):
    return {
        "jsonrpc": "2.0",
        "error": {"code": code, "message": message},
        "id": rpc_id,
    }


@router.post("/rpc")
async def handle_rpc(request: Request, payload: dict = Depends(require_auth)):
    uid_str = payload.get("sub")
    if not uid_str:
        return send_rpc_error(-32600, "unauthorized")

    try:
        body = await request.json()
    except Exception:
        return send_rpc_error(-32700, "parse error")

    jsonrpc = body.get("jsonrpc", "")
    if jsonrpc != "2.0":
        return send_rpc_error(-32600, "invalid request: jsonrpc must be 2.0", body.get("id"))

    method = body.get("method", "")
    params = body.get("params", {})
    rpc_id = body.get("id")

    project_id_str = params.get("project_id", "")
    if not project_id_str:
        return send_rpc_error(-32602, "project_id is required", rpc_id)

    try:
        project_id = uuid.UUID(project_id_str)
    except ValueError:
        return send_rpc_error(-32602, "invalid project_id format", rpc_id)

    try:
        uid = uuid.UUID(uid_str)
    except ValueError:
        return send_rpc_error(-32603, "internal error: invalid user id", rpc_id)

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT workspace_id FROM projects WHERE id = $1",
            project_id_str,
        )
        if not row:
            return send_rpc_error(-32600, "project not found or access denied", rpc_id)

        ws_id = str(row["workspace_id"])
        role = await get_user_workspace_role(conn, ws_id, uid_str)
        if not role:
            return send_rpc_error(-32600, "project not found or access denied", rpc_id)

    tool_name = METHOD_TO_TOOL.get(method, "")
    if not tool_name:
        return send_rpc_error(-32601, f"method not found: {method}", rpc_id)

    ctx = ProjectCtx(
        pool=pool,
        storage=None,
        project_id=project_id,
        user_id=uid,
        role=role,
        http_client=None,
    )

    tool_args = json.dumps(params).encode()
    result = await execute_tool(ctx, tool_name, tool_args)

    try:
        result_val = json.loads(result)
    except Exception:
        result_val = result

    if isinstance(result_val, dict) and result_val.get("error"):
        err_msg = result_val.get("error", "")
        if isinstance(err_msg, str):
            return send_rpc_error(-32603, err_msg, rpc_id)
        return send_rpc_error(-32603, str(err_msg), rpc_id)

    return {
        "jsonrpc": "2.0",
        "result": result_val,
        "id": rpc_id,
    }


@router.get("/tools")
async def list_tools(payload: dict = Depends(require_auth)):
    uid_str = payload.get("sub")
    if not uid_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT p.id, p.workspace_id FROM projects p "
            "JOIN workspace_members wm ON wm.workspace_id = p.workspace_id "
            "WHERE wm.user_id = $1 LIMIT 1",
            uid_str,
        )
        if not rows:
            role = "viewer"
        else:
            ws_id = str(rows[0]["workspace_id"])
            role = await get_user_workspace_role(conn, ws_id, uid_str) or "viewer"

    return {"tools": specs(role)}
