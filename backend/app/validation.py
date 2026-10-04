import re
import hashlib
from .contracts import EvidenceRef, ShortDraft, Contract
from .icons import ICONS
from pydantic import Field

# Narration is spoken without the source video. These phrases point at context the learner cannot see.
DANGLING = [
    (re.compile(r"\b(this|that|my|our|today's) (video|channel)\b|\bin the video\b", re.I), "a video or channel"),
    (re.compile(r"\bstep (number )?(one|two|three|four|five|six|\d+)\b", re.I), "a numbered step from a video"),
    (re.compile(r"\b(that's|that is|this is) the (first|second|third|next|last) step\b", re.I), "a step from a video"),
    (re.compile(r"\bas (i|we|you) (said|mentioned|saw)\b|\bas mentioned\b|\bbefore we\b", re.I), "something said earlier"),
    (re.compile(r"\b(guys|subscribe|smash that|like button)\b", re.I), "presenter filler"),
    (re.compile(r"\b(I|I'm|I've|I'll|I'd)\b"), "the presenter as 'I'"),
    # Case-sensitive so "US" is not read as "us".
    (re.compile(r"\b([Ww]e|[Ww]e're|[Ww]e've|[Ww]e'll|[Oo]ur|us)\b"), "'we' or 'our'"),
]
CYCLE_MIN, KEY_FACT_MIN = 3, 2


def word_set(text):
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def similar(a, b, threshold=.7):
    x, y = word_set(a), word_set(b)
    return bool(x and y) and len(x & y) / len(x | y) >= threshold


def check_narration(texts, earlier=()):
    for text in texts:
        for pattern, what in DANGLING:
            match = pattern.search(text)
            if match:
                raise ValueError(f"Narration '{match.group(0)}' refers to {what}. Rewrite it as a teacher speaking to 'you' with no reference to a video.")
    for i, text in enumerate(texts):
        if any(similar(text, other) for other in list(texts[:i]) + list(earlier)):
            raise ValueError("Narration repeats an earlier point. Teach something new for this objective.")

class SupportCheck(Contract):
    supported: bool
    reason: str = Field(max_length=500)


def validate_evidence(ref: EvidenceRef, segments):
    known = {s.id: s for s in segments}
    if any(sid not in known or known[sid].source_id != ref.source_id for sid in ref.segment_ids):
        raise ValueError("Evidence must use retrieved segment IDs and their source ID.")
    selected = [known[sid] for sid in ref.segment_ids]
    # Exact quotations stop invented supporting passages. This is a provenance check, not a proof of truth.
    if not any(ref.quote in s.text for s in selected):
        raise ValueError("Evidence quote must appear exactly in a referenced segment.")
    if ref.start_ms is not None or ref.end_ms is not None:
        if ref.start_ms is None or ref.end_ms is None or ref.end_ms <= ref.start_ms:
            raise ValueError("Evidence time range is invalid.")
        if any(s.start_ms is None for s in selected):
            raise ValueError("Untimed text cannot have a timestamp.")
        if not any(s.start_ms <= ref.start_ms < ref.end_ms <= s.end_ms for s in selected):
            raise ValueError("Evidence times must fall within a supplied segment.")
    elif all(s.start_ms is not None for s in selected):
        ref.start_ms = min(s.start_ms for s in selected)
        ref.end_ms = max(s.end_ms for s in selected)


def validate_diagram(draft: ShortDraft):
    for node in draft.nodes:
        if node.icon not in ICONS:
            raise ValueError(f"Node {node.id} needs an icon from the allowed list.")
        if len(node.detail.split()) < 2:
            raise ValueError(f"Node {node.id} needs a detail line of 3 to 8 words that explains it.")
    roles = {node.role for node in draft.nodes}
    if draft.template == "dos_donts" and not {"good", "bad"} <= roles:
        raise ValueError("A dos_donts diagram needs at least one node with role good and one with role bad.")
    if draft.template == "cycle" and len(draft.nodes) < CYCLE_MIN:
        raise ValueError("A cycle diagram needs 3 or 4 nodes.")
    if draft.template == "key_fact" and len(draft.nodes) < KEY_FACT_MIN:
        raise ValueError("A key_fact diagram needs the main fact in node_0 plus 1 to 3 supporting nodes.")


