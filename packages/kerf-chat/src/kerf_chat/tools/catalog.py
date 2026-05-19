"""
kerf_chat.tools.catalog — The 12-tool LLM surface.

This module owns the *only* list of ToolSpec objects that are advertised to
the LLM.  Every compute, file, and create operation is reached through one of
these 12 tools.  The underlying implementations (run_fem_run, run_cam_run,
run_create_sketch, …) are unchanged — only the registration surface shrinks.

Tool count: 14 (12 core + duplicate_object + delete_object for JSCAD arrays).
"""
from __future__ import annotations

from kerf_chat.tools.registry import ToolSpec

# ---------------------------------------------------------------------------
# 1. read_file
# ---------------------------------------------------------------------------
read_file_spec = ToolSpec(
    name="read_file",
    description=(
        "Read the full text content of a file by absolute path. "
        "Errors on binary kinds (e.g. step). "
        "Paths under '/docs/llm/' route to the embedded Kerf authoring corpus "
        "(use search_kerf_docs to discover them)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path of the file to read."},
        },
        "required": ["path"],
    },
)

# ---------------------------------------------------------------------------
# 2. write_file
# ---------------------------------------------------------------------------
write_file_spec = ToolSpec(
    name="write_file",
    description=(
        "Replace the entire content of a text file. "
        "Creates intermediate folders if missing. "
        "Use edit_file for targeted edits."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    },
)

# ---------------------------------------------------------------------------
# 3. edit_file
# ---------------------------------------------------------------------------
edit_file_spec = ToolSpec(
    name="edit_file",
    description=(
        "Replace a unique substring inside a text file. "
        "Errors if old_string occurs zero or more than one time (use replace_all=true to replace all). "
        "Use this for surgical edits."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old_string": {"type": "string"},
            "new_string": {"type": "string"},
            "replace_all": {
                "type": "boolean",
                "description": "If true, replace every occurrence instead of requiring uniqueness.",
            },
        },
        "required": ["path", "old_string", "new_string"],
    },
)

# ---------------------------------------------------------------------------
# 4. list_files
# ---------------------------------------------------------------------------
list_files_spec = ToolSpec(
    name="list_files",
    description=(
        "List every file in the current project as a flat array of absolute paths. "
        "Pass glob to filter (e.g. '*.jscad', '/parts/**')."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "glob": {
                "type": "string",
                "description": "Optional glob pattern to filter results.",
            },
        },
    },
)

# ---------------------------------------------------------------------------
# 5. search_files
# ---------------------------------------------------------------------------
search_files_spec = ToolSpec(
    name="search_files",
    description=(
        "Case-insensitive substring / regex search across all text files in the project. "
        "Returns matching lines with file paths."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Substring or regex to search for.",
            },
            "glob": {
                "type": "string",
                "description": "Optional glob pattern to restrict which files are searched.",
            },
        },
        "required": ["pattern"],
    },
)

# ---------------------------------------------------------------------------
# 6. create_file
# ---------------------------------------------------------------------------
create_file_spec = ToolSpec(
    name="create_file",
    description=(
        "Create a new file with a canonical seed for its kind. "
        "kind='sketch' → .sketch with empty constraint graph. "
        "kind='feature' → .feature with empty OCCT timeline. "
        "kind='part' → .part library metadata stub. "
        "kind='circuit' → .circuit.tsx tscircuit scaffold. "
        "kind='assembly' → .assembly with empty components array. "
        "kind='drawing' → .drawing JSON stub. "
        "kind='file' → plain text/JSCAD file (content required). "
        "After creation, edit the resulting JSON via write_file / edit_file — "
        "consult the corresponding /docs/llm/<kind>.md for the schema."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path for the new file.",
            },
            "kind": {
                "type": "string",
                "enum": ["sketch", "feature", "part", "circuit", "assembly", "drawing", "file"],
                "description": "File kind. Defaults to 'file'.",
            },
            "options": {
                "type": "object",
                "description": (
                    "Kind-specific options. "
                    "sketch: {plane: 'XY'|'XZ'|'YZ', name, description}. "
                    "feature: {name}. "
                    "part: {metadata: {name, description, manufacturer, mpn, ...}}. "
                    "circuit: {name, width_mm, height_mm}. "
                    "file: {content}."
                ),
            },
        },
        "required": ["path", "kind"],
    },
)

# ---------------------------------------------------------------------------
# 7. describe_part
# ---------------------------------------------------------------------------
describe_part_spec = ToolSpec(
    name="describe_part",
    description=(
        "Read-only inspector for any Kerf file kind. "
        "Returns the parsed structure, object IDs, feature list, component list, "
        "or circuit summary depending on the file kind. "
        "Use this before editing to understand the current shape."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path of the file to describe.",
            },
            "part_id": {
                "type": "string",
                "description": "Optional object/component/feature id to zoom in on.",
            },
        },
        "required": ["path"],
    },
)

