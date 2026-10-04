# #4 — Presentation, captions, and narration polish

## Purpose and agreed context

Builder handoff for Focus Play, repository `/Users/ankojh/b12/focus-play`. Paths below are repository-relative.

The user considers the diagram videos acceptable but not great and wants presentation polish alongside better teaching, visual demonstrations, and mixed formats. The aim is clearer, more engaging instruction—not decorative motion or a wholesale application redesign.

The user's entered time means the whole learning session, including planned practice allowances. Presentation work must not fill that time with idle animation, artificial silence, slower narration, or repeated content. Numeric/design suggestions below are proposed starting points to validate, not fixed user-approved specifications.

## Current implementation to inspect

- `frontend/src/Diagram.tsx`: SVG layout, cards, typography, wrapping, role colours, highlights, glow, and flowing arrows.
- `frontend/src/Player.tsx`: title, captions, visual area, audio clock, controls, question panel, looping and gestures.
- `frontend/src/styles.css`: player dimensions and responsive layout.
- `frontend/src/icons.ts`, `backend/app/icons.py`: bundled icon mapping.
- `backend/app/providers.py`: narration prompt and `Speech.synthesize()`.
- `backend/app/contracts.py`: narration units and timing data.
- `frontend/tests/app.spec.ts`, `frontend/tests/live.spec.ts`.

Observed limitations:

1. Captions currently display a whole narration unit. With two units per short, that can be a large block of text.
2. Diagram labels/details can repeat the same content as the narration, increasing reading load.
3. `wrap()` truncates displayed lines to three; some card text is dynamically reduced in size to fit. This risks concealed content and tiny text rather than deliberate layout.
4. Several templates use the same card-based visual structure despite different instructional needs.
5. Decorative arrow flow continues throughout playback. Motion is synchronized, but not every movement carries teaching meaning.
6. Narration uses one voice and fixed speed. That is not inherently bad; phrasing and chunking should be improved before adding voice variety.
7. Phrase boundaries are measured by synthesis. Word timestamps do not currently exist.

## Preserve current working-tree behaviour

There are existing uncommitted modifications in `frontend/src/App.tsx`, `frontend/src/Player.tsx`, `frontend/src/styles.css`, `frontend/tests/app.spec.ts`, and `frontend/tests/live.spec.ts`. Inspect and preserve them; do not overwrite files from an older baseline.

At handoff creation, shorts loop until the user navigates. The player supports wheel/swipe/up/down navigation, like/dislike reactions, source links, and browser autoplay error feedback. The library replaces older navigation. Extra-example/explain buttons were removed. Preserve these decisions and their tests unless separately instructed.

Old README descriptions may not match those current player changes. Treat current code/tests as the implementation baseline and update documentation accurately when implementing this workstream.

## Target presentation principles

1. **One dominant visual idea at a time.** The current teaching beat should have clear focus.
2. **Complement narration.** Use short visual labels; do not duplicate the entire spoken sentence on every card.
3. **Stable visual identity.** The same entity retains a consistent colour and symbol across related scenes.
4. **Readable before decorative.** Mobile text size, contrast, spacing, and hierarchy take priority over glow and animation.
5. **Motion explains a change.** Reveal, move, compare, or connect only when it helps the learner understand.
6. **No forced sensory load.** Respect reduced motion; do not add background music or sound effects by default.
7. **Truthful timing.** Only measured or explicitly estimated caption/visual alignment may be described as synchronized.

## Proposed implementation

### A. Establish a compact visual system

Create shared tokens for:

- Background/surface hierarchy and separators.
- Primary versus supporting text.
- Minimum readable typography at actual rendered mobile sizes.
- Semantic colours and non-colour indicators.
- Focus, selected state, and error state.
- Spacing, corner radii, and restrained animation duration/easing.

Do not rely on colour alone for good/bad, selected/unselected, or source uncertainty. Keep labels/icons available. Distinguish entity identity colour from semantic roles so an entity is not arbitrarily recoloured when its role changes.

Move common renderer framing into reusable components as #3 grows. Do not turn `Diagram.tsx` into an application-wide style engine.

### B. Replace silent text loss with deliberate layout

- Define renderer-specific text budgets at authoring/validation time.
- Use actual text measurement or robust wrapping where necessary; a fixed character count is not a reliable width estimate for every glyph.
- Avoid shrinking all content until it technically fits. Enforce a minimum readable size and choose an alternative layout, shorter label, or another beat when needed.
- Preserve full factual content in narration/transcript/source UI when visual labels are intentionally abbreviated.
- Do not silently truncate a qualifier that changes the meaning.
- Keep the visual bounds stable during a scene so progressive reveals do not cause camera-like jumping.
- Test long titles, acronyms, narrow supporting cards, and dense comparison layouts at realistic viewport sizes.

The diagram's `viewBox` affects actual on-screen font size. Validate rendered output, not just SVG font-size values.

### C. Readable captions with honest timing

Preferred first step: use the shorter measured narration beats introduced by #1. Display compact phrase captions with readable line lengths, a consistent safe area, and good contrast without obscuring the key visual.

If a long beat must be divided further:

- Prefer synthesis/alignment that provides real subphrase boundaries.
- Do not manufacture word timestamps by equal division and present them as accurate word alignment.
- If an approximate display pacing mechanism is used, label its limitations internally and ensure it cannot skip or misorder words. It must not become the source of truth for critical visual actions.
- Keep a full readable transcript accessible, whether captions are shortened or hidden.

Coordinate backend caption payloads and cache changes with #1. Avoid a frontend-only split that races the measured audio.

