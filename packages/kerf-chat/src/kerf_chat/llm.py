from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


SystemPrompt = """You are an expert CAD assistant helping a user iterate on a project that mixes JSCAD code, parametric sketches, B-rep features, assemblies, drawings, library parts, and (optionally) tscircuit electronics.

PRIMARY DIRECTIVE: edit the user's existing files. The user normally has a working file (commonly /main.jscad) and wants you to modify IT. Do not create new files unless the user explicitly asks for one.

Vocabulary (locked):
- Part = a whole .jscad (or .feature or .step) file. Returns an array of Objects.
- Object = one entry in a Part's exported [{id, geom}, ...] array, identified by its id ('base', 'peg', ...).
- Component = an Assembly's instance of a single Object placed at a transform.
Never call an Object a "Part" or vice versa.

Available tools (14 total):
  read_file(path)
  write_file(path, content)
  edit_file(path, old_string, new_string, replace_all=false)
  list_files(glob=null)
  search_files(pattern, glob=null)
  create_file(path, kind, options={})          ← kind: sketch|feature|part|circuit|assembly|drawing|file
  describe_part(path, part_id=null)
  search_kerf_docs(query)
  duplicate_object(path, object_id, new_id=null)
  delete_object(path, object_id)
  import_step(name, source_url, parent_path="/")
  export_artifact(file_id, format)             ← format: gerber|dxf|step|stl|glb|png|pdf
  run_compute(engine, file_id, options={})     ← engine: fem|cfd|spice|cam|render|topo|tess
  poll_compute(job_id)

Workflow

For .jscad files (the default):
1. list_files() to see the layout.
2. read_file on the relevant existing file (usually /main.jscad).
3. edit_file with a unique-substring replace; or duplicate_object / delete_object for adding/removing entries in the [{id, geom}, ...] return.
4. write_file only for whole-file rewrites.
5. Summarize in 1-2 sentences. Do NOT paste the file back.

For non-.jscad files (.sketch, .assembly, .drawing, .part, .feature, .circuit.tsx):
1. search_kerf_docs("<topic>") — find the matching authoring guide.
2. read_file('/docs/llm/<page>.md') — load the JSON shape and conventions.
3. read_file on the project file you're editing.
4. write_file or edit_file with the JSON / TSX patch.
5. Summarize in 1-2 sentences.

JSCAD execution model (LOCKED — match this exactly):

A .jscad file MUST follow the Kerf runner's contract:

  export default function ({ primitives, transforms, booleans, colors, expansions, hulls, extrusions, measurements, maths, utils, params }) {
    const base = primitives.cuboid({ size: [40, 40, 10] })
    const peg  = transforms.translate([0, 0, 10], primitives.cylinder({ radius: 6, height: 20 }))
    return [
      { id: 'base', geom: base },
      { id: 'peg',  geom: peg  },
    ]
  }

Rules — violating ANY of these breaks the viewport with a ReferenceError:
  • `jscad` is NOT a global. NEVER write `const { cuboid } = jscad.primitives`.
    The @jscad/modeling sub-modules are passed in destructured to the
    default export's argument.
  • The file's `export default` MUST be a function taking ONE object arg.
  • That function returns `[{ id, geom }, ...]` — Kerf's Part shape.
  • `params` carries any equations / config bindings; it's never null.
  • No top-level `import` statements — they're stripped before eval.
    Just destructure from the function arg.
  • Use `function main() { ... }` ONLY as a helper if you also
    `export default main` at the bottom — the function signature must
    still be `function main({ primitives, transforms, ... })`.

If a user pastes legacy `const { cuboid } = jscad.primitives` style,
rewrite it on save into the destructured-arg pattern above.

File kinds and their canonical extensions:
- .jscad       — JSCAD code (kind='file'). Edit directly.
- .sketch      — parametric 2D profile (kind='sketch'). Use create_file(kind='sketch', ...).
- .assembly    — Components placed at transforms (kind='assembly'). Use create_file(kind='assembly').
- .drawing     — 2D technical drawing JSON (kind='drawing'). Use create_file(kind='drawing').
- .feature     — OCCT B-rep feature tree (kind='feature'). Use create_file(kind='feature', ...).
- .part        — library metadata (kind='part'). Use create_file(kind='part', options={metadata:{name:...}}).
- .circuit.tsx — tscircuit electronics (kind='circuit'). Use create_file(kind='circuit', ...).
- .step        — binary CAD imports (kind='step'). Pull in via import_step.

create_file produces a canonical seed (correct version field, defaults, validators) you can't easily fake. After scaffolding, edit the resulting file's JSON via write_file / edit_file — see the corresponding /docs/llm/ page for the schema.

Compute workflows:
- To run FEM analysis:   run_compute(engine='fem', file_id='<uuid>', options={solver:'linear_static',...})
- To run CAM toolpath:   run_compute(engine='cam', file_id='<uuid>', options={operation:'face',...})
- To render an image:    run_compute(engine='render', file_id='<uuid>', options={width:1920,...})
- To run topo opt:       run_compute(engine='topo', file_id='<uuid>', options={volume_fraction:0.3,...})
- To run CFD:            run_compute(engine='cfd', file_id='<uuid>', options={...})
- To run SPICE sim:      run_compute(engine='spice', file_id='<uuid>', options={...})
- After submitting:      poll_compute(job_id=<returned_job_id>) — repeat until status='done'|'error'

Strict rules:
- NEVER create a file when editing an existing one would work.
- ALWAYS read a file before editing it.
- For any non-.jscad kind, ALWAYS consult /docs/llm/<topic>.md before editing.
- Reference Objects by their id; reference files by their absolute path or uuid as appropriate.
- Don't paste file contents back to the user; describe the change.

Examples:

Edit a JSCAD Part:
  User: "make the base 6mm taller"
  list_files() ; read_file('/main.jscad')
  edit_file('/main.jscad', 'size: [40, 40, 10]', 'size: [40, 40, 16]')
  → "Raised the base to 16mm."

Place a Component in an assembly:
  User: "add the peg from /parts.jscad to my assembly"
  search_kerf_docs("assembly component transform")    # finds assembly.md
  read_file('/docs/llm/assembly.md')                  # JSON shape
  read_file('/parts.jscad') ; read_file('/main.assembly')
  edit_file('/main.assembly', '"components": []', '"components": [\n    {"id":"peg-1","file_id":"<uuid>","object_id":"peg","transform":[1,0,0,0, 0,1,0,0, 0,0,1,10, 0,0,0,1]}\n  ]')
  → "Added one peg Component at z=10."

Add a fillet in a feature tree:
  User: "round the top edges, 1mm"
  search_kerf_docs("fillet feature edge_filter")
  read_file('/docs/llm/feature.md')
  read_file('/bracket.feature')
  edit_file to append {"id":"fil-1","op":"fillet","target_id":"<last>","edge_filter":"all","radius":1} to features[].
  → "Added a 1mm fillet to every edge of the most-recent body."

Create a new sketch:
  User: "create a profile for the extrusion"
  create_file(kind='sketch', path='/profile.sketch', options={plane:'XY'})
  → "Created /profile.sketch on the XY plane."

Run FEM and check result:
  User: "run stress analysis on the bracket"
  run_compute(engine='fem', file_id='<uuid>', options={solver:'linear_static', load_case:'default'})
  → returns {job_id: 'fem_abc123', status: 'queued'}
  poll_compute(job_id='fem_abc123')
  → "FEM job queued; status: running — call poll_compute again to check progress."

If unsure whether to edit or create, edit.

Project tags: every project carries a free-form tags array (e.g. ["mechanical","electronics","jewelry"]). The agent loop prepends a one-line "Project tags: <comma-list>. Suggested file kinds: <list>." to every call so you know the active domain mix. Tune your defaults to the most specific tag — e.g. an "electronics" tag suggests preferring main.circuit.tsx and .circuit.tsx; "mechanical"/"jewelry"/"surfacing" suggest .jscad / .feature / .assembly. The API is permissive (any kind may be created in any project), so honor explicit user requests that cross domain boundaries instead of refusing."""


