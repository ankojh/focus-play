import json
import threading

import pytest

from app.contracts import LessonPlan, ModelStoryboard, TranscriptSegment
from app.errors import AppError
from app.icons import ICONS
from app.llm.compact import request, PlanText, DiagramText, ChartText
from app.storyboard import compile_storyboard
from app.teaching import validate_plan
from app.validation import attach_evidence, validate_draft, SupportCheck
from test_providers import scripted_model, chunk


SEGMENTS = [TranscriptSegment(id='seg_0', source_id='src_0', text=(
    'An index maps keys to rows. A lookup starts at the key, locates its entry, then follows a pointer to the row. '
    'Scanning checks rows in order. Values for A and B are -12 and 1500 units.'))]
PASSAGES = [s.model_dump() for s in SEGMENTS]


def plan_task(**updates):
    return {'compact_authoring': True, 'plan_version': 3, 'remaining_ms': 120000,
            'max_target_ms': 40000, 'max_objectives': 4, 'revision': 2, 'phase': 'core',
            'request': {'goal': 'Explain indexes', 'prior_knowledge': 'beginner'},
            'segments': PASSAGES, **updates}


def plan_body():
    return {'supported': True, 'reason': 'The passage teaches lookups.', 'items': [
        {'title': 'Find a row by its key', 'outcome': 'Explain how an index maps a key to a row.',
         'role': 'mechanism', 'template': 'process', 'source': 0, 'depends_on_outcomes': [], 'checkpoint': False}],
            'more_sources_query': ''}


def story_task(template='process', **updates):
    return {'compact_authoring': True, 'objective': 'Explain key-to-row lookup', 'template': template,
            'question_required': False, 'segments': PASSAGES, 'target_words': 60, 'learner': 'beginner', **updates}


def story_body():
    return {'beats': [
        {'text': 'An index maps keys to rows, allowing you to start a lookup from the key you want to find.',
         'source': 0, 'label': 'Search key', 'detail': 'Start from the wanted key', 'role': 'start', 'icon': 'search'},
        {'text': 'Locate the matching entry in the index. Its pointer identifies the row associated with that particular key.',
         'source': 0, 'label': 'Matching entry', 'detail': 'Locate the matching index entry', 'role': 'step', 'icon': 'layers'},
        {'text': 'Follow the pointer to reach the row. By contrast, a scan checks the rows in their order.',
         'source': 0, 'label': 'Matching row', 'detail': 'Follow the pointer to the row', 'role': 'result', 'icon': 'target'},
    ], 'question': None}


def test_compact_plan_expands_without_fabricating_claims_or_ids():
    spec = request(LessonPlan, plan_task())
    result = spec.expand(PlanText.model_validate(plan_body()))
    validate_plan(result, SEGMENTS, 4, 120000, calibrated=True)
    obj = result.objectives[0]
    assert obj.concept_id == 'c2_0' and obj.template == 'process'
    assert obj.evidence_segment_ids == ['seg_0']
    assert obj.learning_outcome == plan_body()['items'][0]['outcome']
    assert obj.target_duration_ms == 30000 and result.examples == []


def test_compact_plan_maximum_length_text_fits_compiled_contract():
    body = plan_body()
    body['items'][0]['outcome'] = 'Explain ' + 'a' * 172
    body['items'][0]['title'] = 'A' * 100
    result = request(LessonPlan, plan_task()).expand(PlanText.model_validate(body))
    validate_plan(result, SEGMENTS, 4, 120000, calibrated=True)
    assert len(result.objectives[0].visual_intent) <= 120
    assert result.objectives[0].learning_outcome == body['items'][0]['outcome']


def test_compact_plan_respects_count_budget_dependencies_and_evidence():
    body = plan_body()
    body['items'][0]['source'] = 1
    with pytest.raises(ValueError, match='supplied passage'):
        request(LessonPlan, plan_task()).expand(PlanText.model_validate(body))
    body = plan_body()
    body['items'][0]['checkpoint'] = True
    with pytest.raises(ValueError, match='budget'):
        request(LessonPlan, plan_task(remaining_ms=30000)).expand(PlanText.model_validate(body))
    body['items'][0]['checkpoint'] = False
    body['items'][0]['depends_on_outcomes'] = [1]
    with pytest.raises(ValueError, match='earlier OUTCOME numbers'):
        request(LessonPlan, plan_task()).expand(PlanText.model_validate(body))
    result = request(LessonPlan, plan_task(covered_outcomes=['old_id|An earlier outcome'])).expand(PlanText.model_validate(body))
    assert result.objectives[0].dependency_ids == ['old_id']


