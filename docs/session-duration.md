# Session duration and evidence coverage (#5)

## Product semantics

The requested 60–1200 seconds means one intended pass through unique videos plus scheduled question/practice allowances, **not a forced wall-clock timer**. Pauses, replays, skips, loops and answering speed affect elapsed learning time. Generation waiting is never counted. The UI shows requested time, the changing forecast, measured ready media and scheduled practice; completed under-target sessions include a reason. Current looping, reactions, Sources toggling, gestures, keyboard navigation and saved selection are unchanged.

The original target is **90–100%** utilisation when useful, supported content can fit. It is not a promise to fill narrow goals or outages. No silence, slower speech, repeated introductions or unapproved topic expansion is used to fill time. Explicitly approved extra explanations still have their separate 40-second allowance, maximum three; automatic extensions never call `explain()` or consume that extra pool.

The working tree was clean at the beginning of this implementation. The player and existing presentation files were inspected; `Player.tsx`, `styles.css` and `live.spec.ts` were not changed. No commits or pushes were made.

## Ledger and contracts

`backend/app/planning.py` is the pure aggregation/policy module. `aggregate()` is the only duration summation implementation, also used by the compatibility `validation.planned_duration()` function. Integer milliseconds are used throughout accounting.

For every activity:

- Ready audio uses the actual measured waveform duration.
- Unready media uses its explicit `target_duration_ms` estimate.
- A question adds its allowance once, whether represented by `question_required` or a generated question, never twice.
- Queued closing media is placed in `reserved_closing_ms`, not also in `estimated_unready_media_ms`.
- `forecast_total_ms = measured_ready_media_ms + estimated_unready_media_ms + reserved_closing_ms + reserved_practice_ms`.
- `final_content_ms` is null until completion; all remaining items must be playable/ready before a final value is published.
- Original and approved-extra content totals are independent. Publication capacity and the final gate enforce both pools, even if their combined total could otherwise hide an original-session overrun.
- `shortfall_ms` is the deficit **against the 90% target**, not the full difference from 100%. Final copy always states actual content versus requested time, even inside the target band.

`Lesson.planning` and `Lesson.duration_ledger` are version 2. Planning contains a revision, stable short/concept identities, candidate/model/expansion/work limits, deferred concept IDs, concept-level evidence/facet mapping, used claims, missing facets/query intents and a completion reason. The existing teaching contract remains version 2; the bounded model planner task is version 3. `Short.optional` still means an approved extra, not an automatic curriculum extension. Curriculum roles remain core/extension/closing.

`planned_duration_ms` retains its measured-ready + unready-forecast + practice meaning. Version-2 queued forecasts are explicit targets rather than unconditional 40-second reservations; the versioned ledger and UI make this change explicit. `original_planned_duration_ms` remains the initial committed forecast, not the immutable budget; the budget is always `request.time_budget_seconds`.

## Planning, measurement and publication

1. Acquire initial source-supported material within the existing two-round source allowance.
2. Ask for a compact batch of core outcomes and a useful closing, informed by the learner's goal/knowledge. A genuinely narrow one-clip goal can finish with its own takeaway instead of reserving a separate recap.
3. Commit stable short IDs, objective IDs, targets and evidence before drafting. Stable concept lookup replaces positional inference for new activities; the legacy positional adapter remains for old unfinished shorts.
4. Retrieve focused, bounded passages for each short, including its required evidence IDs. Existing diversity and adjacent-passage selection remain in place.
5. Guide drafting with target milliseconds and voice-specific target words. Keep the existing source/teaching review, storyboard validation, strict 40-second media cap and fixed voice speed.
6. Measure synthesized audio and check its **original or extra pool** capacity before ready publication. Capacity protects the useful minimum for other committed unpublished work and reserves scheduled practice once.
7. Repair an overlong unpublished draft once and re-review it. A supported optional curriculum extension/closing that still cannot fit is deferred, along with unpublished dependents, rather than published over budget. Required core or provider failures remain actionable failures.
8. Reconcile queued estimates only; published IDs, order, script, scenes, audio and measurements remain unchanged.
9. At the end of each committed teaching batch, compare measured content plus the useful closing minimum against the target. Select distinct in-goal extensions if evidence and remaining time permit. Insert before **unpublished** closing; never insert before published content or reorder a ready clip.
10. Generate closing to the remaining capacity, then complete with target met, coverage exhausted, source limit, generation limit or budget-fit reason. A short final closing cannot launch an endless recap loop.

