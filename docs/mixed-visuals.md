# Mixed visuals and managed local assets — handoff #3

## Delivered scope

The operator selected **Stages A + B, local fixtures only**. No external asset vendor, paid API, live acquisition, upload/import UI, platform embed, generative video or footage was added. Existing YouTube transcript acquisition is unchanged and confers no image/footage rights.

- Stage A: diagrams, tables, source-snippet code listings, and proper signed bar charts participate in the same measured storyboard timeline.
- Stage B: a managed raster image/screenshot record and safe renderer, normalized annotations, attribution, loading/error/retry states, durable files and references, and one bundled original CC0 illustration. Screenshot records use the same raster renderer (`asset.kind = screenshot`); this delivery does **not** include a live screenshot capture/provider or a reviewed software-workflow lesson.
- Equations, line charts/multi-series charts, custom domains, executable examples, and Stage C footage remain out of scope.

Generation chooses a format for the teaching intent. It may use a supported simpler diagram if there is no appropriate snippet/data/image. Diversity is not a quota. The first scene is no longer forced to be a diagram matching the planner's suggested template. Source-only example policy and bounded source/teaching review remain in force.

## Contract and compatibility

`backend/app/contracts.py` exposes discriminated authoring and playback unions. `visual_contracts.py` contains the bounded payloads; `contract_base.py` contains shared evidence/action primitives to avoid circular imports. OpenAPI and TypeScript are generated, not maintained by hand.

Authoring scenes have `id`, `kind`, `summary` and renderer-specific data. New data renderers also carry `visual_version: 1`. Playback adds absolute `start_ms/end_ms`, `beat_ids`, `evidence_references` and compiled actions. `storyboard_version: 2` identifies the measured scene envelope, including diagrams. Diagram fields stay flat deliberately so existing saved diagrams render without a destructive migration; **new non-diagram renderers use a `payload` union rather than expanding diagram nodes**.

| Kind | Bounds and legal targets | Supported beat operations |
| --- | --- | --- |
| diagram | Existing 2–4 nodes, connections, authored states, allowlisted icons/layouts | Existing reveal/hide/focus/connect/move/change_state |
| table | 1–4 columns; 1–8 uniquely identified rows; rectangular text cells, at most 120 characters each | Reveal/hide/focus rows; focus a cell (`row_0_c1`) in a visible row |
| code | Plain text, 1–30 lines, at most 200 characters per line / 6,000 total; allowlisted language; cited segment ID | Reveal/hide/focus `line_1` etc.; **display only, never execution** |
| chart | One bar series, 1–8 finite values in ±1e12; labels, unit, axis label, point-level segment IDs; fixed zero-inclusive linear scale | Reveal/hide/focus point IDs |
| image | Existing managed asset ID, actual dimensions, alt/caption; at most 6 unique annotations with coordinates in [0,1] and segment IDs | Reveal/hide/focus image and annotations; image must be visible first |

Every primary item must be revealed before use. Illegal renderer operations, duplicate targets, unknown discriminators, empty datasets, nonfinite/out-of-bounds values and corrupt payloads are rejected. Table cells inherit row visibility and support focus only. No arbitrary line-highlight ranges are accepted: focusing individual validated line IDs implements the bounded initial highlight vocabulary.

`storyboard.py` compiles every kind after speech measurement. It reparses payloads before compilation so in-place mutation cannot bypass Pydantic bounds. Intervals remain contiguous and half-open, with a held final frame, and each action resolves to the exact start of its measured beat. The compiler is now `2-mixed-visuals`; prompt version is `18`, schema version `5-mixed-visuals`. Compiler/prompt/schema/visual-version fingerprints and candidate asset IDs invalidate old drafts appropriately. Already-ready lessons and their existing audio are not regenerated.

The saved-diagram adapter inserts `kind: diagram` when absent. Both version-1 flat diagrams and version-2 diagram storyboards remain readable, including the legacy mini-bar chart template. **New authoring cannot use that mini-bar template**: quantitative scenes must use `kind: chart`. New data visuals cannot be smuggled into a version-1 short.

