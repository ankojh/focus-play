import json
import threading

import pytest

from app.contracts import LessonPlan
from app.llm.json_guard import JSONKeyGuard
from app.providers import strict_json_object
from test_providers import scripted_model, chunk, PLAN


@pytest.mark.parametrize('body', [
    {'text': 'Braces { } [ ], commas, and "quoted" words', 'nested': [{'id': 'one'}, {'id': 'two'}]},
    {'outer': {'id': 'x'}, 'other': {'id': 'y'}, 'id': 'outer'},
    {'a"b': 'escaped " value', 'backslash\\': '\\', 'unicode': 'café 🐦'},
])
def test_guard_accepts_fragmented_valid_objects_without_changing_them(body):
    raw = json.dumps(body, ensure_ascii=False)
    for width in range(1, len(raw) + 1):
        guard = JSONKeyGuard()
        for start in range(0, len(raw), width): guard.feed(raw[start:start+width])
    assert strict_json_object(raw) == body


@pytest.mark.parametrize('raw', ['{"x":1,"x":2}', '{"a":{"x":1,"x":2}}', '{"a\\u0062":1,"ab":2}'])
def test_duplicate_keys_are_detected_across_chunks_before_json_completion(raw):
    guard = JSONKeyGuard()
    with pytest.raises(ValueError, match='repeats the JSON field'):
        for char in raw: guard.feed(char)


def test_large_object_loop_aborts_without_consuming_marker_or_feeding_loop_back(scripted_model):
    model, streams, calls, consumed = scripted_model
    long_reason = ' '.join(f'Supported evidence item {i} describes a distinct detail.' for i in range(10))
    # The repeating blocks are longer than the old regex's 80-char pattern window.
    prefix = json.dumps({**PLAN, 'reason': long_reason})[:-1]
    never_read = chunk('THIS MUST NOT BE CONSUMED', done=True)
    streams.extend([[chunk(prefix, done=False), chunk(',"sufficient_evidence":', done=False), never_read], [chunk(json.dumps(PLAN))]])
    model.generate(LessonPlan, {}, threading.Event())
    assert never_read not in consumed
    assert len(calls) == 2
    assert [m['role'] for m in calls[1]['messages']] == ['system', 'user', 'user']
    assert 'Return each field exactly once' in calls[1]['messages'][-1]['content']


@pytest.mark.parametrize('raw, message', [
    ('{"objectives":[{"title":"Supported idea"}]}],"examples":[]}', 'Extra data'),
    ('{"objectives":[{"title":"Supported idea"}}', 'expected ]'),
    ('{"objectives":[{"title":"Supported idea"]', 'expected }'),
    ('{"x":1}{"x":2}', 'Extra data'),
    ('{"x":1} commentary', 'Extra data'),
    ('[]', 'exactly one JSON object'),
    ('```json', 'Markdown fences'),
])
def test_broken_container_boundaries_rejected_at_every_chunk_width(raw, message):
    for width in range(1, len(raw) + 1):
        guard = JSONKeyGuard()
        with pytest.raises(ValueError) as error:
            for start in range(0, len(raw), width):
                guard.feed(raw[start:start + width])
        assert message in str(error.value)


def test_completed_root_allows_only_json_whitespace_and_braces_in_strings():
    raw = ' {"text":"} ], \\\"quoted\\\"","empty":[],"nested":{"empty":{}}} \r\n\t'
    guard = JSONKeyGuard()
    for char in raw:
        guard.feed(char)
    assert guard.finished
    assert strict_json_object(raw)['empty'] == []


def test_incomplete_object_is_not_completed_or_repaired_by_guard():
    raw = '{"objectives":['
    guard = JSONKeyGuard()
    guard.feed(raw)
    assert not guard.finished
    with pytest.raises(ValueError):
        strict_json_object(raw)


def test_premature_plan_closure_retries_cleanly_without_accepting_valid_prefix(scripted_model):
    model, streams, calls, consumed = scripted_model
    # Reproduces the production failure: a complete root followed by an extra
    # array close and a required sibling field outside that root.
    prefix = json.dumps(PLAN)
    never_read = chunk('THIS MUST NOT BE CONSUMED')
    streams.extend([
        [chunk(prefix, done=False), chunk('],"examples":[]}', done=False), never_read],
        [chunk(json.dumps(PLAN))],
    ])
    checked = []
    result = model.generate(LessonPlan, {}, threading.Event(), checked.append)
    assert result.sufficient_evidence and len(checked) == 1
    assert never_read not in consumed
    assert len(calls) == 2
    assert calls[1]['messages'][:2] == calls[0]['messages']
    assert [m['role'] for m in calls[1]['messages']] == ['system', 'user', 'user']
    feedback = calls[1]['messages'][-1]['content']
    assert 'root was closed too early' in feedback
    assert 'ALL top-level fields inside ONE' in feedback


def test_repeated_trailing_content_still_fails_after_three_attempts(scripted_model):
    from app.errors import AppError
    model, streams, calls, _ = scripted_model
    streams.extend([[chunk(json.dumps(PLAN) + '],"examples":[]}')]] * 3)
    checked = []
    with pytest.raises(AppError) as error:
        model.generate(LessonPlan, {}, threading.Event(), checked.append)
    assert error.value.code == 'MODEL_OUTPUT_INVALID'
    assert len(calls) == 3 and checked == []
