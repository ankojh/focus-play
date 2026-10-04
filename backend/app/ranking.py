"""Rank candidate videos by their transcripts. The model scores; this code selects."""
from .contracts import CandidateRanking

KEEP = 3
PER_CHANNEL = 2
MIN_RELEVANCE = 3
MIN_LEVEL_FIT = 2
WEIGHTS = {"relevance": .3, "level_fit": .3, "teaching": .2, "density": .15, "captions": .05}


def excerpt(source, opening=900, middle=500):
    text = " ".join(s.text for s in source.segments)
    if len(text) <= opening + middle:
        return text
    centre = len(text) // 2
    return text[:opening] + " … " + text[centre:centre + middle]


def ranking_task(request, fetched, focus=None):
    return {"task": "Score every candidate YouTube video from 1 to 5 for this learner. "
            "relevance: the transcript teaches the goal. level_fit: it suits the learner's current knowledge without skipping needed steps or repeating known basics. "
            "teaching: it explains step by step rather than chatting, selling, or giving opinions. "
            "density: most of the transcript is on topic, not intros or sponsor reads. captions: the transcript text is clean and readable. "
            "Judge only the supplied transcript excerpts. Titles can mislead. Give a short reason. Score each video_id exactly once.",
            "goal": focus or request.goal, "prior_knowledge": request.prior_knowledge,
            "candidates": [{"video_id": c["video_id"], "title": c["title"], "channel": c["channel"],
                            "duration_seconds": c.get("duration_seconds"), "transcript_excerpt": excerpt(s)} for c, s in fetched]}


def validator(fetched):
    ids = sorted(c["video_id"] for c, _ in fetched)
    def check(ranking: CandidateRanking):
        if sorted(s.video_id for s in ranking.scores) != ids:
            raise ValueError("Score every supplied video_id exactly once.")
    return check


def pick(ranking, fetched):
    by_id = {c["video_id"]: (c, s) for c, s in fetched}
    scored = sorted(ranking.scores, key=lambda r: -sum(getattr(r, k) * w for k, w in WEIGHTS.items()))
    chosen, channels = [], {}
    for score in scored:
        candidate, source = by_id[score.video_id]
        if (score.relevance < MIN_RELEVANCE or score.level_fit < MIN_LEVEL_FIT
                or channels.get(candidate["channel"], 0) >= PER_CHANNEL):
            continue
        channels[candidate["channel"]] = channels.get(candidate["channel"], 0) + 1
        chosen.append(source)
        if len(chosen) == KEEP:
            break
    return chosen
