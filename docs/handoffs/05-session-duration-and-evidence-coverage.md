# #5 — Session-duration planning and sufficient evidence coverage

## Purpose and agreed product decision

Builder handoff for Focus Play at `/Users/ankojh/b12/focus-play`. Paths below are repository-relative.

The user wants enough generated videos for the time entered and selected **whole learning session** as the meaning of that time. Count one intended pass through videos plus explicit practice/question allowances. User pauses, replays, looping, skips, and actual answering speed can change elapsed time.

Recommended product promise:

> Approximately X minutes of videos and practice. Pauses and replays may take longer.

Recommended target: final planned session content falls within **90–100% of the requested budget**, when useful source-supported content is available. This band is a proposed acceptance target from the discussion, not a justification for filler or a guarantee for every topic/source outage.

This workstream owns time accounting, bounded plan expansion, and evidence coverage sufficient for the requested session. It is the first recommended implementation priority. Do not start by merely raising a short-count constant.

## Current implementation and concrete cause

Read:

- `backend/app/jobs.py`: `advance`, `acquire`, `context`, `complete`, `explain`, retry/cancel paths.
- `backend/app/contracts.py`: `LearningRequest`, `Objective`, `LessonPlan`, `Short`, `Question`, `Lesson`.
- `backend/app/validation.py`: `planned_duration`.
- `backend/app/providers.py`: prompts, context/output bounds, speech duration repair, cache fingerprints.
- `backend/app/sources.py`: `retrieve` and search limits.
- `backend/app/youtube.py`, `backend/app/ranking.py`, `backend/app/config.py`.
- `backend/app/store.py`: persisted lesson JSON, request idempotency, events, recovery.
- `frontend/src/App.tsx`: requested versus planned time, outline, incremental updates.
- `backend/tests/test_core.py`, `backend/tests/test_youtube.py`, `frontend/tests/app.spec.ts`.

Current behaviour:

1. Input accepts 60–1200 seconds. The UI includes custom time up to 20 minutes.
2. `max_shorts = min(8, budget_ms // 46667)`.
3. `LessonPlan.objectives` also has `max_length=8`.
4. Planning asks for **1 to max_shorts** objectives and allows partial topic coverage. There is no minimum utilisation objective.
5. `planned_duration()` treats every unfinished short as 40 seconds, then substitutes measured speech once ready; questions reserve 20 seconds.
6. Each clip is at most 40 seconds; every third core short requires a question.
7. Eight maximum-length shorts plus two question allowances total 360 seconds. Thus the current core plan cannot provide more than six minutes even for a 20-minute request.
8. Once all originally planned shorts are ready, the lesson is marked complete. No measured-duration top-up exists.
9. Retrieval selects at most 20 segments under a 4500-character text budget by default. More total sources does not mean the planner sees sufficient topic coverage.
10. Acquisition normally stops after some sources are usable; sufficiency asks whether any useful teaching is possible rather than whether a full session is supportable.
11. Search-attempt variables are local to `advance()`. A new adaptive loop must persist its limits; otherwise retries/continuations could accidentally multiply provider spend.

A historical imported-source benchmark in `docs/performance.md` produced about 69 seconds of planned content for a 300-second request. That supports the diagnosis historically; it is not a current YouTube-flow performance measurement.

## Preserve current player and user work

Pre-existing uncommitted changes affect `frontend/src/App.tsx`, `frontend/src/Player.tsx`, `frontend/src/styles.css`, `frontend/tests/app.spec.ts`, and `frontend/tests/live.spec.ts`. Inspect and preserve them.

Current shorts loop until the learner navigates using scroll/swipe/buttons/keyboard. Likes/dislikes replace removed extra-explanation controls. Therefore “10-minute session” must mean intended unique content plus allowances, not a forced wall-clock timer. Do not change looping or restore old controls to make the duration metric look correct.

The backend still supports explicitly approved extra explanations through `extra_allowance_ms`. Keep that accounting separate from automatic in-budget extensions even if the current UI does not expose it.

## Non-negotiable invariants

