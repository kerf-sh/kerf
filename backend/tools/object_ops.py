import json
import re
import uuid
from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx


def js_skip_string(src: str, i: int) -> int:
    if i >= len(src):
        return i
    q = src[i]
    if q not in ('"', "'", '`'):
        return i
    j = i + 1
    while j < len(src):
        c = src[j]
        if c == '\\':
            j += 2
            continue
        if q == '`' and c == '$' and j + 1 < len(src) and src[j + 1] == '{':
            depth = 1
            j += 2
            while j < len(src) and depth > 0:
                cc = src[j]
                if cc in ('"', "'", '`'):
                    j = js_skip_string(src, j)
                    continue
                if cc == '/' and j + 1 < len(src) and src[j + 1] in ('/', '*'):
                    j = js_skip_comment(src, j)
                    continue
                if cc == '{':
                    depth += 1
                elif cc == '}':
                    depth -= 1
                j += 1
            continue
        if c == q:
            return j + 1
        j += 1
    return j


def js_skip_comment(src: str, i: int) -> int:
    if i + 1 >= len(src) or src[i] != '/':
        return i
    next_c = src[i + 1]
    if next_c == '/':
        j = i + 2
        while j < len(src) and src[j] != '\n':
            j += 1
        return j
    if next_c == '*':
        j = i + 2
        while j + 1 < len(src):
            if src[j] == '*' and src[j + 1] == '/':
                return j + 2
            j += 1
        return len(src)
    return i


def js_skip_aux(src: str, i: int) -> int:
    if i >= len(src):
        return i
    c = src[i]
    if c in ('"', "'", '`'):
        return js_skip_string(src, i)
    if c == '/' and i + 1 < len(src) and src[i + 1] in ('/', '*'):
        return js_skip_comment(src, i)
    return i


def js_match_bracket(src: str, start: int, open_b: str, close_b: str) -> int:
    if start >= len(src) or src[start] != open_b:
        return -1
    depth = 0
    i = start
    while i < len(src):
        a = js_skip_aux(src, i)
        if a != i:
            i = a
            continue
        c = src[i]
        if c == open_b:
            depth += 1
        elif c == close_b:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def is_js_word_byte(b: str) -> bool:
    return (b >= 'a' and b <= 'z') or (b >= 'A' and b <= 'Z') or (b >= '0' and b <= '9') or b == '_' or b == '$'


def is_js_whitespace_byte(b: str) -> bool:
    return b in ' \t\n\r\f\v'


def js_locate_return_array(source: str) -> tuple:
    candidates = []
    i = 0
    while i < len(source):
        j = js_skip_aux(source, i)
        if j != i:
            i = j
            continue
        if source[i] == 'r' and i + 6 <= len(source) and source[i:i + 6] == "return":
            before = '\n' if i == 0 else source[i - 1]
            if not is_js_word_byte(before):
                after = ' ' if i + 6 >= len(source) else source[i + 6]
                if is_js_whitespace_byte(after) or after == '/':
                    k = i + 6
                    while k < len(source):
                        a = js_skip_aux(source, k)
                        if a != k:
                            k = a
                            continue
                        if is_js_whitespace_byte(source[k]):
                            k += 1
                            continue
                        break
                    if k < len(source) and source[k] == '[':
                        end = js_match_bracket(source, k, '[', ']')
                        if end > 0:
                            slice_src = source[k:end + 1]
                            if re.search(r'\bid\s*:', slice_src):
                                candidates.append((k, end))
                            i = end + 1
                            continue
                    i = k
                    continue
        i += 1
    if len(candidates) != 1:
        return -1, -1
    return candidates[0][0], candidates[0][1]


def js_parse_array_entries(source: str, arr_start: int, arr_end: int) -> tuple:
    entries = []
    i = arr_start + 1
    while i < arr_end:
        a = js_skip_aux(source, i)
        if a != i:
            i = a
            continue
        c = source[i]
        if is_js_whitespace_byte(c) or c == ',':
            i += 1
            continue
        if c != '{':
            return None, False
        entry_start = i
        entry_end = js_match_bracket(source, i, '{', '}')
        if entry_end < 0:
            return None, False
        s = entry_end + 1
        while s < arr_end:
            sa = js_skip_aux(source, s)
            if sa != s:
                s = sa
                continue
            if is_js_whitespace_byte(source[s]):
                s += 1
                continue
            break
        sep_end = entry_end + 1
        if s < arr_end and source[s] == ',':
            sep_end = s + 1
        id_val, ok = js_read_entry_id(source, entry_start, entry_end)
        entries.append({
            "entry_start": entry_start,
            "entry_end": entry_end,
            "sep_end": sep_end,
            "id": id_val,
            "valid": ok,
        })
        i = sep_end
    return entries, True


