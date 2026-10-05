"""Renderer capabilities and source-only semantic checks, shared by compilation."""
import re

VISUAL_VERSION = "1"
CAPABILITIES = {kind: {"appear", "disappear", "highlight"} for kind in ("table", "code", "chart", "image")}


def targets(scene):
    p = scene.payload
    if scene.kind == "table":
        return {r.id for r in p.rows} | {f"{r.id}_c{i}" for r in p.rows for i in range(len(p.columns))}
    if scene.kind == "code":
        return {f"line_{i+1}" for i in range(len(p.text.split("\n")))}
    if scene.kind == "chart":
        return {p.id for p in p.points}
    if scene.kind == "image":
        return {"image"} | {a.id for a in p.annotations}
    raise ValueError("Unknown visual renderer.")


def primary_targets(scene):
    if scene.kind == "table":
        return {r.id for r in scene.payload.rows}
    if scene.kind == "image":
        return {"image"} | {a.id for a in scene.payload.annotations}
    return targets(scene)


def validate_visual_scene(scene, actions=None):
    actions = scene.actions if actions is None else actions
    if hasattr(scene, "start_ms") and scene.start_ms >= scene.end_ms:
        raise ValueError("Scene end must follow its start.")
    known = targets(scene)
    if scene.kind == "table":
        expected = sum(1 + len(r.cells) for r in scene.payload.rows)
        if len(known) != expected:
            raise ValueError("Row IDs must not collide with cell targets.")
    if [a.at_ms for a in actions] != sorted(a.at_ms for a in actions):
        raise ValueError("Actions must be in timeline order.")
    for a in actions:
        if a.kind not in CAPABILITIES[scene.kind] or a.target not in known:
            allowed = ", ".join(sorted(known))
            raise ValueError(f"Scene {scene.id} ({scene.kind}): operation {a.kind} targeting {a.target} is unsupported by this renderer. "
                             f"Use only reveal/hide/focus with this scene's payload targets: {allowed}. Do not use diagram node/connection IDs here.")
        if scene.kind == "table" and a.target not in primary_targets(scene) and a.kind != "highlight":
            raise ValueError("Cells inherit row visibility and support focus only.")
        if a.to_slot is not None or a.state_id is not None:
            raise ValueError("This renderer does not support move/state arguments.")
        if hasattr(scene, "start_ms") and not scene.start_ms <= a.at_ms < scene.end_ms:
            raise ValueError("Action lies outside its scene interval.")


def validate_visual_transitions(scene, actions):
    visible = set()
    revealed = set()
    for a in actions:
        # Cells inherit row visibility; focusing a cell still requires its row.
        row = a.target.rsplit("_c", 1)[0] if scene.kind == "table" and a.target not in primary_targets(scene) else None
        if row and row not in visible:
            raise ValueError("Cell operations require a visible row.")
        if scene.kind == "image" and a.target != "image" and "image" not in visible:
            raise ValueError("Annotations require a visible image.")
        if a.kind == "appear":
            if a.target in visible:
                raise ValueError("Cannot reveal an already visible target.")
            visible.add(a.target)
            revealed.add(a.target)
        elif a.kind == "disappear":
            if a.target not in visible:
                raise ValueError("Cannot hide a target before revealing it.")
            visible.remove(a.target)
        elif a.target not in visible and not row:
            raise ValueError("Focus needs a visible target.")
    if not primary_targets(scene) <= revealed:
        raise ValueError("Every visual item needs an explicit reveal.")


def visual_text(scene):
    if scene.kind == "diagram":
        return " ".join(n.label + " " + n.detail for n in scene.nodes)
    p = scene.payload
    if scene.kind == "table":
        return " ".join([*p.columns, *(cell for r in p.rows for cell in r.cells)])
    if scene.kind == "code":
        return p.text
    if scene.kind == "chart":
        return " ".join([p.axis_label, p.unit, *(f"{v.label} {v.value}" for v in p.points)])
    return " ".join([p.alt, p.caption, *(a.label for a in p.annotations)])


CHART_NUMBER = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?(?![\w.])")


def chartable(texts):
    """A chart needs real numbers to plot; without them the model invents values."""
    return any(CHART_NUMBER.search(text) for text in texts)


def validate_visual_evidence(scene, segments, beats):
    known = {s.id: s for s in segments}
    cited = {sid for b in beats if b.scene_id == scene.id for sid in b.evidence.segment_ids}
    def passage(sid):
        if sid not in known or sid not in cited:
            raise ValueError("Visual claims must cite an applicable scene beat's passage.")
        return known[sid].text
    p = scene.payload
    if scene.kind == "code" and p.text not in passage(p.segment_id):
        raise ValueError("Display-only code must be an exact snippet of the cited passage; invented code is not permitted.")
    if scene.kind == "chart":
        for point in p.points:
            text = passage(point.segment_id)
            numbers = {float(v) for v in CHART_NUMBER.findall(text)}
            if point.value not in numbers:
                raise ValueError("Chart value must match a number in its own cited passage.")
            if p.unit.casefold() not in text.casefold():
                raise ValueError("Chart unit must appear in each point's cited passage.")
    if scene.kind == "image":
        for a in p.annotations:
            passage(a.segment_id)
    # Labels, comparisons and table mechanisms still undergo the bounded source review.
