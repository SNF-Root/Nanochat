from dataclasses import dataclass
from typing import Generic, Literal, Optional, TypeVar


T = TypeVar("T")

PipelineStatus = Literal["ok", "rejected", "duplicate", "skipped", "error"]


@dataclass(frozen=True)
class PipelineResult(Generic[T]):
    item: Optional[T]
    status: PipelineStatus
    reason: Optional[str] = None
    source: Optional[str] = None
