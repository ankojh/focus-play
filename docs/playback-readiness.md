# Generation buffering and playback readiness (#6)

## Delivered design

This implements measurement and bounded readiness/preloading (phases A/B). **No model concurrency, pipeline overlap, cloud generation, timed session, or automatic forward playback was introduced.** First playable output is still published and playable immediately. There is no 60–90-second startup gate or performance guarantee. Optional overlap/throughput tuning in phase C remains contingent on representative target-hardware measurements.

### Single-writer, fair scheduling

`Jobs` retains one worker and one `advance()` per lesson at a time. The priority queue now uses FIFO sequence numbers for all normal turns; only shutdown has a special priority. Each turn prepares at most one short (or performs a bounded planning/finalisation checkpoint) and appends remaining work to the tail. New arrivals cannot overtake an already-enqueued continuation. Reservations cap queued **plus running** lessons at `queue_size` (default 8), so a continuation waits behind at most `queue_size - 1` other turns. This is a bound in **turns**, not wall-clock seconds: an acquisition/plan/short can be expensive, and provider timeouts still apply.

A lesson always selects its first unpublished activity in teaching order. Existing #5 logic may add bounded extensions before an unpublished closing; no ready/selected activity is reordered. Separately authorised explanation work still requires the original job to finish, so it cannot jump over that lesson's unfinished required content. No playback hints or high-frequency persisted position events are sent. Two tabs/clients have independent readiness positions and preload windows, cannot repeatedly reprioritise the backend, and receive equal per-lesson scheduling treatment. Tab closure/pausing does not cancel already-authorised generation; explicit cancellation does. Saved complete lessons do not start generation on revisit.

### Publication and snapshots

- Before publication, the final `Short` contract/timeline is validated. Audio must exist as a regular, non-symlink managed file; measured metadata comes from validated synthesis/cache boundaries. Every image scene must resolve to a ready managed asset with a matching content hash.
- API snapshots include `Lesson.readiness` version 1: `ready_short_ids`, `missing_media_short_ids`, and `initial_contiguous_media_ms`.
- Readiness is computed from current files without rewriting the saved lesson or appending job events. It does not erase the historical `ready` state when a file disappears. Missing audio is repairable through Retry; missing bundled images expose an actionable restart/reinstall requirement. Readiness does not guarantee against deletion/corruption after the check. Snapshot checks verify audio existence/header-sized storage, **not a fresh decode of every historical WAV**; new synthesis/cache hits validate duration/channel/rate and phrase boundaries.
- Old lessons have no stored readiness field and load without migration. The frontend has a legacy status/metadata fallback for snapshots without the new field. Cache keys/storyboards were not invalidated or changed by this workstream.

### Ready-ahead definition

The browser calculates:

```text
max(0, measured current media duration - current playback position)
+ measured duration of each immediately following ready short, stopping at the first gap
```

`initial_contiguous_media_ms` is the same calculation from the first planned short at position zero; it is **not** a backend estimate of an arbitrary client's position. No noncontiguous media, practice allowances, or additional loop duration is added. Seeking, replaying, looping, or selecting a different short changes the origin/remaining position. Pause freezes the position; continued generation may increase the ready run. Leaving the lesson unmounts the player and speculative preloads. The UI labels remaining server-ready media separately from browser-preloaded media and reports the real count of contiguous next ready shorts. Missing files are excluded from ready counts.

Navigation still loops the selected short until the learner moves. Unavailable Next/Previous controls and gesture boundaries remain disabled; an outline click explicitly requests an unready short. That wait view preserves the selected ID and plays it when ready without skipping another teaching activity. Like/dislike, keyboard/wheel/swipe navigation, captions, practice, sources and saved position are preserved. Removed extra-explanation controls were not restored.

### Bounded browser preloading

`frontend/src/readiness.ts` speculatively fetches **at most two contiguous upcoming ready shorts**. Requests are sequential, not parallel. Each includes audio and every essential image before it is reported fetched/decode-checked. Detached audio gets `loadeddata` (a decoding check, not a promise of future autoplay); images must load successfully. The full response is fetched with a streaming byte cap before blob decoding:

- At most 8 MiB total retained encoded media per window.
- At most 2,000,044 bytes per audio (40-second 24 kHz mono PCM fits).
- At most 5,000,000 bytes per managed image.
- At most 8,000,000 image pixels in the chosen window (about 32 MB decoded RGBA, excluding browser overhead). Duplicate image scenes are conservatively counted against this pixel budget.
- Each decode check has a 15-second deadline. Oversized/missing/undecodable media stays **not client ready**; a preload failure is not a generation failure.

