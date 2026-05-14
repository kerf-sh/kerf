"""
bim_categories.py — LLM tools for BIM element categories and hosted-element relationships.

Adds `category` and `host_ref` fields to elements inside existing .bim JSON docs.
Does NOT touch compile_bim_to_ifc or any other core bim.py logic.
"""

import json
import uuid as _uuid

from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx
from tools.bim import ensure_folders, record_revision_for_file, resolve_path, serialize_bim

# ── Constants ──────────────────────────────────────────────────────────────────

CATEGORIES = [
    'Wall', 'Floor', 'Roof', 'Door', 'Window', 'Room',
    'Column', 'Beam', 'Stair', 'Railing', 'Casework', 'Site',
    'Generic', 'MEP_Duct', 'MEP_Pipe', 'MEP_Conduit',
]

# hostedCategory -> list of valid host categories.
# Empty list means the category cannot be hosted on anything.
# Category absent from this dict means unconstrained (any host allowed).
HOST_RULES: dict[str, list[str]] = {
    'Door':        ['Wall'],
    'Window':      ['Wall'],
    'Casework':    ['Floor', 'Wall'],
    'MEP_Duct':    [],
    'MEP_Pipe':    [],
    'MEP_Conduit': [],
}

# ── Pure helpers (also exercised by tests without a DB) ───────────────────────

def validate_category(category: str) -> bool:
    return category in CATEGORIES


def validate_host_ref(hosted_category: str, host_category: str) -> bool:
    """
    Returns True if hosted_category is allowed to sit on host_category.
    - Not in HOST_RULES → unconstrained, any host is fine.
    - Empty list in HOST_RULES → cannot be hosted.
    - Non-empty list → host_category must be in the list.
    """
    if hosted_category not in HOST_RULES:
        return True
    allowed = HOST_RULES[hosted_category]
    if not allowed:
        return False
    return host_category in allowed


def _all_elements(bim_doc: dict):
    """
    Yields (array_key, index, element) for every object in every list field.
    """
    for key, val in bim_doc.items():
        if isinstance(val, list):
            for i, el in enumerate(val):
                if isinstance(el, dict):
                    yield key, i, el


def find_hosted_elements(bim_doc: dict, host_id: str) -> list[str]:
    """Return ids of elements directly hosted on host_id."""
    return [
        el['id']
        for _, _, el in _all_elements(bim_doc)
        if el.get('host_ref') == host_id and 'id' in el
    ]


def _descendant_ids(bim_doc: dict, host_id: str) -> list[str]:
    """Collect all element ids transitively hosted on host_id (depth-first)."""
    direct = find_hosted_elements(bim_doc, host_id)
    result = []
    for eid in direct:
        result.append(eid)
        result.extend(_descendant_ids(bim_doc, eid))
    return result


def _translate_element(el: dict, delta: list) -> dict:
    dx, dy = delta[0], delta[1]
    dz = delta[2] if len(delta) > 2 else 0
    el = dict(el)

    if isinstance(el.get('position'), list):
        pos = el['position']
        x, y = pos[0] if len(pos) > 0 else 0, pos[1] if len(pos) > 1 else 0
        z = pos[2] if len(pos) > 2 else 0
        el['position'] = [x + dx, y + dy, z + dz]

    if isinstance(el.get('from'), list):
        f = el['from']
        fx, fy = f[0] if len(f) > 0 else 0, f[1] if len(f) > 1 else 0
        if len(f) == 3:
            el['from'] = [fx + dx, fy + dy, f[2] + dz]
        else:
            el['from'] = [fx + dx, fy + dy]

    if isinstance(el.get('to'), list):
        t = el['to']
        tx, ty = t[0] if len(t) > 0 else 0, t[1] if len(t) > 1 else 0
        if len(t) == 3:
            el['to'] = [tx + dx, ty + dy, t[2] + dz]
        else:
            el['to'] = [tx + dx, ty + dy]

    return el


def cascade_transform(bim_doc: dict, host_id: str, delta: list) -> dict:
    """
    Translate host_id and all its descendants by delta=[dx,dy,dz].
    Returns a new bim_doc; original is not mutated.
    """
    to_move = {host_id, *_descendant_ids(bim_doc, host_id)}
    new_doc = {}
    for key, val in bim_doc.items():
        if not isinstance(val, list):
            new_doc[key] = val
            continue
        new_list = []
        for el in val:
            if isinstance(el, dict) and el.get('id') in to_move:
                new_list.append(_translate_element(el, delta))
            else:
                new_list.append(el)
        new_doc[key] = new_list
    return new_doc


def remove_with_hosted(bim_doc: dict, element_id: str) -> tuple[dict, list[str]]:
    """
    Remove element_id and all its descendants.
    Returns (new_doc, orphan_ids) — orphans are elements outside the removed
    set whose host_ref pointed at something in the removed set.
    """
    to_remove = {element_id, *_descendant_ids(bim_doc, element_id)}
    new_doc = {}
    for key, val in bim_doc.items():
        if not isinstance(val, list):
            new_doc[key] = val
            continue
        new_doc[key] = [
            el for el in val
            if not (isinstance(el, dict) and el.get('id') in to_remove)
        ]

    orphans = [
        el.get('id')
        for _, _, el in _all_elements(new_doc)
        if el.get('host_ref') in to_remove and el.get('id')
    ]
    return new_doc, orphans