# ---------------------------------------------------------------------------
# 8. search_kerf_docs
# ---------------------------------------------------------------------------
search_kerf_docs_spec = ToolSpec(
    name="search_kerf_docs",
    description=(
        "Full-text search of the Kerf authoring documentation corpus. "
        "Returns ranked excerpts with file paths you can then load via read_file('/docs/llm/...'). "
        "Always call this before editing non-.jscad files to find the correct JSON schema."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural-language or keyword query (e.g. 'assembly component transform', 'fillet feature').",
            },
        },
        "required": ["query"],
    },
)

# ---------------------------------------------------------------------------
# 9. run_compute
# ---------------------------------------------------------------------------
run_compute_spec = ToolSpec(
    name="run_compute",
    description=(
        "Launch an async compute job on a Kerf file. "
        "engine='fem'    → finite-element analysis (stress, modal, thermal). "
        "engine='cfd'    → computational fluid dynamics. "
        "engine='spice'  → SPICE circuit simulation. "
        "engine='cam'    → CAM toolpath generation (G-code). "
        "engine='render' → photorealistic render (Cycles). "
        "engine='topo'   → topology optimisation (SIMP). "
        "engine='tess'   → mesh tessellation / STL export. "
        "Returns a job_id; call poll_compute(job_id) to track progress."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "engine": {
                "type": "string",
                "enum": ["fem", "cfd", "spice", "cam", "render", "topo", "tess"],
                "description": "Compute engine to invoke.",
            },
            "file_id": {
                "type": "string",
                "description": "UUID of the target file.",
            },
            "options": {
                "type": "object",
                "description": (
                    "Engine-specific options forwarded verbatim to the underlying engine. "
                    "fem: {solver, load_case, material_id, …}. "
                    "cfd: {model, mesh_size, …}. "
                    "cam: {operation, tool_diameter, step_over, …}. "
                    "render: {width, height, samples, …}. "
                    "topo: {volume_fraction, filter_radius, …}."
                ),
            },
        },
        "required": ["engine", "file_id"],
    },
)

# ---------------------------------------------------------------------------
# 10. poll_compute
# ---------------------------------------------------------------------------
poll_compute_spec = ToolSpec(
    name="poll_compute",
    description=(
        "Check the status of a queued compute job. "
        "Returns {status: 'queued'|'running'|'done'|'error', result_url?, error?}. "
        "Call repeatedly until status is 'done' or 'error'."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "job_id": {
                "type": "string",
                "description": "Job ID returned by run_compute.",
            },
        },
        "required": ["job_id"],
    },
)

# ---------------------------------------------------------------------------
# 11. import_step
# ---------------------------------------------------------------------------
import_step_spec = ToolSpec(
    name="import_step",
    description=(
        "Download a STEP or STL file from an HTTPS URL into the project. "
        "Times out after 30s; rejects files over 50MB."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "File name to save as (e.g. 'bracket.step')."},
            "source_url": {"type": "string", "description": "HTTPS URL of the STEP/STL file."},
            "parent_path": {"type": "string", "description": "Parent folder path (default '/')."},
        },
        "required": ["name", "source_url"],
    },
)

# ---------------------------------------------------------------------------
# 12. export_artifact
# ---------------------------------------------------------------------------
export_artifact_spec = ToolSpec(
    name="export_artifact",
    description=(
        "Request an export of a project file to a standard format. "
        "Returns a download URL or queues an async export job. "
        "Supported formats: gerber, dxf, step, stl, glb, png, pdf."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "UUID of the source file.",
            },
            "format": {
                "type": "string",
                "enum": ["gerber", "dxf", "step", "stl", "glb", "png", "pdf"],
                "description": "Target export format.",
            },
        },
        "required": ["file_id", "format"],
    },
)

# ---------------------------------------------------------------------------
# 13 & 14. duplicate_object / delete_object  (JSCAD array editing)
# ---------------------------------------------------------------------------
duplicate_object_spec = ToolSpec(
    name="duplicate_object",
    description=(
        "Clone a single Object (one entry in a Part's exported `[{id, geom}, ...]` array) "
        "and append the clone after the original. "
        "Pass new_id to set the clone's id; otherwise defaults to `<object_id>-copy[-N]`. "
        "Bails with PARSE_FAILED if the file isn't a clean `return [{id,...}, ...]`."
    ),
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

delete_object_spec = ToolSpec(
    name="delete_object",
    description=(
        "Remove a single Object entry from a Part's exported `[{id, geom}, ...]` array. "
        "Bails with PARSE_FAILED if the file isn't a clean `return [{id,...}, ...]`."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "object_id": {"type": "string"},
        },
        "required": ["path", "object_id"],
    },
)

# ---------------------------------------------------------------------------
# The authoritative 14-entry tool catalog sent to every LLM turn.
# Order matters: Anthropic caches everything up to (and including) the LAST
# entry — keep compute/rarely-changing tools later for better cache hits.
# ---------------------------------------------------------------------------
TOOL_CATALOG: list[ToolSpec] = [
    read_file_spec,
    write_file_spec,
    edit_file_spec,
    list_files_spec,
    search_files_spec,
    create_file_spec,
    describe_part_spec,
    search_kerf_docs_spec,
    duplicate_object_spec,
    delete_object_spec,
    import_step_spec,
    export_artifact_spec,
    run_compute_spec,
    poll_compute_spec,
]