- Ready content is source-supported, validated, and actually playable.
- The original requested budget is immutable; user-approved added time is separate.
- No automatic extension increases authorised time or silently calls `explain()` with fake user consent.
- No padding with silence, slowed voice, duplicate paraphrases, decorative waits, or irrelevant topic expansion.
- New source acquisition has persisted limits and actionable quota/access failures.
- Already published shorts retain stable IDs, order, audio, and content during adaptive replanning.
- Cancellation/restart/retry cannot duplicate extensions or reset acquisition allowances.
- Final measured media plus planned practice allowances does not exceed the authorised budget.
- A target shortfall is visible and explained; it is not disguised as a full-length session.

## Proposed duration model

Separate concepts currently collapsed into `planned_duration_ms`:

| Quantity | Meaning |
| --- | --- |
| Requested budget | Original learner-entered session time |
| Approved extra allowance | Explicitly authorised additions, separate from the original session target |
| Measured ready media | Actual audio/media length already published |
| Reserved practice | Planned answering/feedback allowances, counted once |
| Estimated unready media | Prediction for committed, not-yet-ready items |
| Reserved closing | Recap/final-check time, counted once even if represented by a queued item |
| Forecast total | Measured content plus all remaining estimates/reservations |
| Final planned content | Measured media plus actual scheduled practice allowances after completion |
| Utilisation | Final original-session content divided by original requested budget |

Use integer milliseconds for ledger arithmetic. Treat question time as an allowance, not measured user time. Generation wait time is not learning content and must not be counted toward the fill target.

Recommended addition: a versioned planning state with stable activity IDs, estimates, core/extension/closing roles, plan revision, coverage state, acquisition ledger, expansion attempts, and completion reason. Exact field names are implementation choices. Defaults/adapters must keep legacy lesson JSON readable.

Keep compatibility meaning for existing `planned_duration_ms`, or migrate/version its semantics explicitly. The UI must distinguish forecast from final content rather than silently changing what a displayed number represents.

## Curriculum and count planning

