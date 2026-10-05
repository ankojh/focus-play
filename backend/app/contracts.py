from __future__ import annotations
from typing import Literal, Annotated
from pydantic import Field, model_validator, field_validator
from .contract_base import Contract, EvidenceRef, SceneAction

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
        if self.start_ms is not None and self.end_ms is not None and self.end_ms <= self.start_ms:
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

class NarrationUnit(Contract):
    text: str = Field(min_length=10, max_length=600)
    evidence: EvidenceRef
    # Legacy narration has no beat binding; new playback persists these IDs.
    beat_id: str | None = None
    scene_id: str | None = None
    purpose: str | None = None
    start_ms: int = 0
    end_ms: int = 0

TeachingRole = Literal["foundation", "mechanism", "worked_example", "comparison", "misconception", "application", "practice", "recap"]
CurriculumRole = Literal["core", "extension", "closing"]

Template = Literal["process", "comparison", "example", "timeline", "chart", "steps", "cycle", "dos_donts", "key_fact"]
# Roles colour a node: start, step and result for sequences, good and bad for do vs. don't.
Role = Literal["neutral", "start", "step", "result", "warning", "good", "bad"]
class DiagramNode(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,19}$")
    label: str = Field(min_length=1, max_length=44)
    detail: str = Field(default="", max_length=70)
    slot: int = Field(ge=0, le=3)
    shape: Literal["box", "circle", "bar"] = "box"
    # Saved lessons predate icons and roles; the defaults render as before.
    icon: str | None = Field(default=None, max_length=30)
    role: Role = "neutral"
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
        if len({" ".join(x.lower().split()) for x in self.options}) != len(self.options):
            raise ValueError("Question choices must be distinct.")
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

class DiagramState(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,19}$")
    target: str
    label: str = Field(min_length=1, max_length=44)
    detail: str = Field(min_length=3, max_length=70)
    role: Role = "neutral"

class Scene(Contract):
    # Version-1 saved scenes have no envelope metadata. All times are absolute.
    id: str | None = None
    kind: Literal["diagram"] = "diagram"
    summary: str = Field(default="", max_length=240)
    evidence_references: list[EvidenceRef] = []
    beat_ids: list[str] = []
    states: list[DiagramState] = Field(default=[], max_length=12)
    template: Template
    nodes: list[DiagramNode]
    connections: list[Connection]
    actions: list[SceneAction]
    start_ms: int = Field(default=0, ge=0, le=39999)
    end_ms: int = Field(ge=1, le=40000)
    @model_validator(mode="after")
    def timeline(self):
        from .storyboard import validate_scene
        validate_scene(self)
        return self

from .visual_contracts import (TableVisual, CodeVisual, ChartVisual, ImageVisual,
    TableScene, CodeScene, ChartScene, ImageScene, AssetRecord)

PlaybackScene = Annotated[Scene | TableScene | CodeScene | ChartScene | ImageScene, Field(discriminator="kind")]

def legacy_scene_kinds(value):
    if isinstance(value, list):
        return [{"kind": "diagram", **scene} if isinstance(scene, dict) else scene for scene in value]
    return value

ShortState = Literal["queued", "generating", "validating", "synthesizing", "ready", "failed", "cancelled"]
class Short(Contract):
    target_duration_ms: int = Field(default=40000, ge=1000, le=40000)
    duration_uncertainty_ms: int = Field(default=0, ge=0, le=40000)
    concept_id: str | None = None
    learning_outcome: str | None = None
    teaching_role: TeachingRole | None = None
    curriculum_role: CurriculumRole = "core"
    example_id: str | None = None
    source_review_status: Literal["unchecked", "model_supported"] = "unchecked"
    source_review_reason: str = Field(default="", max_length=500)
    teaching_diagnostics: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(default=[], max_length=8)
    review_repair_reasons: list[Annotated[str, Field(max_length=500)]] = Field(default=[], max_length=2)
    storyboard_version: Literal[1, 2] = 1
    timeline_compiler_version: str | None = None
    id: str
    objective: str
    prerequisites: list[str] = []
    narration_units: list[NarrationUnit] = []
    evidence_references: list[EvidenceRef] = []
    scenes: list[PlaybackScene] = []
    _legacy_scenes = field_validator("scenes", mode="before")(legacy_scene_kinds)
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
    @model_validator(mode="after")
    def playback(self):
        if any(scene.kind != "diagram" for scene in self.scenes) and self.storyboard_version != 2:
            raise ValueError("Mixed visual scenes require storyboard version 2.")
        if self.storyboard_version == 2 and self.status == "ready":
            from .storyboard import validate_timeline
            validate_timeline(self.scenes, self.narration_units, self.measured_duration_ms)
            if not self.audio_path or not self.timeline_compiler_version:
                raise ValueError("Ready storyboards require audio and a compiler version.")
        return self