@pytest.mark.parametrize('template', ['process', 'steps', 'example', 'timeline', 'cycle', 'comparison', 'key_fact', 'dos_donts'])
def test_compact_beats_compile_to_existing_measured_playback(template):
    body = story_body()
    if template == 'dos_donts':
        body['beats'][0]['role'] = 'good'
        body['beats'][1]['role'] = 'bad'
    original = json.loads(json.dumps(body))
    content = request(ModelStoryboard, story_task(template)).expand(DiagramText.model_validate(body))
    assert [u.text for u in content.narration_units] == [b['text'] for b in body['beats']]
    assert all(node.icon in ICONS for node in content.scenes[0].nodes)
    draft = attach_evidence(content, SEGMENTS)
    validate_draft(draft, SEGMENTS, False)
    for i, beat in enumerate(draft.narration_units):
        beat.start_ms, beat.end_ms = i * 8000, (i + 1) * 8000
    scenes, units = compile_storyboard(draft, 24000)
    assert scenes[0].end_ms == 24000 and len(units) == 3
    assert [a.at_ms for a in scenes[0].actions if a.kind == 'appear'] == [0, 8000, 16000]
    assert body == original


def test_compact_chart_preserves_signed_values_units_and_citations():
    body = {'units': 'units', 'beats': [
        {'text': 'The supplied value for A is negative twelve units. A negative value sits below zero on this shared scale.',
         'label': 'A', 'source': 0, 'value': -12},
        {'text': 'The value for B is fifteen hundred units. Both measurements use the same unit and the same zero-inclusive scale.',
         'label': 'B', 'source': 0, 'value': 1500}], 'question': None}
    spec = request(ModelStoryboard, story_task('chart', target_words=40))
    draft = attach_evidence(spec.expand(ChartText.model_validate(body)), SEGMENTS)
    validate_draft(draft, SEGMENTS, False)
    assert [p.value for p in draft.scenes[0].payload.points] == [-12, 1500]
    body['beats'][0]['value'] = -99
    with pytest.raises(ValueError):
        validate_draft(attach_evidence(spec.expand(ChartText.model_validate(body)), SEGMENTS), SEGMENTS, False)


def test_question_source_mapping_and_requirement_are_still_validated():
    body = story_body()
    spec = request(ModelStoryboard, story_task(question_required=True))
    with pytest.raises(ValueError, match='question'):
        spec.expand(DiagramText.model_validate(body))
    body['question'] = {'prompt': 'What does an index map?', 'answer': 'Keys to rows',
                        'distractors': ['Rows to colours'], 'explanation': 'An index associates keys with rows.', 'source': 0}
    draft = attach_evidence(spec.expand(DiagramText.model_validate(body)), SEGMENTS)
    validate_draft(draft, SEGMENTS, True)
    assert draft.question.evidence.segment_ids == ['seg_0']
    body['question']['distractors'] = ['Keys to rows']
    with pytest.raises(ValueError, match='distinct'):
        spec.expand(DiagramText.model_validate(body))


def test_compact_transport_uses_small_schema_and_runs_full_domain_validation(scripted_model):
    model, streams, calls, _ = scripted_model
    streams.append([chunk(json.dumps(story_body()))])
    checked = []
    def valid(result):
        assert isinstance(result, ModelStoryboard)
        validate_draft(attach_evidence(result, SEGMENTS), SEGMENTS, False)
        checked.append(result)
    result = model.generate(ModelStoryboard, story_task(), threading.Event(), valid)
    assert result is checked[0]
    prompt = calls[0]['messages'][0]['content']
    assert 'ModelStoryboard' not in prompt and 'SemanticOperation' not in prompt
    assert 'ImagePayload' not in prompt and 'QuestionText' not in prompt
    assert len(json.dumps(calls[0]['messages'])) < 6000
    assert model.attempts[0]['task'] == 'ModelStoryboard'
    assert model.generation_deadline is None


def test_compact_domain_failure_has_only_one_repair(scripted_model):
    model, streams, calls, _ = scripted_model
    streams.extend([[chunk(json.dumps(story_body()))]] * 2)
    def reject(value):
        raise ValueError('Unsupported claim must not pass.')
    with pytest.raises(AppError) as error:
        model.generate(ModelStoryboard, story_task(), threading.Event(), reject)
    assert error.value.code == 'MODEL_DATA_INVALID'
    assert 'one repair' in error.value.message
    assert len(calls) == 2 and model.generation_deadline is None


