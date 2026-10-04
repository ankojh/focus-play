# #6 — Generation buffering and playback readiness

## Purpose and agreed context

Builder handoff for Focus Play at `/Users/ankojh/b12/focus-play`. All paths below are repository-relative.

The user wants both better teaching videos and enough videos for the requested whole-session time. These create two different requirements:

1. Enough useful content exists to fill the intended session: owned by #5.
2. Enough of that content is ready when the learner requests it: owned by this workstream.

Do not confuse content utilisation with preparation latency. A ten-minute plan with a two-minute stall is not improved by counting the stall as learning time. This workstream owns readiness measurement, prefetching, scheduling, and bounded generation lead. It must preserve current playback semantics and provider safety.

The suggested 60–90-second ready-ahead buffer is an initial tuning hypothesis, not a guaranteed user-approved threshold. Measure real generation rates and startup trade-offs before making it a default gate.

## Current implementation to inspect

- `backend/app/jobs.py`: one worker, `asyncio.PriorityQueue`, reserve/enqueue, `advance`, stage publication, requeue, cancellation, recovery, and metrics.
- `backend/app/providers.py`: one streamed model request at a time, speech generation, cancellation, file writes, and speech cache metadata.
- `backend/app/store.py`: full-lesson JSON saves, RLock, events, and recovery.
- `backend/app/main.py`: SSE snapshot/progress/done flow and audio serving.
- `backend/app/config.py`: queue size, provider defaults, context limits.
- `frontend/src/App.tsx`: SSE reconnection, polling/snapshot application, active-short selection, readiness props.
- `frontend/src/Player.tsx`: current media preload, navigation, loops, autoplay error handling, and local playback persistence.
- `scripts/benchmark.py`, `scripts/report_performance.py`, `docs/performance.md`, `docs/youtube-source-change.md`.

Current flow:

1. A request creates a lesson and queues it.
2. The first `advance()` may acquire sources, plan, and generate the first short.
3. The worker publishes one short, then requeues remaining work at a different priority.
4. Generation, review, and speech currently run sequentially within a short. Model operations are intentionally local and serialized.
5. Later shorts are prepared while an earlier one can play, but there is no measured ready-ahead policy tied to learner position.
6. `waiting_before_short_N_seconds` is derived from assumed immediate forward playback and question allowances. It is not observed user stall telemetry.
7. The browser preloads the current audio element; it does not have a full adaptive next-media preload policy.
8. SQLite locking protects database calls, not arbitrary concurrent mutation of independent loaded copies of a lesson. Adding worker concurrency risks lost updates.

`docs/performance.md` describes historical imported-source results on one machine. It is not a verified live YouTube throughput baseline. Do not use it to promise that richer storyboards or 20-minute sessions will stream without waiting.

## Preserve current uncommitted work and interaction model

At handoff creation the working tree already contains changes to:

- `frontend/src/App.tsx`
- `frontend/src/Player.tsx`
- `frontend/src/styles.css`
- `frontend/tests/app.spec.ts`
- `frontend/tests/live.spec.ts`

Inspect and preserve these diffs. Current shorts loop until the learner navigates, use wheel/swipe/keyboard controls, and expose like/dislike reactions. Removed extra-explanation buttons must not be restored by this workstream.

The current player does **not** automatically advance when audio ends. Therefore:

- Do not implement a scheduler based on the assumption that `onEnded` always requests the next short.
- Do not change looping into automatic forward playback as an optimisation.
- Continuous one-pass playback can be used as a synthetic throughput benchmark, but must be labelled as such.
- Learners may jump ahead or backward. Availability forecasts are conditional, not guarantees.
- Pauses/replays/questions do not reliably provide a fixed amount of generation lead.

## Goals and non-goals

### Goals

- Preserve fast first playable output and clearly expose preparation state.
- Maintain a useful contiguous run of ready content after the active short when feasible.
- Avoid starting excessive preparation or asset preloads for work the user cancelled.
- Identify actual bottlenecks and report meaningful readiness/stall metrics.
- Keep scheduling fair across multiple active lessons.
- Remain recoverable under restart, failure, duplicate progress events, and retry.

### Not goals

- Guarantee uninterrupted playback on every machine or arbitrary seek pattern.
- Replace local inference with a cloud service without approval.
- Add unlimited concurrent LLM calls or media downloads.
- Modify the requested session duration or count waiting as content.
- Add an automatically enforced timed-session mode.

## Readiness model

Keep distinct states/metrics:

- **First playable:** first short has validated metadata and durable required media.
- **Server ready-ahead:** contiguous measured media available after/including the remaining active content, using a clearly documented definition.
- **Client preload readiness:** media actually fetched/decodable in the current browser, distinct from server publication.
- **Production rate:** new playable media seconds produced per wall-clock generation second, excluding cache hits or reporting them separately.
- **Requested-next stall:** user attempts to move to an unavailable required next item and waits, distinct from a deliberate pause.
- **Startup delay:** request acceptance to first playable and, separately, to any optional recommended buffer.

