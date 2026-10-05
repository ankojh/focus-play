# Bounded first-video authoring (prompt 24)

## Why the request design changed

The saved aerodynamics lesson spent 586.873 seconds and produced no playable short:
100.423 seconds acquiring/ranking sources, 129.747 planning, and 352.672 on three
failed storyboard attempts. Full mixed-renderer authoring exposed approximately
11,500 prompt tokens per storyboard attempt and fragile nested operations/IDs.
The earlier planning-only JSON fix did **not** validate first-video readiness.

The selected runtime remains the installed TurboFieldfare + Gemma 4 26B-A4B IT.
No model/runtime download, replacement, rebuild, speech change, new source purchase,
or user-library rewrite is part of this change.

## Production path

- `backend/app/llm/compact.py`: typed model-facing plan, diagram, chart and question
  contracts. The planner writes bounded outcomes and numbered earlier-outcome
  dependencies; code assigns stable concept IDs and budgeted durations.
- Storyboard authoring writes 2–4 narration beats, passage indexes, short visual
  labels/details/roles/icons, and an optional question. A chart instead requires
  finite source values, labels and units. It does not write renderer IDs, nested
  operation arrays, scene clocks or measured timing.
- The selected template determines documented mechanics: ordered stages connect
  sequentially, cycles close the loop, comparison/key-fact/do-don't have no arrows.
  Each item reveals/focuses at the start of its measured narration beat.
- Compilation retains the authored claims verbatim and maps indexes to the exact
  supplied evidence IDs. Invalid indexes/dependencies fail; none are guessed.
  Full storyboard, citation, narration, question, numerical and teaching checks
  still run, followed by the existing model source/teaching review and Kokoro.
  Source review is a model check, not independent factual verification.
- Review sends source passages once; repeated quoted evidence metadata is removed
  from the review request, not from saved evidence or playback.
- Source selection uses the existing search-order fallback directly, retaining
  at most three captioned sources and at most two per channel. It does not spend
  three model attempts ranking before the first video. No scores are fabricated;
  source review and evidence validation remain mandatory. This is a ranking-quality
  trade-off, not a claim that YouTube order is equivalent to semantic ranking.
- Production compact calls get at most **two attempts total**, sharing
  `LLM_TASK_TIMEOUT` (default 60 s, configurable 1–120 s). Existing conservative
  three-call reservations and persisted source/work/candidate limits remain;
  unused reserved units are not silently refunded or reset.
- `FIRST_PLAYABLE_TIMEOUT` defaults to 180 s (configurable 1–240 s) after dequeue,
  shared across initial worker turns until a ready short exists. It stops failed
  preparation; it does not promise success within that time. TurboFieldfare I/O
  closes at the earliest stage/attempt/first-video deadline. Synchronous source
  and speech work observes it at existing call/unit boundaries, so it is not an
  exact universal wall-clock or GPU-release guarantee. Queue waiting is excluded.
- Prompt/parser/repair/authoring updates may rebind a **same-runtime unpublished**
  lesson, preserving its committed plan, sources, IDs and all consumed allowances.
  Existing media/coverage history still blocks rebinding. Actual model/runtime/
  settings switches remain errors. Historical ready provenance is never relabelled.

### Deliberate limits

Production authoring is currently one diagram or chart per short. Rich existing
mixed scene contracts, compiler and renderers (table/code/image/etc.) remain
supported for saved content and explicit rich diagnostics; this change does not
claim that compact authoring produces all of them. Full mixed generation needs
similarly small, separately tested authoring contracts rather than restoring the
large union schema. No player navigation, looping, likes/dislikes or caption
behaviour was changed.

The existing teaching validator now recognizes `summarize`, `summarise` and
`recap` as observable actions alongside `explain`/`recall`, rather than rejecting
legitimate recap outcomes. Recap placement/dependency checks remain.

## Actual isolated first-video checks

`cached_lesson_check.py --first-only` copies saved real sources into a new isolated
store, disables acquisition, runs actual Jobs/LLM/Kokoro, and deliberately cancels
remaining work after a validated ready short. The report's final `cancelled` status
is intentional and **not** a claim of a complete lesson. No draft/audio cache hits
were used for the measured shorts. Model/OS prefix caching was not reset.

| Saved-source topic | Planning | First draft incl. repair | Review | Speech | First playable | Measured video |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Aerodynamics | 22.406 s | 23.931 s | 22.406 s | 1.250 s | 73.786 s | 15.725 s |
| Kano model | 32.349 s | 18.391 s | 20.362 s | 2.044 s | 76.546 s | 25.725 s |

Each success required one repair: aerodynamics narration used `us`, which the
existing narration guard rejected; the Kano plan initially used zero-based rather
than one-based outcome dependencies. These are two topic checks, **not** a
statistical reliability benchmark. A cancellation attempt on the next short may
appear in the report's total counters after first publication.

Development failures are retained, not hidden: aerodynamics checks 1 and 2 found
adapter bugs (missing template, overlong generated visual-intent metadata); Kano
checks 1 and 2 exposed dependency-number confusion and rejection of the legitimate
`recap` action. Regression tests cover the corresponding changes. The aerodynamics
success predates the final numbered-dependency/prompt wording improvements; the
Kano success exercises them. Do not treat six development runs as six successes.

Local artifacts (source-bearing reports remain ignored/private):

- `.runtime/compact-aerodynamics-first-{1,2,3}/cached-lesson-check.json`
- `.runtime/compact-kano-first-{1,2,3}/cached-lesson-check.json`
- Browser playback of the actual aerodynamics WAV/scenes passed in an isolated
  API on port 8012: playback clock, WAV duration, loop attribute, per-beat captions
  and node focus, seeking, refresh restoration, and transcript visibility.
- `frontend/test-results/real-provider-final-beat.png` records that actual output;
  its cancellation banner is from the intentional first-only test stop.

These measurements include provider/speech preparation but **exclude new search
and transcript acquisition**. Both source-provider call counts are zero. They are
not directly comparable to a fresh ten-minute request as an end-to-end speedup
ratio. A fresh run still adds acquisition time. Full-session 90–100% coverage,
continuous buffer production, long-run repair rates, heat and energy are not
verified here. Subsequent shorts can still take longer to prepare than to watch.

## Reproduce without credits or library mutation

Use an existing saved source lesson, a **new** work directory, and the existing
ready runtime. Do not run concurrently with a real lesson:

```sh
.venv/bin/python scripts/cached_lesson_check.py \
  --approve-inference --source-lesson YOUR_SAVED_LESSON_ID \
  --work-dir .runtime/compact-first-check \
  --duration-seconds 120 --budget-seconds 200 --first-only
```

Opt-in browser check against that isolated store's API (GET-only):

```sh
cd frontend
FOCUS_PROVIDER_API=http://127.0.0.1:8012 \
FOCUS_PROVIDER_LESSON_ID=THE_ISOLATED_LESSON_ID \
  npx playwright test tests/provider-playback.spec.ts
```

An API-only restart, with operator permission and no active generation, is required
for the live app to load these changes. Do not restart the model or redownload it.