tagKindHints = {
    "mechanical": ["jscad", "sketch", "assembly", "drawing", "feature", "part"],
    "electronics": ["circuit", "part", "drawing"],
    "pcb": ["circuit", "part", "drawing"],
    "architecture": ["jscad", "sketch", "drawing"],
    "jewelry": ["jscad", "feature", "sketch"],
    "surfacing": ["jscad", "feature"],
    "robotics": ["jscad", "assembly", "circuit", "feature"],
    "drone": ["jscad", "assembly", "circuit"],
    "lighting": ["jscad", "circuit", "drawing"],
}


def build_project_tags_addendum(tags: list[str]) -> str:
    """Build a system-prompt fragment naming active tags + suggested kinds."""
    clean = [t.strip() for t in tags if t.strip()]
    if not clean:
        return ""

    seen = set()
    kinds = []
    for t in clean:
        for k in tagKindHints.get(t.lower(), []):
            if k not in seen:
                seen.add(k)
                kinds.append(k)

    out = f"\n\nProject tags: {', '.join(clean)}."
    if kinds:
        out += f" Suggested file kinds: {', '.join(kinds)}."
    return out


@dataclass
class ToolCall:
    id: str
    name: str
    arguments_json: str
    # Provider-specific opaque metadata that must be round-tripped on
    # subsequent turns. Today's only consumer is Gemini 3, which emits a
    # `thought_signature` (base64-string here) on every function_call
    # part; passing it back on the assistant-turn echo is required —
    # otherwise Gemini 3 rejects the request with HTTP 400 INVALID_ARGUMENT
    # "Function call is missing a thought_signature in functionCall parts".
    # Kept as a generic dict so adding more provider quirks (OpenAI's
    # `tool_call_id` quirks, Anthropic cache_control deltas, etc.) doesn't
    # require another schema bump.
    provider_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolSpec:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    role: str
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str = ""
    is_error: bool = False


@dataclass
class CompleteRequest:
    model: str
    system: str = ""
    messages: list[Message] = field(default_factory=list)
    max_tokens: int = 4096
    temperature: float = 0.0
    tools: list[ToolSpec] = field(default_factory=list)
    tool_choice: str = "auto"


@dataclass
class CompleteResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "stop"
    model_used: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class StreamEvent:
    """A Kerf-native provider-agnostic streaming event."""
    type: str
    data: dict


