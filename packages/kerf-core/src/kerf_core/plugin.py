"""Plugin contract: PluginContext, PluginManifest, ToolRegistry, WorkerRegistry.

All kerf plugins receive a PluginContext at registration time and return a
PluginManifest.  The exact shape of these types is the shared contract across
all plugin packages — do not change without coordinating with all plugin
maintainers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import structlog

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
ToolHandler = Callable[..., Awaitable[Any]]
WorkerFactory = Callable[[], Awaitable[Any]]


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------
@dataclass
class ToolSpec:
    """JSON-serialisable description of an LLM tool (function calling spec)."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class ToolRegistry:
    """Collects LLM tool registrations from all plugins."""

    _tools: dict[str, tuple[ToolSpec, ToolHandler]] = field(default_factory=dict)

    def register(self, name: str, spec: ToolSpec, handler: ToolHandler) -> None:
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered")
        self._tools[name] = (spec, handler)

    def get(self, name: str) -> tuple[ToolSpec, ToolHandler] | None:
        return self._tools.get(name)

    def all_specs(self) -> list[ToolSpec]:
        return [spec for spec, _ in self._tools.values()]

    def all_names(self) -> list[str]:
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)


# ---------------------------------------------------------------------------
# WorkerRegistry
# ---------------------------------------------------------------------------
@dataclass
class WorkerRegistry:
    """Collects background-worker factories from all plugins."""

    _workers: dict[str, WorkerFactory] = field(default_factory=dict)

    def register(self, name: str, factory: WorkerFactory) -> None:
        if name in self._workers:
            raise ValueError(f"Worker '{name}' is already registered")
        self._workers[name] = factory

    def get(self, name: str) -> WorkerFactory | None:
        return self._workers.get(name)

    def all_names(self) -> list[str]:
        return list(self._workers.keys())

    async def start_all(self) -> list[Any]:
        handles = []
        for name, factory in self._workers.items():
            handle = await factory()
            handles.append(handle)
        return handles

    def __len__(self) -> int:
        return len(self._workers)


# ---------------------------------------------------------------------------
# StorageBackend (re-exported from storage.base)
# ---------------------------------------------------------------------------
from kerf_core.storage.base import StorageBackend  # noqa: E402


# ---------------------------------------------------------------------------
# PluginContext
# ---------------------------------------------------------------------------
@dataclass
class PluginContext:
    """Runtime context passed to every plugin's register() function."""

    pool: Any  # asyncpg.Pool
    storage: StorageBackend
    config: Any  # kerf_core.config.Config
    tools: ToolRegistry
    workers: WorkerRegistry
    logger: Any  # structlog.BoundLogger
    cloud_enabled: bool
    local_mode: bool


# ---------------------------------------------------------------------------
# PluginManifest
# ---------------------------------------------------------------------------
@dataclass
class PluginManifest:
    """Returned by every plugin's register() function."""

    name: str
    version: str
    provides: list[str] = field(default_factory=list)
    depends: list[str] = field(default_factory=list)