def js_read_entry_id(source: str, entry_start: int, entry_end: int) -> tuple:
    i = entry_start + 1
    while i < entry_end:
        a = js_skip_aux(source, i)
        if a != i:
            i = a
            continue
        if i + 1 < entry_end and source[i] == 'i' and source[i + 1] == 'd':
            before = ' ' if i == 0 else source[i - 1]
            after = ' ' if i + 2 >= entry_end else source[i + 2]
            if not is_js_word_byte(before) and not is_js_word_byte(after):
                k = i + 2
                while k < entry_end and is_js_whitespace_byte(source[k]):
                    k += 1
                if k >= entry_end or source[k] != ':':
                    i += 1
                    continue
                k += 1
                while k < entry_end and is_js_whitespace_byte(source[k]):
                    k += 1
                if k >= entry_end:
                    return "", False
                q = source[k]
                if q not in ('"', "'", '`'):
                    return "", False
                end = js_skip_string(source, k)
                if end <= k + 1 or end > entry_end + 1:
                    return "", False
                return source[k + 1:end - 1], True
        i += 1
    return "", False


def js_find_object_entry(source: str, object_id: str) -> tuple:
    arr_start, arr_end = js_locate_return_array(source)
    if arr_start < 0:
        return None, -1, False
    entries, ok = js_parse_array_entries(source, arr_start, arr_end)
    if not ok:
        return None, -1, False
    for e in entries:
        if not e["valid"]:
            return None, -1, False
    for i, e in enumerate(entries):
        if e["id"] == object_id:
            return entries, i, True
    return entries, -1, True


def js_mint_copy_id(base: str, taken: list) -> str:
    taken_set = set(taken)
    root = base + "-copy"
    if root not in taken_set:
        return root
    n = 2
    while True:
        cand = f"{root}-{n}"
        if cand not in taken_set:
            return cand
        n += 1


def escape_for_js_quote(s: str, q: str) -> str:
    s = s.replace('\\', '\\\\')
    s = s.replace(q, '\\' + q)
    return s


def js_duplicate_object(source: str, object_id: str, new_id: str) -> tuple:
    if not source or not object_id:
        return "", False
    entries, idx, _ = js_find_object_entry(source, object_id)
    if entries is None or idx < 0:
        return "", False
    target = entries[idx]
    taken = []
    for e in entries:
        if e["id"]:
            taken.append(e["id"])
    if not new_id:
        new_id = js_mint_copy_id(object_id, taken)
    for t in taken:
        if t == new_id:
            return "", False
    entry_text = source[target["entry_start"]:target["entry_end"] + 1]
    renamed, ok = js_rename_id_in_entry(entry_text, object_id, new_id)
    if not ok:
        return "", False
    line_start = target["entry_start"]
    while line_start > 0 and source[line_start - 1] != '\n':
        line_start -= 1
    indent = source[line_start:target["entry_start"]]
    has_trailing_comma = target["sep_end"] > target["entry_end"] + 1
    if has_trailing_comma:
        insertion = "\n" + indent + renamed + ","
    else:
        insertion = ",\n" + indent + renamed
    insert_at = target["sep_end"]
    return source[:insert_at] + insertion + source[insert_at:], True


def js_delete_object(source: str, object_id: str) -> tuple:
    if not source or not object_id:
        return "", False
    entries, idx, _ = js_find_object_entry(source, object_id)
    if entries is None or idx < 0:
        return "", False
    target = entries[idx]
    from_idx = target["entry_start"]
    to_idx = target["sep_end"]
    while from_idx > 0 and source[from_idx - 1] in ' \t':
        from_idx -= 1
    if from_idx > 0 and source[from_idx - 1] == '\n':
        look = to_idx
        while look < len(source) and source[look] in ' \t':
            look += 1
        if look < len(source) and source[look] == '\n':
            to_idx = look + 1
        else:
            from_idx -= 1
    return source[:from_idx] + source[to_idx:], True


