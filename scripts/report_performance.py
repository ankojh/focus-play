"""Summarise a benchmark file without inventing hardware, cache state or p95."""
import argparse
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', default='docs/readiness-measurements.md')
    args = parser.parse_args()
    data = json.loads((ROOT / args.input).read_text()); runs = data['runs']
    mode = data.get('mode', 'legacy')
    lines = ['# Readiness measurements', '', f'Mode: **{mode}**. Raw data: [{Path(args.input).name}]({Path(args.input).name}).', '',
             data.get('note', 'Legacy input: cache/throughput assumptions require manual review.'), '',
             'These are synthetic **one-pass** stalls, not observed interactive stalls. The player loops until navigation. '
             'No question allowance, replay, or generation wait is counted as useful media.', '',
             f'Experimental startup buffer: {data.get("experimental_buffer_seconds", 0)} seconds; not a UI default.', '',
             '| Case | Budget (s) | Result | Startup (s) | Sequential stalls (s) | Ready-ahead at starts (s) |',
             '| --- | ---: | --- | ---: | ---: | --- |']
    for run in runs:
        simulation = run.get('synthetic_one_pass', {})
        startup = simulation.get('startup_seconds')
        stalls = simulation.get('stalls_seconds', [])
        ahead = ', '.join(f'{value / 1000:.1f}' for value in simulation.get('ready_ahead_ms', []))
        first = '—' if startup is None else f'{startup:.3f}'
        lines.append(f'| {run["kind"]} | {run.get("budget_seconds", "—")} | {run["status"]} | {first} | {sum(stalls):.3f} | {ahead} |')
    if data.get('experimental_buffer_seconds', 0):
        lines += ['', '## Experimental initial preparation trade-off', '',
                  '| Case | Threshold reached (s) | Buffered startup (s) | Subsequent synthetic stalls (s) |',
                  '| --- | ---: | ---: | ---: |']
        for run in runs:
            experimental = run.get('experimental_buffer', {})
            reached = experimental.get('experimental_buffer_reached_seconds')
            start = experimental.get('startup_seconds')
            lines.append(f'| {run["kind"]} | {"not reached" if reached is None else f"{reached:.3f}"} | {"—" if start is None else f"{start:.3f}"} | {sum(experimental.get("stalls_seconds", [])):.3f} |')
    if mode == 'fixture':
        lines += ['', 'The fixture publication intervals are 5, 10, and 15 seconds for 10-second media. '
                  'They exercise production faster than, equal to, and slower than consumption; they do not demonstrate a provider speed improvement.']
    if mode == 'live':
        lines += ['', '## Hardware and provider observations', '', '```json', json.dumps(data.get('hardware', {}), indent=2), '```', '',
                  'Cache state is operator-declared; inspect actual acquisition and per-short draft/audio cache hits in the raw file. '
                  'The raw file retains exact model/voice fingerprints and settings for each run.', '',
                  '## Active production and stage breakdown', '',
                  '| Lesson | First playable active (s) | Active work (s) | Queue wait (s) | Uncached output / active second |',
                  '| --- | ---: | ---: | ---: | ---: |']
        def value(metrics, key):
            return f'{metrics[key]:.3f}' if key in metrics else '—'
        for run in runs:
            m = run.get('metrics', {})
            lines.append(f'| {run["lesson_id"]} | {value(m, "first_playable_active_seconds")} | {value(m, "active_processing_seconds")} | {value(m, "queue_wait_seconds")} | {value(m, "uncached_output_per_active_second")} |')
        lines += ['', 'Stage totals in seconds (including failed attempts where instrumentation persisted):', '',
                  '| Lesson | Search | Transcript | Ranking | Plan | Continuation plan | Draft | Review | Repair | Speech |',
                  '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
        for run in runs:
            metrics = run.get('metrics', {})
            vals = [value(metrics, f'{name}_seconds') for name in ('search', 'transcript', 'ranking', 'plan', 'continuation_plan', 'draft', 'review', 'repair', 'synthesize')]
            lines.append('| ' + run['lesson_id'] + ' | ' + ' | '.join(vals) + ' |')
        successful = [r for r in runs if r['status'] == 'complete']
        first = [r['synthetic_one_pass']['startup_seconds'] for r in successful if r.get('synthetic_one_pass', {}).get('startup_seconds') is not None]
        if first:
            lines += ['', f'Completed samples: {len(first)}. Startup median {statistics.median(first):.3f}s; maximum {max(first):.3f}s.']
    lines += ['', 'No p95 is inferred from this sample. No universal zero-wait guarantee or release throughput threshold is established. '
              'Peak CPU/GPU/memory, interactive stalls, and live cancellation/recovery still require target-hardware evaluation.']
    output = ROOT / args.output; output.parent.mkdir(parents=True, exist_ok=True); output.write_text('\n'.join(lines) + '\n')
    print('Summary saved:', output)

if __name__ == '__main__':
    main()