The frontend dispatches through `Visual.tsx`; `Diagram.tsx` remains focused on diagrams. Each new renderer uses the same audio clock and recomputes state from actions, so seek/loop/restore do not accumulate state. The loop, reactions, navigation buttons and gestures are retained. Overflowing data panels are focusable and scrollable; wheel/swipe inside a reader reads its content rather than switching shorts. Gestures outside the reader and navigation buttons still switch shorts.

## Evidence policy

- Code text must be an **exact substring of its own cited passage**, which must also be cited by a beat in that scene. No synthetic executable-code policy was introduced. Many spoken transcripts do not contain an exact code snippet: use a simpler format in those cases.
- Each chart point must match a signed decimal number in its **own** cited passage; its unit must occur there too. A bare numeric match is not independent fact verification: the bounded source review also checks label/value associations, units, uncertainty and narrated comparisons.
- The chart domain is derived once from the entire dataset and includes zero, keeping one truthful scale across reveals. Signed bars extend left/right from that zero. Zero values have a distinct zero marker, including the right-edge zero baseline for negative-only data. All-zero datasets explicitly disclose the display-only 0–1 domain. No logarithmic, truncated or independently rescaled bars are supported.
- Tables and charts expose an illustrative-data label. That flag is **not** permission for the model to invent entities or measurements: generation still undergoes the existing source-only review. Diagnostic fixture data are deliberately synthetic and prominently identified as such, not real benchmark results.
- Annotation citations must resolve to a scene beat's source passage. Narration, labels, captions and table cells undergo the expanded source review. Asset permission is recorded separately and is not evidence for a teaching claim. Source review remains a local model assessment, not an independent expert verdict.

## Asset lifecycle, limits and serving

`Assets` is an internal service, not an upload/network API. Application-owned files in `fixtures/assets/manifest.json` are installed at startup. The manifest records original source, creator, permission, attribution, licence URL, context and illustrative status. The included illustration is a clearly labeled schematic, not a fake product screenshot.

Lifecycle: trusted local fixture + rights metadata → verify/decode → canonicalize → hash/deduplicate → atomic file/record publication (`ready`) → attach to compiled scene → reference lesson/short → final short validation → saved lesson publication. Invalid acquisition returns a useful validation error without publishing a partial asset. Missing/corrupt stored content is recorded as `missing` with a repair reason. Successful retry restores `ready`. Cancellation checkpoints occur before decoding, after verification and before atomic publication; no remote jobs or download cancellation behavior is claimed.

Bounds are constants in `assets.py`, not user/model-controlled settings:

- Single-frame PNG or JPEG input only; no SVG, HTML, animation, audio or video.
- At most 5 MB input and canonical output, 4,096 pixels per dimension, 8 million decoded pixels.
- Pillow verifies actual encoding and fully decodes it under pixel/decompression-bomb limits. Declared extensions or MIME headers do not determine acceptance. RGB PNG re-encoding removes EXIF, ancillary metadata and appended executable bytes; stored MIME is derived from the canonical encoding.
- SHA-256 of the **canonical stored bytes** is the stable opaque asset ID, content hash and filename. Original encodings are not served. First accepted provenance is retained on content deduplication.
- Temporary writes are flushed/fsynced and atomically replaced before the ready DB record is committed. Retry is idempotent and repairs bundled bytes.
- SQLite `assets` holds metadata and `asset_refs` holds lesson/short attachments. There is **no automatic deletion**. Future garbage collection must consult both saved lesson references and this reference table; orphaned references after cancellation are safer than deleting active media.

Routes:

- `GET /api/assets/{64-hex-id}` returns checksum-verified bytes from a no-follow directory/file descriptor, never a client path. Symlink roots/files, traversal, missing files and checksum mismatches fail closed. Immutable private caching, `nosniff` and restrictive response CSP are set.
- `GET /api/assets/{id}/metadata` returns the bounded provenance record, including status/failure reason.

Existing host/origin middleware applies to both. React escapes all code/captions/annotations/text; no raw model HTML, SVG or script is inserted. Licence/source URLs are displayed as text in provenance, not turned into model-controlled executable links. No API secrets or external-service keys are needed or stored in these records.

**No asset network downloader exists.** There is no URL-to-asset API and no browser hotlinking. Host allowlisting, DNS/private-address/redirect defenses, deadlines and bounded remote downloads must be designed and tested before live acquisition is approved. Tests prove rejection of URL/path IDs and absence of a remote import route; they do **not** claim to exercise a nonexistent downloader's rebinding/redirect/timeout defenses.

