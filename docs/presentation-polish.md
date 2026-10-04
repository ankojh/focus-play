# Presentation, captions and narration polish (#4)

## Implementation

The working tree was clean when this work began. Current library, looping, reactions, Sources toggle, keyboard/gesture navigation, saved playback, browser-blocked-autoplay feedback and question behaviour remain the baseline. No commits or pushes were made.

- `frontend/src/presentation.css` defines shared surface, contrast, typography, spacing, focus, status and reduced-motion tokens. `main.tsx` loads this small presentation layer after the existing application styles. Mixed renderers share its framing/typography; `Diagram.tsx` is not an application-wide style engine.
- `diagramLayout.ts` measures actual Arial glyph widths with Canvas, wraps all text without a three-line limit, and breaks oversized saved tokens without dropping characters. Existing authoring limits remain **44 characters per label / 70 per detail**, with **24-character maximum words**; the prompt also asks for 1–4-word labels and 3–8-word details. These are authoring bounds, not width estimates: renderer measurements determine layout. No schema tightening rejects previously valid saved lessons.
- SVG coordinates now match rendered CSS pixels instead of shrinking a fixed viewBox into a small player. Labels are **16px**, details **14px**, and the dominant key-fact label **20px** at the default text scale. Text-scale changes are measured again; 200% root-font tests verify doubled rendered sizes. Card height reserves the largest initial/authored state, including hidden nodes and move destinations. No text-scale-to-fit, ellipsis or qualifier loss.
- Comparisons/legacy charts/do–don't scenes use two columns when the reading area is at least 340px at default text scale, otherwise stack. Timelines retain a rail and numbering; cycles retain their explicit/legacy returning connections; key facts get a larger primary label. Existing template data and move/hide/state actions remain compatible, but original slot coordinates are not preserved.
- Dense diagrams and mixed renderers use a bounded 360px reading area. New semantic focus can snap an off-screen card into view; it never launches smooth scrolling or continuously fights manual reading. Entity accent is derived from entity ID, independent of role. Roles are also written as Start/Step/Result/Caution/Do/Don't/Concept. Focus has an outline and a textual `Focus` indicator. Selected answers have a non-colour check plus `aria-pressed`, without changing their accessible names.
- `Captions.tsx` displays the existing measured synthesis beat in a dedicated **8rem safe area**, separate from the visual. Longer legacy phrases scroll in that area; they are not divided into fabricated timestamps or shortened. Caption scrolling resets on a measured phrase change. **Hide/Show captions** and a full, ordinary readable transcript with phrase-boundary seek buttons remain available independently of Sources. Captions are `aria-live="off"`.
- Arrow drawing, reveal, hide and explicit movement still derive from the audio clock. Settled connections are solid/stationary, glow and continuous dash flow are removed, and interpolation is limited to **180ms** rather than 650ms. Reduced motion snaps transitions only at their semantic boundary, not before future reveals. No independent teaching animation timer runs while paused.
- Wheel/swipe navigation leaves overflowing visual/caption readers alone. Horizontal gestures, pinch zoom, input controls and scrolling outside the player are not intercepted. Reader focus allows native keyboard scrolling; player keyboard shortcuts do not hijack child controls. Seek range hit height is increased. Once a question is available, backward seeking does not dismiss its answer panel.
- `backend/app/providers.py` asks for short complete sentences, natural clause boundaries, varied sentence starts, source-supported abbreviation handling, unambiguous spoken units/symbols and preserved exact values/qualifiers. It asks for complementary visual text and explicitly prohibits SSML/padding/slowed speech. This is a generation instruction, **not an automatic text normalizer or guaranteed pronunciation improvement**.

## Contracts, caching and duration

No API payload, word-alignment field, compiler or speech-setting changes. OpenAPI and TypeScript contracts were regenerated and produce **no diff**. Narration beat timing remains owned by the storyboard compiler; no parallel caption clock exists.

Generation prompt version **18 → 19** separates changed generation instructions in existing model/lesson cache fingerprints. The schema version stays `5-mixed-visuals`; the speech fingerprint remains Kokoro `af_heart`, speed 1, 24kHz mono PCM WAV with its model/voice identity. No new voices, background audio, pronunciation replacement rules, artificial silence or pause policy. Ready saved shorts are not rewritten. Planned session duration and practice allowances are unchanged; looping remains user-controlled elapsed interaction, not timed auto-advance.

## Verification and measurements

Latest full verification:

| Check | Result |
| --- | --- |
| `.venv/bin/python -m pytest backend/tests -q` | **196 passed**, existing FastAPI/Starlette deprecation warning |
| `.venv/bin/python scripts/export_openapi.py` | Passed; no contract diff |
| `npm run types --prefix frontend` | Passed; no generated TypeScript diff |
| `npm run build --prefix frontend` | Passed; JS 333.22kB / 106.54kB gzip, CSS 39.92kB / 8.90kB gzip in this run |
| `npm test --prefix frontend -- --workers=4` | **61 passed, 1 live test skipped** |

The 16 added browser cases cover long title/label/detail/narration content at **320, 390 and 1280 CSS pixels**, 100%/200% root-font scaling, dense four-card comparisons/key facts, full text retention, actual SVG text bounds and rendered font sizes, caption scrolling/hiding/transcript seeking, injection escaping in captions/transcript/source labels/accessibility text, entity identity across role changes, stationary settled/paused visuals, actionable autoplay blocking, contrast/focus and retained question answers. Existing tests still cover measured boundary/seek equivalence, reduced-motion reveal order, looping, reactions, saved selection/position, source links, wheel/swipe boundaries and mixed renderers.

