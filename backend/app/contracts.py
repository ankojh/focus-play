from __future__ import annotations
from typing import Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")

class ErrorInfo(Contract):
    code: str
    message: str

class LearningRequest(Contract):
    goal: str = Field(min_length=3, max_length=500)
    prior_knowledge: str = Field(default="beginner", min_length=1, max_length=500)
    time_budget_seconds: int = Field(default=300, ge=60, le=1200)
    language: Literal["en"] = "en"
    request_id: str = Field(min_length=8, max_length=100)

class SavedLearningRequest(LearningRequest):
    # Retain the actual request of old lessons. These fields are never accepted by POST /lessons.
    source_mode: Literal["import", "youtube"] | None = None
    source_ids: list[str] = []

class TranscriptSegment(Contract):
    id: str
    source_id: str
    text: str = Field(min_length=1, max_length=1800)
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    @model_validator(mode="after")
    def timing(self):
        if (self.start_ms is None) != (self.end_ms is None):
            raise ValueError("Both transcript times are required.")
        if self.start_ms is not None and self.end_ms <= self.start_ms:
            raise ValueError("The transcript end must follow its start.")
        return self

class Source(Contract):
    id: str
    title: str
    source_type: Literal["original_sample", "import", "youtube"]
    video_id: str | None = None
    url: str | None = None
    channel: str | None = None
    transcript_provider: Literal["youtube-transcript-api", "supadata"] | None = None
    transcript_status: Literal["available", "needed"]
    provenance: str
    content_hash: str
    segments: list[TranscriptSegment] = []

class ImportRequest(Contract):
    title: str = Field(min_length=1, max_length=150)
    text: str = Field(min_length=10, max_length=200_000)
    format: Literal["txt", "srt", "vtt"] = "txt"
    youtube_url: str | None = Field(default=None, max_length=300)
    provenance: str = Field(default="User supplied transcript. Access permission is supplied by the user.", max_length=500)

class EvidenceRef(Contract):
    source_id: str
    segment_ids: list[str] = Field(min_length=1, max_length=4)
    start_ms: int | None = None
    end_ms: int | None = None
    quote: str = Field(min_length=1, max_length=1800)

class NarrationUnit(Contract):
    text: str = Field(min_length=10, max_length=600)
    evidence: EvidenceRef
    start_ms: int = 0
    end_ms: int = 0

Template = Literal["process", "comparison", "example", "timeline", "chart"]
class DiagramNode(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,19}$")
    label: str = Field(min_length=1, max_length=44)
    detail: str = Field(default="", max_length=70)
    slot: int = Field(ge=0, le=3)
    shape: Literal["box", "circle", "bar"] = "box"
    @model_validator(mode="after")
    def label_bounds(self):
        if any(len(word) > 24 for word in (self.label + " " + self.detail).split()):
            raise ValueError("Use diagram words no longer than 24 characters.")
        return self
    value: float | None = Field(default=None, ge=0, le=100)

class Connection(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,19}$")
    source: str
    target: str

class DraftAction(Contract):
    kind: Literal["appear", "disappear", "highlight", "move", "draw"]
    target: str
    unit: int = Field(ge=0, le=3)
    to_slot: int | None = Field(default=None, ge=0, le=3)

class Question(Contract):
    prompt: str = Field(min_length=10, max_length=240)
    options: list[str] = Field(min_length=2, max_length=4)
    answer_index: int = Field(ge=0, le=3)
    explanation: str = Field(min_length=10, max_length=600)
    evidence: EvidenceRef
    allowance_ms: Literal[20000] = 20000
    @model_validator(mode="after")
    def answer(self):
        if self.answer_index >= len(self.options) or any(len(x) > 180 for x in self.options):
            raise ValueError("Invalid question options.")
        return self

class ShortDraft(Contract):
    objective: str = Field(min_length=5, max_length=150)
    prerequisites: list[str] = Field(max_length=4)
    narration_units: list[NarrationUnit] = Field(min_length=2, max_length=4)
    template: Template
    nodes: list[DiagramNode] = Field(min_length=2, max_length=4)
    connections: list[Connection] = Field(max_length=4)
    actions: list[DraftAction] = Field(min_length=1, max_length=16)
    question: Question | None = None
    @model_validator(mode="after")
    def diagram(self):
        ids = {n.id for n in self.nodes}
        edge_ids = {e.id for e in self.connections}
        if len(ids) != len(self.nodes) or len(edge_ids) != len(self.connections) or ids & edge_ids:
            raise ValueError("Diagram IDs must be unique.")
        if len({n.slot for n in self.nodes}) != len(self.nodes):
            raise ValueError("Nodes cannot share a slot.")
        for e in self.connections:
            if e.source not in ids or e.target not in ids or e.source == e.target:
                raise ValueError("Invalid connection.")
        if [a.unit for a in self.actions] != sorted(a.unit for a in self.actions):
            raise ValueError("Put actions in narration order.")
        occupancy = {n.id: n.slot for n in self.nodes}
        for a in self.actions:
            if a.unit >= len(self.narration_units) or a.target not in (edge_ids if a.kind == "draw" else ids):
                raise ValueError(f"Action {a.kind} on {a.target} uses unit {a.unit}. Use a valid target and narration indexes 0 through {len(self.narration_units)-1}.")
            if a.kind == "move":
                if a.to_slot is None or any(v == a.to_slot for k, v in occupancy.items() if k != a.target):
                    raise ValueError("A move needs a free destination slot.")
                if self.template not in {"comparison", "chart"} and any(min(occupancy[a.target],a.to_slot)<v<max(occupancy[a.target],a.to_slot) for k,v in occupancy.items() if k!=a.target):
                    raise ValueError("A move cannot pass through an occupied slot.")
                occupancy[a.target] = a.to_slot
        words = len(" ".join(u.text for u in self.narration_units).split())
        if not 30 <= words <= 120:
            raise ValueError(f"Narration has {words} words. Use 30 to 120, aiming for 40 to 80. Measured speech must fit 40 seconds.")
        return self

