from dataclasses import dataclass, field
from typing import Callable, Any

Registry: list["Tool"] = []


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict


@dataclass
class Tool:
    spec: ToolSpec
    write: bool = False
    run: Callable = None


def register(spec: ToolSpec, write: bool = False):
    def decorator(fn):
        Registry.append(Tool(spec=spec, write=write, run=fn))
        return fn
    return decorator


def ok_payload(v: Any) -> str:
    import json
    try:
        return json.dumps(v)
    except Exception as e:
        return err_payload(f"encode result: {e}", "ERROR")


def err_payload(msg: str, code: str) -> str:
    import json
    return json.dumps({"error": msg, "code": code})
