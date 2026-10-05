"""Task-specific authoring guidance, never output normalization or fabrication.

Plan shapes and IDs below are syntax examples, not lesson content. Repair inventories come only
from schema/Pydantic-valid model payloads and do not add targets or claims.
"""
import json


def authoring_rules(contract_name, task):
    if contract_name == "LessonPlan" and task.get("plan_version") in {2, 3}:
        revision = task.get("revision", 0)
        # The revision is app-supplied metadata, not learner/source instructions.
        revision = revision if type(revision) is int and 0 <= revision <= 1000 else 0
        return (
            f"Authoring rules for LessonPlan: use short new concept_id values such as c{revision}_0, c{revision}_1; "
            "IDs are at most 20 characters. dependency_ids reference only earlier concepts, never an outcome sentence. "
            "Use an observable learning_outcome starting with Explain, Trace, Compare, Predict or Apply. "
            "ExampleRecord.facts are VERBATIM quotations copied exactly from the supplied passages, including case and punctuation; "
            "they are NOT paraphrases, narration or explanations. entities must occur in those same passages. "
            "If no recurring example is needed, return examples=[] and example_id=null on each objective. "
            "Never create an example record just because a diagram/table/chart could illustrate an outcome. "
            "Use missing_coverage=[] unless a specific supported-goal facet needs more evidence. "
            "prerequisites is an array of short knowledge concepts: use [] for none, NEVER [\"[]\"] or a dependency sentence. "
            "Write learner-facing text in the requested language (English for language=en). "
            "Count media targets plus 20000 milliseconds per checkpoint against the supplied budget. "
            "Write the top-level fields in this order: sufficient_evidence, reason, missing_coverage, examples, objectives. "
            "examples is a sibling of objectives, never inside an objective or outside the root object. "
            "The final objective closes with }, the objectives array with ], and the root with }; then STOP. "
            "Use this valid JSON as a FORMAT-ONLY example, not as teaching content. Replace every uppercase placeholder "
            "with your own source-supported text or a supplied evidence ID, and choose appropriate roles, templates, "
            "durations and dependencies. Add only the requested number of objectives inside the same array: "
            + json.dumps({
                "sufficient_evidence": True, "reason": "BRIEF COVERAGE REASON",
                "missing_coverage": [], "examples": [], "objectives": [{
                    "concept_id": f"c{revision}_0", "learning_outcome": "Explain A SOURCE-SUPPORTED OUTCOME",
                    "teaching_role": "foundation", "dependency_ids": [],
                    "relevance": "WHY THIS OUTCOME HELPS THE LEARNER", "evidence_segment_ids": ["SUPPLIED_SEGMENT_ID"],
                    "curriculum_role": "extension" if task.get("phase") == "extension" else "core",
                    "target_duration_ms": 40000 if task.get("plan_version") == 2 else 15000,
                    "example_id": None, "visual_intent": "WHAT THE VISUAL WILL DEMONSTRATE",
                    "checkpoint": False, "title": "SHORT LEARNER GOAL", "template": "key_fact", "prerequisites": [],
                }],
            }, separators=(",", ":"))
        )
    if contract_name == "ModelStoryboard":
        return (
            "Authoring rules for ModelStoryboard: scenes own their targets; beat.scene_id chooses WHICH scene its operations affect. "
            "A diagram uses node IDs for reveal/hide/focus/move/change_state and connection IDs ONLY for connect. "
            "Connection endpoints source/target belong inside scenes[].connections[], NEVER inside a beat operation. "
            "For every declared connection, reveal both endpoint nodes then explicitly connect its conn ID. "
            'Example syntax: {"kind":"connect","target":"conn_0"}. '
            "A table beat reveals its payload row IDs, not node IDs; cells support focus only after their row is revealed. "
            'Example syntax: [{"kind":"reveal","target":"row_0"},{"kind":"reveal","target":"row_1"}]. '
            "A chart beat reveals its payload point IDs, not node IDs or row IDs. "
            'Example syntax: [{"kind":"reveal","target":"point_0"},{"kind":"reveal","target":"point_1"}]. '
            "A code beat uses line_1, line_2 etc; image uses image and authored annotation IDs. "
            "These are syntax examples, not an instruction to add nonexistent items. Reveal EVERY primary item actually in that scene. "
            "Only diagram scenes have template/nodes/connections/states. Other scenes have kind/id/summary/payload. "
            "Use only source-supported terms and qualifiers; do not upgrade 'a key maps to a row' into a uniqueness guarantee."
        )
    return ""


def storyboard_repair_inventory(result):
    """A bounded all-scene inventory so a repair doesn't fix only the first error."""
    from ..visuals import targets, primary_targets
    rows = []
    for scene in result.scenes:
        beats = [b for b in result.narration_units if b.scene_id == scene.id]
        if scene.kind == "diagram":
            reveal = [n.id for n in scene.nodes]
            connect = [c.id for c in scene.connections]
            allowed = reveal + connect
        else:
            reveal = sorted(primary_targets(scene))
            connect = []
            allowed = sorted(targets(scene))
        rows.append({"scene_id": scene.id, "kind": scene.kind,
                     "beat_ids": [b.beat_id for b in beats], "payload_targets": allowed,
                     "must_reveal": reveal, "must_connect_after_endpoint_reveals": connect})
    return ("Repair ALL scenes, not just the first reported error. This inventory describes YOUR previous payload; "
            "operations must use the targets of their own scene. If you change a scene's payload, update its beats consistently. "
            "Do not add claims or evidence. Previous scene inventory: "
            + json.dumps(rows, separators=(",", ":")))[:3500]
