"""Locate + import authored generator modules.

A generator lives at ``kerf_partsgen/generators/<family_id>.py`` and exposes
``FAMILY``, ``SIZES`` and ``build`` (see :mod:`kerf_partsgen.spec`).  Loading
is by file path (importlib) so a freshly ``author``-ed file is picked up
without a reinstall, and so tests can point at an arbitrary sample dir.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from types import ModuleType

from kerf_partsgen.spec import GeneratorModule


def generators_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "generators")


def generator_path(family_id: str, gen_dir: str | None = None) -> str:
    return os.path.join(gen_dir or generators_dir(), f"{family_id}.py")


def _import_path(path: str) -> ModuleType:
    mod_name = f"_kpg_gen_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load generator at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_generator(path: str) -> GeneratorModule:
    """Import a generator file and validate its contract. Raises ValueError
    on any contract violation (missing/typed-wrong FAMILY, SIZES, build)."""
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    module = _import_path(path)

    fam = getattr(module, "FAMILY", None)
    sizes = getattr(module, "SIZES", None)
    build = getattr(module, "build", None)

    if not isinstance(fam, dict):
        raise ValueError(f"{path}: FAMILY must be a dict")
    if not isinstance(sizes, list) or not sizes:
        raise ValueError(f"{path}: SIZES must be a non-empty list")
    if not callable(build):
        raise ValueError(f"{path}: build must be callable")

    for key in ("family_id", "name", "standard", "domain", "category"):
        if not fam.get(key):
            raise ValueError(f"{path}: FAMILY missing required key {key!r}")

    seen: set[str] = set()
    for i, row in enumerate(sizes):
        if not isinstance(row, dict):
            raise ValueError(f"{path}: SIZES[{i}] must be a dict")
        sz = row.get("size")
        if not sz:
            raise ValueError(f"{path}: SIZES[{i}] missing 'size'")
        if sz in seen:
            raise ValueError(f"{path}: duplicate size {sz!r}")
        seen.add(sz)

    return GeneratorModule(
        family_id=fam["family_id"],
        name=fam["name"],
        standard=fam["standard"],
        domain=fam["domain"],
        category=fam["category"],
        sizes=sizes,
        build=build,
        source_path=path,
    )


def load_family(family_id: str, gen_dir: str | None = None) -> GeneratorModule:
    return load_generator(generator_path(family_id, gen_dir))
