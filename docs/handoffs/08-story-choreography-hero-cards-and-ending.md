# #8 — Story choreography: image-led setup, one card at a time, big-picture ending

## Purpose and authority

Builder handoff for Focus Play. The user reviewed the current short rhythm and found it repetitive:
every short plays the same way — the cover photo appears as a polaroid for a fixed 1.6 s, shrinks into
a round sticker in the top bar, then diagram cards stack down the slide one by one. The user approved
three changes, to be implemented together and thoroughly:

1. **The image belongs to the story setup.** When a short has a cover, it is the hero for the whole
   first narration beat (the story's setup), not a fixed 1.6 s preamble. The first card still appears
   during beat 1 (as a caption/lower-third card over or under the photo), so beat 1's narration has its
   visual. At the start of beat 2 the photo becomes the sticker and the card system takes over.
2. **One card at a time, then the big picture.** The current item is shown large and centred (the
   "hero card": bigger icon, label and detail). Items already covered shrink into a compact progress
   strip (mini chips: icon + number, optionally a short label) at the top of the slide area, so the
   learner sees where they are in the sequence; remaining items may show as faint placeholders. This
   replaces the growing, scrolling list for list-like layouts and naturally handles 5–8 items.
3. **A proper ending.** On the last beat, zoom out to the full diagram (the existing complete
   diagram renderer) as a recap — "the whole picture" — with the last item focused. In the final
   moment of the short, show a takeaway card (check mark, `short.learning_outcome` if present,
   otherwise the last item's label/detail) with a small, tasteful celebration. Each short should feel
   complete before the learner swipes on.

Out of scope unless trivial after everything above is verified: per-layout entrance choreography
(steps slide up as the arrow draws, comparison sides slide in, venn circles slide together, …) and
rotating intro styles. Do not change backend generation, prompts or contracts unless a requirement is
impossible without it — if so, stop and report instead.

This is an implementation brief, not a claim that the feature exists. Repository:
`/Users/ankojh/b12/focus-play`. Paths below are repository-relative.

## Read before editing

- `frontend/src/Player.tsx` — `Cover` (polaroid → sticker driven by `intro = clock < INTRO_MS`),
  `.player.intro` class, beat progress bar, beat kicker (`NN / NN · label` from `narration_units[i].purpose`),
  animated title words, slide-up transition between shorts (WAAPI in the reset effect), question card,
  rating card, captions default off.
- `frontend/src/Diagram.tsx` — full diagram renderer: nodes in layout slots, edges, Venn circles, funnel
  trapezoids, matrix axes, hierarchy elbows, focus = `highlight`, crowded slides dim covered items
  (`data-past`), smooth scroll to the focused card. `data-testid` `node-*` / `connection-*` are used by tests.
- `frontend/src/diagramLayout.ts` — `diagramLayout()`, `FIXED_LAYOUTS`, `CROWDED`, shared card
  `metrics()` (padding, icon circle, role line, label, detail). Reuse these metrics for hero/mini cards so
  spacing stays consistent (the user explicitly complained about cramped spacing before; it was just fixed).
- `frontend/src/playback.ts` — `atTime()`, `diagramFrame(scene, time, reduced)` (pure function of audio
  time → per-node visible/highlight/appearAt/…), `timelineError()`.
- `frontend/src/Visual.tsx`, `ChartVisual.tsx`, `ImageVisual.tsx`, `TableVisual.tsx`, `CodeVisual.tsx`.
- `frontend/src/theme.css` (light, cartoony player theme: `--ink`, `--coral`, white cards with chunky
  outline + offset shadow, polaroid/sticker cover), `styles.css`, `presentation.css`, `visuals.css`.
- `frontend/src/api.ts` / `api.generated.ts` — `Short` (`narration_units` with measured `start_ms`/`end_ms`
  and `purpose`, `scenes`, `cover`, `learning_outcome`, `measured_duration_ms`).
- `backend/app/llm/compact.py` (read only) — how production shorts are shaped: one diagram (or chart)
  scene `scene_0`; beat *i* reveals + focuses `node_i` (or `point_i`) and draws edges whose later endpoint
  is *i*; beats total 2–8. Templates: process, steps, example, timeline, cycle, comparison, key_fact,
  dos_donts, funnel, matrix, hierarchy, venn, plus chart.
- `frontend/tests/app.spec.ts`, `visuals.spec.ts`, `provider-playback.spec.ts`, `frontend/playwright.config.ts`.

## Invariants (do not break)

1. **Audio time is the only clock.** Every visual phase (photo hero, hero card, strip, overview, takeaway)
   must be a pure function of the current audio position and the measured `narration_units` timings —
   no independent timers or `setTimeout`-driven state. Seeking backwards must restore the earlier
   phase exactly; the short loops, so the end → start wrap must look right too. CSS transitions/WAAPI for
   *smoothing* between phases are fine.
2. **Reduced motion.** `prefers-reduced-motion: reduce` gets no motion (instant phase changes, no
   celebration particles). The global reduced-motion CSS rule exists in `styles.css`; JS-driven motion must
   check the media query itself.
3. **Other content keeps working unchanged:** chart/table/code/image scenes, legacy saved shorts, and rich
   multi-scene storyboards (moves, hides, state changes). Apply the hero-card mode only where it fits:
   a single diagram scene following the compact pattern (each beat reveals one node). Spatial layouts whose
   meaning is the whole arrangement — `matrix`, `venn`, likely `hierarchy` — should keep the incremental full
   diagram but still get the overview/ending treatment; justify the final split in your report.
   Charts may keep the current renderer plus the ending.
4. **Shorts without a cover** skip the photo phase entirely; beat 1 starts directly with the hero card.
5. Keep keyboard/scroll/swipe navigation, the question card (shown after the audio ends), rating card,
   transcript, captions toggle, Sources pane and existing `data-testid`s working. Accessibility: the hero
   view and strip need sensible accessible names; the full-diagram SVG summary must stay available.
6. Light theme only (theme.css). Match the existing look: white cards, chunky `--ink` outline, offset
   shadow, coral focus. Use the shared card metrics so text never crowds icons or edges at any width
   (desktop ≈ 440 px player, mobile ≈ 360 px).
7. Match the surrounding code style (dense JSX, short comments only where they add intent). No heavy new
   dependencies (no animation libraries); CSS + Web Animations API are enough.

## Environment and validation

- A Vite dev server is already running at `http://127.0.0.1:5173` and the API at `http://127.0.0.1:8000`.
  Use them; **do not kill, restart or reconfigure them**, and do not edit `.env`.
- Saved lesson for visual checks: `lesson_3a360e2e836a49a495be` (Caltrain; has covers). Ready shorts:
  `short_2fc477df113043a18c93` (steps, 23 625 ms), `short_59a458c6053b4ed6aa1c` (key_fact, 27 350 ms),
  `short_7a2a15644b344a11969e` (comparison, 25 200 ms), `short_ddced311e8634a9f83ce` (process, 25 750 ms).
  Fetch exact beat timings from `GET /api/lessons/<id>`. Other saved lessons exist (`GET /api/lessons`).
- Proven screenshot technique (keep scripts outside the repo, e.g. `/tmp`): with Playwright's chromium
  (`require('<repo>/frontend/node_modules/@playwright/test').chromium`), open the app, set localStorage
  `lastLesson` = `"<lessonId>"`, `current:<lessonId>` = `"<shortId>"`,
  `playback:<lessonId>:<shortId>` = `<ms>`; reload; wait for `.player`; screenshot `.player`. Capture each
  phase (mid beat 1 with cover, beats 2…n, last beat overview, final takeaway) for several templates, at
  desktop and a ~390 px mobile viewport, plus one reduced-motion run (`page.emulateMedia({reducedMotion:'reduce'})`).
  To exercise 5–8 items and the funnel/matrix/hierarchy/venn layouts, which no saved lesson has yet, build a
  synthetic `Short` fixture inside a throwaway harness or a Playwright route mock — do not add it to the
  user's data store.
- Save final screenshots to `.runtime/handoff-08/` (gitignored) and inspect them yourself; iterate until
  spacing and transitions look right. Judge motion by sampling several positions inside a transition.
- Required checks: `npx tsc --noEmit -p frontend`, `npm run build --prefix frontend`, and the non-live
  Playwright suites (`app.spec.ts`, `visuals.spec.ts`, `provider-playback.spec.ts`; skip `live.spec.ts`).
  Some of those expectations are already stale from recent, intentional changes (captions now off by
  default, the kicker now shows `NN / NN · label` instead of "ONE IDEA AT A TIME", light theme, 2–8 items).
  Update outdated expectations to the intended behaviour, add coverage for the new phases (photo phase,
  hero/strip, overview, takeaway, seek-back restores phase), and never weaken a meaningful assertion just
  to pass. Report any failure you could not resolve with its output.

## Boundaries

- Do **not** commit, push, or change git state beyond the working tree; the parent owns publication.
- Do not change backend code, prompts, contracts or `.env`; frontend only. If a requirement truly needs a
  backend change, stop and report why.
- Stop and report if an invariant above conflicts with a requirement, or if the dev server/API are not
  reachable.

## Expected report

1. The design as built: phases and their timing rules, which templates get hero mode vs full diagram, and why.
2. Files changed, with a one-line purpose each.
3. Validation: exact commands and results (tsc, build, Playwright suites), and test changes made.
4. Screenshot paths in `.runtime/handoff-08/` with what each shows.
5. Known limitations and follow-up suggestions (e.g. per-layout entrances, intro variety).
