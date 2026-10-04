# Readiness measurements

Mode: **fixture**. Raw data: [readiness-fixture-runs.json](readiness-fixture-runs.json).

Deterministic serial publications. Not hardware/provider throughput or observed learner stalls.

These are synthetic **one-pass** stalls, not observed interactive stalls. The player loops until navigation. No question allowance, replay, or generation wait is counted as useful media.

Experimental startup buffer: 60.0 seconds; not a UI default.

| Case | Budget (s) | Result | Startup (s) | Sequential stalls (s) | Ready-ahead at starts (s) |
| --- | ---: | --- | ---: | ---: | --- |
| faster | — | complete | 5.000 | 0.000 | 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 100.0, 90.0, 80.0, 70.0, 60.0, 50.0, 40.0, 30.0, 20.0, 10.0 |
| equal | — | complete | 10.000 | 0.000 | 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0 |
| slower | — | complete | 15.000 | 95.000 | 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0 |

## Experimental initial preparation trade-off

| Case | Threshold reached (s) | Buffered startup (s) | Subsequent synthetic stalls (s) |
| --- | ---: | ---: | ---: |
| faster | 30.000 | 30.000 | 0.000 |
| equal | 60.000 | 60.000 | 0.000 |
| slower | 90.000 | 90.000 | 20.000 |

The fixture publication intervals are 5, 10, and 15 seconds for 10-second media. They exercise production faster than, equal to, and slower than consumption; they do not demonstrate a provider speed improvement.

No p95 is inferred from this sample. No universal zero-wait guarantee or release throughput threshold is established. Peak CPU/GPU/memory, interactive stalls, and live cancellation/recovery still require target-hardware evaluation.
