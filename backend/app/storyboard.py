"""Bounded diagram storyboards. Persisted times are absolute audio milliseconds.

Scenes/narration are contiguous half-open intervals; the last frame holds at duration.
No lexical targeting, model timestamps, or independent animation clock is used.
"""
from .contracts import Scene, SceneAction, NarrationUnit

STORYBOARD_VERSION = 2
COMPILER_VERSION = "1"
KINDS = {"reveal": "appear", "hide": "disappear", "focus": "highlight",
         "connect": "draw", "move": "move", "change_state": "change_state"}
FIXED_LAYOUTS = {"cycle", "dos_donts", "key_fact"}


def validate_scene(scene):
    if scene.start_ms >= scene.end_ms:
        raise ValueError("Scene end must follow its start.")
    nodes = {n.id: n for n in scene.nodes}
    edges = {e.id: e for e in scene.connections}
    states = {s.id: s for s in scene.states}
    if not 2 <= len(nodes) <= 4 or len(nodes) != len(scene.nodes) or len(edges) != len(scene.connections) or len(edges) > 4 or nodes.keys() & edges.keys():
        raise ValueError("Scene needs 2 to 4 unique nodes and unique connection IDs.")
    if len({n.slot for n in scene.nodes}) != len(nodes):
        raise ValueError("Nodes cannot share a slot.")
    if any(e.source not in nodes or e.target not in nodes or e.source == e.target for e in edges.values()):
        raise ValueError("Invalid connection target.")
    if len(states) != len(scene.states) or any(s.target not in nodes for s in states.values()):
        raise ValueError("States need unique IDs and existing node targets.")
    for state in states.values():
        if any(len(word) > 24 for word in (state.label + " " + state.detail).split()):
            raise ValueError("State text needs words no longer than 24 characters.")
        if scene.template == "dos_donts" and state.role != nodes[state.target].role:
            raise ValueError("State changes cannot switch fixed-layout columns.")
    if [a.at_ms for a in scene.actions] != sorted(a.at_ms for a in scene.actions):
        raise ValueError("Actions must be in timeline order.")
    occupancy = {n.id: n.slot for n in scene.nodes}
    for action in scene.actions:
        if not scene.start_ms <= action.at_ms < scene.end_ms:
            raise ValueError("Action lies outside its scene interval.")
        if action.target not in (edges if action.kind == "draw" else nodes):
            raise ValueError("Action references an unknown target.")
        if action.kind == "change_state":
            if action.state_id not in states or states[action.state_id].target != action.target:
                raise ValueError("State change references an unknown or mismatched state.")
        elif action.state_id is not None:
            raise ValueError("Only state changes accept state_id.")
        if action.kind == "move":
            if scene.template in FIXED_LAYOUTS:
                raise ValueError("This renderer layout does not support move.")
            dest = action.to_slot
            if dest is None or dest == occupancy[action.target] or any(slot == dest for node, slot in occupancy.items() if node != action.target):
                raise ValueError("A move needs a free, different destination slot.")
            if scene.template not in {"comparison", "chart"} and any(min(occupancy[action.target], dest) < slot < max(occupancy[action.target], dest) for node, slot in occupancy.items() if node != action.target):
                raise ValueError("A move cannot pass through an occupied slot.")
            occupancy[action.target] = dest
        elif action.to_slot is not None:
            raise ValueError("Only moves accept to_slot.")


def validate_storyboard(draft):
    beats = draft.narration_units
    if len({b.beat_id for b in beats}) != len(beats):
        raise ValueError("Beat IDs must be unique.")
    scene_ids = [s.id for s in draft.scenes]
    if len(set(scene_ids)) != len(scene_ids):
        raise ValueError("Scene IDs must be unique.")
    bindings = []
    for beat in beats:
        if not bindings or bindings[-1] != beat.scene_id:
            bindings.append(beat.scene_id)
    if bindings != scene_ids:
        raise ValueError("Every beat must bind to an existing scene in contiguous scene order.")
    words = len(" ".join(b.text for b in beats).split())
    if not 30 <= words <= 120:
        raise ValueError(f"Narration has {words} words. Use 30 to 120, aiming for 40 to 80.")
    # Validate semantics using beat indexes, never guessed milliseconds.
    for scene in draft.scenes:
        selected = [b for b in beats if b.scene_id == scene.id]
        actions = [SceneAction(kind=KINDS[op.kind], target=op.target, at_ms=i,
                    to_slot=op.to_slot, state_id=op.state_id, beat_id=beat.beat_id)
                   for i, beat in enumerate(selected) for op in beat.operations]
        Scene(**scene.model_dump(), actions=actions, start_ms=0, end_ms=len(selected))
        validate_transitions(scene, actions)