def validate_bim_categories_doc(bim_doc: dict) -> dict:
    """
    Validate all elements in a bim_doc for category correctness and host_ref integrity.
    Returns {'ok': bool, 'errors': [...], 'warnings': [...]}.
    """
    errors = []
    warnings = []
    all_ids = {el['id'] for _, _, el in _all_elements(bim_doc) if 'id' in el}

    for key, i, el in _all_elements(bim_doc):
        ref = f"{key}[{i}]" + (f" id={el['id']}" if 'id' in el else "")

        if 'category' in el and not validate_category(el['category']):
            errors.append(f"{ref}: unknown category '{el['category']}'")

        if 'host_ref' in el:
            host_ref = el['host_ref']
            if host_ref not in all_ids:
                errors.append(f"{ref}: host_ref '{host_ref}' does not exist in document")
            else:
                # Find host element and check rule
                host_el = next(
                    (e for _, _, e in _all_elements(bim_doc) if e.get('id') == host_ref),
                    None,
                )
                if host_el and 'category' in el and 'category' in host_el:
                    if not validate_host_ref(el['category'], host_el['category']):
                        errors.append(
                            f"{ref}: category '{el['category']}' cannot be hosted on "
                            f"'{host_el['category']}' (host_ref={host_ref})"
                        )

    return {'ok': len(errors) == 0, 'errors': errors, 'warnings': warnings}


# ── DB helpers ─────────────────────────────────────────────────────────────────

async def _load_bim(ctx: ProjectCtx, file_id: str) -> dict | None:
    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE id = $1 AND project_id = $2 AND kind = 'bim'",
        _uuid.UUID(file_id), ctx.project_id,
    )
    if not row:
        return None
    return json.loads(row['content'] or '{}')


async def _save_bim(ctx: ProjectCtx, file_id: str, bim_doc: dict):
    body = serialize_bim(bim_doc)
    await ctx.pool.execute(
        "UPDATE files SET content = $1 WHERE id = $2 AND project_id = $3",
        body, _uuid.UUID(file_id), ctx.project_id,
    )
    await record_revision_for_file(ctx, _uuid.UUID(file_id), body, "tool")


def _find_element(bim_doc: dict, element_id: str):
    """Return (array_key, index, element) or (None, None, None) if not found."""
    for key, i, el in _all_elements(bim_doc):
        if el.get('id') == element_id:
            return key, i, el
    return None, None, None


# ── Tool: set_element_category ─────────────────────────────────────────────────

_set_element_category_spec = ToolSpec(
    name='set_element_category',
    description=(
        'Set the category field on a BIM element. '
        'Valid categories: ' + ', '.join(CATEGORIES)
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'file_id':    {'type': 'string'},
            'element_id': {'type': 'string'},
            'category':   {'type': 'string'},
        },
        'required': ['file_id', 'element_id', 'category'],
    },
)


@register(_set_element_category_spec, write=True)
async def run_set_element_category(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f'invalid args: {e}', 'BAD_ARGS')

    file_id = a.get('file_id', '')
    element_id = a.get('element_id', '')
    category = a.get('category', '')

    if not validate_category(category):
        return err_payload(
            f"unknown category '{category}'. Valid: {CATEGORIES}", 'BAD_CATEGORY'
        )

    bim_doc = await _load_bim(ctx, file_id)
    if bim_doc is None:
        return err_payload('bim file not found', 'NOT_FOUND')

    key, idx, el = _find_element(bim_doc, element_id)
    if el is None:
        return err_payload(f"element '{element_id}' not found", 'NOT_FOUND')

    bim_doc[key][idx] = {**el, 'category': category}
    await _save_bim(ctx, file_id, bim_doc)
    return ok_payload({'element_id': element_id, 'category': category})


# ── Tool: set_element_host ─────────────────────────────────────────────────────

_set_element_host_spec = ToolSpec(
    name='set_element_host',
    description=(
        'Attach a BIM element to a host element via host_ref. '
        'Validates HOST_RULES (e.g. Door must host on Wall). '
        'Rejects invalid host category pairs.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'file_id':    {'type': 'string'},
            'element_id': {'type': 'string'},
            'host_ref':   {'type': 'string'},
        },
        'required': ['file_id', 'element_id', 'host_ref'],
    },
)


