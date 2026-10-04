import re
import hashlib
from .contracts import EvidenceRef, ShortDraft, Contract
from pydantic import Field

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


def validate_draft(draft: ShortDraft, segments, require_question: bool):
    for unit in draft.narration_units:
        validate_evidence(unit.evidence, segments)
        if normalize(unit.text) not in normalize(unit.evidence.quote):
            raise ValueError("Narration must be an exact continuous excerpt from its selected source segment. Do not paraphrase.")
    if require_question and draft.question is None:
        raise ValueError("This short must include a question.")
    if not require_question and draft.question is not None:
        raise ValueError("No question is planned for this short.")
    if draft.question:
        validate_evidence(draft.question.evidence, segments)
        if normalize(draft.question.options[draft.question.answer_index]) not in normalize(draft.question.evidence.quote) or normalize(draft.question.explanation) not in normalize(draft.question.evidence.quote):
            raise ValueError("The correct answer and explanation must use exact source text.")
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
    result = model.generate(SupportCheck, {"task": "Check every factual narration unit, diagram label/detail, and question answer against its quoted evidence. Reject unsupported details, disagreement mixed together, or unseen visual context. Reject a claim about fewer disk reads or a measured speed increase unless the source supplies that evidence. Do not replace a conditional claim with a guarantee. Reject a question with an unsupported premise or more than one correct choice. This is a model review, not independent fact verification.", "draft": draft.model_dump(), "segments": [s.model_dump() for s in segments]}, cancel)
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
        question["options"],question["answer_index"],question["explanation"]=options,index,answer
    result=ShortDraft.model_validate(body)
    refine_cues(result)
    return result


def normalize(text):
    return re.sub(r"\s+", " ", text).strip()


def source_excerpts(segments, max_length=300):
    excerpts=[]
    for segment in segments:
        sentences=re.split(r"(?<=[.!?])\s+", segment.text)
        for i in range(len(sentences)):
            for count in (1,2):
                excerpt=" ".join(sentences[i:i+count]).strip()
                if 10<=len(excerpt)<=max_length and normalize(excerpt) in normalize(segment.text):
                    excerpts.append(excerpt)
    return list(dict.fromkeys(excerpts))


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