class SemanticOperation(Contract):
    kind: Literal["reveal", "hide", "focus", "connect", "move", "change_state"]
    target: str
    to_slot: int | None = Field(default=None, ge=0, le=3)
    state_id: str | None = None

class StoryboardScene(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,19}$")
    kind: Literal["diagram"] = "diagram"
    summary: str = Field(min_length=5, max_length=240)
    template: Template
    nodes: list[DiagramNode] = Field(min_length=2, max_length=4)
    connections: list[Connection] = Field(max_length=4)
    states: list[DiagramState] = Field(max_length=12)

AuthoredVisual = Annotated[StoryboardScene | TableVisual | CodeVisual | ChartVisual | ImageVisual, Field(discriminator="kind")]

class NarrationBeat(NarrationUnit):
    beat_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,19}$")
    scene_id: str
    purpose: str = Field(min_length=5, max_length=120)
    operations: list[SemanticOperation] = Field(min_length=1, max_length=8)

class StoryboardDraft(Contract):
    storyboard_version: Literal[2] = 2
    objective: str = Field(min_length=5, max_length=150)
    prerequisites: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(max_length=4)
    narration_units: list[NarrationBeat] = Field(min_length=2, max_length=5)
    scenes: list[AuthoredVisual] = Field(min_length=1, max_length=3)
    _legacy_scenes = field_validator("scenes", mode="before")(legacy_scene_kinds)
    question: Question | None = None
    @model_validator(mode="after")
    def storyboard(self):
        from .storyboard import validate_storyboard
        validate_storyboard(self)
        return self

class ExampleRecord(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,19}$")
    # Source-only policy: facts are exact excerpts, not synthetic measurements.
    entities: list[Annotated[str, Field(min_length=1, max_length=60)]] = Field(min_length=1, max_length=4)
    facts: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(min_length=1, max_length=4)
    evidence_segment_ids: list[str] = Field(min_length=1, max_length=4)

class Objective(Contract):
    # Defaults only adapt legacy saved lessons. New model plans require these fields.
    concept_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,19}$")
    learning_outcome: str | None = Field(default=None, min_length=10, max_length=180)
    teaching_role: TeachingRole = "foundation"
    dependency_ids: list[str] = Field(default=[], max_length=4)
    relevance: str = Field(default="", max_length=180)
    evidence_segment_ids: list[str] = Field(default=[], max_length=4)
    curriculum_role: CurriculumRole = "core"
    target_duration_ms: int = Field(default=40000, ge=1000, le=40000)
    example_id: str | None = None
    visual_intent: str = Field(default="", max_length=120)
    checkpoint: bool = False
    title: str = Field(min_length=5, max_length=150)
    template: Template
    prerequisites: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(max_length=4)

class CoverageGap(Contract):
    outcome: str = Field(min_length=5, max_length=180)
    missing_facets: list[Literal["definition", "mechanism", "example", "caveat", "application"]] = Field(max_length=5)
    query_intent: str = Field(min_length=5, max_length=180)

class LessonPlan(Contract):
    sufficient_evidence: bool
    reason: str = Field(max_length=400)
    missing_coverage: list[CoverageGap] = Field(default=[], max_length=2)
    objectives: list[Objective] = Field(max_length=80)
    examples: list[ExampleRecord] = Field(default=[], max_length=2)

class CoverageEntry(Contract):
    short_id: str
    concept_id: str
    learning_outcome: str = Field(max_length=180)
    teaching_role: TeachingRole
    claim_summary: str = Field(max_length=240)
    evidence_segment_ids: list[str] = Field(max_length=20)
    example_id: str | None = None
    adds_coverage: bool = True

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

class AcquisitionRound(Contract):
    query: str
    completed: bool = False
    candidates: list[dict] = Field(default=[], max_length=15)
    source_ids: list[str] = Field(default=[], max_length=15)
    transcript_attempts: int = 0

class AcquisitionLedger(Contract):
    round_limit: int = Field(default=2, ge=1, le=2)
    transcript_limit: int = Field(default=16, ge=1, le=30)
    per_round_limit: int = Field(default=8, ge=1, le=15)
    rounds: list[AcquisitionRound] = Field(default=[], max_length=2)
    tried_video_ids: list[str] = Field(default=[], max_length=30)
    search_provider_calls: int = 0
    transcript_provider_calls: int = 0
    # Started HTTP attempts, separately from conservative logical reservations.
    youtube_http_calls: int = 0
    youtube_quota_units: int = 0
    transcript_http_calls: int = 0
    search_cache_hits: int = 0
    transcript_cache_hits: int = 0

CompletionReason = Literal["target_met", "coverage_exhausted", "source_limit", "generation_limit", "budget_fit"]

class DurationLedger(Contract):
    version: Literal[2] = 2
    measured_ready_media_ms: int = 0
    reserved_practice_ms: int = 0
    estimated_unready_media_ms: int = 0
    reserved_closing_ms: int = 0
    forecast_total_ms: int = 0
    final_content_ms: int | None = None
    original_content_ms: int = 0
    extra_content_ms: int = 0
    utilisation: float = 0
    shortfall_ms: int = 0

