# #1 — Visual storyboards and audio-synchronised demonstrations

## Purpose and authority

Builder handoff for Focus Play. The user wants all four video-quality improvements discussed: concepts shown in action, better teaching, presentation polish, and mixed visual formats. They also want enough content for the entered time, defined as the whole learning session. This document owns the storyboard and visual-timing workstream, not the other five workstreams.

This is a proposed implementation brief, not a claim that the feature exists. The 3–5-beat structure below is a recommended starting point, not a user-mandated rigid format. Preserve evidence quality, local generation, saved lessons, and the existing 40-second short limit unless a separate product decision changes them.

Repository: `/Users/ankojh/b12/focus-play`. All subsequent paths are repository-relative.

## Read before editing

- `backend/app/contracts.py`: `ModelShort`, `ModelUnit`, `ShortDraft`, `NarrationUnit`, `Scene`, `SceneAction`, `DiagramNode`.
- `backend/app/jobs.py`: `TEMPLATES`, draft generation, speech generation, and the assignment to `short.scenes`.
- `backend/app/providers.py`: model schema specialisation, system prompts, version fingerprints, `Speech.synthesize`.
- `backend/app/validation.py`: `attach_evidence`, `refine_cues`, `validate_draft`, `verify_support`, `diagram_evidence`.
- `frontend/src/Diagram.tsx`, `frontend/src/Player.tsx`.
- `backend/tests/test_core.py`, `backend/tests/test_generation.py`, `frontend/tests/app.spec.ts`.

At handoff creation there are pre-existing uncommitted changes to `frontend/src/App.tsx`, `frontend/src/Player.tsx`, `frontend/src/styles.css`, `frontend/tests/app.spec.ts`, and `frontend/tests/live.spec.ts`. Inspect current status/diffs; preserve these changes. The current player loops each short, supports swipe/wheel/keyboard navigation, and has like/dislike controls. Do not restore removed extra-explanation buttons or auto-advance behaviour from old documentation.

## Current implementation and diagnosis

1. `Jobs.advance()` requests exactly two narration units and 40–80 spoken words.
2. `Ollama.generate()` also embeds the two-unit requirement and specialises a flat diagram schema by contract name. Updating only the task prompt will not be enough.
3. `ShortDraft` permits 2–4 narration units; `DraftAction.unit` is restricted to 0–3. Inspect the separate model-facing contracts too.
4. A generated short is published with one `Scene`, ending at measured audio duration.
5. `refine_cues()` makes every node appear at unit zero. It picks highlights by lexical overlap and draws connections at one of the first two units.
6. `Diagram` computes visual state from audio time, including seeks. This is a valuable invariant to retain.
7. The frontend already selects a scene from `short.scenes`, but boundary handling and time coordinates were written around a single scene. Multi-scene support is not complete merely because the field is an array.

Result: the system can present relationships, but seldom demonstrates their evolution. More icons or glow effects alone will not fix this.

## Desired experience

One short has one clear learning outcome, supported by a short visual sequence. A beat is a meaningful narrated change, not necessarily a new scene or layout.

Example: explain a database index, using an evidence-supported illustrative table:

| Beat | Teaching purpose | Visible state |
| --- | --- | --- |
| Question | Find a particular customer | Table and clearly identified search value |
| Baseline | Show scanning | Candidate rows examined sequentially |
| Alternative | Show lookup | Index structure points to the matching row |
| Takeaway | Explain the supported trade-off | Result and concise storage/update caveat |

Do not introduce fictional benchmark numbers. An illustrative table is not a real dataset; label it accordingly and validate the mechanism against the sources. Until workstream #3 supplies a table renderer, use a controlled diagram approximation that actually shows the state changes.

Recommended initial target: 3–5 brief beats, natural pacing, one or a few scenes, total measured duration at most 40 seconds. Allow a simpler short when pedagogically justified; do not inflate every explanation.

## Proposed design

### 1. Separate semantic authoring from compiled playback

The model should return bounded semantic data:

- Stable beat IDs and ordered narration.
- Evidence segment references per spoken claim/beat.
- Scene or visual identity for each beat.
- Explicit entity targets and supported operations: reveal, focus, connect, change state, replace scene.
- Learning purpose of the beat, supplied by the teaching plan where possible.

The application should derive:

- Evidence quotes and timestamps from stored passages.
- Narration audio and measured beat boundaries.
- Concrete scene intervals and action timestamps.
- A validated, deterministic playback representation.

Do not ask the model to invent milliseconds, raw SVG, executable JavaScript, CSS, or arbitrary renderer code. Retain an allowlisted visual vocabulary. Reference targets explicitly rather than inferring new-storyboard meaning from keyword overlap.

### 2. Establish one timing convention

Recommended convention: persisted scene and action times are absolute milliseconds on the short's audio timeline. `Diagram` receives absolute audio time. Alternatively use relative scene times, but implement conversion at one boundary and document/test it; do not mix conventions.

Required invariants:

- Scene intervals are ordered, valid, and contained in measured media duration.
- Define whether gaps are prohibited or render a documented hold state. Never fall back silently to scene zero during an unintended gap.
- Use half-open intervals for interior boundaries; define the final-frame behaviour explicitly.
- Every action references an existing target in its applicable scene.
- Every beat reference resolves, and operations are legal for that renderer.
- Narration, captions, and scene transitions use the same audio clock.
- Seek, replay, refresh, and looping reproduce the same frame at the same time.

The existing `Scene.end_ms <= 40000` bound does not itself validate interval ordering, overlaps, or action placement. Add cross-field validators and tests.