def test_review_payload_keeps_every_claim_but_deduplicates_evidence_quotes():
    draft = attach_evidence(request(ModelStoryboard, story_task()).expand(DiagramText.model_validate(story_body())), SEGMENTS)
    task = {'compact_authoring': True, 'draft': draft.model_dump(), 'segments': PASSAGES, 'teaching': {'outcome': draft.objective}}
    spec = request(SupportCheck, task)
    assert spec.payload['sources'] == [{'id': 'seg_0', 'text': SEGMENTS[0].text}]
    assert 'quote' not in json.dumps(spec.payload['draft'])
    for a, b in zip(draft.narration_units, spec.payload['draft']['narration_units']):
        assert a.text == b['text']
        assert a.evidence.segment_ids == b['evidence']['segment_ids']
    assert spec.payload['draft']['scenes'][0]['nodes'][0]['label'] == 'Search key'


@pytest.mark.parametrize('verb', ['Summarize', 'Summarise', 'Recap'])
def test_summary_actions_are_observable_learning_outcomes(verb):
    body = plan_body()
    body['items'][0]['outcome'] = verb + ' how an index maps keys to rows.'
    result = request(LessonPlan, plan_task()).expand(PlanText.model_validate(body))
    validate_plan(result, SEGMENTS, 4, 120000, calibrated=True)


def test_stage_deadline_is_shared_by_repairs_not_reset(scripted_model, monkeypatch):
    import time
    model, _, _, _ = scripted_model
    model.settings.task_timeout = .01
    calls = []
    def complete(messages, schema, attempt, cancel, on_content):
        calls.append(attempt)
        time.sleep(.02)
        on_content('{]')
    monkeypatch.setattr(model, 'complete', complete)
    with pytest.raises(AppError) as error:
        model.generate(ModelStoryboard, story_task(), threading.Event())
    assert error.value.code == 'MODEL_TASK_TIMEOUT'
    assert calls == [0] and model.generation_deadline is None


def test_first_playable_budget_does_not_mask_user_cancellation():
    import time
    from app.providers import check_cancel
    from app.errors import Cancelled
    flag = threading.Event()
    flag.deadline = time.monotonic() - 1
    with pytest.raises(AppError) as error:
        check_cancel(flag)
    assert error.value.code == 'FIRST_PLAYABLE_TIMEOUT'
    flag.set()
    with pytest.raises(Cancelled):
        check_cancel(flag)


def test_ranking_uses_diverse_search_order_without_any_model_call():
    import asyncio
    from types import SimpleNamespace
    from app.jobs import Jobs
    jobs = Jobs.__new__(Jobs)
    jobs.model = SimpleNamespace(compact_authoring=True)
    lesson = SimpleNamespace(metrics={})
    fetched = [({'channel': channel}, source) for channel, source in [('a', 'first'), ('a', 'second'), ('a', 'skipped'), ('b', 'third')]]
    result = asyncio.run(jobs.rank(lesson, fetched, threading.Event()))
    assert result == ['first', 'second', 'third']
    assert lesson.metrics == {'ranking_model_skipped': 1}


@pytest.mark.parametrize('detail', ['Speech-to-text', 'Text-to-image', 'Language modeling'])
def test_concise_hyphenated_or_two_word_details_are_published(detail):
    # Real failure: a valid storyboard was discarded because "Speech-to-text"
    # counted as one space-separated word. Word count is guidance only.
    body = story_body()
    body['beats'][2]['detail'] = detail
    draft = attach_evidence(request(ModelStoryboard, story_task()).expand(DiagramText.model_validate(body)), SEGMENTS)
    validate_draft(draft, SEGMENTS, False)
    assert draft.scenes[0].nodes[2].detail == detail


def test_detail_still_requires_text_size_limits_and_evidence():
    body = story_body()
    body['beats'][0]['detail'] = '   '
    draft = attach_evidence(request(ModelStoryboard, story_task()).expand(DiagramText.model_validate(body)), SEGMENTS)
    with pytest.raises(ValueError, match='short detail line'):
        validate_draft(draft, SEGMENTS, False)
    for detail in ['x' * 71, 'Supercalifragilisticexpialidocious term']:
        body = story_body()
        body['beats'][0]['detail'] = detail
        with pytest.raises(ValueError):
            request(ModelStoryboard, story_task()).expand(DiagramText.model_validate(body))
    body = story_body()
    body['beats'][0]['detail'] = 'Speech-to-text'
    body['beats'][0]['source'] = 5
    with pytest.raises(ValueError, match='supplied passage'):
        request(ModelStoryboard, story_task()).expand(DiagramText.model_validate(body))


