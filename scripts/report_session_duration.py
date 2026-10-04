"""Reproducible offline duration matrix. Never calls live/credit-bearing providers.

Uses the explicitly fake providers from backend/tests/test_session.py. Silent
WAVs measure orchestration and ledger behaviour, NOT speech or teaching quality.
"""
import json
import sys
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'backend/tests')]
from app.config import Settings
from app.main import create_app
from test_session import SessionModel, SessionSources, DurationSpeech, request, wait_for


def matrix():
    rows = []
    for rate in [250, 430, 550]:
        for seconds in [60, 73, 120, 137, 300, 600, 1200]:
            with tempfile.TemporaryDirectory() as folder:
                settings = Settings(data=Path(folder))
                model, sources = SessionModel(), SessionSources()
                speech = DurationSpeech(settings, rate)
                with TestClient(create_app(settings, model, speech, sources)) as client:
                    lid = client.post('/api/lessons', json=request(seconds)).json()['id']
                    final = wait_for(client, lid)
                ledger, state = final['duration_ledger'], final['planning']
                rows.append(dict(requested_seconds=seconds, fake_ms_per_word=rate,
                    measured_media_ms=ledger['measured_ready_media_ms'],
                    practice_allowance_ms=ledger['reserved_practice_ms'], final_content_ms=ledger['final_content_ms'],
                    utilisation=ledger['utilisation'], shorts=len(final['shorts']),
                    unique_outcomes=len({o['learning_outcome'] for o in final['objectives']}),
                    mapped_coverage_entries=len(state['coverage']),
                    plan_calls=len(model.plan_tasks), model_logical_calls=model.calls,
                    reserved_model_call_units=state['model_call_units'],
                    acquisition=final['acquisition'],
                    max_plan_task_characters=max(len(json.dumps(t)) for t in model.plan_tasks),
                    max_retrieved_characters=max(sum(len(s['text']) for s in t['segments']) for t in model.plan_tasks+model.draft_tasks),
                    synthetic_preparation_seconds=final['metrics']['total_preparation_seconds'],
                    completion_reason=state['completion_reason'], failure_reason=final['job']['error']))
    return {'notice': 'Synthetic offline arithmetic/control-flow diagnostic. Silent test WAVs, fake source and model/review providers. This is not live evidence, real provider cost/performance, semantic teaching evaluation or wall-clock learning duration.',
            'live_provider_calls': 0, 'live_source_credits_used': 0, 'rows': rows}


if __name__ == '__main__':
    result = matrix()
    path = ROOT / 'docs/session-duration-report.json'
    path.write_text(json.dumps(result, indent=2)+'\n')
    print(path)
    print('requested | fake ms/word | content seconds | utilisation | shorts')
    for row in result['rows']:
        print(f"{row['requested_seconds']:9} | {row['fake_ms_per_word']:12} | {row['final_content_ms']/1000:15.2f} | {row['utilisation']:11.1%} | {row['shorts']:6}")
