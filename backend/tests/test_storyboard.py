"""Deterministic storyboard and measured-timeline checks, no live providers."""
import copy
import json
import sys
import threading
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts import ModelStoryboard, Short, StoryboardDraft, TranscriptSegment
from app.errors import AppError
from app.providers import Speech
from app.storyboard import compile_storyboard, validate_timeline
from app.validation import attach_evidence, refine_cues, validate_draft
from test_core import StubModel, StubSpeech, StubYouTube, request_for, wait_for
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from export_storyboard_fixture import fixture_short


def fixture():
    body = json.loads((ROOT / "fixtures/storyboard-lookup.json").read_text())
    segments = [TranscriptSegment.model_validate(s) for s in body["segments"]]
    draft = attach_evidence(ModelStoryboard.model_validate(body["draft"]), segments)
    for beat, bounds in zip(draft.narration_units, body["boundaries"], strict=True):
        beat.start_ms, beat.end_ms = bounds
    return draft, segments, body["duration_ms"]


def test_compiler_matches_committed_browser_fixture_and_absolute_boundaries():
    short = fixture_short()
    assert short.model_dump() == json.loads((ROOT / "fixtures/storyboard-lookup-playback.json").read_text())
    assert [(s.start_ms, s.end_ms) for s in short.scenes] == [(0, 14000), (14000, 30000)]
    assert [a.at_ms for a in short.scenes[1].actions] == [14000] * 4 + [22000] * 2
    assert [u.beat_id for u in short.narration_units] == [f"beat_{i}" for i in range(4)]
    assert all(s.evidence_references and s.kind == "diagram" for s in short.scenes)
    Short.model_validate_json(short.model_dump_json())


@pytest.mark.parametrize("change", [
    lambda d: d["narration_units"][1].update(beat_id="beat_0"),
    lambda d: d["narration_units"][1].update(scene_id="missing"),
    lambda d: d["narration_units"][3].update(scene_id="scene_0"),
    lambda d: d["scenes"][1].update(id="scene_0"),
    lambda d: d["narration_units"][0]["operations"][0].update(target="missing"),
    lambda d: d["narration_units"][0]["operations"][0].update(kind="execute"),
    lambda d: d["narration_units"][0]["operations"][0].update(kind="focus"),
    lambda d: d["narration_units"][1]["operations"][0].update(state_id="missing"),
    lambda d: d["scenes"][0]["states"][0].update(target="node_0"),
    lambda d: d["narration_units"][2]["operations"].reverse(),
    lambda d: d["narration_units"][0]["operations"][0].update(to_slot=3),
    lambda d: d["narration_units"][1]["operations"][0].update(kind="move",state_id=None,to_slot=0),
])
def test_reject_invalid_semantics_before_speech(change):
    draft, _, _ = fixture()
    body = draft.model_dump()
    change(body)
    with pytest.raises((ValidationError, ValueError)):
        StoryboardDraft.model_validate(body)


@pytest.mark.parametrize("change", [
    lambda s: s.update(measured_duration_ms=40001),
    lambda s: s.update(measured_duration_ms=999),
    lambda s: s["scenes"][1].update(start_ms=13999),
    lambda s: s["scenes"][1].update(start_ms=14001),
    lambda s: s["scenes"].reverse(),
    lambda s: s["scenes"][0].update(end_ms=0),
    lambda s: s["scenes"][1]["actions"][0].update(at_ms=0),
    lambda s: s["scenes"][1]["actions"][-1].update(at_ms=30000),
    lambda s: s["scenes"][1]["actions"][0].update(beat_id="missing"),
    lambda s: s["scenes"][1]["actions"][0].update(target="missing"),
    lambda s: s["scenes"][1]["actions"].reverse(),
    lambda s: s["narration_units"][1].update(start_ms=5999),
    lambda s: s["narration_units"][1].update(end_ms=6000),
    lambda s: s["scenes"][0].update(beat_ids=["beat_1"]),
    lambda s: s["scenes"][0]["actions"][0].update(kind="highlight"),
    lambda s: s.update(scenes=[]),
    lambda s: s['scenes'][0].update(summary=''),
    lambda s: s['scenes'][0].update(evidence_references=[]),
    lambda s: s['narration_units'][0].update(purpose=None),
])
def test_ready_format_rejects_corrupt_timelines(change):
    body = fixture_short().model_dump()
    change(body)
    with pytest.raises((ValidationError, ValueError)):
        Short.model_validate(body)


def test_explicit_targeting_is_not_overridden_by_negative_mentions():
    draft, segments, _ = fixture()
    draft.narration_units[1].text = "Without a useful index, a scan tests rows until it finds matching data in the table."
    before = copy.deepcopy(draft.narration_units[1].operations)
    refine_cues(draft)
    assert draft.narration_units[1].operations == before
    assert [op.target for op in before if op.kind == "focus"] == ["node_1"]
    validate_draft(draft, segments, False)


def test_very_short_beat_stays_contiguous_and_actions_do_not_get_staggered():
    draft, _, _ = fixture()
    for beat, bounds in zip(draft.narration_units, [(0,1),(1,2),(2,3),(3,1000)], strict=True):
        beat.start_ms, beat.end_ms = bounds
    scenes, units = compile_storyboard(draft, 1000)
    validate_timeline(scenes, units, 1000)
    assert scenes[1].start_ms == 2
    assert all(a.at_ms in {2,3} for a in scenes[1].actions)