## Offline playback and repair

With the local API/UI running and the complete data directory preserved, saved ready lessons use local audio and managed assets without network acquisition. Back up SQLite plus `audio/` and `assets/` together. This is **offline local-server playback**, not a service-worker PWA that works after shutting down the API.

Missing essential images are not marked optional or silently replaced with a misleading diagram. The player displays an actionable error and explicit image retry; preparing a new ready short requires a checksum-valid, ready asset with matching dimensions. Restart reinstalls the bundled CC0 fixture and repairs missing/corrupt bytes (unsafe symlinks are intentionally not repaired). Retry the image or lesson after restart. Restoring an unbundled managed asset would require the backup or a separately approved future acquisition flow.

No migration command is required: the service creates `assets` and `asset_refs` tables if absent. Older saved data is adapted on read, not rewritten in bulk. Keep the whole existing data directory; there is no new cache-clearing requirement.

## Fixtures, screenshots and verification

- `scripts/export_visual_fixture.py` creates `fixtures/mixed-visuals.json` through the production evidence attachment, validation and measured compiler. These are **original illustrative diagnostics**, not live YouTube/model-quality demonstrations.
- One fixture short mixes diagram → table → chart at 0/10/20 seconds. Other shorts reveal two display-only source-code lines and a managed image/annotation at 0/15 seconds. Silence WAVs are browser-test audio, not narration-quality evidence.
- `backend/tests/test_visuals.py` covers discriminators, bounds, source snippets/point citations, capabilities, mutated payloads, managed IDs/rights, decode/pixel/byte limits, malformed/animated/SVG content, stripped appended scripts, atomic retry/deduplication, missing/corrupt/symlink/traversal cases, cancellation, reference retention, local routes and model candidate allowlisting.
- `frontend/tests/visuals.spec.ts` covers 390/1280 widths, boundaries/seek/reduced motion, code injection, long labels, zero/negative/large values, negative-only zero markers, reader scrolling, images/annotations/attribution/missing-file retry and corrupt snapshots.
- Representative diagnostic screenshots: [table mobile](visual-screenshots/table-390.png), [code mobile](visual-screenshots/code-390.png), [chart mobile](visual-screenshots/chart-390.png), [image mobile](visual-screenshots/image-390.png). Desktop equivalents are in the same directory.
- Asset and dependency licence notices: [fixture notices](../fixtures/assets/NOTICE.md), [Pillow and bundled-library notices](licenses/Pillow-11.3.0.txt).

Final verification commands:

```sh
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python scripts/export_openapi.py
npm run types --prefix frontend
npm run build --prefix frontend
npm test --prefix frontend
```

Results: **195 Python tests passed; 45 browser tests passed, 1 live-provider test skipped**. The Python suite reports an existing Starlette/httpx deprecation warning. An initial browser run caught a malformed test seek (9999 is outside a 100 ms slider step) and a timing-sensitive existing 4× loop assertion; the new test now uses native audio seeks for non-step boundaries, and the untouched existing loop test passed on subsequent full runs.

Image inspection at 390/1280 checked illustrative labels, source-code focus, chart scale/visible signed values, image credit and annotation alignment. The first mobile chart layout clipped comparison values; it was compacted and scroll-reader behavior was added before the final screenshots. This is assistant screenshot inspection, **not the requested human/expert teaching review**. Human source-supported worked-example review for each kind, and an approved live-provider generation check, remain acceptance follow-ups. No source credits were spent and no claim of broad real-world visual quality is made.

A local diagnostic microbenchmark (100 warm iterations, three fixture shorts including source validation, reparsing and compilation; no model/speech calls) is recorded below. It is not a generation latency benchmark. The fixture's managed raster is 640×400 / 7,316 canonical bytes; there is no network/media-generation latency for these assets.

| Measurement | Local result |
| --- | ---: |
| Cold fixture install/decode/store | 9.87 ms |
| Warm three-short validation/compilation, median | 0.97 ms |
| Warm three-short validation/compilation, p95 | 1.03 ms |

Measurements used the existing Python 3.12 environment with Pillow 11.3.0 on the developer machine. Model/voice settings are not applicable because no model or speech provider was called.