Duplicate concept IDs/outcomes proposed by an extension planner are filtered as exhaustion, not published as filler. New extensions must pass plan structure, distinct-outcome, dependency, evidence, source-review and teaching-review checks. Semantic support and distinctness still rely partly on the same local model and are not independent proof of pedagogical quality.

## Bounded defaults and rationale

| Limit | Default / derivation |
| --- | --- |
| Operational minimum target | 15,000ms; calibrated upward for slower voices |
| Initial clip target | 30,000ms; strict measured maximum remains 40,000ms |
| Activity ceiling | `min(80, ceil(requested_ms / 15000))` |
| Planner batch | At most 4 outcomes, not dozens of detailed objectives |
| Total planning attempts | At most the activity ceiling, persisted before calls; includes initial/focused re-planning |
| Candidate attempts | `3 * activity_ceiling + 9`, persisted; retries consume the same allowance |
| Model call units | `36 * activity_ceiling + 60`; each logical model call reserves 3 units for its initial/schema-repair maximum before execution |
| Provider work-time stop | 7,200 accumulated provider-work seconds per lesson, checked before calls and retained through retry |
| Source search rounds | 2 total per lesson, shared by initial, focused and approved-extra acquisition |
| Transcript attempts | `2 * RANK_CANDIDATES`, default 16; at most `RANK_CANDIDATES` (default 8) per round |
| Retrieval | At most 20 passages / 4,500 source-text characters per call |
| Speech calibration | Latest 16 measured clips; robust median ms/word and median absolute deviation, keyed by complete speech fingerprint |
| Model output / context | Existing configured bounds; planner schema restricts output to 4 objectives; compact all-outcome list plus last 4 coverage summaries, not all earlier narration |

The existing measured Kokoro `af_heart`, speed-1 illustrative samples in [measured-captions.json](presentation-audio/measured-captions.json) contain **66 words / 25,825ms** (~391ms/word) and **57 words / 26,875ms** (~471ms/word). These support a rounded **430ms/word prior**, 30-second target and a 15-second operational minimum near the existing 30-word storyboard floor. They are only two observations, not a voice-wide performance guarantee. The minimum rises to `max(15000, 30 * calibrated_ms_per_word + 1000)` for slower observed speech, avoiding impossible tiny closing/extension targets. Kokoro and macOS profiles, voices, revisions and speed changes do not share samples.

The 80-activity ceiling derives from the supported 20-minute maximum and minimum useful target rather than an arbitrary eight-short ceiling. It is a spend/safety cap, not a requirement to generate 80 clips. Very short measured speech, rejected candidates or uncooperative provider/model output can still produce an honest shortfall instead of unlimited generation.

**Source limits were not raised.** At default settings a cold successful search allowance is at most **202 YouTube quota units** (two `search.list` calls at 100, two `videos.list` calls at 1) and **16 Supadata native-caption attempts/credits**, including unavailable captions. Actual usage can be lower. Cache hits consume an operational round/attempt but not an external request. Authentication/quota/network failures remain distinct from valid coverage exhaustion. `TRANSCRIPT_NETWORK_FAILED` and timeouts no longer masquerade as inaccessible captions.

The ledger separates conservative logical cache-miss reservations (`search_provider_calls`, `transcript_provider_calls`) from started HTTP attempts (`youtube_http_calls`, `transcript_http_calls`) and YouTube quota units. HTTP-boundary audits persist before requests, including failures. A crash at that boundary is conservatively charged; counters do not claim that a remote service billed a request it never received. Cache hits are recorded separately. No live cost increase or external evaluation was authorised/run.

## Evidence coverage and acquisition

Coverage maps stable outcome IDs to source segment IDs, supported facets inferred from the declared teaching role, and the latest used claim summary. The planner can declare missing definition/mechanism/example/caveat/application facets with a focused query intent. When no additional supported outcome exists, return the useful shorter session; only specific missing support or an unsupported goal triggers focused acquisition.

Expansion retrieval prefers previously unused passages while preserving source diversity, adjacency, exact required evidence and the existing context limits. It does not ingest entire transcripts, use search snippets as evidence or equate transcript size with learning coverage. A detailed already-used passage can still be retrieved and support a distinct application; source/teaching review decides whether it is genuinely distinct.

Acquisition rounds persist query, candidate list, tried video IDs, transcript attempt count and successful pending source IDs **before/after each spend boundary**. Successful pending transcripts survive cancellation before ranking; retry ranks/commits them without refetching. Search/transcript caches keep their existing identity/TTL safeguards. Source access errors retain actionable error codes. Automatic retry/restart does not reset any acquisition, model, candidate or expansion allowance; if exhausted, a deliberate new learning request is required.