def js_rename_id_in_entry(entry_text: str, old_id: str, new_id: str) -> tuple:
    i = 1
    while i < len(entry_text) - 1:
        a = js_skip_aux(entry_text, i)
        if a != i:
            i = a
            continue
        if i + 1 < len(entry_text) and entry_text[i] == 'i' and entry_text[i + 1] == 'd':
            before = ' ' if i == 0 else entry_text[i - 1]
            after = ' ' if i + 2 >= len(entry_text) else entry_text[i + 2]
            if not is_js_word_byte(before) and not is_js_word_byte(after):
                k = i + 2
                while k < len(entry_text) and is_js_whitespace_byte(entry_text[k]):
                    k += 1
                if k >= len(entry_text) or entry_text[k] != ':':
                    i += 1
                    continue
                k += 1
                while k < len(entry_text) and is_js_whitespace_byte(entry_text[k]):
                    k += 1
                if k >= len(entry_text):
                    return "", False
                q = entry_text[k]
                if q not in ('"', "'", '`'):
                    i += 1
                    continue
                end = js_skip_string(entry_text, k)
                if end <= k + 1:
                    return "", False
                lit = entry_text[k + 1:end - 1]
                if lit != old_id:
                    i += 1
                    continue
                return entry_text[:k] + q + escape_for_js_quote(new_id, q) + q + entry_text[end:], True
        i += 1
    return "", False


async def resolve_path(ctx: ProjectCtx, path: str) -> dict:
    clean = path.rstrip("/")
    if not clean.startswith("/"):
        return {"exists": False}
    row = await ctx.pool.fetchrow(
        "SELECT id, parent_id, name, kind FROM files WHERE project_id = $1 AND path = $2 AND deleted_at IS NULL",
        ctx.project_id, clean,
    )
    if not row:
        return {"exists": False}
    return {
        "exists": True,
        "id": row["id"],
        "parent_id": row["parent_id"],
        "name": row["name"],
        "kind": row["kind"],
    }


async def record_revision_for_file(ctx: ProjectCtx, file_id: uuid.UUID, content: str, source: str):
    cap = ctx.file_revisions_max if ctx.file_revisions_max > 0 else 200
    new_id = uuid.uuid4()
    preview = content[:200] if len(content) > 200 else content
    latest = await ctx.pool.fetchrow(
        "SELECT id, kind FROM file_revisions WHERE file_id = $1 ORDER BY created_at DESC LIMIT 1",
        file_id,
    )
    user_id = ctx.user_id if ctx.user_id != uuid.Nil else None
    if latest is None or latest["kind"] == "base":
        diffs_after = 0
    else:
        diffs_after = await ctx.pool.fetchval(
            "SELECT COUNT(*) FROM file_revisions WHERE file_id = $1 AND kind = 'diff' AND created_at > COALESCE((SELECT MAX(created_at) FROM file_revisions WHERE file_id = $1 AND kind = 'base'), 'epoch'::timestamptz)",
            file_id,
        )
    make_base = latest is None or diffs_after >= 20
    import gzip
    import base64
    if make_base:
        gz = gzip.compress(content.encode())
        await ctx.pool.execute(
            "INSERT INTO file_revisions(id, file_id, content, content_gz, kind, source, user_id, content_preview) VALUES ($1, $2, $3, $4, 'base', $5, $6, $7)",
            new_id, file_id, content, base64.b64encode(gz).decode(), source, user_id, preview,
        )
    else:
        parent_content_row = await ctx.pool.fetchrow(
            "SELECT content_gz FROM file_revisions WHERE id = $1",
            latest["id"],
        )
        parent_content = content
        if parent_content_row and parent_content_row["content_gz"]:
            parent_content = gzip.decompress(parent_content_row["content_gz"]).decode()
        delta = content
        gz = gzip.compress(delta.encode())
        await ctx.pool.execute(
            "INSERT INTO file_revisions(id, file_id, content, content_gz, kind, parent_revision_id, source, user_id, content_preview) VALUES ($1, $2, '', $3, 'diff', $4, $5, $6, $7)",
            new_id, file_id, base64.b64encode(gz).decode(), latest["id"], source, user_id, preview,
        )
    await ctx.pool.execute(
        "DELETE FROM file_revisions WHERE file_id = $1 AND created_at < (SELECT created_at FROM file_revisions WHERE file_id = $1 ORDER BY created_at DESC OFFSET $2 LIMIT 1)",
        file_id, cap,
    )
    return new_id