def validate_draft(draft: ShortDraft, segments, require_question: bool, earlier=()):
    for unit in draft.narration_units:
        validate_evidence(unit.evidence, segments)
    check_narration([unit.text for unit in draft.narration_units], earlier)
    validate_diagram(draft)
    if require_question and draft.question is None:
        raise ValueError("This short must include a question.")
    if not require_question and draft.question is not None:
        raise ValueError("No question is planned for this short.")
    if draft.question:
        validate_evidence(draft.question.evidence, segments)
    # Charts use supplied numeric values only; reject invented measurements.
    values={float(value) for s in segments for value in re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])",s.text)}
    if draft.template == "chart" and any(node.value is None for node in draft.nodes):
        raise ValueError("A chart requires source numeric values for every bar.")
    for node in draft.nodes:
        if draft.template != "chart":
            node.value = None
        elif node.value is not None and node.value not in values:
            raise ValueError("A chart value must match an actual source number.")


def planned_duration(shorts):
    return sum((s.measured_duration_ms if s.status == "ready" else 40000) + (20000 if (s.question is not None or s.question_required) else 0) for i, s in enumerate(shorts))


def verify_support(model, draft, segments, cancel):
    result = model.generate(SupportCheck, {"task": "Review this short against the supplied passages. The narration is a teacher's paraphrase; rewording and simplifying are fine. "
        "Reject only when a narration unit, diagram detail, or question answer states something the passages contradict or do not teach at all, "
        "turns a conditional claim into a guarantee, or when a question has more than one correct choice. Give the specific problem as the reason. "
        "This is a model review, not independent fact verification.", "draft": draft.model_dump(), "segments": [s.model_dump() for s in segments]}, cancel)
    if not result.supported:
        raise ValueError("The model source review rejected this short: " + result.reason)


def attach_evidence(content, segments):
    from .contracts import ShortDraft, EvidenceRef
    by_id = {s.id:s for s in segments}
    def reference(segment_id):
        if segment_id not in by_id:
            raise ValueError("Select an existing evidence segment ID.")
        segment = by_id[segment_id]
        return EvidenceRef(source_id=segment.source_id, segment_ids=[segment.id], quote=segment.text,
                           start_ms=segment.start_ms, end_ms=segment.end_ms).model_dump()
    body=content.model_dump()
    # Template cues are compiled from validated diagram references. The model
    # chooses relationships; it does not need to invent animation target IDs.
    actions=[{"kind":"appear","target":n["id"],"unit":0} for n in body["nodes"]]
    actions.append({"kind":"highlight","target":body["nodes"][0]["id"],"unit":0})
    actions.extend({"kind":"draw","target":e["id"],"unit":min(i,1)} for i,e in enumerate(body["connections"]))
    actions.append({"kind":"highlight","target":body["nodes"][-1]["id"],"unit":1})
    body["actions"]=sorted(actions,key=lambda a:a["unit"])
    for unit in body["narration_units"]:
        unit["evidence"]=reference(unit.pop("segment_id"))
    if body["question"]:
        question=body["question"]
        question["evidence"]=reference(question.pop("segment_id"))
        answer=question.pop("correct_answer")
        options=question.pop("distractors")
        index=int(hashlib.sha256(question["prompt"].encode()).hexdigest()[:8],16) % (len(options)+1)
        options.insert(index,answer)
        if len({o.strip().lower() for o in options})!=len(options):
            raise ValueError("Question choices must be distinct.")
        question["options"],question["answer_index"]=options,index
    result=ShortDraft.model_validate(body)
    refine_cues(result)
    return result


def normalize(text):
    return re.sub(r"\s+", " ", text).strip()


def terms(text):
    stop={"the","a","an","on","to","of","in","and","with","for"}
    return {word.rstrip("s") for word in re.findall(r"[a-z0-9]+",text.lower()) if word not in stop}


def refine_cues(draft):
    from .contracts import DraftAction
    actions=[DraftAction(kind="appear",target=node.id,unit=0) for node in draft.nodes]
    for i,unit in enumerate(draft.narration_units):
        words=terms(unit.text)
        # A label in the supporting passage can name a concept omitted from the excerpt.
        # For example, a scan explanation can mention an index only to say it is absent.
        target=max(draft.nodes,key=lambda node:len(words & terms(node.label+" "+node.detail))
                   + 2 * int(normalize(node.label).casefold() in normalize(unit.evidence.quote).casefold()))
        actions.append(DraftAction(kind="highlight",target=target.id,unit=i))
    actions.extend(DraftAction(kind="draw",target=edge.id,unit=min(i,1)) for i,edge in enumerate(draft.connections))
    draft.actions=sorted(actions,key=lambda action:action.unit)


def diagram_evidence(draft,segments):
    refs=[]
    for node in draft.nodes:
        words=terms(node.label+" "+node.detail)
        segment=max(segments,key=lambda s:len(words & terms(s.text)))
        if words & terms(segment.text):
            refs.append(EvidenceRef(source_id=segment.source_id,segment_ids=[segment.id],quote=segment.text,start_ms=segment.start_ms,end_ms=segment.end_ms))
    return refs