### D. Improve speech delivery without changing the product stack

Start with content and punctuation:

- Short complete sentences and natural clause boundaries.
- Clear handling of abbreviations, symbols, and numerical units.
- Remove filler and awkward video-transcript phrasing.
- Review repeated starts, unnatural fragments, and abrupt transitions between synthesized units.
- Use one consistent voice and natural fixed speed as the baseline.

If pauses are added deliberately, include them in the actual waveform or explicitly model them on the media timeline. Include their duration in #5's ledger. Never append unseen silence just to meet the session target.

Pronunciation normalization must preserve meaning. A display form and spoken form may differ, but both need evidence-consistent semantics and cache identity. Do not claim SSML support unless the selected speech provider actually supports and is tested with it.

Changing voice, speech speed, sample handling, or pause policy requires new cache fingerprints and measured quality/performance checks. Multiple voices, music, and voice cloning are not part of this initial brief.

### E. Make motion purposeful

With #1's semantic beats:

- Reveal a concept when introduced.
- Highlight the entity being discussed, not whichever label happens to match a word.
- Animate a changing state or connection when it teaches a mechanism.
- Keep settled content settled rather than continuously moving every edge.
- Avoid flashes and excessive zoom/pan.

Reduced-motion mode should preserve the same instructional sequence but show state transitions without animation. It should not reveal all future answers immediately. Pause and seek must remain tied to audio time, not independent timers.

## Accessibility and interaction requirements

- Maintain readable contrast and focus-visible controls; use WCAG AA as the baseline target and verify the actual combinations.
- Keep keyboard play/pause, seek, and short navigation working without hijacking input fields.
- Gesture controls must not block normal horizontal interactions or scrolling outside the player.
- Captions/transcript should not flood a screen reader with frame-by-frame announcements.
- Supply meaningful accessible visual summaries, especially as #3 introduces non-diagram renderers.
- Preserve usable controls under text zoom and narrow layouts.
- Reactions remain mutually exclusive, toggleable, and scoped to the short.
- Browser-blocked autoplay must remain actionable and not be reported as a missing/corrupt audio file.
- Questions must remain operable while clips loop; do not inadvertently dismiss answers on every loop.

Do not change looping to timed auto-advance merely to make a session look exactly X minutes long. #5's planned duration is one intended pass plus practice allowances; elapsed interaction time is separate.

## Implementation ownership and dependencies

- [#1 Storyboards](01-visual-storyboards-and-audio-sync.md) owns semantic beats and measured scene/caption timing. Agree interface changes rather than maintaining two timelines.
- [#2 Teaching](02-teaching-quality-and-lesson-coherence.md) owns explanation structure, examples, and source-consistent wording.
- [#3 Mixed visuals](03-mixed-visual-formats-and-assets.md) owns payload validation and renderers; share tokens and accessibility framing.
- [#5 Duration](05-session-duration-and-evidence-coverage.md) owns time accounting, including actual pauses if introduced.
- [#6 Buffering](06-generation-buffering-and-playback-readiness.md) owns readiness and preload state, not typography or playback semantics.

Likely changes are focused on `Diagram.tsx`, `Player.tsx`, `styles.css`, renderer components, and browser fixtures. Only change backend narration/caption contracts when necessary and coordinated. Regenerate API contracts for any such change. Preserve old captions and diagrams via compatibility paths.

## Suggested delivery sequence

1. Capture baseline screenshots and representative clips at desktop and mobile widths.
2. Audit truncation, text scaling, contrast, and caption collisions.
3. Implement typography/layout tokens and fix content overflow.
4. Improve captions using existing measured phrases, then integrate shorter beats from #1.
5. Remove non-instructional motion and tune focused transitions.
6. Evaluate pronunciation/phrasing failures with the actual configured voice; make targeted changes.
7. Run accessibility, interaction, legacy-data, and performance regressions.

Do not claim speech or comprehension improvement from screenshots alone. Review both visuals and audio.

## Tests and acceptance criteria

Automated/browser tests:

- Long labels/details/titles do not silently remove essential qualifiers or become unreadably small.
- Captions remain within the player at narrow mobile widths and under text zoom.
- Caption/scene state after seeking matches continuous playback at the same audio time.
- Reduced motion disables interpolation while retaining correct reveal order.
- Looping, swipe/wheel navigation, likes/dislikes, source links, saved playback, and question answers retain current behaviour.
- No XSS through narration, source labels, diagram labels, or accessibility text.
- Relevant contrast/focus/accessibility checks pass; supplement automated checks manually.
- No independent animation loop keeps mutating the teaching state while paused.
- If speech settings or pauses change, cache separation and measured durations are tested.

Manual review:

- Review at least a process, comparison, key-fact, and worked example, plus one mixed renderer when available.
- Check at representative narrow widths such as 320–390 CSS pixels and a normal desktop viewport.
- Listen to technical terms, numbers, and transitions between narration units.
- Compare the baseline and new outputs using the same content.

Definition of done: meaningful content remains legible, captions complement rather than obscure visuals, instructional motion is restrained and synchronized, speech is no less accurate, and current interactions remain intact. Report remaining problem layouts rather than declaring universal polish.

## Verification and handback

```sh
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python scripts/export_openapi.py
npm run types --prefix frontend
npm run build --prefix frontend
npm test --prefix frontend
```

Deliver screenshots, caption/audio examples, accessibility findings, tests, any contract/cache changes, and a concise list of measured improvements and known limits. Live source/provider checks are separate from fixture tests and may incur source credits. Do not commit or push without permission; follow repository identity and Conventional Commit policy if later authorised.
