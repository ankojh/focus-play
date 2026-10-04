"""Bounded data-only renderer contracts. No paths, URLs or executable renderer code."""
from typing import Annotated, Literal
from pydantic import Field, model_validator
from .contract_base import Contract, EvidenceRef, SceneAction

VisualID = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,19}$")]
CellText = Annotated[str, Field(min_length=1, max_length=120)]
FiniteNumber = Annotated[float, Field(allow_inf_nan=False, ge=-1e12, le=1e12)]

class TableRow(Contract):
    id: VisualID
    cells: list[CellText] = Field(min_length=1, max_length=4)

class TablePayload(Contract):
    columns: list[CellText] = Field(min_length=1, max_length=4)
    rows: list[TableRow] = Field(min_length=1, max_length=8)
    illustrative: bool = False
    @model_validator(mode="after")
    def rectangular(self):
        if len({r.id for r in self.rows}) != len(self.rows) or any(len(r.cells) != len(self.columns) for r in self.rows):
            raise ValueError("Table rows need unique IDs and exactly one cell per column.")
        return self

class CodePayload(Contract):
    language: Literal["text", "python", "sql", "javascript", "shell"]
    text: str = Field(min_length=1, max_length=6000)
    segment_id: str
    @model_validator(mode="after")
    def lines(self):
        lines = self.text.split("\n")
        if not 1 <= len(lines) <= 30 or any(len(line) > 200 for line in lines):
            raise ValueError("Code is limited to 30 lines of 200 characters.")
        return self

class ChartPoint(Contract):
    id: VisualID
    label: str = Field(min_length=1, max_length=60)
    value: FiniteNumber
    segment_id: str

class ChartPayload(Contract):
    chart_kind: Literal["bar"] = "bar"
    unit: str = Field(min_length=1, max_length=40)
    axis_label: str = Field(min_length=1, max_length=80)
    scale_policy: Literal["zero_inclusive"] = "zero_inclusive"
    illustrative: bool = False
    points: list[ChartPoint] = Field(min_length=1, max_length=8)
    @model_validator(mode="after")
    def unique(self):
        if len({p.id for p in self.points}) != len(self.points):
            raise ValueError("Chart points need unique IDs.")
        return self

class Annotation(Contract):
    id: VisualID
    x: float = Field(ge=0, le=1, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, allow_inf_nan=False)
    label: str = Field(min_length=1, max_length=100)
    segment_id: str

class ImagePayload(Contract):
    asset_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    width: int = Field(ge=1, le=4096)
    height: int = Field(ge=1, le=4096)
    alt: str = Field(min_length=5, max_length=240)
    caption: str = Field(min_length=1, max_length=240)
    annotations: list[Annotation] = Field(default=[], max_length=6)
    @model_validator(mode="after")
    def unique(self):
        if len({a.id for a in self.annotations}) != len(self.annotations) or any(a.id == "image" for a in self.annotations):
            raise ValueError("Annotations need unique IDs.")
        return self

class AssetRecord(Contract):
    id: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    kind: Literal["image", "screenshot"]
    mime_type: Literal["image/png", "image/jpeg"]
    byte_size: int = Field(ge=1, le=5_000_000)
    width: int = Field(ge=1, le=4096)
    height: int = Field(ge=1, le=4096)
    original_source: str = Field(min_length=1, max_length=500)
    creator: str = Field(min_length=1, max_length=150)
    permission_basis: str = Field(min_length=5, max_length=500)
    attribution: str = Field(min_length=5, max_length=300)
    license_url: str | None = Field(default=None, max_length=500)
    acquired_at: float = Field(ge=0, allow_inf_nan=False)
    managed_filename: str = Field(pattern=r"^[a-f0-9]{64}\.(png|jpg)$")
    source_context: str = Field(min_length=5, max_length=300)
    illustrative: bool
    status: Literal["validated", "ready", "missing", "failed"] = "validated"
    failure_reason: str = Field(default="", max_length=300)
    @model_validator(mode="after")
    def identity(self):
        ext = "png" if self.mime_type == "image/png" else "jpg"
        if self.id != self.content_hash or self.managed_filename != f"{self.id}.{ext}":
            raise ValueError("Managed asset identity must match its content hash and encoding.")
        return self

class VisualAuthoring(Contract):
    visual_version: Literal[1] = 1
    id: VisualID
    summary: str = Field(min_length=5, max_length=240)

class TableVisual(VisualAuthoring):
    kind: Literal["table"]
    payload: TablePayload

class CodeVisual(VisualAuthoring):
    kind: Literal["code"]
    payload: CodePayload

class ChartVisual(VisualAuthoring):
    kind: Literal["chart"]
    payload: ChartPayload

class ImageVisual(VisualAuthoring):
    kind: Literal["image"]
    payload: ImagePayload

class VisualPlayback(Contract):
    evidence_references: list[EvidenceRef] = Field(default=[], max_length=5)
    beat_ids: list[str] = Field(default=[], max_length=5)
    actions: list[SceneAction] = Field(max_length=40)
    start_ms: int = Field(default=0, ge=0, le=39999)
    end_ms: int = Field(ge=1, le=40000)
    @model_validator(mode="after")
    def timeline(self):
        from .visuals import validate_visual_scene, validate_visual_transitions
        validate_visual_scene(self)
        validate_visual_transitions(self, self.actions)
        return self

class TableScene(TableVisual, VisualPlayback):
    pass

class CodeScene(CodeVisual, VisualPlayback):
    pass

class ChartScene(ChartVisual, VisualPlayback):
    pass

class ImageScene(ImageVisual, VisualPlayback):
    # Attached by the application; never model authored.
    asset: AssetRecord
    @model_validator(mode="after")
    def attached(self):
        if self.asset.id != self.payload.asset_id or (self.asset.width, self.asset.height) != (self.payload.width, self.payload.height) or self.asset.status != "ready":
            raise ValueError("Images require a ready managed asset with matching identity and dimensions.")
        return self
