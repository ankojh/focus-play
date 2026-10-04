# Teaching quality and lesson coherence

Implementation of handoff #2. This is an instructional-contract and prompt change, not the session-utilisation algorithm in #5.

## Contracts and worker behaviour

New lessons use `teaching_plan_version=2`. Each objective has a stable `concept_id`, observable `learning_outcome`, `teaching_role`, ordered `dependency_ids`, learner `relevance`, supplied `evidence_segment_ids`, `curriculum_role`, `target_duration_ms`, optional `example_id`, `visual_intent`, and an intentional `checkpoint`. A short persists the corresponding concept/outcome/role/example identity. Template lookup uses the concept ID; optional insertions no longer shift new lesson mappings.

`backend/app/teaching.py` checks missing/forward/cyclic dependencies, duplicate IDs/outcomes, invalid source references, examples, closing ordering and conservative budget arithmetic before committing a plan. Observable verbs and lexical similarity are structural heuristics, **not semantic proof**. Distinct applications are permitted; a recap requires earlier dependencies and closing classification.

The planner asks for understanding, mechanism, supported example, distinction/application and recall where appropriate, not mandatory five-clip sequences or padded introductions. The learner's prior knowledge remains part of the plan and draft tasks. A narrow goal stays narrow; insufficient evidence still takes the existing bounded retrieval/failure path. A partial-coverage reason is retained in `plan_diagnostics` and displayed with the outline.

### Recurring examples: explicit source-only policy

`Lesson.examples` contains up to two immutable records, each with stable entities, exact source-excerpt facts and evidence IDs. No synthetic substitutions, invented entities, invented performance results or measurements are allowed, even labelled illustrative. This deliberately chooses the conservative policy allowed by the handoff; it does not loosen source grounding.

The record is shared across drafts, source/teaching review, retries and persisted snapshots. Required evidence is pinned into focused retrieval without increasing the existing 20-passage / 4500-text-character limit. Missing or oversized required evidence produces `PLAN_EVIDENCE_UNAVAILABLE`, rather than silently swapping context. A related draft must retain at least one recorded entity and cite example evidence. These deterministic checks do not detect every possible entity/fact drift: the existing review also checks continuity and source support. Unsupported examples should be omitted at planning time; additional example-specific acquisition beyond the existing source flow is not introduced.

### Bounded history and novelty

Ready publication atomically saves an idempotent `coverage_history` entry with outcome, role, concise claim/purpose summary, evidence and example identity. Recaps have `adds_coverage=false`. Missing-media retries replace the same entry; they do not count the outcome twice. Ready media is not automatically rewritten.

Later draft/review tasks receive:

- Up to 64 covered identities.
- At most 12 recent ledger entries; oldest detail is removed to keep the entire history JSON within 4800 characters for server-generated IDs.
- Whole recent narration units from the last two ready shorts, with a 1200-character cap.
- The last six question prompts, rather than all prior questions.

Full coverage is persisted (up to 64 entries); old detail need not be injected forever. The recent repeated-text guard remains. An explicit recap can repeat earlier text, but repeated units inside the recap still fail. Semantic duplicate paraphrases and old-history duplicates also rely on the bounded reviewer and may be missed. The ledger's claim summary is a compact authored-purpose/text summary, not a separately fact-verified claim ontology.

Tests exercise 40 prior shorts (a 20-minute-sized history), reload and continuation. **This is a context-bound test, not a promise that the current planner creates 40 shorts or fills 20 minutes.** Exact token capacity depends on the local tokenizer; character caps do not prove an 8192-token full request will fit in every case.

### Practice and duration coordination

Checkpoints come from the plan instead of every third short. Prompts favour prediction/application, misconception-based distractors, one correct answer, and reasoning supported by passages actually taught. Duplicate answer options and recently repeated questions fail validation. Source review checks ambiguous answers and unsupported explanations.

Each checkpoint retains the existing 20,000ms allowance, counted exactly once by `planned_duration()`. The UI explicitly calls it an allowance, says answers are not timed and shows it in the outline. It displays the current learning outcome. Looping, swipe/wheel navigation, reactions and removed extra-explanation controls are unchanged.

Until #5 supplies calibrated estimates/reconciliation, new plans require `target_duration_ms=40000` and reserve the existing conservative 40-second speech cap plus practice allowances. One minute can contain one clip and a check; it is not forced to reserve an impossible multi-clip closing sequence. The eight-objective outline bound remains. Dynamic batching, measured top-up, long-session utilisation targets and persisted acquisition spending limits remain #5 work; no new acquisition loop or paid adaptive remediation was added here. `Short.optional` still means explicitly user-approved extra explanations, not curriculum extensions.

## Review dimensions and diagnostics