class OutcomeCoverage(Contract):
    concept_id: str
    outcome: str
    evidence_segment_ids: list[str] = Field(max_length=20)
    supported_facets: list[str] = Field(default=[], max_length=5)
    used_claims: list[str] = Field(default=[], max_length=1)

class PlanningState(Contract):
    version: Literal[2] = 2
    revision: int = 0
    minimum_media_ms: int = Field(default=15000, ge=15000, le=40000)
    activity_limit: int = Field(ge=1, le=80)
    batch_limit: Literal[4] = 4
    expansion_limit: int = Field(ge=1, le=80)
    expansion_attempts: int = 0
    candidate_attempts: int = 0
    candidate_limit: int = 0
    model_call_units: int = 0
    model_call_limit: int = 0
    work_seconds: float = 0
    work_limit_seconds: int = 7200
    completion_reason: CompletionReason | None = None
    completion_detail: str = Field(default="", max_length=500)
    coverage: list[OutcomeCoverage] = Field(default=[], max_length=80)
    missing_coverage: list[CoverageGap] = Field(default=[], max_length=2)
    deferred_concept_ids: list[str] = Field(default=[], max_length=80)
    # Titles of planned points skipped because drafts only repeated earlier
    # shorts. Shown to the planner so it does not re-plan them.
    nothing_new: list[Annotated[str, Field(max_length=100)]] = Field(default=[], max_length=80)
    # Repeat skips since sources last grew; at 2 the next plan must search first.
    repeat_skips_since_sources: int = Field(default=0, ge=0)
    # Planned points dropped because they still failed a content check, with a
    # plain reason, shown on the lesson page. Never fails the whole lesson.
    skipped_points: list[Annotated[str, Field(max_length=200)]] = Field(default=[], max_length=80)
    failed_skips_in_row: int = Field(default=0, ge=0)

class Readiness(Contract):
    version: Literal[1] = 1
    ready_short_ids: list[str] = []
    missing_media_short_ids: list[str] = []
    # From the beginning at position zero, not a forecast for an arbitrary client.
    initial_contiguous_media_ms: int = 0

class Lesson(Contract):
    # Computed on API snapshots; old saved lessons need no migration.
    readiness: Readiness | None = None
    # None means legacy policy: never automatically expand old ready lessons.
    planning: PlanningState | None = None
    acquisition: AcquisitionLedger = Field(default_factory=AcquisitionLedger)
    duration_ledger: DurationLedger | None = None
    teaching_plan_version: Literal[1, 2] = 1
    examples: list[ExampleRecord] = Field(default=[], max_length=2)
    coverage_history: list[CoverageEntry] = Field(default=[], max_length=83)
    plan_diagnostics: list[str] = Field(default=[], max_length=8)
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
    provider: str = "unknown"
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

# Model contracts cite evidence by ID. The model writes narration in its own words;
# the server copies quotes and times from the cited segment.
class ModelUnit(Contract):
    text: str = Field(min_length=10, max_length=300)
    segment_id: str

class ModelQuestion(Contract):
    prompt: str = Field(min_length=10, max_length=240)
    correct_answer: str = Field(min_length=1, max_length=180)
    distractors: list[Annotated[str, Field(min_length=1, max_length=180)]] = Field(min_length=1, max_length=3)
    explanation: str = Field(min_length=10, max_length=300)
    segment_id: str
    @model_validator(mode="after")
    def unique_answers(self):
        options = [self.correct_answer, *self.distractors]
        if len({" ".join(x.lower().split()) for x in options}) != len(options):
            raise ValueError("Question choices must be distinct.")
        return self

class ModelBeat(Contract):
    beat_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,19}$")
    scene_id: str
    purpose: str = Field(min_length=5, max_length=120)
    text: str = Field(min_length=10, max_length=300)
    segment_id: str
    operations: list[SemanticOperation] = Field(min_length=1, max_length=8)

class ModelStoryboard(Contract):
    storyboard_version: Literal[2]
    objective: str = Field(min_length=5, max_length=150)
    prerequisites: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(max_length=4)
    narration_units: list[ModelBeat] = Field(min_length=2, max_length=5)
    scenes: list[AuthoredVisual] = Field(min_length=1, max_length=3)
    _legacy_scenes = field_validator("scenes", mode="before")(legacy_scene_kinds)
    question: ModelQuestion | None = None

# Legacy flat model data is retained only for explicit adapters and tests.
class ModelShort(Contract):
    objective: str = Field(min_length=5, max_length=150)
    prerequisites: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(max_length=4)
    narration_units: list[ModelUnit] = Field(min_length=2, max_length=2)
    template: Template
    nodes: list[DiagramNode] = Field(min_length=2, max_length=4)
    connections: list[Connection] = Field(max_length=4)
    question: ModelQuestion | None = None