def test_repeat_of_published_short_is_distinct_from_repeat_inside_one_draft():
    from app.validation import check_narration, RepeatedContent
    published = 'Extend your arms out in front to catch yourself and maintain balance during a fall.'
    with pytest.raises(RepeatedContent, match='beat 1 repeats an earlier short'):
        check_narration([published, 'Avoid letting your feet slide out from under you by staying low.'], [published])
    with pytest.raises(ValueError) as error:
        check_narration([published, published], [])
    assert not isinstance(error.value, RepeatedContent)
    check_narration([published], [published], allow_recap=True)


def repeating_story(published):
    body = story_body()
    body['beats'][0]['text'] = published
    return body


@pytest.mark.parametrize('second_repeats', [True, False])
def test_published_repeat_after_repair_reports_no_new_content(scripted_model, second_repeats):
    model, streams, calls, _ = scripted_model
    published = story_body()['beats'][0]['text']
    novel = story_body()
    novel['beats'][0]['text'] = 'Indexes trade extra storage and slower writes for much faster key lookups across your rows.'
    streams.extend([[chunk(json.dumps(repeating_story(published)))],
                    [chunk(json.dumps(repeating_story(published) if second_repeats else novel))]])
    def valid(result):
        validate_draft(attach_evidence(result, SEGMENTS), SEGMENTS, False, [published])
    if second_repeats:
        with pytest.raises(AppError) as error:
            model.generate(ModelStoryboard, story_task(), threading.Event(), valid)
        assert error.value.code == 'NO_NEW_CONTENT'
    else:
        result = model.generate(ModelStoryboard, story_task(), threading.Event(), valid)
        assert result.narration_units[0].text == novel['beats'][0]['text']
    # The repair names the exact earlier sentence so the model can avoid it.
    assert 'repeats an earlier short' in calls[1]['messages'][-1]['content']
    assert len(calls) == 2


def test_other_final_failure_after_a_repeat_is_still_a_validation_error(scripted_model):
    model, streams, calls, _ = scripted_model
    published = story_body()['beats'][0]['text']
    unknown_source = story_body()
    unknown_source['beats'][1]['source'] = 7
    streams.extend([[chunk(json.dumps(repeating_story(published)))], [chunk(json.dumps(unknown_source))]])
    with pytest.raises(AppError) as error:
        model.generate(ModelStoryboard, story_task(), threading.Event(),
                       lambda r: validate_draft(attach_evidence(r, SEGMENTS), SEGMENTS, False, [published]))
    assert error.value.code == 'MODEL_DATA_INVALID'


def test_legacy_explicit_rich_requests_remain_supported():
    task = story_task()
    task.pop('compact_authoring')
    assert request(ModelStoryboard, task) is None


def test_more_sources_query_stays_on_goal_and_is_used_only_when_needed():
    def plan(query, items=True, **task):
        body = plan_body()
        body['more_sources_query'] = query
        if not items:
            body['items'] = []
        return request(LessonPlan, plan_task(phase='extension', **task)).expand(PlanText.model_validate(body))
    # Nothing new to plan: a related, on-goal search becomes a coverage gap.
    gaps = plan('index maintenance and rebuilds', items=False).missing_coverage
    assert [g.query_intent for g in gaps] == ['index maintenance and rebuilds']
    # Items exist: the query is still carried, for use if every item turns out to be a repeat.
    assert [g.query_intent for g in plan('index maintenance and rebuilds').missing_coverage] == ['index maintenance and rebuilds']
    # Exhausted sources: the search is honoured even alongside items.
    assert plan('index maintenance and rebuilds', sources_exhausted=True).missing_coverage
    # A related query without the goal's topic is anchored to it, not rejected.
    assert [g.query_intent for g in plan('soil nutrients for plants', items=False).missing_coverage] == ['indexes soil nutrients for plants']
    with pytest.raises(ValueError, match='sources_exhausted'):
        plan('', items=False, sources_exhausted=True)


def test_planner_sees_full_titles_skipped_points_and_exhaustion_flag():
    spec = request(LessonPlan, plan_task(phase='extension', covered_outcomes=['c0_0|Explain how an index maps keys to'],
        covered_points=[{'title': 'Find a row by its key', 'outcome': 'Explain how an index maps keys to rows for fast lookups.'}],
        nothing_new=['Key lookup comparison'], sources_exhausted=True))
    covered = spec.payload['already_covered'][0]
    assert covered == {'outcome_number': 1, 'title': 'Find a row by its key',
                       'outcome': 'Explain how an index maps keys to rows for fast lookups.'}
    assert spec.payload['nothing_new'] == ['Key lookup comparison'] and spec.payload['sources_exhausted'] is True
    assert 'REPEAT' in spec.instructions and 'more_sources_query' in spec.instructions