## Persistence and compatibility

- No SQL schema migration: new state lives in the existing atomically saved lesson JSON snapshots and ordered events. OpenAPI and generated frontend types were regenerated.
- Missing planning/ledger fields default to **None** for old lessons. Old ready lessons are not expanded, re-timed or regenerated automatically. Legacy unfinished shorts retain 40-second defaults and old objective mapping.
- An empty, interrupted old job may adopt the new policy when explicitly retried and newly planned; this never rewrites old ready content.
- Source-ledger defaults adapt old JSON. Before its first source round, legacy acquisition is clamped so it cannot raise a smaller configured source limit.
- `Store.save()` now preserves a concurrently persisted cancellation decision and monotonic event sequence while still saving work/spend reservations. Explicit retry uses a resume flag.
- Retry preserves committed IDs and pending batches. Missing-media repair reuses the published narration and audio key, not a newly calibrated draft. It refuses changed voice settings or changed measured phrase boundaries instead of silently replacing the published timeline.
- Planner/draft cache keys include planning version, source identity/content, evidence context, target duration/words, speech settings and compact coverage. Prompt version is **20**, schema version **6-session-planning**. Old ready audio remains playable; changed policy does not reuse an unsuitable old plan/draft.

## Verification and utilisation report

Offline report: [session-duration-report.json](session-duration-report.json). Reproduce with:

```sh
.venv/bin/python scripts/report_session_duration.py
```

This script uses explicitly fake source/model/reviewer providers and silent WAVs. It measures ledger/orchestration, **not real speech, teaching fidelity, source sufficiency or live provider performance**. It used **zero live API requests and zero source credits**. Across 21 cases (60, 73, 120, 137, 300, 600, 1200 seconds; synthetic rates 250, 430 and 550ms/word), all final totals are within 90–100%, with no overruns. At the 430ms/word diagnostic rate:

| Requested | Measured videos + practice | Utilisation | Shorts |
| --- | --- | --- | --- |
| 60s | 58.05s | 96.8% | 3 |
| 120s | 117.82s | 98.2% | 5 |
| 300s | 298.00s | 99.3% | 9 |
| 600s | 597.94s | 99.7% | 18 |
| 1200s | 1104.29s | 92.0% | 32 |

Tests include longer-than-prior speech repair, shorter speech expansion, narrow-goal exhaustion, focused acquisition/quota failure, cached vs external requests, separate original/extra pools, useful minimums, 600 random ledger-conservation cases, all four cancellation phases, restart/retry identity/allowance preservation, deferred unfit closing, generation-limit completion, legacy compatibility and exact missing-media recovery. Browser fixtures cover forecast updates, selected-ready-short stability during outline expansion and truthful final shortfall copy, alongside existing loop/reaction/gesture/presentation regression checks.

Final verification:

| Check | Result |
| --- | --- |
| `.venv/bin/python -m pytest backend/tests -q` | **237 passed**; existing Starlette/httpx deprecation warning |
| `.venv/bin/python scripts/export_openapi.py` | Passed |
| `npm run types --prefix frontend` | Passed |
| `npm run build --prefix frontend` | Passed |
| `npm test --prefix frontend -- --workers=4` | **63 passed, 1 live test skipped** |
| `.venv/bin/python scripts/report_session_duration.py` | All **21** diagnostic cases in the 90–100% band |
| `git diff --check` | Passed |

Live matrix measurements were **not run**; real cost, latency, model compliance, spoken-content fidelity and evidence sufficiency still need a credit-aware live evaluation and human review. In particular:

- Coverage facets are a model plan/review declaration, not independently scored per-facet proof.
- Distinctness guards include lexical heuristics plus the same local model reviewer; adversarial or semantically redundant outcomes can evade them.
- A model that under-plans essential core, fails concise output or refuses a fitting repair may finish shorter or fail actionably. No guarantee is made for every goal/voice/source outage.
- Calibration predicts duration from words/recent clips, not phonemes or deliberate new pauses; no speech-speed or waveform policy changed.
- Provider work time is accumulated across completed calls, not generation wait counted as learning time. An abruptly killed in-flight call can lose its final elapsed-time sample, but its persisted model/source/candidate reservation remains consumed.
- The existing single-worker scheduler and buffering policy were not redesigned (#6 remains separate).