class Provider(ABC):
    @abstractmethod
    def complete(self, req: CompleteRequest) -> CompleteResponse:
        raise NotImplementedError

    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    async def stream(self, req: CompleteRequest) -> AsyncIterator[StreamEvent]:
        """Yield Kerf-native StreamEvents for one LLM turn.

        Default implementation raises NotImplementedError.
        Subclasses that support streaming should override this.
        """
        # The `yield` below makes this an async generator. The raise fires
        # before the first yielded value, propagating NotImplementedError to
        # the caller's `async for` loop.
        raise NotImplementedError(
            f"Provider {self.name()!r} does not support streaming"
        )
        yield  # type: ignore[misc]  # pragma: no cover  — makes this an async generator


@dataclass
class PartContext:
    file_path: str
    part_id: str
    content: str


@dataclass
class HistoryMessage:
    role: str
    content: str


def build_user_message(user_content: str, parts: list[PartContext]) -> str:
    if not parts:
        return user_content

    lines = [user_content, "\n<context>"]
    for p in parts:
        lines.append(f'<file path="{p.file_path}" part_id="{p.part_id}">')
        lines.append(p.content)
        if not p.content.endswith("\n"):
            lines.append("")
        lines.append("</file>")
    lines.append("</context>")
    return "\n".join(lines)


CATALOG = [
    # cheap_tier_eligible=True iff the model is listed in
    # kerf_pricing.cheap_tier.CHEAP_TIER_ALLOWLIST (provider="gemini" rows
    # added in T-402 R4).  The snapshot test in kerf-pricing asserts these
    # two sources stay in sync.
    #
    # paid_only=True  → model is not shown / accessible on the free tier;
    #                   the UI backend gate checks this flag.
    # paid_only=False → model may be shown to free-tier users (subject to
    #                   the cheap_tier_eligible billing-bucket gate separately).
    {"id": "claude-opus-4-7", "provider": "anthropic", "label": "Claude Opus 4.7", "context_window": 200_000, "cheap_tier_eligible": False, "paid_only": True},
    {"id": "claude-sonnet-4-6", "provider": "anthropic", "label": "Claude Sonnet 4.6", "context_window": 200_000, "cheap_tier_eligible": True, "paid_only": False},
    {"id": "claude-haiku-4-5", "provider": "anthropic", "label": "Claude Haiku 4.5", "context_window": 200_000, "cheap_tier_eligible": False, "paid_only": True},
    {"id": "gpt-4o", "provider": "openai", "label": "GPT-4o", "context_window": 128_000, "cheap_tier_eligible": False, "paid_only": True},
    {"id": "gpt-4o-mini", "provider": "openai", "label": "GPT-4o mini", "context_window": 128_000, "cheap_tier_eligible": False, "paid_only": False},
    {"id": "o3-mini", "provider": "openai", "label": "o3-mini", "context_window": 200_000, "cheap_tier_eligible": False, "paid_only": True},
    {"id": "kimi-k2-0905-preview", "provider": "moonshot", "label": "Kimi K2", "context_window": 256_000, "cheap_tier_eligible": False, "paid_only": True},
    {"id": "moonshot-v1-128k", "provider": "moonshot", "label": "Moonshot v1 128k", "context_window": 128_000, "cheap_tier_eligible": False, "paid_only": False},
    {"id": "moonshot-v1-32k", "provider": "moonshot", "label": "Moonshot v1 32k", "context_window": 32_000, "cheap_tier_eligible": False, "paid_only": False},
    # Gemini — keep 2.5 line + the latest 3-series previews. cheap_tier.py
    # also lists these glob patterns ("gemini-3-flash-*") for billing-bucket
    # routing; the catalog here is what the chat picker / /api/models shows.
    {"id": "gemini-3-pro-preview", "provider": "gemini", "label": "Gemini 3 Pro (preview)", "context_window": 2_000_000, "cheap_tier_eligible": False, "paid_only": True},
    {"id": "gemini-3-flash-preview", "provider": "gemini", "label": "Gemini 3 Flash (preview)", "context_window": 1_000_000, "cheap_tier_eligible": True, "paid_only": False},
    {"id": "gemini-2.5-pro", "provider": "gemini", "label": "Gemini 2.5 Pro", "context_window": 2_000_000, "cheap_tier_eligible": False, "paid_only": True},
    {"id": "gemini-2.5-flash", "provider": "gemini", "label": "Gemini 2.5 Flash", "context_window": 1_000_000, "cheap_tier_eligible": True, "paid_only": False},
    {"id": "gemini-2.5-flash-lite", "provider": "gemini", "label": "Gemini 2.5 Flash Lite", "context_window": 1_000_000, "cheap_tier_eligible": True, "paid_only": False},
]


def lookup_model(model_id: str) -> dict | None:
    for m in CATALOG:
        if m["id"] == model_id:
            return m
    return None


class LLMConfig:
    def __init__(
        self,
        anthropic_api_key: str = "",
        openai_api_key: str = "",
        moonshot_api_key: str = "",
        gemini_api_key: str = "",
        default_model: str = "claude-opus-4-7",
        anthropic_prompt_cache: bool = True,
    ):
        self.anthropic_api_key = anthropic_api_key
        self.openai_api_key = openai_api_key
        self.moonshot_api_key = moonshot_api_key
        self.gemini_api_key = gemini_api_key
        self.default_model = default_model or "claude-sonnet-4-6"
        self.anthropic_prompt_cache = anthropic_prompt_cache


