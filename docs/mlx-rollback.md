# Explicit local MLX rollback after the cricket failure

The operator approved testing the previous installed Gemma 4 MLX setup and
activating it only after a saved-source cricket test produced playable media.
This is an explicit profile switch, not automatic provider fallback.

## Active local profile

- Ollama 0.35.0, `http://127.0.0.1:11434`.
- Installed `gemma4:12b-mlx`, safetensors, reported resident size 7,661,404,112 bytes.
- Digest: `117d0d84cf2ab865feb59afc2cd30ff5d55f0035e05eb8d1b814f9688e3f3671`.
- Client context budget 8192; output cap 2200; temperature 0; `think=false`.
- Kokoro `af_heart` unchanged. Compact authoring and validation remain in place.
- The owned TurboFieldfare launcher/server was stopped gracefully; its checkout,
  packed model, receipt and configuration backup remain intact. No downloads,
  builds or removals were performed. The already installed MLX runner was reused.
- Only the API was restarted for activation. Health verified Ollama/MLX/Kokoro.
  All eight saved lessons' sources, objectives, shorts, provenance and consumed
  allowances matched before/after activation. No lesson was auto-retried.

The ignored local `.env` selects this profile. Repository fresh-install defaults
still describe TurboFieldfare; do not copy `.env.example` over the active `.env`
without deliberately selecting a profile. The rollback configuration backup is
private in `.runtime/env-before-mlx-rollback-*.backup`.

## Tests, including limits

The exact saved cricket sources from `lesson_8e27a09acbdc4c209f8e` were copied into
two fresh isolated stores with acquisition disabled. Both requests retained the
user's beginner level, cricket goal and 300-second session budget. Tests deliberately
stopped after the first short; neither claims a complete five-minute session.

| Run | First playable | Planning | Drafting | Source/teaching review | Repairs before first short |
| --- | ---: | ---: | ---: | ---: | ---: |
| First | 27.092 s | 8.363 s | 6.409 s | 7.431 s | 0 |
| Repeat | 16.463 s | 6.051 s | 2.563 s | 2.302 s | 0 |

Planning, drafting and review passed on their first attempts in both runs.
Measured Kokoro audio and compiled visual timings were included. Source-provider
calls, draft-cache hits and audio-cache hits were zero. The already-loaded model
and OS/runtime caches were not reset; these are **not cold-start timings** or a
cross-topic reliability benchmark. Search/transcript acquisition is excluded.
The saved final job state is intentionally `cancelled` after first publication;
the next clip's cancellation may appear in counters. Cleanup took additional time.

The first output passed actual browser audio playback/decoding, duration, loop
attribute, per-beat captions and diagram focus, seek, refresh and transcript checks.
The backend suite passed 380 tests (one dependency deprecation warning), and
`git diff --check` passed.

### Schema probe

The installed endpoint was asked to output `NOT_JSON`. Without `format`, it did.
With `format` specifying an object containing only `result: "schema-ok"`, it
returned that JSON object instead. This demonstrates effective schema-parameter
behaviour in this probe, not a proof of all schema features or semantic correctness.
It does not establish that MLX itself guarantees JSON. Strict application-side
validation remains mandatory.

### Local evidence

- `.runtime/mlx-cricket-first-{1,2}/cached-lesson-check.json`
- `.runtime/mlx-cricket-first-1/browser-final-beat.png`
- `.runtime/mlx-format-probe.json`
- `.runtime/mlx-rollback-activation.json`

The first report's `model_attempts` list covers only the last task, because the
provider resets its per-task list. Its persisted lesson/short counters establish
three first-pass successes and zero repairs. The diagnostic was corrected before
the repeat to capture a bounded cross-task trace, which shows the three successful
attempts followed by the intentionally cancelled next-short request.

## Saved lessons and retry

Existing ready videos remain playable. Failed TurboFieldfare lessons retain their
original profile and cannot silently continue under MLX. A new lesson uses the
active MLX profile; moving a failed lesson across providers would require an
explicit new-lesson/source-reuse workflow, not relabelling old provenance or
resetting consumed allowances. No such migration was performed here.

## Reproduce the saved-source check

After explicitly selecting the installed Ollama profile:

```sh
.venv/bin/python scripts/cached_lesson_check.py \
  --approve-inference --expected-provider ollama \
  --source-lesson YOUR_SAVED_LESSON_ID --work-dir .runtime/new-mlx-check \
  --duration-seconds 300 --budget-seconds 200 --first-only
```

The script refuses a different configured provider and never downloads or switches
providers itself. Use a new isolated directory and do not run alongside active
lesson generation. The browser check accepts `FOCUS_PROVIDER_EXPECTED_PROVIDER=ollama`
plus the isolated API URL and lesson ID.
