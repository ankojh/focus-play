"""Separate reproducible fixture scheduling from credit-consuming live throughput."""
import argparse
import json
import platform
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.readiness import simulate_one_pass


def fixtures(buffer_seconds):
    runs = []
    for name, preparation in [('faster', 5), ('equal', 10), ('slower', 15)]:
        publications = [preparation * (i + 1) for i in range(20)]
        durations = [10000] * 20
        runs.append({'kind': name, 'cache_state': 'fixture_uncached', 'status': 'complete',
                     'publication_seconds': publications, 'durations_ms': durations,
                     'fixture_production_rate': 10 / preparation,
                     'synthetic_one_pass': simulate_one_pass(publications, durations),
                     'experimental_buffer': simulate_one_pass(publications, durations, round(buffer_seconds * 1000))})
    return {'mode': 'fixture', 'note': 'Deterministic serial publications. Not hardware/provider throughput or observed learner stalls.',
            'experimental_buffer_seconds': buffer_seconds, 'runs': runs}


def live(args):
    import httpx
    if not args.approve_source_credits:
        raise SystemExit('Live runs require --approve-source-credits; source searches/transcripts may be billed.')
    if args.cache_state == 'unspecified':
        raise SystemExit('Declare --cache-state cold, warm-uncached, partially-cached, or fully-cached. No cache is deleted automatically.')
    rows = []
    data = {'mode': 'live', 'hardware': {'platform': platform.platform(), 'machine': platform.machine(),
                                      'processor': platform.processor(), 'operator_notes': args.hardware_notes},
            'cache_state_operator_declared': args.cache_state,
            'note': 'Cache labels are operator declarations, not forced by this script. Actual per-stage hits are recorded. '
                    'Synthetic playback is sequential, has no practice credit and is NOT the looping player. '
                    'Interactive stalls and peak CPU/GPU/memory are not measured by this script.',
            'experimental_buffer_seconds': args.buffer_seconds, 'runs': rows}
    with httpx.Client(base_url=args.base_url, timeout=30, trust_env=False) as client:
        health = client.get('/api/health'); health.raise_for_status(); data['health'] = health.json()
        if not data['health'].get('ready'):
            raise SystemExit(data['health'])
        for budget in args.budgets:
            for run in range(args.runs):
                body = {'goal': args.goal, 'prior_knowledge': args.knowledge,
                        'time_budget_seconds': budget, 'request_id': str(uuid.uuid4())}
                start = time.monotonic()
                response = client.post('/api/lessons', json=body); response.raise_for_status()
                lesson = response.json(); lid = lesson['id']; accepted = time.monotonic() - start
                observed = {}; deadline = time.monotonic() + args.timeout_seconds
                timed_out = False
                while True:
                    response = client.get(f'/api/lessons/{lid}'); response.raise_for_status(); lesson = response.json()
                    for short in lesson['shorts']:
                        if short['status'] == 'ready':
                            observed.setdefault(short['id'], time.monotonic() - start)
                    if lesson['job']['status'] in {'complete', 'failed', 'cancelled', 'interrupted'}:
                        break
                    if time.monotonic() >= deadline:
                        response = client.post(f'/api/lessons/{lid}/cancel', json={}); response.raise_for_status()
                        lesson = response.json(); timed_out = True; break
                    time.sleep(.25)
                shorts = [s for s in lesson['shorts'] if s['status'] == 'ready']
                # A partial failure is not a completed session: report only its ready prefix.
                prefix = []
                for short in lesson['shorts']:
                    if short['status'] != 'ready': break
                    prefix.append(short)
                publications = [s['timings'].get('published_after_monotonic_seconds', observed.get(s['id'], 0)) for s in prefix]
                durations = [s['measured_duration_ms'] for s in prefix]
                row = {'kind': args.cache_state, 'budget_seconds': budget, 'run': run + 1,
                       'lesson_id': lid, 'accepted_seconds': accepted, 'observed_terminal_seconds': time.monotonic() - start,
                       'status': lesson['job']['status'], 'timed_out': timed_out, 'error': lesson['job']['error'],
                       'settings': lesson['provider_settings'], 'metrics': lesson['metrics'],
                       'stage_timings': lesson['job']['stage_timings'], 'acquisition': lesson['acquisition'],
                       'duration_ledger': lesson.get('duration_ledger'), 'readiness': lesson.get('readiness'),
                       'shorts': [{'id': s['id'], 'visual_kinds': [scene.get('kind', 'diagram') for scene in s['scenes']],
                                   'duration_ms': s['measured_duration_ms'], 'cache_hit': s['cache_hit'], 'timings': s['timings']} for s in shorts],
                       'synthetic_one_pass_scope': 'ready prefix only' if len(prefix) != len(lesson['shorts']) else 'entire final plan',
                       'synthetic_one_pass': simulate_one_pass(publications, durations),
                       'experimental_buffer': simulate_one_pass(publications, durations, round(args.buffer_seconds * 1000))}
                rows.append(row); save(args.output, data)
                print(f'{budget}s run {run+1}: {row["status"]}, first playable {lesson["metrics"].get("first_playable_seconds")}', flush=True)
    return data


def save(output, data):
    path = ROOT / output; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['fixture', 'live'], required=True)
    parser.add_argument('--output', default='docs/readiness-fixture-runs.json')
    parser.add_argument('--buffer-seconds', type=float, default=0, help='Experimental benchmark gate only; never gates the UI')
    parser.add_argument('--approve-source-credits', action='store_true')
    parser.add_argument('--cache-state', choices=['unspecified', 'cold', 'warm-uncached', 'partially-cached', 'fully-cached'], default='unspecified')
    parser.add_argument('--hardware-notes', default='Not supplied; hardware/resource conclusions unavailable')
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--budgets', nargs='+', type=int, default=[120, 300, 600, 1200])
    parser.add_argument('--runs', type=int, default=1)
    parser.add_argument('--timeout-seconds', type=int, default=7200)
    parser.add_argument('--goal', default='Explain database indexes: compare an index lookup with a table scan, then explain lookup and maintenance.')
    parser.add_argument('--knowledge', default='I know basic SQL.')
    args = parser.parse_args()
    if args.runs < 1 or args.buffer_seconds < 0 or args.timeout_seconds < 1 or any(b < 60 or b > 1200 for b in args.budgets):
        parser.error('Use positive runs/timeouts, nonnegative buffer and 60–1200 second budgets.')
    if args.mode == 'live' and args.output == 'docs/readiness-fixture-runs.json':
        args.output = 'docs/readiness-live-runs.json'
    save(args.output, fixtures(args.buffer_seconds) if args.mode == 'fixture' else live(args))
    print('Measurements saved:', ROOT / args.output)

if __name__ == '__main__':
    main()
