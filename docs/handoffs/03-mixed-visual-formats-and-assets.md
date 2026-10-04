# #3 — Mixed visual formats and safe asset handling

## Purpose and agreed context

Builder handoff for Focus Play at `/Users/ankojh/b12/focus-play`. Paths below are repository-relative.

The user wants diagrams plus other appropriate visual formats, alongside improved teaching, storyboards, polish, and enough content for the requested whole-session duration. This workstream owns renderer diversity and the provenance/security lifecycle of external assets. It does not author a new curriculum, control session duration, or replace the local generation stack.

The user approved the direction, not a specific asset vendor, paid API, cloud-generation provider, or licensing policy. Those choices require a product decision before introducing new external acquisition. The renderer architecture and controlled local fixtures can proceed independently.

## Current state to verify

- `backend/app/contracts.py`: `Template`, `DiagramNode`, `Connection`, `Scene`, model-facing draft types.
- `frontend/src/Diagram.tsx`: nine named templates, all largely rendered using shared node cards and connections.
- `backend/app/jobs.py`: `TEMPLATES`, model drafting and single-scene compilation.
- `backend/app/validation.py`: diagram structure, chart values, and visual evidence validation.
- `backend/app/providers.py`: allowlisted icons and constrained `ModelShort` output.
- `backend/app/main.py`: local-origin protections and the safe audio-serving route.
- `backend/app/config.py`, `backend/app/store.py`: local directories, storage, source records, and caches.
- `backend/app/youtube.py`, `backend/app/sources.py`: transcript acquisition; this is not footage acquisition.

Important existing limitations:

- `example` is a diagram template, not an executable worked example or dedicated code/table renderer.
- Chart nodes currently use nonnegative values limited to 100, lack a full axis/unit model, and render small bars under cards. That is insufficient for general-purpose quantitative graphics.
- The model can choose bundled icons but cannot safely provide arbitrary rendering code.
- Sources establish transcript evidence and links, not permission to reproduce source footage or images.

Pre-existing uncommitted changes exist in `frontend/src/App.tsx`, `frontend/src/Player.tsx`, `frontend/src/styles.css`, `frontend/tests/app.spec.ts`, and `frontend/tests/live.spec.ts`. Preserve them. Current playback loops with swipe/wheel navigation and like/dislike controls; do not restore earlier controls or automatic advancement.

## Desired format selection

Choose the visual that explains the subject, not a random format for variety.

| Teaching content | Preferred controlled format |
| --- | --- |
| Relationships or processes | Existing diagram with progressive states |
| Data lookup or transformation | Small table with highlighted cells/rows |
| Programming | Escaped code listing and validated line highlights |
| Quantitative comparison/trend | Proper chart with units, labels, and truthful scale |
| Worked calculation | Stepwise equation or calculation state |
| Software workflow | Permissioned screenshot with annotations |
| Physical object or geography | Relevant image with attribution |
| Physical technique | Permitted footage where available; do not substitute misleading symbolic diagrams |

Generative video is not the default. It introduces a separate cost, latency, consistency, and verification problem and is outside the initial scope. A licensed stock image is not automatically evidence for a factual claim either.

## Recommended delivery stages

### Stage A: deterministic local formats

Implement the shared renderer contract plus a useful subset: diagram, table, code, and a corrected chart representation. Add equations if source fixtures justify them. Each format must have bounded, schema-validated data and a safe renderer.

This stage requires no new remote asset provider. Use clearly labelled illustrative content or source-derived content according to the existing evidence policy. Do not execute model-generated code or treat fabricated numbers as measurements.

### Stage B: images and screenshots

Add the managed asset lifecycle, provenance metadata, annotations, loading states, and evidence linkage. Test with bundled fixtures whose licences permit inclusion. Before live acquisition, agree an allowlisted source/provider and permissible reuse rules with the user.

Do not add an upload/import UI by default; the current product intentionally removed manual source entry. If user-provided assets are desired, obtain an explicit decision and design separate validation.

### Stage C: permitted footage

Only after image acquisition and rights handling are reliable. Define clip boundaries, audio policy, caching, duration, and synchronization. A transcript source URL is not authorisation to download or redistribute footage. Embedding a platform player introduces network, playback, and policy constraints and should not be smuggled in as a simple image-like asset.

## Shared scene contract