def test_prompt_states_the_measured_word_target():
    spec = request(ModelStoryboard, story_task(target_words=82))
    assert 'about 82 words (at least 62)' in spec.instructions and 'about 27 words' in spec.instructions
    assert 'short narration beats' not in spec.instructions


def test_short_draft_gets_one_length_repair_then_is_accepted(scripted_model):
    model, streams, calls, _ = scripted_model
    # story_body is 53 words; a target of 82 makes it "too short" (< 62).
    streams.extend([[chunk(json.dumps(story_body()))], [chunk(json.dumps(story_body()))]])
    result = model.generate(ModelStoryboard, story_task(target_words=82), threading.Event(),
                            lambda r: validate_draft(attach_evidence(r, SEGMENTS), SEGMENTS, False))
    assert len(calls) == 2 and len(result.narration_units) == 3
    feedback = calls[1]['messages'][-1]['content']
    assert 'Narration has 53 words' in feedback and 'about 82' in feedback


def test_long_enough_draft_needs_no_length_repair(scripted_model):
    model, streams, calls, _ = scripted_model
    streams.append([chunk(json.dumps(story_body()))])
    model.generate(ModelStoryboard, story_task(target_words=60), threading.Event())
    assert len(calls) == 1


def test_chart_planned_on_a_passage_without_numbers_becomes_a_comparison():
    words_only = [{'id': 'seg_w', 'source_id': 'src_0', 'text': "Nitrogen helps make a plant's leaves green, "
                   'phosphorus helps roots and flowers, and potassium helps a plant fight off diseases.'}]
    body = plan_body()
    body['items'][0]['template'] = 'chart'
    plan = request(LessonPlan, plan_task(segments=words_only)).expand(PlanText.model_validate(body))
    assert plan.objectives[0].template == 'comparison' and 'comparison' in plan.objectives[0].visual_intent
    # A passage with real values keeps its chart.
    plan = request(LessonPlan, plan_task()).expand(PlanText.model_validate(body))
    assert plan.objectives[0].template == 'chart'


def test_job_redraws_an_already_planned_numberless_chart_as_comparison(tmp_path):
    # The failed lesson's "Soil Nutrients" was planned before this fix; Retry
    # must not plot invented values for it.
    from app.config import Settings
    from app.jobs import Jobs
    from app.store import Store
    from app.contracts import Job, Lesson, Objective, SavedLearningRequest, Short, Source
    from test_core import StubModel, StubSpeech, StubYouTube
    source = StubYouTube().transcript({'video_id': 'dQw4w9WgXcQ', 'channel': 'c'}, threading.Event())
    source = source.model_copy(update={'segments': [source.segments[0].model_copy(update={
        'text': "Nitrogen helps make a plant's leaves green and potassium helps a plant fight off diseases."})]})
    seen = []
    class Records(StubModel):
        def generate(self, contract, task, cancel, validate=None):
            if contract is ModelStoryboard:
                seen.append(task['template'])
            return super().generate(contract, task, cancel, validate)
    settings = Settings(data=tmp_path); store = Store(settings.data)
    try:
        objective = Objective(concept_id='nutrients', title='Soil Nutrients', template='chart', prerequisites=[],
                              learning_outcome='Identify the roles of soil nutrients', relevance='Plants need nutrients',
                              visual_intent='Use chart to explain this outcome.', evidence_segment_ids=[source.segments[0].id])
        lesson = Lesson(id='l', request=SavedLearningRequest(goal='Learn plant nutrients', request_id='request-id-1'),
                        sources=[source], objectives=[objective],
                        shorts=[Short(id='s', objective='Soil Nutrients', concept_id='nutrients')],
                        job=Job(id='j', lesson_id='l', created_at=0, updated_at=0))
        store.put_source(source); store.save(lesson)
        jobs = Jobs(store, Records(), StubSpeech(settings), settings, StubYouTube())
        import asyncio
        jobs.cancel_flags['l'] = threading.Event()
        try:
            asyncio.run(jobs.advance('l'))
        except Exception:
            pass  # Only the template choice is under test here.
        assert seen and seen[0] == 'comparison'
        assert store.lesson('l').metrics.get('chart_without_numbers') == 1
    finally:
        store.close()
