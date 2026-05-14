from dataclasses import dataclass
from typing import Any, Optional
import uuid


@dataclass
class ProjectCtx:
    """Request-scoped context every tool runs against."""
    pool: Any
    storage: Any
    project_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    http_client: Any
    file_revisions_max: int = 0
