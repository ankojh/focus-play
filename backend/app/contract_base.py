"""Common scene primitives shared without cyclic imports."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")

class EvidenceRef(Contract):
    source_id: str
    segment_ids: list[str] = Field(min_length=1, max_length=4)
    start_ms: int | None = None
    end_ms: int | None = None
    quote: str = Field(min_length=1, max_length=1800)

class SceneAction(Contract):
    kind: Literal["appear", "disappear", "highlight", "move", "draw", "change_state"]
    target: str
    at_ms: int = Field(ge=0)
    to_slot: int | None = Field(default=None, ge=0, le=7)
    state_id: str | None = None
    beat_id: str | None = None