Coordinate with [#2 Teaching quality](02-teaching-quality-and-lesson-coherence.md). Plan useful outcomes before selecting the number of clips.

Divide the plan into:

- **Core:** necessary concepts and applications for the requested outcome.
- **Extensions:** evidence-supported examples, comparisons, misconceptions, or applications that deepen the same goal.
- **Closing:** recap and final check.

Do not equate an objective with exactly one short in every case. A concept may require an explanation and an application; a short must still have one clear teaching purpose.

Replace the fixed eight-short ceiling with bounded dynamic planning. Derive operational limits from maximum supported session duration and an explicit minimum useful clip duration, plus a hard safety cap. The precise minimum/cap should be chosen and documented from measured clips; do not silently cap all long sessions at an arbitrary count that reintroduces underfilling.

Generate the plan in bounded batches if needed. Do not ask the local 2200-output-token model to return dozens of fully detailed objectives, storyboards, and evidence maps at once. Keep a compact coverage ledger rather than all earlier narration in every prompt.

Illustrative 600-second allocation, not a fixed recipe:

- 14 teaching/example shorts averaging 35 seconds: 490 seconds.
- Four practice allowances of 20 seconds: 80 seconds.
- One recap short: 30 seconds.
- Total: 600 seconds.

Actual measured audio will differ, which is why adaptive reconciliation is required.

## Duration prediction

Start with a conservative prior for the configured voice, then calibrate using measured seconds per spoken word and relevant recent clips. Key estimates by voice/provider and any meaningful speech-setting changes. Do not mix macOS development speech with Kokoro statistics.

- Track expected duration and prediction uncertainty separately from the strict 40-second cap.
- Use target words/beat lengths to guide drafting, then validate actual synthesized duration.
- Incorporate deliberate pauses in measured waveform duration if #4 introduces them.
- Treat existing 40-second unfinished reservations as a safety bound, not the only estimate for deciding how much to teach.
- Do not reject a good plan solely because every unfinished short could theoretically be 40 seconds. Instead constrain per-short targets, reserve headroom, and reconcile before publication.

A short that is too long for the remaining budget can be repaired while unpublished, deferred as an unused extension, or replaced by a shorter supported closing. Never speed up playback or truncate already-published audio to force a fit.

## Bounded adaptive planning algorithm

Recommended flow:

1. Acquire initial evidence within the normal provider limits.
2. Build a core/extension/closing outline and coverage map; reserve practice and closing time.
3. Commit a bounded batch of stable activities with target durations.
4. Draft, review, synthesize, and measure each candidate short.
5. Reconcile its measured duration against remaining authorised content time **before marking it ready**.
6. Publish a valid candidate, update the ledger, and persist the revision atomically enough to survive retry.
7. At bounded checkpoints, update estimates for queued activities.
8. If projected final utilisation is below target, select a distinct supported extension that fits after required core and closing reservations.
9. If that extension lacks evidence, run focused acquisition under the persisted acquisition ledger.
10. If forecast exceeds the budget, remove/defer only unpublished optional extensions or repair unpublished scripts; do not reorder already-ready content.
11. Once core/selected extensions are complete, produce the reserved closing sized to remaining time.
12. Complete with an honest result: target met, useful coverage exhausted, source/credit limit reached, or operational generation limit reached. Provider failures remain distinguishable from a valid shorter lesson.

Illustrative reconciliation:

```text
remaining_for_extensions =
    authorised_budget
    - measured_published_media
    - all_scheduled_practice_allowances
    - estimated_unready_core_media
    - reserved_closing_media
    - already_committed_extension_estimates
```

Avoid double-counting closing/practice when they already appear in activity estimates. Define one canonical aggregation function and test it thoroughly.

The 90% lower band is a target, not an endless while-loop condition. Bound expansion count, total generated candidates, total model calls/repairs, acquisition attempts, and wall-clock work. Persist stop reasons and enough state for idempotent continuation.

## Evidence sufficiency and acquisition policy

A single `sufficient_evidence` boolean is not enough for time-aware lessons. Track concept-level coverage:

- Objective/outcome ID.
- Supporting source segment IDs.
- Coverage for definition/mechanism/example/caveat as applicable.
- Already-used learning claims.
- Missing coverage and a focused acquisition query intent.

Assess support, not transcript word count alone. Three near-duplicate videos may offer less useful coverage than one detailed source.

Retrieve focused passages per concept/batch. Preserve source diversity and adjacent context. Do not simply remove retrieval bounds or feed entire transcripts into every model call.

Acquisition must:

- Reuse valid cached search/transcript data and record cache hits separately.
- Track tried video IDs, query/round usage, transcript attempts, and actual provider calls across continuation and retry.
- Respect existing caption availability handling, rate limiting, and quota/authentication error semantics.
- Set explicit per-lesson limits; increasing existing limits requires documented cost implications and user approval where appropriate.
- Stop when additional evidence is redundant or cannot cover the missing concepts.
- Never use search snippets or arbitrary model knowledge as teaching evidence.

If the goal is genuinely narrow, return the useful shorter session with a clear explanation. Offering the user a broader related goal can be future UI work; do not silently broaden it.

## Persistence, retries, and compatibility

- Store planning revisions and selected extension IDs before generation so retry selects the same work.
- Preserve source attempt ledgers through failures and restarts. A deliberate new user request can have a new budget; an automatic retry must not reset it silently.
- Keep cache keys sensitive to plan semantics, source identity, evidence, target duration, speech settings, and prompt/schema versions where relevant.
- A new target duration must not accidentally reuse an unsuitable old draft solely because objective text matches.
- Do not repurpose `Short.optional` without considering existing semantics for user-added explanations. Introduce a separate curriculum role if needed.
- Audit `lesson.objectives[min(core_index, ...)]` template selection: adaptive activities need stable objective/plan IDs, not fragile positional inference.
- Old ready lessons retain their content and duration. New target policy applies to new lessons unless an explicit migration/regeneration action is approved.
- Preserve request idempotency, ready-output recovery, missing-media repair, source attribution, and event sequencing.

## UI requirements

Update `frontend/src/App.tsx` and relevant types to distinguish:

- Requested session time.
- Current estimated total while preparation continues.
- Measured video time plus practice allowance.
- Ready count versus planned/expanding outline.
- Final shortfall and reason where applicable.

Suggested honest copy: “About 9m 35s of videos and practice planned for your 10-minute session.”

Do not show “complete: 10 minutes” for six minutes of unique content. Do not count repeated loops toward original-session utilisation. The outline may expand while generation continues, but it should not move the currently selected short or remove ready items.

## Implementation map and dependencies

- Add a pure duration-ledger/planning helper module rather than embedding all arithmetic in `Jobs.advance()`.
- `contracts.py`: versioned plan, coverage, estimates, outcome roles, completion reasons, compatible defaults.
- `jobs.py`: batch planning, measured reconciliation, adaptive extension, safe completion gate, stable objective mapping.
- `validation.py`: canonical duration aggregation and validation.
- `providers.py`: bounded planner prompts, target-aware draft prompts, cache/version changes.
- `sources.py`, `youtube.py`, `ranking.py`: focused coverage-aware acquisition without losing safeguards.
- `store.py`: persistence/recovery of new state; guard against lost updates as #6 evolves scheduling.
- `App.tsx`: honest forecast/final duration and shortfall UI.
- Regenerate OpenAPI and generated frontend types.

[#1 Storyboards](01-visual-storyboards-and-audio-sync.md) consumes target durations. [#2 Teaching](02-teaching-quality-and-lesson-coherence.md) determines useful extensions. [#3 Mixed visuals](03-mixed-visual-formats-and-assets.md) and [#4 Polish](04-presentation-captions-and-narration-polish.md) must report actual media time. [#6 Buffering](06-generation-buffering-and-playback-readiness.md) manages generation lead and must not invent a second session budget.

Recommended overall build order: implement this ledger/coverage foundation with #2's minimal plan contract; add #1; improve #2/#4; expand #3; measure and tune #6 throughout. File numbers are workstream identifiers, not a mandate to implement in numeric order.

## Tests and acceptance criteria

### Deterministic tests

Use fake model/speech/source providers; no live credits in unit tests.

- Budgets of 60, 120, 300, 600, and 1200 seconds plus non-round valid budgets.
- Adequate evidence and bounded-duration fixtures achieve 90–100% utilisation with no overrun.
- Demonstrate a 10/20-minute plan can exceed eight shorts and contains distinct useful outcomes.
- Actual speech shorter than prediction triggers bounded meaningful top-up.
- Actual speech longer than prediction repairs/trims unpublished work without changing ready clips.
- Practice and closing are counted exactly once, including adaptive placement changes.
- One-minute budgets do not over-reserve an impossible number of questions or closing beats.
- Narrow goals and limited evidence finish honestly below target, with no duplicate filler.
- Quota/authentication/network failures remain actionable and distinct from coverage exhaustion.
- Retry/restart never duplicates extensions or resets acquisition/model-call limits.
- Cancel during acquisition, drafting, synthesis, or extension planning preserves ready outputs.
- Original and user-added allowances are separate and idempotent.
- Legacy lessons deserialize/play without being automatically expanded.
- Context and output requests remain bounded for a 20-minute lesson.
- Property-based/random-duration tests confirm ledger conservation and no negative/double-counted reservations.

### Browser and live evaluation

- Forecast updates, dynamic outline, selection stability, and under-target copy are correct.
- Looping/reactions/gestures/refresh still behave as the current tests require.
- Run a representative live matrix only with configured providers and credit awareness. Record requested time, final measured media, practice allowance, utilisation, evidence coverage, unique outcomes, retrieval calls, cache hits, generation time, and failure reason.
- Do not assert guaranteed wall-clock session duration from planned allowances.

Definition of done: sufficient-evidence cases meet the target band without overrunning or padding; insufficient-evidence cases are truthful and bounded; retries are safe; the UI explains what the duration means; and long sessions are no longer structurally limited to six minutes.

## Verification and builder handback

```sh
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python scripts/export_openapi.py
npm run types --prefix frontend
npm run build --prefix frontend
npm test --prefix frontend
```

Deliver the ledger/plan contract, migration notes, bounded-limit defaults and rationale, deterministic tests, utilisation reports, measured provider-cost/performance data where run, and documented remaining limitations. Do not commit or push without permission; follow repository identity and Conventional Commit policy if later authorised.