def test_duration_repair_reviews_new_script_and_uses_new_measurements(tmp_path):
    class RepairSpeech(StubSpeech):
        calls = 0
        def synthesize(self, units, key, cancel):
            self.calls += 1
            if self.calls == 1:
                units[0].end_ms = 41000  # Old failed attempt must not survive repair.
                raise AppError("SPEECH_DURATION", "Too long")
            audio, _, cached = super().synthesize(units, key, cancel)
            for i, unit in enumerate(units):
                unit.start_ms, unit.end_ms = i * 700, (i + 1) * 700
            return audio, len(units) * 700, cached
    class ReviewedModel(StubModel):
        reviews = []
        def generate(self, contract, task, cancel, validate=None):
            from app.validation import SupportCheck
            if contract is SupportCheck:
                self.reviews.append(task["draft"])
            return super().generate(contract, task, cancel, validate)
    settings = Settings(data=tmp_path)
    model, speech = ReviewedModel(), RepairSpeech(settings)
    with TestClient(create_app(settings, model, speech, StubYouTube())) as client:
        lid = client.post('/api/lessons', json=request_for(None)).json()['id']
        lesson = wait_for(client, lid)
        short = Short.model_validate(lesson['shorts'][0])
        assert short.measured_duration_ms == 1400
        assert short.scenes[0].end_ms == 1400
        assert {a.at_ms for a in short.scenes[0].actions} == {0,700}
        assert model.reviews[0]['narration_units'][0]['text'] != model.reviews[1]['narration_units'][0]['text']
        assert all(u.evidence.quote for u in short.narration_units)
        assert short.storyboard_version == 2


def test_old_audio_cache_metadata_is_readable_and_corrupt_boundaries_are_regenerated(tmp_path):
    import numpy as np
    import soundfile as sf
    settings = Settings(data=tmp_path)
    speech = Speech(settings)
    draft, _, _ = fixture()
    sf.write(settings.data / 'audio/old.wav', np.zeros(24000*30), 24000)
    metadata = {'texts':[u.text for u in draft.narration_units], 'boundaries':[[u.start_ms,u.end_ms] for u in draft.narration_units], 'duration_ms':30000}
    path = settings.data / 'cache/old.json'
    path.write_text(json.dumps(metadata))
    assert speech.synthesize(draft.narration_units, 'old', threading.Event()) == ('old.wav',30000,True)
    metadata['boundaries'][1][0] = 999
    path.write_text(json.dumps(metadata))
    speech.prepare = lambda: (_ for _ in ()).throw(AppError('TEST_REGENERATE', 'Broken cache was rejected'))
    with pytest.raises(AppError, match='Broken cache'):
        speech.synthesize(draft.narration_units, 'old', threading.Event())


def test_invalid_measurement_fails_before_ready_publication(tmp_path):
    class BrokenSpeech(StubSpeech):
        def synthesize(self, units, key, cancel):
            result = super().synthesize(units, key, cancel)
            units[1].start_ms = 1001  # A one-millisecond gap is not a hold state.
            return result
    settings = Settings(data=tmp_path)
    with TestClient(create_app(settings, StubModel(), BrokenSpeech(settings), StubYouTube())) as client:
        lid = client.post('/api/lessons', json=request_for(None)).json()['id']
        lesson = wait_for(client, lid, 'failed')
        assert lesson['job']['error']['code'] == 'STORYBOARD_TIMELINE_INVALID'
        assert all(short['status'] != 'ready' for short in lesson['shorts'])
        assert lesson['shorts'][0]['audio_path'] is None


def test_legacy_saved_scene_defaults_need_no_regeneration():
    from test_core import draft_for, source
    draft = draft_for(source().segments)
    body = {'id':'saved','objective':draft.objective,'status':'ready','audio_path':'old.wav',
        'measured_duration_ms':2000,'narration_units':[
            {'text':u.text,'evidence':u.evidence.model_dump(),'start_ms':i*1000,'end_ms':(i+1)*1000}
            for i,u in enumerate(draft.narration_units)],
        'scenes':[{'template':draft.template,'nodes':[n.model_dump(exclude={'icon','role'}) for n in draft.nodes],
                   'connections':[e.model_dump() for e in draft.connections],
                   'actions':[{'kind':a.kind,'target':a.target,'at_ms':a.unit*1000} for a in draft.actions],
                   'start_ms':0,'end_ms':2000}]}
    saved = Short.model_validate(body)
    assert saved.storyboard_version == 1 and saved.scenes[0].id is None
    assert saved.scenes[0].nodes[0].icon is None
    assert saved.audio_path == 'old.wav'


def test_storyboard_compilation_performance():
    draft, _, duration = fixture()
    start = time.perf_counter()
    for _ in range(200):
        compile_storyboard(draft, duration)
    milliseconds = (time.perf_counter()-start) * 1000 / 200
    print(f'Fixture compiler mean: {milliseconds:.3f} ms (200 warm iterations)')
    # No flaky speed assertion; measured cost is reported, not a live latency claim.