### 3. Compile after speech measurement

Suggested flow:

1. Retrieve objective-specific evidence.
2. Generate a bounded storyboard draft.
3. Validate structure, citations, and teaching alignment.
4. Run source-support review, including state changes and visual labels.
5. Synthesize narration beats through the existing speech provider.
6. Compile beat references into measured action/scene times.
7. Validate final timeline and renderable content.
8. Publish media plus final metadata atomically as ready.

Speech currently concatenates independently synthesised units and records phrase boundaries. Reuse that mechanism initially. Phrase-level timing is sufficient for the first iteration; do not claim word alignment unless an actual alignment mechanism is implemented and tested.

If narration is repaired for duration, redo evidence review and compilation. Never keep timestamps from an earlier script. Maintain bounded retries and cancellation checkpoints.

### 4. Versioned compatibility

Coordinate shared contracts with #3. Prefer an explicit saved-format/storyboard version and an adapter for older flat scenes. Existing ready audio and diagrams must remain playable without regeneration.

Update all affected prompt/schema versions and cache keys. Semantic storyboard format and timeline compiler versions must participate in the appropriate caches. Old drafts must not be read as new-format validated output merely because narration text is identical.

Keep the lexical cue compiler only as a legacy adapter or explicit fallback. New storyboards should have explicit semantics.

## File-level implementation plan

- `backend/app/contracts.py`: bounded authoring types; evidence references; beat-to-scene bindings; timeline validation; compatibility defaults or adapters.
- `backend/app/providers.py`: update both system prompt and runtime schema specialisation; preserve allowed evidence IDs and bounded repairs; fingerprint changes.
- `backend/app/jobs.py`: replace flat scene assembly with a compile step after measured speech; preserve incremental publication and source review.
- `backend/app/validation.py`: validate semantic targets and visible/narrated consistency; stop overriding new explicit cues in `refine_cues`.
- Consider a small `backend/app/storyboard.py` for pure compilation/validation helpers instead of making `Jobs.advance()` larger.
- `frontend/src/Player.tsx`: deterministic scene lookup at boundaries; preserve loop and navigation behaviour.
- `frontend/src/Diagram.tsx`: support progressive state and explicit operations; keep state evaluation pure with respect to time.
- Regenerate `backend/openapi.json` and `frontend/src/api.generated.ts`; do not hand-edit generated contracts.

## Scope boundaries and coordination

- [#2 Teaching quality](02-teaching-quality-and-lesson-coherence.md) supplies intent, example continuity, and learning outcomes.
- [#3 Mixed visuals](03-mixed-visual-formats-and-assets.md) owns renderer-specific payloads and external assets. Agree on the scene envelope before either workstream expands it.
- [#4 Presentation](04-presentation-captions-and-narration-polish.md) owns typography, captions, visual tokens, and motion polish.
- [#5 Time planning](05-session-duration-and-evidence-coverage.md) owns per-short target durations and the session ledger. More beats do not mean longer permitted clips.
- [#6 Buffering](06-generation-buffering-and-playback-readiness.md) owns scheduling and readiness. Additional storyboard work must be measured for latency.

Do not implement an arbitrary animation editor, video export pipeline, generative-video provider, or unrestricted rendering language for this milestone.

## Failure handling and edge cases

- Reject missing/duplicate beat IDs, unknown targets, illegal state transitions, and unsupported visual claims before publication.
- Handle a very short spoken beat without overlapping effects or flashing content.
- Reduced motion should remove interpolation/decorative animation, not reveal future instructional states early.
- Scene changes must not leave caption text from an unrelated beat.
- A loop must reset state cleanly. Question answer state should retain existing behaviour.
- Missing or invalid new-format metadata must yield an actionable failure or an explicit compatible fallback, not a blank player marked ready.
- Keep source review honest: model review can miss errors and is not independent fact verification.

## Tests and acceptance criteria

### Automated

- Unit-test storyboard compilation with fixed measured beat boundaries, including zero/last frames and exact scene boundaries.
- Reject invalid targets, out-of-order intervals, overlaps, unsupported operations, and durations outside limits.
- Assert explicit semantic targeting fixes negative-mention cases (e.g. a narration about scanning without an index must not focus the index just because its name appears).
- Test duration repair regenerates timestamps and preserves evidence validity.
- Test old saved lessons and old audio cache metadata remain readable.
- Browser-test reveal order, scene transitions, seeking backward/forward, looping, refresh restore, pause, and reduced motion.
- Assert the visual state at time T is identical after uninterrupted playback and a direct seek to T.

### Human review

Review representative process, comparison, and worked-example clips at desktop and narrow mobile widths. A reviewer should be able to describe what changed and why. The demonstration must explain more than the same labels displayed all at once.

Acceptance requires: all new clips use valid measured timelines; every meaningful visual change is linked to a relevant beat; no future state leaks on seek/reduced motion; source support and the 40-second limit remain enforced; existing player interactions and old lessons still work.

## Verification and builder deliverables

From repository root, use the existing environment:

```sh
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python scripts/export_openapi.py
npm run types --prefix frontend
npm run build --prefix frontend
npm test --prefix frontend
```

Run live-provider checks only when configured and approved for source-credit use. Record actual model, voice, cold/warm/cache status, timing, and failures. Fixture tests are not evidence of live visual quality.

Deliver code, migration/compatibility notes, deterministic fixtures, browser tests, screenshots at meaningful beat times, and a short measured quality/performance report. Document any change to this proposed design. Do not commit or push without permission; follow repository identity and Conventional Commit policy if later authorised.