No extra routine model-review stage was added. The existing source-review call now returns separate `supported`/`reason` and `teaching_issues` fields. With teaching context, it checks outcome fit, level, prerequisites, clarity, causal/procedural usefulness, example continuity, question quality and semantic novelty. A rejection still gets at most one rewrite. Source failure remains `UNSUPPORTED_CLAIM`; instructional failure becomes `TEACHING_QUALITY_FAILED`.

Successful shorts persist `source_review_status=model_supported`, the reason, teaching diagnostics and up to two repair reasons. Reviewed draft caches retain those diagnostics. This status means only that a local model reviewer accepted the source support; it is **not independent factual verification or a quality score**. Rejected/failing shorts keep repair reasons. Do not interpret an empty issue list as proof of correctness.

Existing generation/validation/speech/compile timing metrics remain available. Adding instructional criteria may affect review latency and repair frequency; this has not been measured with a live model.

## Migration and cache semantics

- `Objective` and `Short` additions have legacy defaults. Old lesson JSON loads with `teaching_plan_version=1`, empty examples/history and null concept/outcome identifiers.
- Required fields are enforced for new version-2 planner output in the runtime model JSON schema and deterministic validator, without requiring a database rewrite of old saved lessons.
- Old ready audio/scenes/content and duration accounting remain intact. Legacy unfinished items use their former positional mapping. They are not automatically expanded or converted into a new curriculum.
- Prompt fingerprint is **17**, provider schema fingerprint **4**, and the teaching cache fingerprint **2**. Draft keys also include outcome/role/dependencies, examples, bounded history, checkpoint status and retrieved segment identities. Old plan/draft caches are not reused under the new semantics; already-ready media is not invalidated.
- Storyboard-v2 beats and measured phrase boundaries from #1 are retained (2–5 beats); the legacy flat adapter stays legacy-only.
- OpenAPI and `frontend/src/api.generated.ts` are regenerated.

## Evaluation fixtures and results

`fixtures/teaching-quality.json` contains original CC0 passages and **hand-authored reference outlines**, not scraped transcripts or real model output:

| Case | Beginner sequence | Knowledgeable sequence | Failure focus |
| --- | --- | --- | --- |
| Technical/indexes | mechanism → Maya lookup → maintenance application → recap | maintenance → no speed guarantee | entity substitution, invented benchmark, duplicate mapping |
| Conceptual/correlation | definition → warm-weather example → inference | alternative explanation → causal limitation | unsupported causal conclusion |
| Practical/container watering | soil condition → drainage procedure → decision | drainage condition → schedule distinction | invented universal volume/interval |
| Narrow/UTC | one expansion outcome | same narrow outcome | adjacent unsupported curriculum or padding |

The technical fixture includes illustrative **before/after authored samples** showing the difference between repetitive mapping statements and a worked lookup plus trade-off. They are design examples, not a measured old/new generation comparison. Existing `fixtures/storyboard-lookup.json` remains a renderer/compiler fixture, not a demonstration that new source-only generation accepts arbitrary synthetic examples.

Automated regressions cover both learner-level reference plans, invalid dependencies/outcomes/evidence, stable example records and retrieval, distinct applications, intentional recap accounting, question uniqueness/checkpoints/budgets, bounded continuation history, strict new schema with legacy loading, separate review dimensions/repair limits, and plan/coverage/ready-output preservation through retry. The existing source-repair and speech-duration-repair tests also remain in the suite. Browser coverage checks the displayed outcome, limitation reason, allowance, untimed answer controls and unchanged looping.

### Human/live evaluation still required

Before release, run the old and new prompts on the same adequate passages and learner requests. Score each actual pair 1–5 for:

1. Goal and learner-level fit.
2. Explanatory clarity.
3. Mechanism/example usefulness.
4. Coherence/prerequisite handling.
5. New learning value versus repetition.

For each score record the quoted output and reason. Separately record factual support as pass/fail, reviewer reasons, source-support failures, input/output tokens, actual provider calls/credits, cache state, total and first-playable times, review latency and repair frequency. Include both learner levels, all four fixture topics, conflicting/incomplete passages and cancel/restart runs. Set release thresholds only after establishing this baseline.

No live source or model provider was called for this implementation's unit/browser verification. Provider costs were zero for these checks; mock speech/generation timings are not performance estimates. Human rubric scores, old/new live samples and live generation cost/latency results are **not yet available**. Passing reference-contract tests does not demonstrate a measured teaching-quality improvement.

## Verification

From the repository root:

```sh
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python scripts/export_openapi.py
npm run types --prefix frontend
npm run build --prefix frontend
npm test --prefix frontend
```

Final offline verification: **143 backend tests passed** (2.26s; one existing Starlette/httpx deprecation warning); OpenAPI export and type generation passed; production build passed; **29 browser tests passed** (5.1s), with the live-provider test skipped. `git diff --check` passed. The saved-import browser assertion was stabilised to check the opened content instead of racing autoplay's Play/Pause label.

No commits or pushes are part of this handback.