duplicate_object_spec = ToolSpec(
    name="duplicate_object",
    description="Clone a single Object (one entry in a Part's exported `[{id, geom}, ...]` array) and append the clone after the original. Pass `new_id` to set the clone's id; otherwise it defaults to `<object_id>-copy[-N]`. Bails with PARSE_FAILED if the file's structure isn't a clean `return [{id,...}, ...]`.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "object_id": {"type": "string"},
            "new_id": {"type": "string"},
        },
        "required": ["path", "object_id"],
    },
)


@register(duplicate_object_spec, write=True)
async def run_duplicate_object(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("path", "")
    object_id = a.get("object_id", "")
    new_id = a.get("new_id", "")

    if not path or not object_id:
        return err_payload("path and object_id are required", "BAD_ARGS")

    rp = await resolve_path(ctx, path)
    if not rp.get("exists"):
        return err_payload(f"file not found: {path}", "NOT_FOUND")

    kind = rp.get("kind")
    if kind in ("step", "folder", "assembly", "drawing"):
        return err_payload(f"not a JSCAD file (kind={kind})", "BAD_KIND")
    if kind == "sketch":
        return err_payload("sketches are read-only via tools; use the sketch UI", "READONLY_SKETCH")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2",
        rp["id"], ctx.project_id,
    )
    content = row["content"] if row else ""

    next_content, ok = js_duplicate_object(content, object_id, new_id)
    if not ok:
        return err_payload(
            "couldn't auto-duplicate; the file's structure isn't a single `return [{id, geom}, ...]`. Use edit_file to clone the entry by hand.",
            "PARSE_FAILED",
        )

    await ctx.pool.execute(
        "UPDATE files SET content = $1, updated_at = now() WHERE id = $2 AND project_id = $3",
        next_content, rp["id"], ctx.project_id,
    )
    await record_revision_for_file(ctx, rp["id"], next_content, "tool")

    return ok_payload({
        "path": path,
        "object_id": object_id,
    })


delete_object_spec = ToolSpec(
    name="delete_object",
    description="Remove a single Object entry from a Part's exported `[{id, geom}, ...]` array. Bails with PARSE_FAILED if the file's structure isn't a clean `return [{id,...}, ...]`.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "object_id": {"type": "string"},
        },
        "required": ["path", "object_id"],
    },
)


@register(delete_object_spec, write=True)
async def run_delete_object(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path = a.get("path", "")
    object_id = a.get("object_id", "")

    if not path or not object_id:
        return err_payload("path and object_id are required", "BAD_ARGS")

    rp = await resolve_path(ctx, path)
    if not rp.get("exists"):
        return err_payload(f"file not found: {path}", "NOT_FOUND")

    kind = rp.get("kind")
    if kind in ("step", "folder", "assembly", "drawing"):
        return err_payload(f"not a JSCAD file (kind={kind})", "BAD_KIND")
    if kind == "sketch":
        return err_payload("sketches are read-only via tools; use the sketch UI", "READONLY_SKETCH")

    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2",
        rp["id"], ctx.project_id,
    )
    content = row["content"] if row else ""

    next_content, ok = js_delete_object(content, object_id)
    if not ok:
        return err_payload(
            "couldn't auto-delete; the file's structure isn't a single `return [{id, geom}, ...]`. Use edit_file to remove the entry by hand.",
            "PARSE_FAILED",
        )

    await ctx.pool.execute(
        "UPDATE files SET content = $1, updated_at = now() WHERE id = $2 AND project_id = $3",
        next_content, rp["id"], ctx.project_id,
    )
    await record_revision_for_file(ctx, rp["id"], next_content, "tool")

    return ok_payload({
        "path": path,
        "object_id": object_id,
    })