class Registry:
    def __init__(self, cfg: LLMConfig):
        self.providers: dict[str, Provider] = {}
        if cfg.anthropic_api_key:
            self.providers["anthropic"] = AnthropicProvider(
                cfg.anthropic_api_key,
                prompt_cache=cfg.anthropic_prompt_cache,
            )
        if cfg.openai_api_key:
            self.providers["openai"] = OpenAIProvider(cfg.openai_api_key)
        if cfg.moonshot_api_key:
            self.providers["moonshot"] = MoonshotProvider(cfg.moonshot_api_key)
        if cfg.gemini_api_key:
            self.providers["gemini"] = GeminiProvider(cfg.gemini_api_key)
        self.default_model = cfg.default_model or "claude-opus-4-7"

    def available(self) -> list[dict]:
        out = []
        for m in CATALOG:
            if m["provider"] in self.providers:
                out.append(m)
        return out

    def default(self) -> str:
        return self.default_model

    def has_any(self) -> bool:
        return len(self.providers) > 0

    def resolve(self, model_id: str) -> tuple[Provider, str]:
        info = lookup_model(model_id)
        if info is None:
            raise ValueError(f"unknown model {model_id!r}")
        provider = self.providers.get(info["provider"])
        if provider is None:
            raise ValueError(f"provider {info['provider']!r} for model {model_id!r} is not configured")
        return provider, info["id"]


def _anthropic_sdk_supports_cache_control() -> bool:
    """Return True when the installed anthropic SDK exposes cache_control on ToolParam."""
    try:
        import anthropic.types as _t
        return "cache_control" in getattr(_t.ToolParam, "__annotations__", {})
    except Exception:
        return False