Measured output is retained as JSON beside the screenshots:

- Supporting text is approximately **14 CSS pixels** (SVG subpixel rounding can be less than 0.001px), **28px at 200%**. Tested full labels/details stay inside their card rectangles, including the qualifiers `not always faster`, `only if selective` and `most matching rows`.
- No document horizontal overflow at the tested narrow widths/text scales. Long captions keep their complete text and scroll without changing shorts.
- Actual computed SVG text fills on normal/focused cards plus caption text/background in the representative process fixture have a minimum contrast of **7.72:1** (AA text threshold 4.5:1). This is a targeted contrast check, **not an application-wide WCAG certification**. Reader keyboard focus has a visible outline; answer selection is programmatically exposed and visually marked.
- Same-time playback/direct-seek markup remains equal; paused SVG markup stays unchanged over a 250ms observation. There is no repeating arrow dash mutation at later audio positions.

The browser suite also now clones the compiled storyboard fixture per test. Previously, tests that changed reveal/move/hide operations mutated a shared object and could contaminate subsequent seek assertions and screenshots. This was a test isolation bug, not a playback timeline change.

## Before/after visual material

Baseline captures were made before editing using the existing fixture screenshot tests. Updated captures use the same template/storyboard inputs and beat positions. Element screenshots hide the fixed application topbar **only during capture**, preventing the header from covering a player taller than the viewport; whole-page mixed screenshots include normal chrome. These are fixture outputs, not live model quality evidence.

- [Before desktop templates](presentation-screenshots/before/) / [after templates and stress layouts](presentation-screenshots/after/).
- Worked example at 390px, beat 1: [before](presentation-screenshots/before/storyboard-390-beat-1.png) / [after](presentation-screenshots/after/storyboard-390-beat-1.png).
- Process/state-change at 390px, beat 3: [before](presentation-screenshots/before/storyboard-390-beat-3.png) / [after](presentation-screenshots/after/storyboard-390-beat-3.png).
- Comparison: [before](presentation-screenshots/before/template-comparison.png) / [after](presentation-screenshots/after/template-comparison.png).
- Key fact: [before](presentation-screenshots/before/template-key_fact.png) / [after](presentation-screenshots/after/template-key_fact.png).
- Mixed table: [390px](presentation-screenshots/after/visual-table-390.png) / [desktop](presentation-screenshots/after/visual-table-1280.png).
- [Long title/text at 320px and 200%](presentation-screenshots/after/presentation-long-320-2.png), [dense comparison](presentation-screenshots/after/presentation-dense-comparison-390.png), [dense key fact](presentation-screenshots/after/presentation-dense-key_fact-320.png).

Screenshot inspection covered the process, comparison, key-fact, worked-example and mixed table outputs. The new labels/details are larger, settled cards are less decorative, and caption text occupies its own contrasting region. Dense diagrams and long zoomed titles no longer all fit on one screen; that trade-off is deliberate rather than silent text removal.

## Actual configured-voice examples

`scripts/export_presentation_audio.py` exports original illustrative fixture text with the configured local speech provider, and measured caption JSON. It makes **no model or source-service calls**, consumes no source credits and adds no silence or normalization. Reproduce with:

```sh
.venv/bin/python scripts/export_presentation_audio.py
```

Exported Kokoro CPU `af_heart`, speed 1, 24kHz examples:

- [Lookup / transitions](presentation-audio/lookup.wav): **25,825ms**, four measured phrases. Single synthesis call took 5.972s including pipeline preparation, cache miss.
- [Numbers / display-only SQL](presentation-audio/numbers-and-code.wav): **26,875ms**, two measured phrases. Warm pipeline call took 2.932s, cache miss. Includes `-12`, `0`, `1500`, `SELECT` and `FROM` as pronunciation-review material, not new lesson claims.
- [Full caption text, boundaries and speech fingerprint](presentation-audio/measured-captions.json).

These sample durations differ from the browser fixture's explicitly fixed/silent diagnostic timeline. The audio examples' measured JSON is authoritative **for those WAV files**; the browser screenshots are not presented as synchronized to the exported audio. The timings are single observations while other checks ran, not a controlled speech-performance benchmark. Waveform measurement/synthesis succeeded, but **human listening and pronunciation/transition quality review remain outstanding**. No speech/comprehension improvement is claimed from screenshots or a prompt change.

## Known limits and remaining review

- Legacy/full beats can still be long; scroll preserves every word but does not create real subphrase alignment. Actual word timestamps are not available. New content relies on the storyboard prompt to author compact beats; no live regeneration was performed to prove compliance.
- Four-card, long-state and zoomed diagrams may require scrolling. Focus snaps can change scroll position at semantic boundaries; they do not pan/zoom the SVG or alter its bounds. Extremely tall single cards need manual reading. Stacked comparisons lose some side-by-side immediacy. This is not universal template polish.
- At 200% text scale, a long objective can make the player substantially taller than the screen. Controls and transcript stay in document flow instead of overlapping/shrinking, but compactness is not guaranteed.
- Cycle presentation is a readable sequence with a returning connection on narrow screens, not the old circular arrangement. Dense image annotation collisions are not solved by typography tokens; asset-specific review remains necessary.
- Browser regression checks use Chromium fixtures and silent test WAVs. Physical-device swipe/pinch, native browser text-only zoom, VoiceOver/screen-reader walkthroughs, all contrast combinations and human listening still need manual review. No live YouTube/Supadata/model checks were run.