@register(_set_element_host_spec, write=True)
async def run_set_element_host(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f'invalid args: {e}', 'BAD_ARGS')

    file_id    = a.get('file_id', '')
    element_id = a.get('element_id', '')
    host_ref   = a.get('host_ref', '')

    bim_doc = await _load_bim(ctx, file_id)
    if bim_doc is None:
        return err_payload('bim file not found', 'NOT_FOUND')

    _, _, el = _find_element(bim_doc, element_id)
    if el is None:
        return err_payload(f"element '{element_id}' not found", 'NOT_FOUND')

    _, _, host_el = _find_element(bim_doc, host_ref)
    if host_el is None:
        return err_payload(f"host element '{host_ref}' not found", 'NOT_FOUND')

    # Validate host rules when both categories are known
    el_cat   = el.get('category')
    host_cat = host_el.get('category')
    if el_cat and host_cat and not validate_host_ref(el_cat, host_cat):
        return err_payload(
            f"'{el_cat}' cannot be hosted on '{host_cat}'", 'INVALID_HOST'
        )

    key, idx, el = _find_element(bim_doc, element_id)
    bim_doc[key][idx] = {**el, 'host_ref': host_ref}
    await _save_bim(ctx, file_id, bim_doc)
    return ok_payload({'element_id': element_id, 'host_ref': host_ref})


# ── Tool: unset_element_host ───────────────────────────────────────────────────

_unset_element_host_spec = ToolSpec(
    name='unset_element_host',
    description='Remove the host_ref from a BIM element, detaching it from its host.',
    input_schema={
        'type': 'object',
        'properties': {
            'file_id':    {'type': 'string'},
            'element_id': {'type': 'string'},
        },
        'required': ['file_id', 'element_id'],
    },
)


@register(_unset_element_host_spec, write=True)
async def run_unset_element_host(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f'invalid args: {e}', 'BAD_ARGS')

    file_id    = a.get('file_id', '')
    element_id = a.get('element_id', '')

    bim_doc = await _load_bim(ctx, file_id)
    if bim_doc is None:
        return err_payload('bim file not found', 'NOT_FOUND')

    key, idx, el = _find_element(bim_doc, element_id)
    if el is None:
        return err_payload(f"element '{element_id}' not found", 'NOT_FOUND')

    new_el = {k: v for k, v in el.items() if k != 'host_ref'}
    bim_doc[key][idx] = new_el
    await _save_bim(ctx, file_id, bim_doc)
    return ok_payload({'element_id': element_id, 'host_ref': None})


# ── Tool: move_element ─────────────────────────────────────────────────────────

_move_element_spec = ToolSpec(
    name='move_element',
    description=(
        'Translate a BIM element and all elements hosted on it (recursively) '
        'by delta=[dx, dy, dz] in millimetres.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'file_id':    {'type': 'string'},
            'element_id': {'type': 'string'},
            'delta': {
                'type': 'array',
                'items': {'type': 'number'},
                'minItems': 2,
                'maxItems': 3,
            },
        },
        'required': ['file_id', 'element_id', 'delta'],
    },
)


@register(_move_element_spec, write=True)
async def run_move_element(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f'invalid args: {e}', 'BAD_ARGS')

    file_id    = a.get('file_id', '')
    element_id = a.get('element_id', '')
    delta      = a.get('delta', [])

    if not isinstance(delta, list) or len(delta) < 2:
        return err_payload('delta must be [dx, dy] or [dx, dy, dz]', 'BAD_ARGS')

    bim_doc = await _load_bim(ctx, file_id)
    if bim_doc is None:
        return err_payload('bim file not found', 'NOT_FOUND')

    _, _, el = _find_element(bim_doc, element_id)
    if el is None:
        return err_payload(f"element '{element_id}' not found", 'NOT_FOUND')

    new_doc = cascade_transform(bim_doc, element_id, delta)
    await _save_bim(ctx, file_id, new_doc)

    descendants = _descendant_ids(bim_doc, element_id)
    return ok_payload({
        'element_id':   element_id,
        'delta':        delta,
        'also_moved':   descendants,
    })


# ── Tool: find_hosted ──────────────────────────────────────────────────────────

_find_hosted_spec = ToolSpec(
    name='find_hosted',
    description='Return the ids of all elements directly hosted on a given host element.',
    input_schema={
        'type': 'object',
        'properties': {
            'file_id': {'type': 'string'},
            'host_id': {'type': 'string'},
        },
        'required': ['file_id', 'host_id'],
    },
)


@register(_find_hosted_spec)
async def run_find_hosted(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f'invalid args: {e}', 'BAD_ARGS')

    file_id = a.get('file_id', '')
    host_id = a.get('host_id', '')

    bim_doc = await _load_bim(ctx, file_id)
    if bim_doc is None:
        return err_payload('bim file not found', 'NOT_FOUND')

    hosted = find_hosted_elements(bim_doc, host_id)
    return ok_payload({'host_id': host_id, 'hosted': hosted})


# ── Tool: validate_bim_categories ─────────────────────────────────────────────

_validate_bim_categories_spec = ToolSpec(
    name='validate_bim_categories',
    description=(
        'Validate all element categories and host_ref relationships in a .bim file. '
        'Returns {ok, errors, warnings}.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'file_id': {'type': 'string'},
        },
        'required': ['file_id'],
    },
)


@register(_validate_bim_categories_spec)
async def run_validate_bim_categories(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f'invalid args: {e}', 'BAD_ARGS')

    file_id = a.get('file_id', '')
    bim_doc = await _load_bim(ctx, file_id)
    if bim_doc is None:
        return err_payload('bim file not found', 'NOT_FOUND')

    result = validate_bim_categories_doc(bim_doc)
    return ok_payload(result)