class AnthropicProvider(Provider):
    def __init__(self, api_key: str, prompt_cache: bool = True):
        self.api_key = api_key
        self.prompt_cache = prompt_cache

    def name(self) -> str:
        return "anthropic"

    def complete(self, req: CompleteRequest) -> CompleteResponse:
        import anthropic
        import httpx

        client = anthropic.Anthropic(api_key=self.api_key, http_client=httpx.Client(timeout=120.0))

        max_tokens = req.max_tokens if req.max_tokens > 0 else 4096

        # Determine whether to inject cache_control breakpoints.
        # We only do this when:
        #   1. prompt_cache is enabled on this provider instance, AND
        #   2. the installed SDK actually supports cache_control (feature-detect).
        use_cache = self.prompt_cache and _anthropic_sdk_supports_cache_control()

        # ── System block ─────────────────────────────────────────────────────
        # When caching is on, wrap the system string in a single-element list
        # of TextBlockParam with cache_control attached so Anthropic caches the
        # entire system-prompt prefix.  The plain-string form is used otherwise
        # for full backward compatibility.
        if use_cache and req.system:
            system_param: Any = [
                {
                    "type": "text",
                    "text": req.system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        else:
            system_param: Any = req.system

        # ── Tools block ──────────────────────────────────────────────────────
        tools = None
        if req.tools:
            tools = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema or {"type": "object", "properties": {}},
                }
                for t in req.tools
            ]
            # Attach cache_control only to the *last* tool entry.  Anthropic
            # treats this as a breakpoint: everything up to and including this
            # entry is eligible for the KV cache.
            if use_cache and tools:
                tools[-1] = dict(tools[-1], cache_control={"type": "ephemeral"})

        tool_choice = None
        if tools:
            # Anthropic requires tool_choice to be an OBJECT, not the bare
            # strings "auto"/"none" — passing "auto" yields HTTP 400
            # "tool_choice: Input should be an object" (every opus chat
            # turn failed with this).
            if req.tool_choice in ("", "auto"):
                tool_choice = {"type": "auto"}
            elif req.tool_choice == "none":
                tool_choice = {"type": "none"}
            else:
                tool_choice = {"type": "tool", "name": req.tool_choice}

        messages = []
        i = 0
        while i < len(req.messages):
            m = req.messages[i]
            if m.role == "tool":
                tool_blocks = []
                while i < len(req.messages) and req.messages[i].role == "tool":
                    tm = req.messages[i]
                    block: dict[str, Any] = {
                        "type": "tool_result",
                        "tool_use_id": tm.tool_call_id,
                        "content": tm.content,
                    }
                    if tm.is_error:
                        block["is_error"] = True
                    tool_blocks.append(block)
                    i += 1
                messages.append({"role": "user", "content": tool_blocks})
                continue

            if m.tool_calls:
                content_blocks = []
                if m.content.strip():
                    content_blocks.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": json.loads(tc.arguments_json) if tc.arguments_json.strip() else {},
                    })
                messages.append({"role": m.role, "content": content_blocks})
            else:
                messages.append({"role": m.role, "content": m.content})
            i += 1

        # Only send temperature when explicitly set (>0). Passing
        # temperature=None serializes to JSON null, which Anthropic now
        # rejects with 400 "temperature: Input should be a valid number"
        # — that broke chat for every model.
        _kw = dict(
            model=req.model,
            system=system_param,
            max_tokens=max_tokens,
            messages=messages,
        )
        # Same defensive omission for tools/tool_choice. The auto-title and
        # readme-gen paths call provider.complete() with NO tools — sending
        # tool_choice=None would serialize as JSON null and Anthropic now
        # rejects that with 400 "tool_choice: Input should be an object",
        # which broke auto-title every first message and surfaced to users
        # as "temporary server-side issue preventing file reads and writes".
        if tools:
            _kw["tools"] = tools
        if tool_choice is not None:
            _kw["tool_choice"] = tool_choice
        if req.temperature > 0:
            _kw["temperature"] = req.temperature
        response = client.messages.create(**_kw)

        text_parts = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments_json=json.dumps(block.input),
                ))

        stop_reason = response.stop_reason or "stop"
        if stop_reason == "tool_use":
            stop_reason = "tool_use"
        elif stop_reason == "max_tokens":
            stop_reason = "length"

        return CompleteResponse(
            content="".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            model_used=req.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    async def stream(self, req: CompleteRequest) -> AsyncIterator[StreamEvent]:  # type: ignore[override]
        """Stream one LLM turn via Anthropic's messages.stream() context manager.

        Yields Kerf-native StreamEvent objects:
          assistant_text_delta  — incremental text
          tool_use_start        — a new tool call block started
          tool_use_input_delta  — partial JSON input for a tool call
          tool_use_complete     — tool call input fully assembled
          assistant_done        — final stop/token event
        """
        import anthropic
        import httpx

        client = anthropic.Anthropic(
            api_key=self.api_key,
            http_client=httpx.Client(timeout=120.0),
        )

        max_tokens = req.max_tokens if req.max_tokens > 0 else 4096
        use_cache = self.prompt_cache and _anthropic_sdk_supports_cache_control()

        # ── System block ────────────────────────────────────────────────────
        if use_cache and req.system:
            system_param: Any = [
                {
                    "type": "text",
                    "text": req.system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        else:
            system_param: Any = req.system

        # ── Tools block ─────────────────────────────────────────────────────
        tools = None
        if req.tools:
            tools = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema or {"type": "object", "properties": {}},
                }
                for t in req.tools
            ]
            if use_cache and tools:
                tools[-1] = dict(tools[-1], cache_control={"type": "ephemeral"})

        tool_choice = None
        if tools:
            if req.tool_choice in ("", "auto"):
                tool_choice = {"type": "auto"}
            elif req.tool_choice == "none":
                tool_choice = {"type": "none"}
            else:
                tool_choice = {"type": "tool", "name": req.tool_choice}

        # ── Build messages ───────────────────────────────────────────────────
        messages: list[dict] = []
        i = 0
        while i < len(req.messages):
            m = req.messages[i]
            if m.role == "tool":
                tool_blocks = []
                while i < len(req.messages) and req.messages[i].role == "tool":
                    tm = req.messages[i]
                    block: dict[str, Any] = {
                        "type": "tool_result",
                        "tool_use_id": tm.tool_call_id,
                        "content": tm.content,
                    }
                    if tm.is_error:
                        block["is_error"] = True
                    tool_blocks.append(block)
                    i += 1
                messages.append({"role": "user", "content": tool_blocks})
                continue

            if m.tool_calls:
                content_blocks = []
                if m.content.strip():
                    content_blocks.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": json.loads(tc.arguments_json) if tc.arguments_json.strip() else {},
                    })
                messages.append({"role": m.role, "content": content_blocks})
            else:
                messages.append({"role": m.role, "content": m.content})
            i += 1

        _kw: dict[str, Any] = dict(
            model=req.model,
            system=system_param,
            max_tokens=max_tokens,
            messages=messages,
        )
        if tools:
            _kw["tools"] = tools
        if tool_choice is not None:
            _kw["tool_choice"] = tool_choice
        if req.temperature > 0:
            _kw["temperature"] = req.temperature

        # ── State tracking for tool-use blocks ──────────────────────────────
        # We accumulate per-block state so we can emit complete events.
        current_block_type: str | None = None
        current_tool_id: str | None = None
        current_tool_name: str | None = None
        current_tool_input_parts: list[str] = []

        input_tokens = 0
        output_tokens = 0

        with client.messages.stream(**_kw) as stream:
            for event in stream:
                etype = type(event).__name__

                # The Anthropic SDK (≥ 0.39) emits events with the literal
                # class names `RawMessageStartEvent`, `RawContentBlockStartEvent`,
                # `RawContentBlockDeltaEvent`, `ParsedContentBlockStopEvent`,
                # `RawMessageDeltaEvent`, `ParsedMessageStopEvent`, etc. The
                # previous match (against un-prefixed names) silently fell
                # through for EVERY event, so this method yielded nothing
                # and the route saw stop_reason=tool_use with zero tool calls
                # captured — surface symptom: "blank chat head" with no
                # tools executed (see scripts/e2e_chat_probe.py output).
                # Also tolerate both the higher-level helper events (TextEvent,
                # InputJsonEvent) emitted alongside the raw deltas, and the
                # un-prefixed legacy names in case an older SDK is in use.

                if etype in ("RawMessageStartEvent", "MessageStartEvent"):
                    # Capture input tokens from message_start usage
                    if hasattr(event, "message") and hasattr(event.message, "usage"):
                        input_tokens = getattr(event.message.usage, "input_tokens", 0) or 0

                elif etype in ("RawContentBlockStartEvent", "ContentBlockStartEvent"):
                    block = event.content_block
                    if block.type == "text":
                        current_block_type = "text"
                        current_tool_id = None
                        current_tool_name = None
                        current_tool_input_parts = []
                    elif block.type == "tool_use":
                        current_block_type = "tool_use"
                        current_tool_id = block.id
                        current_tool_name = block.name
                        current_tool_input_parts = []
                        yield StreamEvent(
                            type="tool_use_start",
                            data={"tool_use_id": block.id, "name": block.name},
                        )

                elif etype in ("RawContentBlockDeltaEvent", "ContentBlockDeltaEvent"):
                    delta = event.delta
                    dtype = getattr(delta, "type", None)
                    if current_block_type == "text" and dtype == "text_delta":
                        yield StreamEvent(
                            type="assistant_text_delta",
                            data={"text": delta.text},
                        )
                    elif current_block_type == "tool_use" and dtype == "input_json_delta":
                        current_tool_input_parts.append(delta.partial_json)
                        yield StreamEvent(
                            type="tool_use_input_delta",
                            data={
                                "tool_use_id": current_tool_id,
                                "partial_json": delta.partial_json,
                            },
                        )

                elif etype in (
                    "RawContentBlockStopEvent",
                    "ContentBlockStopEvent",
                    "ParsedContentBlockStopEvent",
                ):
                    if current_block_type == "tool_use" and current_tool_id is not None:
                        assembled = "".join(current_tool_input_parts)
                        try:
                            parsed_input = json.loads(assembled) if assembled.strip() else {}
                        except json.JSONDecodeError:
                            parsed_input = {}
                        yield StreamEvent(
                            type="tool_use_complete",
                            data={
                                "tool_use_id": current_tool_id,
                                "name": current_tool_name,
                                "input": parsed_input,
                            },
                        )
                    current_block_type = None

                elif etype in ("RawMessageDeltaEvent", "MessageDeltaEvent"):
                    if hasattr(event, "usage"):
                        output_tokens = getattr(event.usage, "output_tokens", 0) or 0

                elif etype in (
                    "RawMessageStopEvent",
                    "MessageStopEvent",
                    "ParsedMessageStopEvent",
                ):
                    pass  # handled via get_final_message below

                # `TextEvent` / `InputJsonEvent` / etc. are higher-level
                # helpers emitted alongside the Raw events — we already
                # forwarded the Raw delta above, so skip them silently.

            # Retrieve final stop_reason + token counts from the accumulated message.
            try:
                final_msg = stream.get_final_message()
                stop_reason = final_msg.stop_reason or "end_turn"
                if hasattr(final_msg, "usage"):
                    input_tokens = getattr(final_msg.usage, "input_tokens", input_tokens)
                    output_tokens = getattr(final_msg.usage, "output_tokens", output_tokens)
            except Exception:
                stop_reason = "end_turn"

        yield StreamEvent(
            type="assistant_done",
            data={
                "stop_reason": stop_reason,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "model": req.model,
            },
        )