Coordinate with [#1 Storyboards](01-visual-storyboards-and-audio-sync.md) before modifying `Scene`.

Recommended architecture:

- A versioned scene envelope containing timing, stable identity, visual kind, accessible summary, and evidence/asset references.
- A discriminated union of bounded renderer payloads, rather than an ever-growing diagram node object with dozens of optional properties.
- Explicit renderer capabilities and legal beat operations.
- A compatibility adapter for saved flat diagram scenes.

Candidate payload requirements:

- **Diagram:** allowlisted nodes, roles, connections, and state changes.
- **Table:** bounded columns/rows, headers, cell values, highlight targets, and illustrative-data labelling.
- **Code:** language identifier, plain code text, bounded line count/length, highlight ranges, and optional displayed trace values. Rendering is not execution.
- **Chart:** chart kind, finite numeric data, units, labels, scale/domain policy, source refs per series/claim, and accessible values. Support negative or larger values only when the renderer and validation do so truthfully.
- **Equation:** bounded expressions/steps in a constrained display format; reject untrusted macros, HTML, or executable extensions.
- **Image/screenshot:** managed asset ID, intrinsic dimensions, alt text, caption/credit, bounded normalized annotation coordinates, and claim references.
- **Footage, later:** managed asset ID, permitted trim interval, muted/original-audio policy, and deterministic timing behaviour.

Never persist arbitrary model-supplied local paths or fetch arbitrary model-supplied URLs from the browser. The model should select an existing managed asset ID from candidates the application has already validated.

## Evidence and semantic validation

The narration and visuals must teach the same supported thing. Review more than the label text:

- A chart's data, unit, scale, comparisons, and uncertainty must be correct. Zero-based bars are the safe default; any alternative scale must be explicit and non-misleading.
- A code example must reflect the source-supported mechanism and be clearly illustrative if synthetic. Do not relax the current system instruction against invented executable code without an explicit, tested policy. Display-only source snippets are a safe initial step.
- Equation transformations need support and should not invent numerical inputs as though quoted.
- A screenshot may be outdated or depict a different product version; capture metadata and avoid unsupported instructions.
- Images can be illustrative without proving a claim. Keep asset provenance distinct from teaching evidence.
- If no suitable format/asset is available, use a truthful simpler representation or omit the unsupported point. Do not render a fake screenshot that looks authoritative.

## Managed asset lifecycle

Suggested stages: discovered -> rights/provenance checked -> downloaded -> content validated -> stored -> attached -> ready. Exact enums are implementation choices.

Minimum metadata:

- Stable asset ID and content hash.
- Kind, MIME type, byte size, dimensions, and duration where applicable.
- Original source URL and creator/provider.
- Licence/permission basis, attribution text, licence URL where applicable, and acquisition time.
- Local managed filename, never a client-supplied filesystem path.
- Source/version context and whether the asset is illustrative.
- Validation status and a useful failure reason.

Deduplicate by content hash. Write atomically. Track references before cleanup so active or saved lessons do not lose required media. Saved ready lessons should continue to work offline when their managed assets are present. Do not hotlink all images and call the result offline-capable.

Add repair or a documented fallback for missing assets. Do not mark a visually essential asset optional just to report a short as ready.

## Security requirements

Remote acquisition is a new attack surface:

- Allowlist providers/hosts and validate redirects; block loopback, private/link-local targets, credentials in URLs, and unsupported schemes. Account for DNS/redirect rebinding rather than relying only on string matching.
- Enforce connection/read deadlines, download size, decoded pixel count, media duration, and supported MIME/encoding limits.
- Verify actual content, not just an extension or `Content-Type` header.
- Prefer safe raster formats initially; reject or rigorously sanitize SVG. Never render raw remote HTML or scripts.
- Keep downloads in a managed directory with opaque safe IDs; reject traversal and symlinks when serving files.
- Avoid shell interpolation. If media tools are required, pass validated arguments and enforce resource/time limits.
- Escape code, annotations, captions, and source text in React. No `dangerouslySetInnerHTML` for model content.
- Use narrow local API routes and retain current host/origin protections.
- Do not persist API secrets in asset metadata or expose them to the frontend.

## Integration and files

- `backend/app/contracts.py`: visual discriminated union, asset records, evidence links, backward compatibility.
- `backend/app/providers.py`: task/schema specialization for supported visual kinds and allowed asset IDs; prompt/version updates.
- `backend/app/validation.py`: renderer-specific structural and semantic validation.
- `backend/app/jobs.py`: asset preparation and final ready checks; bounded fallback policy.
- Consider dedicated asset service/storage helpers rather than putting network downloads into model drafting.
- `backend/app/main.py`: safe managed-asset serving endpoint if Stage B is implemented.
- `backend/app/config.py`: bounded validated acquisition settings; document them in `.env.example` without secrets.
- `frontend/src/Player.tsx`: dispatch to a visual renderer through a shared component.
- Keep `Diagram.tsx` focused; add separate renderer components and common accessible framing.
- Regenerate OpenAPI and TypeScript contracts.

[#2 Teaching](02-teaching-quality-and-lesson-coherence.md) owns visual intent and example continuity. [#4 Polish](04-presentation-captions-and-narration-polish.md) owns shared type/colour/layout tokens. [#5 Duration](05-session-duration-and-evidence-coverage.md) owns activity budgets. [#6 Buffering](06-generation-buffering-and-playback-readiness.md) owns readiness and bounded prefetching.

## Tests and acceptance

- Contract tests for every visual discriminator and malformed payload.
- Renderer tests at narrow widths, long labels, zero values, negative/large chart data, and empty/invalid datasets.
- No injected HTML, script, URL, code, annotation, or SVG executes.
- Asset tests cover blocked networks, redirects, oversized/decompression-heavy content, mismatched MIME, timeouts, missing rights metadata, traversal, missing files, cancellation, and retry.
- Attribution remains visible/discoverable alongside evidence.
- Legacy saved diagrams render unchanged.
- Unknown/corrupt visual kinds fail clearly rather than producing a blank ready player.
- Diagrams, code/table, and charts can appear in one storyboard without losing audio synchronization.
- Live assets have an auditable provenance record and offline playback after caching, where permitted.

Human-review at least one source-supported worked example per implemented kind. A mixed lesson should be more informative, not merely more varied. Report which stages are delivered; do not claim “real visuals supported” based only on a static fixture.

## Verification and builder handback

```sh
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python scripts/export_openapi.py
npm run types --prefix frontend
npm run build --prefix frontend
npm test --prefix frontend
```

Deliver implementation, renderer/asset contract documentation, licence notices for bundled fixtures/dependencies, security tests, representative screenshots, and migration/offline behaviour notes. Any new live provider or paid dependency requires explicit approval. Do not commit or push without permission; follow repository identity and Conventional Commit policy if authorised later.
