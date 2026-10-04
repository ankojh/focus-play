# #2 — Teaching quality, examples, and lesson coherence

## Purpose and agreed context

Builder handoff for Focus Play, repository `/Users/ankojh/b12/focus-play`. Paths below are repository-relative.

The user wants all four proposed quality improvements, not just nicer diagrams. They selected the whole learning session as the meaning of the entered time: video plus explicit practice allowances, with pauses/replays potentially extending elapsed time. This workstream owns instructional quality and coherence. It must produce useful depth rather than additional paraphrases to fill time.

The designs and numeric thresholds in these handoffs are recommendations for implementation and evaluation, not features already implemented or individually approved requirements. Maintain the current source-grounded, local-generation architecture. Do not add a cloud model or outside-knowledge fallback silently.

## Current implementation to inspect

- `backend/app/jobs.py`: planning prompt, `LessonPlan`, ordering of `Short` objects, the `earlier_narration` draft context, optional explanations, and `reviewed()`.
- `backend/app/contracts.py`: `Objective`, `LessonPlan`, `ModelShort`, `ModelQuestion`, `Question`, `Short`.
- `backend/app/providers.py`: two-unit teacher prompt and generic planner/reviewer prompt.
- `backend/app/validation.py`: `check_narration`, `validate_draft`, `verify_support`, and citation attachment.
- `backend/app/sources.py`: `retrieve()`.
- `backend/app/ranking.py` and `backend/app/youtube.py`: source selection and focused acquisition.
- `fixtures/`, `backend/tests/test_core.py`, `backend/tests/test_generation.py`, `backend/tests/test_youtube.py`.

Present strengths: basics-first planning, a learner-knowledge field, distinct-objective instructions, paraphrased teaching, citations, repeated-text checks, source review, and questions with explanatory feedback.

Present limitations:

1. Planning explicitly requests brief introductory learning points and permits partial coverage whenever anything useful can be taught.
2. An objective mainly contains a title, template, and prerequisites. It does not encode an observable learner outcome, teaching role, dependency IDs, or evidence coverage.
3. Generation requests an opening statement followed by explanation/tip, not a complete instructional progression.
4. All earlier narration is added to later prompts. As sessions grow, this is a context-size and latency problem.
5. Questions are required every third core short, regardless of concept difficulty or natural checkpoints.
6. Source review checks support, not whether the explanation is helpful, appropriately scaffolded, or coherent across clips.

At handoff creation, existing uncommitted changes affect `frontend/src/App.tsx`, `frontend/src/Player.tsx`, `frontend/src/styles.css`, `frontend/tests/app.spec.ts`, and `frontend/tests/live.spec.ts`. Preserve them. Current shorts loop; swipe/wheel navigation and like/dislike controls are intentional current behaviour. Backend extra-explanation endpoints still exist, but their old frontend buttons have been removed. Do not restore those buttons as part of improving pedagogy.

## Target teaching experience

A lesson should answer: “What will I be able to explain or do when this session ends?”

Recommended progression, applied where suitable:

1. **Understand:** establish the essential concept and why it matters.
2. **See:** walk through a concrete, source-supported example.
3. **Distinguish:** compare an alternative or expose a misconception.
4. **Apply:** predict the next step or choose an appropriate approach.
5. **Recall:** retrieve the key idea and connect it back to the goal.

Do not require every concept to have five shorts. A one-minute lesson may contain two useful clips and a very small check; a longer session can develop applications and transfer. Scale depth to learner knowledge and time, not by stretching introductions.

Maintain one learning outcome per short. Related shorts may share an example or concept without repeating the same explanation.

## Proposed instructional plan

### Plan concepts before renderer templates

Extend or replace the current objective representation with a bounded plan containing:

- Stable concept/objective ID.
- Observable learning outcome, not just a catchy title.
- Teaching role: foundation, mechanism, worked example, comparison, misconception, application, practice, recap.
- Dependencies on earlier concepts, with no cycles.
- Relevance to the learner's stated goal and prior knowledge.
- Evidence references or coverage status.
- Core/extension/closing classification, coordinated with #5.
- Estimated or target duration supplied by #5.
- Optional recurring example ID and its permitted facts/entities.
- Preferred visual intent, which #1/#3 map to supported renderers.

Do not force model output into one huge course-sized JSON object. Use a bounded high-level outline and chapter/concept-level expansion when needed. The default local context is 8192 tokens and output limit 2200 tokens. Large plans, source passages, and full prior narration cannot all grow unbounded.

### Preserve example continuity

Use a small persisted example record or equivalent plan data:

- Names/entities and values already introduced.
- Which attributes are illustrative rather than factual measurements.
- Which source passages support the mechanism and constraints.
- Which concept is being demonstrated next.

Example continuity should prevent unexplained switches from customer names to product IDs halfway through a worked example. Do not invent quantitative outcomes or imply that synthetic data were measured in the source.

Current source policy is strict: passages must support what is taught. Prefer examples already present in sources. If synthetic substitutions are introduced, specify and test an explicit policy that labels the example as illustrative, preserves the evidenced mechanism, and does not relax factual grounding. Unsupported examples should trigger targeted retrieval or be omitted, not pass by wording changes alone.

### Write for understanding

Draft instructions should favour:

- A direct opening tied to the current outcome.
- Plain language with necessary terminology defined once.
- A visible causal or procedural explanation.
- One concrete example when useful.
- A concise takeaway, limitation, or transition.
- Explicit conditions rather than false guarantees.

Coordinate with #1 to replace the exactly-two-unit restriction with bounded teaching beats. Preserve natural voice speed and the total short limit. Do not add generic hooks, filler introductions, forced enthusiasm, or repeated “In this video” language.

### Track covered meaning, not just previous strings

Use a compact concept/claim ledger plus recent narration rather than injecting every previous sentence forever. Persist enough structure to:

- Identify which outcome has already been taught.
- Allow a recap to revisit a concept intentionally.
- Distinguish a new application from a synonym-based duplicate.
- Carry example context across batches and retries.
- Keep prompt size bounded.

Existing repeated-text validation should remain a useful guard, but intentional brief retrieval/recap must not be rejected as if it were accidental duplicate teaching. Conversely, paraphrasing the same point should not count as new instructional coverage.

## Practice and feedback

Start with the current multiple-choice mechanism. Improve placement and question design before adding a new interaction engine.

- Place checks at coherent boundaries, not only every third short.
- Test an outcome that was actually taught.
- Prefer useful prediction/application over irrelevant trivia.
- Require one unambiguous correct answer.
- Use plausible distractors representing specific misconceptions.
- Explain the correct reasoning, without adding unsupported new claims.
- Allow estimated answer/feedback time in #5's ledger. Existing questions have a fixed 20-second allowance; changing this requires coordinated schema and UI work.
- Do not enforce a timed auto-submit or pretend every learner answers in exactly the allowance.

Adaptive remediation is a later enhancement unless explicitly included in the implementation scope. An answer must not silently trigger paid retrieval, unbounded generation, or content beyond the user's time allowance.

## Validation and quality controls

Keep separate dimensions:

1. **Structural validity:** bounded schema, valid dependencies, targets, evidence references.
2. **Source support:** factual statements, visual details, question answers, and caveats agree with passages.
3. **Teaching quality:** outcome fit, clarity, useful example, causal explanation, continuity, and level fit.
4. **Novelty:** each new instructional short adds something beyond previous coverage.

Do not add an expensive model review to every stage without measuring it. First add deterministic plan checks and improve prompts; use a bounded teaching review where it has demonstrated value. Source review already has a rewrite path and may miss errors. Avoid circular claims that model approval proves correctness.

Proposed evaluation rubric, scored 1–5 for manual comparison:

- Goal and learner-level fit.
- Explanatory clarity.
- Mechanism/example usefulness.
- Coherence and prerequisite handling.
- New learning value versus repetition.

Track factual support separately as pass/fail with recorded reviewer reasons. Compare the old and new outputs on the same goals and source fixtures. Set release thresholds after a baseline rather than inventing an improvement percentage.

## Implementation sequence and ownership

1. Add a representative teaching-quality fixture set and document current weaknesses.
2. Agree plan contracts with [#5 Duration and coverage](05-session-duration-and-evidence-coverage.md).
3. Add concept IDs, outcomes, roles, dependency validation, and compact coverage history.
4. Improve draft prompts and example continuity, coordinating with [#1 Storyboards](01-visual-storyboards-and-audio-sync.md).
5. Make practice placement intentional and expose its planned allowance clearly.
6. Add quality diagnostics, compare outputs, and revise based on failures.

Likely files: `backend/app/contracts.py`, `backend/app/jobs.py`, `backend/app/providers.py`, `backend/app/validation.py`, `backend/app/sources.py`, test fixtures, and frontend outline/question copy. A small planner module can keep curriculum logic out of the already large worker.

[#3 Mixed visuals](03-mixed-visual-formats-and-assets.md) selects safe visual primitives, not learning outcomes. [#4 Presentation](04-presentation-captions-and-narration-polish.md) improves delivery. [#6 Buffering](06-generation-buffering-and-playback-readiness.md) measures any additional latency.

Bump prompt/schema/cache fingerprints when semantics change. New plan fields must have a migration/default strategy for old saved lessons; do not regenerate ready media automatically.

## Edge cases

- Very narrow goal already covered in a few clips: do not invent adjacent curriculum to fill time; report insufficient useful coverage through #5.
- Advanced learner: skip unnecessary basics without skipping required dependencies.
- Conflicting sources: retain conditions and uncertainty; do not merge incompatible claims into one confident rule.
- Caption errors and incomplete passages: retrieve better context or reject unsupported teaching.
- Repeated analogy versus repeated content: preserve useful continuity without treating a new label as novelty.
- Cancel/retry and restarts: preserve concept identities, examples, and completed outcomes.
- Long sessions: bound context and plan expansion; source text stays untrusted data.
- Unsupported learner request: do not silently fall back to unrestricted model knowledge.

## Tests and definition of done

Automated tests must cover:

- Missing/cyclic dependencies, duplicate outcomes, and invalid evidence references.
- Beginner versus knowledgeable learner plans on controlled fixtures.
- Example facts/entities remaining stable across related shorts.
- New applications allowed while duplicate paraphrases are rejected or flagged.
- Recap explicitly allowed without being counted as new concept coverage.
- Question uniqueness, support, checkpoint placement, and budget accounting.
- Bounded context for a 20-minute plan and continuation batches.
- Retry preserving approved plan/coverage state and already-ready outputs.
- Existing source-review failure and repair tests still passing.

Human review should include technical, conceptual, and practical topics with adequate source fixtures, plus a deliberately narrow goal. Deliver before/after samples, rubric scores and reasons, source-support failures, and actual generation costs/timings. A passing fixture test alone is not proof of teaching quality.

Completion means the plan expresses observable outcomes, longer sessions add useful depth, examples are coherent, claims remain grounded, and the lesson reads like a sequence rather than unrelated summaries.

## Verification and handback

Run from repository root:

```sh
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python scripts/export_openapi.py
npm run types --prefix frontend
npm run build --prefix frontend
npm test --prefix frontend
```

Do not call live source providers just to satisfy unit tests. Live checks require configured providers, credit awareness, and honest cached/uncached labelling. Return implementation summary, contract/migration notes, evaluation fixtures/results, remaining limitations, and any proposed product decisions. Do not commit or push without permission; use the repository's identity and Conventional Commit policy if later authorised.