A conservative media-only ready-ahead calculation is:

```text
remaining measured media in current ready short
+ measured media of contiguous subsequent ready shorts
```

Stop at the first unready item. Do not sum noncontiguous ready shorts beyond a gap as if they prevent that gap. Do not repeatedly add the current loop duration. Track practice allowances separately: learners may answer instantly, slowly, or skip them.

Define how ready-ahead changes when the user selects a different short, seeks, pauses, or leaves the lesson. A browser can calculate the immediate figure from the snapshot and playback position. If backend scheduling needs current position, add a minimal bounded playback hint with expiry; do not send updates every animation frame or put high-frequency position events into the persisted job event log.

Playback hints are advisory, not authoritative changes to the lesson. Define behaviour for two tabs or two clients so they cannot starve one another or repeatedly reorder a plan.

## Proposed delivery sequence

### Phase A: measure before changing concurrency

Add reproducible timing instrumentation:

- Acquisition/search/transcript/ranking time and cache status.
- Plan and continuation-planning time.
- Draft, review, repair, speech, and asset preparation time per short.
- Measured media duration per short.
- Queue wait and publish timestamps.
- First playable latency and contiguous server-ready-ahead over a simulated session.
- Observed client stalls where the UI actually waits for requested content.

Use a monotonic clock for elapsed intervals. Persist wall-clock timestamps only where required across restarts and define their limitations. Existing elapsed metrics based on job creation include time between failures/retries; distinguish session elapsed from active processing time.

Create an explicit benchmark mode using fixtures for scheduler behaviour and a separate live benchmark for local provider throughput. Label cold, warm uncached, partially cached, and fully cached cases. Do not infer p95 from a tiny sample.

### Phase B: ready-ahead and preload without model concurrency

- Keep first ready content playable immediately; do not force a 90-second startup wait without evidence and a deliberate UX decision.
- Show an honest status such as “Next two shorts ready; preparing the rest.”
- Optionally show when a recommended buffer has accumulated, without disabling early Play by default.
- Prioritize contiguous next required work over distant optional extensions where the existing worker can do so safely.
- Prefetch a bounded number of upcoming ready audio files, with cancellation/cleanup and memory/network limits.
- Include essential image/visual assets from #3 in readiness. An audio-only ready flag is insufficient if the explanation requires an unavailable image.
- Preserve gesture boundaries and disabled/unavailable state semantics. If a wait view is added, make navigation intent explicit rather than silently skipping unready teaching.

Do not mark a short ready just because its narration draft exists. All necessary validated metadata and durable media must be present before publication.

### Phase C: throughput optimisation only if measured necessary

Start with low-risk improvements:

- Reuse valid caches with complete fingerprints.
- Avoid repeated model/provider fingerprint or preparation work when it can be safely reused.
- Bound prompt size and replace full prior narration with the compact coverage ledger from #2/#5.
- Avoid unnecessary duplicate validation/model calls while retaining support checks.
- Keep the model warm using the existing local-provider policy where appropriate.

If generation is consistently slower than consumption, a small buffer only delays a stall. For example, 35 seconds of media requiring 50 seconds of serial preparation consumes lead over time. Choose among more initial preparation, cheaper/faster validated generation, or a clearly disclosed waiting experience. Do not promise no stalls from buffering alone.

Safe pipeline overlap is an optional measured optimisation, not the starting assumption. It might overlap approved speech work for one short with drafting the next, while still serializing model calls. Implement only with:

- Explicit stage ownership and bounded queues.
- One authoritative lesson mutation path or revision-aware atomic updates.
- Provider thread-safety verified; the existence of `Speech.lock` is not proof all call paths use it.
- Content-hash/cache file writes protected against same-key races.
- Cancellation and shutdown propagated to every in-flight stage.
- No ready publication from an obsolete/cancelled plan revision.
- Memory/CPU/GPU contention measured, including whether overlap actually makes both stages slower.

Do not dispatch multiple `advance()` calls for the same lesson concurrently and assume the SQLite RLock makes the higher-level workflow safe.

## Scheduling and fairness

The current worker uses new-work and continuation priorities. Any ready-ahead policy should define:

- A bounded amount of first-playable work before yielding.
- Starvation prevention for longer existing lessons when new requests arrive repeatedly.
- Priority for the active lesson's imminent required content without starving all other lessons.
- Interaction with new optional extension planning from #5.
- What happens when playback hints expire, the tab closes, or a learner revisits a saved ready lesson.
- Queue capacity and backpressure for acquisition, drafting, speech, and assets if stages are separated.