def validate_transitions(scene, actions):
    visible, drawn = set(), set()
    edge_map = {e.id: e for e in scene.connections}
    for action in actions:
        if action.kind == "appear":
            if action.target in visible:
                raise ValueError("Cannot reveal an already visible node.")
            visible.add(action.target)
        elif action.kind == "disappear":
            if action.target not in visible:
                raise ValueError("Cannot hide a node before revealing it.")
            visible.remove(action.target)
        elif action.kind == "draw":
            edge = edge_map[action.target]
            if edge.source not in visible or edge.target not in visible or edge.id in drawn:
                raise ValueError("Connect needs visible endpoints and an undrawn connection.")
            if scene.template == "dos_donts":
                raise ValueError("This renderer does not support connections.")
            drawn.add(edge.id)
        elif action.target not in visible:
            raise ValueError("Focus, move and state changes need a visible target.")
    if {a.target for a in actions if a.kind == "appear"} != {n.id for n in scene.nodes}:
        raise ValueError("Every storyboard node needs an explicit reveal.")
    if drawn != set(edge_map):
        raise ValueError("Every storyboard connection needs an explicit connect.")


def validate_boundaries(units, duration):
    if not 1000 <= duration <= 40000 or not units:
        raise ValueError("Measured speech must be between 1 and 40 seconds.")
    cursor = 0
    for unit in units:
        if unit.start_ms != cursor or not unit.start_ms < unit.end_ms <= duration:
            raise ValueError("Measured beat intervals must be positive, ordered and contiguous.")
        cursor = unit.end_ms
    if cursor != duration:
        raise ValueError("Measured beats must cover the entire audio duration.")


def validate_timeline(scenes, units, duration):
    if not 2 <= len(units) <= 5 or not 1 <= len(scenes) <= 3:
        raise ValueError("Playback needs 2 to 5 beats and 1 to 3 scenes.")
    validate_boundaries(units, duration)
    if not scenes or len({s.id for s in scenes}) != len(scenes) or any(not s.id for s in scenes):
        raise ValueError("Timeline needs unique scene IDs.")
    beat_map = {u.beat_id: u for u in units}
    if None in beat_map or "" in beat_map or len(beat_map) != len(units) or any(not u.purpose or len(u.purpose) < 5 for u in units):
        raise ValueError("Timeline needs unique beat IDs.")
    cursor, covered = 0, []
    for scene in scenes:
        validate_scene(scene)
        validate_transitions(scene, scene.actions)
        if scene.start_ms != cursor or scene.end_ms > duration:
            raise ValueError("Scene intervals must be ordered, contiguous and within audio.")
        selected = [u for u in units if u.scene_id == scene.id]
        if not selected or scene.beat_ids != [u.beat_id for u in selected] or selected[0].start_ms != scene.start_ms or selected[-1].end_ms != scene.end_ms:
            raise ValueError("Scene intervals must match their measured beats.")
        cited = {(u.evidence.source_id, tuple(u.evidence.segment_ids)) for u in selected}
        if len(scene.summary) < 5 or {(r.source_id, tuple(r.segment_ids)) for r in scene.evidence_references} != cited:
            raise ValueError("Storyboard scenes need a summary and evidence from their beats.")
        for action in scene.actions:
            unit = beat_map.get(action.beat_id)
            if unit is None or unit.scene_id != scene.id or action.at_ms != unit.start_ms:
                raise ValueError("Every action must resolve to its applicable beat boundary.")
        if any(not 1 <= sum(a.beat_id == u.beat_id for a in scene.actions) <= 8 for u in selected):
            raise ValueError("Every beat must have 1 to 8 explicit visual operations.")
        covered.extend(scene.beat_ids)
        cursor = scene.end_ms
    if cursor != duration or covered != [u.beat_id for u in units]:
        raise ValueError("Scenes must cover the entire ordered narration.")


def compile_storyboard(draft, duration):
    # Revalidate even when a caller has mutated a Pydantic object in-place.
    validate_storyboard(draft)
    validate_boundaries(draft.narration_units, duration)
    scenes = []
    for authored in draft.scenes:
        beats = [b for b in draft.narration_units if b.scene_id == authored.id]
        refs = list({(b.evidence.source_id, tuple(b.evidence.segment_ids)): b.evidence for b in beats}.values())
        scenes.append(Scene(**authored.model_dump(), start_ms=beats[0].start_ms, end_ms=beats[-1].end_ms,
            beat_ids=[b.beat_id for b in beats], evidence_references=refs,
            actions=[SceneAction(kind=KINDS[op.kind], target=op.target, at_ms=beat.start_ms,
                       to_slot=op.to_slot, state_id=op.state_id, beat_id=beat.beat_id)
                     for beat in beats for op in beat.operations]))
    # Playback stores evidence/bindings, not the authoring operation lists.
    units = [NarrationUnit.model_validate(b.model_dump(exclude={"operations"})) for b in draft.narration_units]
    validate_timeline(scenes, units, duration)
    return scenes, units