Selection, lesson changes, entering Library, and cancellation abort outstanding fetches/decode waits, release detached elements and revoke blob URLs. Cancel preserves the selected already-ready short. Origin requests use the browser's HTTP cache where allowed; the actual player continues using the original managed URL (not a retained speculative blob). Browser cache/decoder memory is browser-controlled and cannot be guaranteed to disappear when JS references are released. A successful preload is a current-client observation, not a network/autoplay guarantee. Current playback still handles autoplay rejection separately from missing media.

## Metric definitions

New elapsed intervals use `time.monotonic()`. Metrics accumulate across retries rather than silently resetting. Provider/model instrumentation saves completed or failed-call elapsed work at stage boundaries. Abrupt process termination can lose the final in-flight interval; these are measurements, not billing ledgers.

| Metric | Definition |
| --- | --- |
| `queue_wait_seconds` | Sum of monotonic enqueue-to-dequeue intervals in this process. Does not include time while failed/interrupted waiting for Retry. |
| `worker_turns` | Number of dequeued worker turns, including cancelled/finalisation turns. |
| `active_processing_seconds` | Sum of worker-turn monotonic intervals, including plans, preparation, failures and cache checking; excludes queue/retry downtime. |
| `search_seconds`, `transcript_seconds`, `ranking_seconds` | Elapsed actual search/transcript/model-ranking calls, including failed attempts. Acquisition ledger separately records logical reservations, actual HTTP calls and cache hits. |
| `plan_seconds`, `continuation_plan_seconds` | Actual model calls for initial/continuation plans, respectively. Existing `planning_seconds` covers the initial workflow including cache/validation. `plan_cache_hits` / `ranking_cache_hits` identify cache reuse. |
| `draft_seconds`, `review_seconds`, `repair_seconds` | Actual draft, source/teaching review, and explicitly requested rewrite model-call time. Includes provider-internal schema repair attempts; those cannot currently be broken out individually. Review rewrites and duration rewrites are classified as repair; reviewing a rewrite remains review. |
| `synthesize_seconds` | Actual speech call time, including cache checks or failed synthesis; does not include model duration rewrites. |
| `fingerprint_seconds`, `prepare_seconds` | Provider fingerprint and speech preparation calls. Preparation/fingerprinting remains serial; there is no speculative reuse of a stale fingerprint. |
| Per-short `storyboard_compile_seconds` | Compilation, essential asset attachment/hash checking and reference publication. No remote assets are acquired. |
| Per-short `draft_cache_hit`, `audio_cache_hit` | Independent stage hit flags; `cache_hit` remains the old both-hit boolean. |
| Per-short `preparation_seconds` | Elapsed successful publication attempt from selecting this candidate through measured/validated required media. Includes review/rewrites/speech/assets, excludes initial acquisition/planning/queue and earlier failed attempts. |
| `{uncached,partially_cached,fully_cached}_media_seconds` and `_preparation_seconds` | Separately accumulated outputs and successful-publication preparation intervals. Partially cached means either stage hit, fully cached means both. |
| `successful_short_uncached_media_production_rate` | Fully uncached published media seconds / those successful preparation intervals. **Not sustained session throughput**: excludes plans and earlier failed attempts. |
| `uncached_output_per_active_second` | Fully uncached output / **all** active worker time, including acquisition, planning, failures and cache checks. Conservative rate: cached output contributes zero, while its processing still contributes to denominator. Inspect cache-class totals separately. |
| `first_playable_monotonic_seconds` | Creation acceptance to first durable publication within the creation process. Includes queue time; absent if the first output was only published after recovery in another process. Existing first-output measurements are retained on Retry. |
| `first_playable_active_seconds` | Active worker processing through first durable publication, excluding queue/retry downtime. |
| `first_playable_session_elapsed_seconds` | Wall-clock first-publication time minus persisted job creation; includes failure/retry downtime and is sensitive to clock adjustments. |
| Per-short `published_at`, `published_after_monotonic_seconds` | Wall timestamp for recovery/audits and, when creation-process origin is available, monotonic elapsed publication time for synthetic benchmarks. |

Legacy `ready_after_seconds`, `first_playable_seconds`, and `total_preparation_seconds` remain compatible wall-clock/session-elapsed fields. Legacy `generation_seconds`, `validation_seconds`, and `speech_seconds` also remain: the last includes duration rewrite/review inside its historical workflow span. **Do not add overlapping workflow aliases to the new call-stage totals.** Existing #5 `work_seconds` still bounds provider work; it is not the worker-turn metric. New jobs no longer emit misleading `waiting_before_short_N_seconds`; old saved metrics are retained but must be labelled historical assumed-playback estimates.

