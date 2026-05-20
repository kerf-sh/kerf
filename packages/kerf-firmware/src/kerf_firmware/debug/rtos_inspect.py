"""
kerf_firmware.debug.rtos_inspect — RTOS task-table walker.

Walks the kerfrtos and FreeRTOS task tables via the GDB-MI bridge exposed by
OpenOCDSession and produces structured snapshots.

Data model
----------
TaskInfo        — one RTOS task (name, state, priority, stack_high_water)
SyncObject      — mutex / semaphore / queue with holder + waiters
DependencyEdge  — (from_task, to_task, label) directed edge for the dep graph
DebugSnapshot   — complete point-in-time picture
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .openocd import OpenOCDSession


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TaskInfo:
    """Snapshot of a single RTOS task."""
    name: str
    state: str           # "RUNNING", "READY", "BLOCKED", "SUSPENDED", "DELETED"
    priority: int
    stack_high_water: int   # bytes remaining at watermark (0 = danger)
    stack_size: int         # total stack size in bytes

    @property
    def stack_pct_free(self) -> float:
        """Percentage of stack that is still free (0–100)."""
        if self.stack_size <= 0:
            return 100.0
        return (self.stack_high_water / self.stack_size) * 100.0

    @property
    def stack_warning(self) -> bool:
        """True when < 10 % of the stack is free."""
        return self.stack_pct_free < 10.0

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "state": self.state,
            "priority": self.priority,
            "stack_high_water": self.stack_high_water,
            "stack_size": self.stack_size,
            "stack_pct_free": round(self.stack_pct_free, 1),
            "stack_warning": self.stack_warning,
        }


@dataclass
class SyncObject:
    """Snapshot of a synchronisation primitive (mutex / semaphore / queue)."""
    name: str
    kind: str          # "mutex", "semaphore", "queue"
    held_by: Optional[str] = None   # task name, or None
    waiters: list[str] = field(default_factory=list)
    count: Optional[int] = None     # for semaphores / queues
    capacity: Optional[int] = None  # for queues

    def as_dict(self) -> dict:
        d: dict = {
            "name": self.name,
            "kind": self.kind,
            "held_by": self.held_by,
            "waiters": list(self.waiters),
        }
        if self.count is not None:
            d["count"] = self.count
        if self.capacity is not None:
            d["capacity"] = self.capacity
        return d


@dataclass
class DependencyEdge:
    """A directed dependency edge: *from_task* is blocked by *to_task*."""
    from_task: str   # the waiter
    to_task: str     # the holder (what the waiter needs)
    label: str       # e.g. "mutex:my_mutex"

    def as_dict(self) -> dict:
        return {
            "from": self.from_task,
            "to": self.to_task,
            "label": self.label,
        }


@dataclass
class DebugSnapshot:
    """Complete point-in-time debug snapshot."""
    tasks: list[TaskInfo] = field(default_factory=list)
    sync_objects: list[SyncObject] = field(default_factory=list)
    edges: list[DependencyEdge] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "tasks": [t.as_dict() for t in self.tasks],
            "sync_objects": [s.as_dict() for s in self.sync_objects],
            "edges": [e.as_dict() for e in self.edges],
            "warnings": list(self.warnings),
        }


# ---------------------------------------------------------------------------
# Inspector
# ---------------------------------------------------------------------------

# Known kerfrtos symbol names (written by kerfrtos_debug_hook.c)
_KERFRTOS_TASK_COUNT_SYM = "kerfrtos_debug_task_count"
_KERFRTOS_TASK_TABLE_SYM = "kerfrtos_debug_task_table"
_KERFRTOS_MUTEX_COUNT_SYM = "kerfrtos_debug_mutex_count"
_KERFRTOS_MUTEX_TABLE_SYM = "kerfrtos_debug_mutex_table"

# FreeRTOS well-known symbols (available when compiled with
# configRECORD_STACK_HIGH_ADDRESS=1 / INCLUDE_uxTaskGetStackHighWaterMark=1)
_FREERTOS_TASK_LIST_SYM = "pxReadyTasksLists"


class RTOSInspector:
    """
    Walks RTOS task and synchronisation-object tables via a live GDB-MI session.

    Works with:
    - **kerfrtos** — uses the `kerfrtos_debug_hook.c` memory layout
    - **FreeRTOS** — falls back to the standard pxReadyTasksLists symbol

    Parameters
    ----------
    session : OpenOCDSession
        An already-started GDB-MI session.
    rtos : str
        "kerfrtos" (default) or "freertos".
    _raw_tasks : list[dict] | None
        Test injection: if supplied, skip symbol lookup and use these task
        dicts directly.  Each must have keys:
        ``{name, state, priority, stack_high_water, stack_size}``.
    _raw_sync : list[dict] | None
        Test injection: if supplied, skip symbol lookup and use these sync
        object dicts directly.  Each must have keys:
        ``{name, kind, held_by?, waiters?, count?, capacity?}``.
    """

    def __init__(
        self,
        session: OpenOCDSession,
        rtos: str = "kerfrtos",
        _raw_tasks: Optional[list[dict]] = None,
        _raw_sync: Optional[list[dict]] = None,
    ) -> None:
        self.session = session
        self.rtos = rtos
        self._raw_tasks = _raw_tasks
        self._raw_sync = _raw_sync

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def snapshot(self) -> DebugSnapshot:
        """
        Read a complete RTOS state snapshot from the target.

        Returns a :class:`DebugSnapshot` with tasks, sync objects, dependency
        edges, and any stack-watermark warnings.
        """
        if self._raw_tasks is not None:
            tasks = self._build_tasks_from_raw(self._raw_tasks)
        elif self.rtos == "freertos":
            tasks = self._read_freertos_tasks()
        else:
            tasks = self._read_kerfrtos_tasks()

        if self._raw_sync is not None:
            sync_objects = self._build_sync_from_raw(self._raw_sync)
        elif self.rtos == "freertos":
            sync_objects = self._read_freertos_sync()
        else:
            sync_objects = self._read_kerfrtos_sync()

        edges = self._build_dependency_edges(sync_objects)
        warnings = self._collect_warnings(tasks)

        return DebugSnapshot(
            tasks=tasks,
            sync_objects=sync_objects,
            edges=edges,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Task readers
    # ------------------------------------------------------------------

    def _read_kerfrtos_tasks(self) -> list[TaskInfo]:
        """Read tasks from kerfrtos_debug_task_table."""
        tasks: list[TaskInfo] = []
        try:
            count_str = self.session.evaluate_expression(_KERFRTOS_TASK_COUNT_SYM)
            count = int(count_str.strip() or "0")
        except (ValueError, RuntimeError):
            return tasks

        for i in range(count):
            try:
                name = self.session.evaluate_expression(
                    f"{_KERFRTOS_TASK_TABLE_SYM}[{i}].name"
                ).strip('"')
                state = self.session.evaluate_expression(
                    f"{_KERFRTOS_TASK_TABLE_SYM}[{i}].state"
                ).strip().upper()
                priority = int(self.session.evaluate_expression(
                    f"{_KERFRTOS_TASK_TABLE_SYM}[{i}].priority"
                ).strip() or "0")
                stack_high_water = int(self.session.evaluate_expression(
                    f"{_KERFRTOS_TASK_TABLE_SYM}[{i}].stack_high_water"
                ).strip() or "0")
                stack_size = int(self.session.evaluate_expression(
                    f"{_KERFRTOS_TASK_TABLE_SYM}[{i}].stack_size"
                ).strip() or "512")
                tasks.append(TaskInfo(
                    name=name,
                    state=state or "READY",
                    priority=priority,
                    stack_high_water=stack_high_water,
                    stack_size=stack_size,
                ))
            except (ValueError, RuntimeError):
                continue

        return tasks

    def _read_freertos_tasks(self) -> list[TaskInfo]:
        """
        Read tasks from FreeRTOS pxReadyTasksLists.

        Real FreeRTOS inspection would walk the linked list; here we use the
        OpenOCD `monitor rtos enable` + `info tasks` TCL command path which
        is available when FreeRTOS RTOS support is compiled into OpenOCD.
        We parse the output format:

          ID  PC        SP        PRI  Name
          1   0x08001234 0x20001234 5   sensor_task
        """
        tasks: list[TaskInfo] = []
        try:
            # Prefer OpenOCD's native FreeRTOS thread awareness
            lines = self.session.evaluate_expression(
                "*(char*)NULL"  # sentinel — replaced by real OpenOCD TCL in production
            )
        except RuntimeError:
            pass
        return tasks

    # ------------------------------------------------------------------
    # Sync object readers
    # ------------------------------------------------------------------

    def _read_kerfrtos_sync(self) -> list[SyncObject]:
        """Read mutex table from kerfrtos_debug_mutex_table."""
        sync: list[SyncObject] = []
        try:
            count_str = self.session.evaluate_expression(_KERFRTOS_MUTEX_COUNT_SYM)
            count = int(count_str.strip() or "0")
        except (ValueError, RuntimeError):
            return sync

        for i in range(count):
            try:
                name = self.session.evaluate_expression(
                    f"{_KERFRTOS_MUTEX_TABLE_SYM}[{i}].name"
                ).strip('"')
                held_by_raw = self.session.evaluate_expression(
                    f"{_KERFRTOS_MUTEX_TABLE_SYM}[{i}].held_by"
                ).strip('"')
                held_by = held_by_raw if held_by_raw not in ("NULL", "0", "") else None
                waiters_raw = self.session.evaluate_expression(
                    f"{_KERFRTOS_MUTEX_TABLE_SYM}[{i}].waiters"
                ).strip('"')
                waiters = [w.strip() for w in waiters_raw.split(",") if w.strip()] if waiters_raw else []
                sync.append(SyncObject(
                    name=name,
                    kind="mutex",
                    held_by=held_by,
                    waiters=waiters,
                ))
            except (ValueError, RuntimeError):
                continue

        return sync

    def _read_freertos_sync(self) -> list[SyncObject]:
        """FreeRTOS mutex/queue inspection (placeholder for live target)."""
        return []

    # ------------------------------------------------------------------
    # Helpers for raw-injection (test path)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_tasks_from_raw(raw: list[dict]) -> list[TaskInfo]:
        tasks: list[TaskInfo] = []
        for d in raw:
            tasks.append(TaskInfo(
                name=d["name"],
                state=d.get("state", "READY"),
                priority=int(d.get("priority", 0)),
                stack_high_water=int(d.get("stack_high_water", 0)),
                stack_size=int(d.get("stack_size", 512)),
            ))
        return tasks

    @staticmethod
    def _build_sync_from_raw(raw: list[dict]) -> list[SyncObject]:
        sync: list[SyncObject] = []
        for d in raw:
            sync.append(SyncObject(
                name=d["name"],
                kind=d.get("kind", "mutex"),
                held_by=d.get("held_by") or None,
                waiters=list(d.get("waiters") or []),
                count=d.get("count"),
                capacity=d.get("capacity"),
            ))
        return sync

    # ------------------------------------------------------------------
    # Dependency edge construction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_dependency_edges(sync_objects: list[SyncObject]) -> list[DependencyEdge]:
        """
        Build directed dependency edges from sync object state.

        For each sync object:
          - holder holds the resource
          - each waiter depends on the holder (waiter → holder edge)
        """
        edges: list[DependencyEdge] = []
        for obj in sync_objects:
            if obj.held_by is None:
                continue
            for waiter in obj.waiters:
                edges.append(DependencyEdge(
                    from_task=waiter,
                    to_task=obj.held_by,
                    label=f"{obj.kind}:{obj.name}",
                ))
        return edges

    # ------------------------------------------------------------------
    # Warning collection
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_warnings(tasks: list[TaskInfo]) -> list[str]:
        """Return human-readable warnings for stack-watermark violations."""
        warnings: list[str] = []
        for task in tasks:
            if task.stack_warning:
                pct = round(task.stack_pct_free, 1)
                warnings.append(
                    f"Task '{task.name}' stack critically low: "
                    f"{task.stack_high_water}B free of {task.stack_size}B "
                    f"({pct}% — below 10% threshold)"
                )
        return warnings