class SceneAction(Contract):
    kind: Literal["appear", "disappear", "highlight", "move", "draw"]
    target: str
    at_ms: int = Field(ge=0)
    to_slot: int | None = None

class Scene(Contract):
    template: Template
    nodes: list[DiagramNode]
    connections: list[Connection]
    actions: list[SceneAction]
    start_ms: int = 0
    end_ms: int = Field(ge=1, le=40000)

ShortState = Literal["queued", "generating", "validating", "synthesizing", "ready", "failed", "cancelled"]
class Short(Contract):
    id: str
    objective: str
    prerequisites: list[str] = []
    narration_units: list[NarrationUnit] = []
    evidence_references: list[EvidenceRef] = []
    scenes: list[Scene] = []
    question: Question | None = None
    audio_path: str | None = None
    measured_duration_ms: int = 0
    status: ShortState = "queued"
    error: ErrorInfo | None = None
    optional: bool = False
    question_required: bool = False
    cache_hit: bool = False
    provider_settings: dict = {}
    timings: dict[str, float] = {}

class Objective(Contract):
    title: str = Field(min_length=5, max_length=150)
    template: Template
    prerequisites: list[str] = Field(max_length=4)

class LessonPlan(Contract):
    sufficient_evidence: bool
    reason: str = Field(max_length=400)
    objectives: list[Objective] = Field(max_length=8)

# The model scores candidate videos 1 to 5 from their transcripts. Code picks the sources.
class CandidateScore(Contract):
    video_id: str
    relevance: int = Field(ge=1, le=5)
    level_fit: int = Field(ge=1, le=5)
    teaching: int = Field(ge=1, le=5)
    density: int = Field(ge=1, le=5)
    captions: int = Field(ge=1, le=5)
    reason: str = Field(min_length=1, max_length=200)

class CandidateRanking(Contract):
    scores: list[CandidateScore] = Field(min_length=1, max_length=15)

class Job(Contract):
    id: str
    lesson_id: str
    stage: str = "queued"
    status: Literal["queued", "running", "complete", "failed", "cancelled", "interrupted"] = "queued"
    error: ErrorInfo | None = None
    event_sequence: int = 0
    stage_timings: dict[str, float] = {}
    created_at: float
    updated_at: float

class Lesson(Contract):
    id: str
    request: SavedLearningRequest
    objectives: list[Objective] = []
    short_ids: list[str] = []
    shorts: list[Short] = []
    sources: list[Source]
    status: Literal["queued", "preparing", "partially_ready", "ready", "failed", "cancelled", "interrupted"] = "queued"
    planned_duration_ms: int = 0
    original_planned_duration_ms: int = 0
    extra_allowance_ms: int = 0
    job: Job
    provider_settings: dict = {}
    metrics: dict[str, float] = {}
    video_rankings: list[CandidateScore] = []

class ProviderHealth(Contract):
    ready: bool
    model_ready: bool
    speech_ready: bool
    model: str
    digest: str | None = None
    speech_provider: str
    voice: str
    message: str
    youtube_ready: bool = False
    youtube_message: str = "YouTube source setup has not been checked."

class SourceList(Contract):
    sources: list[Source]
class ExplanationRequest(Contract):
    kind: Literal["example", "again"]
    # User must approve this visible allowance before the job is created.
    added_seconds: Literal[40] = 40
    request_id: str = Field(min_length=8, max_length=100)

class SearchItem(Contract):
    video_id: str
    title: str
    channel: str
    url: str
    duration_seconds: int | None = None
    transcript_status: Literal["needed"] = "needed"

class SearchResponse(Contract):
    results: list[SearchItem]
    cached: bool
    acquisition: Literal["assisted"] = "assisted"

# Model contracts select evidence by ID. The server copies quotes and times from
# the stored segment; the model cannot invent quotation or timing fields.
class ModelUnit(Contract):
    text: str = Field(min_length=10, max_length=300)
    segment_id: str

class ModelQuestion(Contract):
    prompt: str = Field(min_length=10, max_length=240)
    correct_answer: str = Field(min_length=10, max_length=180)
    distractors: list[Annotated[str, Field(min_length=1, max_length=180)]] = Field(min_length=1, max_length=3)
    segment_id: str

class ModelShort(Contract):
    objective: str = Field(min_length=5, max_length=150)
    prerequisites: list[str] = Field(max_length=4)
    narration_units: list[ModelUnit] = Field(min_length=2, max_length=2)
    template: Template
    nodes: list[DiagramNode] = Field(min_length=2, max_length=4)
    connections: list[Connection] = Field(max_length=4)
    question: ModelQuestion | None = None