### Observed requested-content waits and privacy

An explicit outline selection of unready required media starts a monotonic browser timer. It ends as `ready` when that exact selection becomes playable, or `abandoned` when the learner changes selection/leaves/cancels. This measures actual selection-to-availability waiting, not deliberate pauses or disabled Next clicks. There is no wait timer automatically attached to audio end. Startup and speculative preload failures are not counted as these waits. A failed selection retained for Retry can include retry downtime; that is real requested-content waiting, not active processing. Ready does not prove the learner successfully started audio; autoplay rejection is separate.

Observations are **only localStorage on this device**, under `focusplay:requested-waits:v1`, at most 50 records. Records contain timestamp, short ID, elapsed seconds and outcome, never goals, source text, answers or reactions. Entries older than seven days are pruned on the next observation write (not a guaranteed background deletion deadline). Nothing is sent to a new third party or the server job event log. Clearing site data removes them. Storage-disabled/quota errors cannot break playback. Existing per-short local position/reaction/answer persistence is unchanged.

## Measurements and verification

Reproducible **fixture-only** runs (no source credits or provider requests):

```sh
.venv/bin/python scripts/benchmark.py --mode fixture --buffer-seconds 60
.venv/bin/python scripts/report_performance.py --input docs/readiness-fixture-runs.json
```

Raw results: [readiness-fixture-runs.json](readiness-fixture-runs.json). Summary: [readiness-measurements.md](readiness-measurements.md). Synthetic one-pass playback correctly produces no stalls for faster/equal production and accumulates stalls when production is slower. This is not the looping interaction model and does not measure target-hardware speed. An experimental buffer records threshold latency separately; when the total ready media cannot meet it, the threshold is explicitly `null`/not reached. The 20-clip slow-production fixture and test demonstrate that a 60-second buffer only delays eventual stalls.

**Live evaluation was not run:** source credits need approval, and no target-hardware throughput gain is claimed. The new script requires an explicit mode and credit acknowledgement and supports the 2/5/10/20-minute workloads. After approval and manually establishing/verifying the declared cold/cache state:

```sh
.venv/bin/python scripts/benchmark.py --mode live --approve-source-credits \
  --cache-state warm-uncached --hardware-notes 'Actual hardware and resource notes' \
  --budgets 120 300 600 1200 --runs 1 --buffer-seconds 60
.venv/bin/python scripts/report_performance.py --input docs/readiness-live-runs.json \
  --output docs/readiness-live-measurements.md
```

Cache labels are operator declarations; the script never deletes saved media or forces cold/uncached state. Inspect actual acquisition and stage hits. Live reports retain exact model/voice/settings, duration ledgers, acquisition calls, first-playable/queue/active/stage timings, output rates, ready-prefix one-pass stalls and experimental threshold latency. Mixed visuals are listed as produced; no script promises to force an image or unsupported format. Hardware notes and platform are captured; **peak CPU/GPU/memory and observed interactive stalls are not collected by this script**. Failed runs are preserved and labelled ready-prefix simulations, not completed sessions. No p95 or release threshold is inferred from a tiny sample. `docs/performance.md` and its imported-source measurements remain historical, not a live YouTube baseline.

Verification completed:

- Backend tests cover contiguous gaps, clamps, pause/replay/loop/jumps, question exclusion, faster/equal/slower consumption, fair progress with repeated arrivals, capacity/duplicate work, shutdown admission, stage-boundary cancellation (acquisition/planning/draft/review/speech/assets), obsolete cancelled saves, durable audio/image loss/repair, restart/retry identity and first-publication preservation.
- Browser tests cover real readiness copy, seek/jump updates, bounded two-short preload, blob cleanup on selection/exit, cancellation of in-flight fetches, essential upcoming image failure, oversized preload rejection, explicit wait recovery/local observation, duplicate/stale snapshot protection, repair UI, plus existing interaction/accessibility/autoplay/source/refresh regressions.
- OpenAPI and generated TypeScript types are regenerated; frontend production build succeeds.
- Final suites: **257 backend tests passed; 71 browser tests passed; 1 opt-in live browser test skipped.** `git diff --check` passes. The existing backend dependency deprecation warning is unchanged.

Remaining limitations: no fair wall-time guarantee for a long turn; no imminent-learner hint weighting; no automatic arbitrary-jump preparation; no provider overlap/race testing because overlap is absent; no forced cache baseline, peak-resource measurements or approved live 2/5/10/20-minute evaluation yet. Browser HTTP caches remain best effort. Asset installation repairs bundled images on restart; there is no authorised external-asset re-download path. Audio removed after a snapshot still errors explicitly at playback. No universal zero-wait guarantee.