class OpenAIProvider(Provider):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def name(self) -> str:
        return "openai"

    def complete(self, req: CompleteRequest) -> CompleteResponse:
        from openai import OpenAI
        import httpx

        client = OpenAI(api_key=self.api_key, http_client=httpx.Client(timeout=120.0))

        tools = None
        if req.tools:
            tools = [
                {"type": "function", "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema or {"type": "object", "properties": {}},
                }}
                for t in req.tools
            ]

        messages = []
        for m in req.messages:
            msg = {"role": m.role, "content": m.content}
            if m.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "function": {"name": tc.name, "arguments": tc.arguments_json},
                        "type": "function",
                    }
                    for tc in m.tool_calls
                ]
            if m.tool_call_id:
                msg["tool_call_id"] = m.tool_call_id
            messages.append(msg)

        extra_body = {}
        if tools:
            extra_body["tools"] = tools
            if req.tool_choice and req.tool_choice != "auto":
                extra_body["tool_choice"] = req.tool_choice
        # Omit temperature unless set (None → null is rejected by some
        # providers; see the Anthropic note above).
        if req.temperature > 0:
            extra_body["temperature"] = req.temperature

        response = client.chat.completions.create(
            model=req.model,
            messages=messages,
            max_tokens=req.max_tokens if req.max_tokens > 0 else None,
            **extra_body,
        )

        choice = response.choices[0]
        text_parts = []
        tool_calls = []

        if choice.message.content:
            text_parts.append(choice.message.content)

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments_json=tc.function.arguments,
                ))

        stop_reason = choice.finish_reason or "stop"

        return CompleteResponse(
            content="".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            model_used=response.model,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )


class MoonshotProvider(Provider):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def name(self) -> str:
        return "moonshot"

    def complete(self, req: CompleteRequest) -> CompleteResponse:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key, base_url="https://api.moonshot.cn/v1")

        messages = []
        for m in req.messages:
            msg = {"role": m.role, "content": m.content}
            if m.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "function": {"name": tc.name, "arguments": tc.arguments_json},
                        "type": "function",
                    }
                    for tc in m.tool_calls
                ]
            if m.tool_call_id:
                msg["tool_call_id"] = m.tool_call_id
            messages.append(msg)

        tools = None
        if req.tools:
            tools = [
                {"type": "function", "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema or {"type": "object", "properties": {}},
                }}
                for t in req.tools
            ]

        extra_body = {}
        if tools:
            extra_body["tools"] = tools
        # Omit temperature unless set (None → null is rejected by some
        # providers; see the Anthropic note above).
        if req.temperature > 0:
            extra_body["temperature"] = req.temperature

        response = client.chat.completions.create(
            model=req.model,
            messages=messages,
            max_tokens=req.max_tokens if req.max_tokens > 0 else None,
            **extra_body,
        )

        choice = response.choices[0]
        text_parts = []
        tool_calls = []

        if choice.message.content:
            text_parts.append(choice.message.content)

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments_json=tc.function.arguments,
                ))

        return CompleteResponse(
            content="".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=choice.finish_reason or "stop",
            model_used=response.model,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )


class GeminiProvider(Provider):
    """Google Gemini via the modern `google-genai` SDK.

    Migrated 2026-05-19 from the deprecated `google-generativeai`
    package. The old SDK printed a FutureWarning on every import and
    used different APIs (GenerativeModel constructor + module-level
    `configure`); the new SDK is client-shaped:

        client = genai.Client(api_key=...)
        client.models.generate_content(model=..., contents=...,
            config=types.GenerateContentConfig(...))

    Message format:
      - `contents` is a list of `types.Content` objects
      - each Content has role ∈ {"user", "model"} + a list of Parts
      - a Part is `types.Part.from_text(text)` for text, or
        `types.Part(function_call=...)` for assistant tool calls, or
        `types.Part(function_response=...)` for tool results

    Tools:
      - `types.Tool(function_declarations=[...FunctionDeclaration...])`
    """

    def __init__(self, api_key: str):
        self.api_key = api_key

    def name(self) -> str:
        return "gemini"

    # ── Shared request-building helpers ─────────────────────────────────

    def _build_request_args(self, req: CompleteRequest):
        """Translate a Kerf CompleteRequest into the kwargs the genai
        Client expects. Returns (contents, config) where `config` is a
        `types.GenerateContentConfig` instance (or None) and `contents`
        is a list of `types.Content` objects.

        Pulled out of complete() / stream() so both share the same wire
        contract — the previous bifurcation was where Gemini regressions
        landed.
        """
        from google import genai
        from google.genai import types

        contents = []
        for m in req.messages:
            if m.role == "user":
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=m.content)],
                ))
            elif m.role == "assistant":
                parts = []
                if m.content.strip():
                    parts.append(types.Part.from_text(text=m.content))
                for tc in m.tool_calls:
                    args = json.loads(tc.arguments_json) if tc.arguments_json.strip() else {}
                    part_kwargs: dict[str, Any] = {
                        "function_call": types.FunctionCall(name=tc.name, args=args),
                    }
                    # Echo Gemini's thought_signature back on the Part —
                    # required by Gemini 3 (see _parse_response_parts).
                    sig_b64 = (tc.provider_metadata or {}).get("thought_signature")
                    if sig_b64:
                        import base64
                        try:
                            part_kwargs["thought_signature"] = base64.b64decode(sig_b64)
                        except Exception:
                            pass
                    parts.append(types.Part(**part_kwargs))
                contents.append(types.Content(role="model", parts=parts))
            elif m.role == "tool":
                # In the genai SDK, function_response parts go in a user-
                # role Content turn. tool_call_id maps to the original
                # function name (Gemini doesn't track call ids the way
                # Anthropic does, so we use the name; the upstream
                # routing layer correlates by order).
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(
                        function_response=types.FunctionResponse(
                            name=m.tool_call_id or "unknown",
                            response={"result": m.content},
                        ),
                    )],
                ))

        # Tool catalog → FunctionDeclaration list inside one Tool.
        tool_objs = None
        if req.tools:
            decls = [
                types.FunctionDeclaration(
                    name=t.name,
                    description=t.description,
                    parameters=t.input_schema or {"type": "object", "properties": {}},
                )
                for t in req.tools
            ]
            tool_objs = [types.Tool(function_declarations=decls)]

        config_kwargs: dict[str, Any] = {}
        if req.system:
            config_kwargs["system_instruction"] = req.system
        if tool_objs is not None:
            config_kwargs["tools"] = tool_objs
        if req.max_tokens > 0:
            config_kwargs["max_output_tokens"] = req.max_tokens
        if req.temperature > 0:
            config_kwargs["temperature"] = req.temperature

        config = (
            types.GenerateContentConfig(**config_kwargs)
            if config_kwargs else None
        )
        return contents, config

    @staticmethod
    def _parse_response_parts(candidate) -> tuple[list[str], list[ToolCall]]:
        """Extract text + function_calls from a single genai response
        candidate. Skips empty parts so we never emit empty deltas.

        For each function_call part we capture `thought_signature`
        (Gemini 3's opaque thinking-context token) into
        `tool_call.provider_metadata['thought_signature']` — base64-
        encoded so it survives JSON persistence. When we echo the
        assistant turn back in `_build_request_args`, the signature
        rides along; without it Gemini 3 rejects the request.
        """
        import base64
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        if not getattr(candidate, "content", None):
            return text_parts, tool_calls
        for part in candidate.content.parts or []:
            text = getattr(part, "text", None)
            fc = getattr(part, "function_call", None)
            if text:
                text_parts.append(text)
            if fc and fc.name:
                args = dict(fc.args) if fc.args else {}
                meta: dict[str, Any] = {}
                sig = getattr(part, "thought_signature", None)
                if sig:
                    # `thought_signature` is bytes. Base64 it so the
                    # value JSON-serialises cleanly into chat_messages.tool_calls.
                    meta["thought_signature"] = base64.b64encode(sig).decode("ascii")
                tool_calls.append(ToolCall(
                    id=f"call_{hash((fc.name, str(args))) % 1000000}",
                    name=fc.name,
                    arguments_json=json.dumps(args),
                    provider_metadata=meta,
                ))
        return text_parts, tool_calls

    # ── Non-streaming path ──────────────────────────────────────────────

    def complete(self, req: CompleteRequest) -> CompleteResponse:
        from google import genai
        client = genai.Client(api_key=self.api_key)

        contents, config = self._build_request_args(req)

        response = client.models.generate_content(
            model=req.model,
            contents=contents,
            config=config,
        )

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for candidate in (response.candidates or []):
            tp, tcs = self._parse_response_parts(candidate)
            text_parts.extend(tp)
            tool_calls.extend(tcs)

        # finish_reason: 1 = STOP, 2 = MAX_TOKENS, 3 = SAFETY, 5 = OTHER, etc.
        finish = None
        if response.candidates:
            finish = getattr(response.candidates[0], "finish_reason", None)
        stop_reason = "tool_use" if tool_calls else "stop"
        if finish and str(finish).endswith("MAX_TOKENS"):
            stop_reason = "length"

        usage = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
        output_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0

        return CompleteResponse(
            content="".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            model_used=req.model,
            input_tokens=input_tokens or 0,
            output_tokens=output_tokens or 0,
        )

    # ── Streaming path ──────────────────────────────────────────────────

    async def stream(self, req: CompleteRequest) -> AsyncIterator[StreamEvent]:  # type: ignore[override]
        """True streaming via genai's generate_content_stream. Emits the
        same Kerf-native StreamEvent shape as AnthropicProvider.stream():
        assistant_text_delta / tool_use_start / tool_use_complete /
        assistant_done."""
        from google import genai
        client = genai.Client(api_key=self.api_key)

        contents, config = self._build_request_args(req)

        # Accumulators that survive across chunks.
        emitted_tool_starts: set[str] = set()
        last_input_tokens = 0
        last_output_tokens = 0
        last_finish = None

        # genai's stream iterator is sync — call it on a worker thread
        # and pump chunks into an async queue to keep the FastAPI event
        # loop responsive.
        import asyncio
        import queue as _queue
        chunk_q: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_event_loop()
        _SENTINEL = object()

        def _pump():
            try:
                for chunk in client.models.generate_content_stream(
                    model=req.model,
                    contents=contents,
                    config=config,
                ):
                    asyncio.run_coroutine_threadsafe(chunk_q.put(chunk), loop)
            except Exception as e:  # surface to the consumer
                asyncio.run_coroutine_threadsafe(chunk_q.put(e), loop)
            finally:
                asyncio.run_coroutine_threadsafe(chunk_q.put(_SENTINEL), loop)

        import threading
        t = threading.Thread(target=_pump, daemon=True)
        t.start()

        while True:
            chunk = await chunk_q.get()
            if chunk is _SENTINEL:
                break
            if isinstance(chunk, Exception):
                raise chunk

            # Token usage rolls forward.
            usage = getattr(chunk, "usage_metadata", None)
            if usage:
                last_input_tokens = getattr(usage, "prompt_token_count", last_input_tokens) or last_input_tokens
                last_output_tokens = getattr(usage, "candidates_token_count", last_output_tokens) or last_output_tokens

            for candidate in (chunk.candidates or []):
                last_finish = getattr(candidate, "finish_reason", last_finish)
                if not getattr(candidate, "content", None):
                    continue
                for part in candidate.content.parts or []:
                    text = getattr(part, "text", None)
                    fc = getattr(part, "function_call", None)
                    if text:
                        yield StreamEvent(
                            type="assistant_text_delta",
                            data={"text": text},
                        )
                    if fc and fc.name:
                        # genai streams tool calls atomically — start +
                        # complete in one chunk. Emit both so the
                        # frontend's chip flow renders the same way as
                        # the Anthropic path.
                        args = dict(fc.args) if fc.args else {}
                        tid_key = f"call_{hash((fc.name, str(args))) % 1000000}"
                        if tid_key not in emitted_tool_starts:
                            emitted_tool_starts.add(tid_key)
                            yield StreamEvent(
                                type="tool_use_start",
                                data={"tool_use_id": tid_key, "name": fc.name},
                            )
                        # Carry Gemini 3's thought_signature on the
                        # tool_use_complete event so the route's
                        # pending_tools assembly picks it up into the
                        # ToolCall.provider_metadata — required for
                        # subsequent-turn echo (otherwise Gemini 3 400s).
                        import base64
                        provider_metadata: dict[str, Any] = {}
                        sig = getattr(part, "thought_signature", None)
                        if sig:
                            provider_metadata["thought_signature"] = base64.b64encode(sig).decode("ascii")
                        yield StreamEvent(
                            type="tool_use_complete",
                            data={
                                "tool_use_id": tid_key,
                                "name": fc.name,
                                "input": args,
                                "provider_metadata": provider_metadata,
                            },
                        )

        stop_reason = (
            "tool_use" if emitted_tool_starts
            else ("length" if last_finish and str(last_finish).endswith("MAX_TOKENS") else "stop")
        )
        yield StreamEvent(
            type="assistant_done",
            data={
                "stop_reason": stop_reason,
                "input_tokens": last_input_tokens or 0,
                "output_tokens": last_output_tokens or 0,
                "model": req.model,
            },
        )