Keep prerequisite/sequence order intact. Scheduling priority is not permission to reorder the teaching plan or change the user's active short.

## Error, cancellation, and recovery behaviour

- A source/provider failure must not hide already-ready content.
- Retry should reuse valid stages/media and preserve plan identities and acquisition limits from #5.
- A missing current/next audio asset should surface repair behaviour rather than an infinite buffering spinner.
- Browser autoplay rejection is not a generation failure.
- SSE reconnect must restore the current snapshot without creating a new lesson or resetting the selected short.
- Duplicate events and stale snapshots must not downgrade a ready item or resurrect cancelled work.
- If paused, stop playback-time accounting; generation may continue within the existing authorised job.
- If cancelled, stop new work and prefetching while preserving completed valid outputs according to current product behaviour.
- On shutdown, stop accepting new stage work, signal providers, drain/terminate safely, then close storage.

If observation of skipped/waited content is added, document local telemetry retention and avoid sending learner goals or playback behaviour to a new third party.

## Integration and ownership

- [#5 Duration and coverage](05-session-duration-and-evidence-coverage.md) owns plan expansion, content estimates, and acquisition limits. Consume its stable activity IDs and plan revisions.
- [#1 Storyboards](01-visual-storyboards-and-audio-sync.md) owns the compiled timeline; richer output may alter preparation cost.
- [#2 Teaching](02-teaching-quality-and-lesson-coherence.md) owns coherent sequence and compact semantic history.
- [#3 Mixed visuals](03-mixed-visual-formats-and-assets.md) owns essential assets and their ready criteria.
- [#4 Polish](04-presentation-captions-and-narration-polish.md) owns the visual treatment of preparing/waiting states and current controls.

Likely files: `jobs.py`, `providers.py`, `store.py`, `contracts.py`, `main.py`, `App.tsx`, `Player.tsx`, benchmark scripts, and tests. Add small scheduler/metrics helpers rather than hiding concurrency inside provider methods. If API fields/endpoints change, regenerate OpenAPI and TypeScript types. Version cache/state semantics and retain old saved lessons.

## Tests and acceptance criteria

### Deterministic scheduler tests

Use controlled fake clocks/providers, not timing-sensitive sleeps where avoidable:

- Production faster than, equal to, and slower than a simulated one-pass consumption rate.
- First-playable publication before total lesson completion.
- Correct contiguous ready-ahead calculation, stopping at an unready gap.
- Pause, replay, loop, seek forward/backward, and jump to another ready short.
- Question time treated separately from guaranteed playback lead.
- Two lessons under load, repeated new arrivals, and bounded fair progress.
- Cancel during model generation, review, speech, acquisition, and asset prefetch.
- Restart/retry with partly completed stages and cached outputs.
- Same-key media generation races if overlap is introduced.
- Stale stage completion cannot overwrite a newer/cancelled lesson revision.
- Queue/memory limits are enforced and errors are actionable.

### Browser tests

- Existing looping, gesture, like/dislike, keyboard, source, and refresh tests remain passing.
- Next-ready status reflects real snapshot data.
- Prefetch is bounded and cleans up when lesson/selection changes.
- Missing media and blocked autoplay are distinguished.
- Reconnecting events does not duplicate lesson creation or reset playback unexpectedly.
- Any waiting UI can recover to the requested short without skipping or unsolicited navigation.
- Reduced motion and accessibility remain usable during preparation.

### Live evaluation

Run representative 2-, 5-, 10-, and 20-minute workloads when the new planner supports them, with source credits approved. Include rich-storyboard/mixed-asset cases as those workstreams land. Report:

- Actual hardware/model/voice and settings.
- Cache/cold/warm status and source acquisition calls.
- First-playable latency and recommended-buffer latency.
- Media production rate and stage breakdown.
- Simulated sequential stalls separately from observed interactive stalls.
- Ready-ahead distribution, resource use, failures, and retry behaviour.

Set release performance thresholds against a measured baseline on the target hardware. Do not fabricate a universal zero-wait guarantee or claim performance improvement from fixture tests alone.

Definition of done: readiness is accurately measured/exposed, prefetching and scheduling are bounded, startup is not unnecessarily blocked, current interactions remain intact, recovery is safe, and any claimed throughput gains are supported by measurements.

## Verification and handback

```sh
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python scripts/export_openapi.py
npm run types --prefix frontend
npm run build --prefix frontend
npm test --prefix frontend
```

Use `scripts/benchmark.py` for live measurements only after checking its assumptions against the new plan/player behaviour and provider configuration. Deliver scheduler design notes, metric definitions, tests, raw and summarized measurements, cancellation/recovery evidence, and remaining limitations. Do not commit or push without permission; follow repository identity and Conventional Commit policy if later authorised.
