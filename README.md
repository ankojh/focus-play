# Focus Play

Learn one point at a time with short local narrated visuals. Enter a goal, your current knowledge, and a time budget. The server searches YouTube and reads video captions automatically. The dark Shorts player uses readable, adaptive visuals and measured phrase captions with an accessible full transcript. Play the first short while the worker prepares later shorts.

The application uses React, TypeScript, Vite, FastAPI, SQLite and Kokoro CPU speech, with explicit TurboFieldfare or Ollama model profiles; there is no automatic fallback. **The active local deployment has rolled back to the installed `gemma4:12b-mlx` through Ollama after two saved-source cricket checks passed without repairs.** See [rollback measurements and limitations](docs/mlx-rollback.md). The fresh-install instructions below still describe the TurboFieldfare profile; do not overwrite an existing `.env` or switch models implicitly. The local model rewrites transcript content into clear, self-contained teaching narration and question explanations. Narration no longer copies YouTube speech word for word. Transcript quotes and timestamps remain available in Sources for attribution. A local model review checks for contradictions and unsupported claims and requests one rewrite when necessary; it can still miss errors. Diagrams use topic-specific icons, concise detail lines, stable entity colours, labelled semantic roles, and audio-clock-driven highlights and connection reveals. Settled arrows no longer move continuously. Model processing, speech, saved transcripts, lesson records, and audio stay on this computer. New lessons need internet access: the goal and current knowledge go to YouTube search, and video IDs go to the Supadata caption service. Search titles and snippets are not teaching evidence.

## Setup on an Apple Silicon Mac

Use Python 3.12 or 3.13, Node.js 22.12 or later, Apple Silicon, macOS 26/Metal 4 and Xcode 26/Swift 6.2 or newer for TurboFieldfare. Reuse an existing compatible installation first. Text weights occupy about 14.3 GB; a genuinely fresh install transfers about 15 GB plus build/speech dependencies and scratch space. Downloads need internet access and explicit operator approval. Saved ready shorts can play offline while the local services run. New lessons need YouTube access.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install uv==0.12.23
cd backend
UV_PROJECT_ENVIRONMENT=../.venv ../.venv/bin/uv sync --locked --extra speech --extra dev
cd ..
npm ci --prefix frontend
cp .env.example .env
.venv/bin/python scripts/download_speech.py
```

This installs the locked English language model for speech. `espeakng-loader` supplies the espeak-ng library and language files on the tested Mac. A separate Homebrew installation was not needed. If this library does not load on another system, install espeak-ng and check the provider error before you continue. CPU speech is the default. GPU speech is not required or evaluated.

Start the existing verified TurboFieldfare server in one terminal (substitute your discovered absolute paths and inspected exact checkout revision):

```sh
.venv/bin/python scripts/turbofieldfare_server.py \
  --checkout /absolute/path/turbo-fieldfare \
  --model /absolute/path/gemma4.gturbo \
  --runtime-revision EXACT_40_CHARACTER_INSPECTED_COMMIT
```

The explicit launcher runs the installed non-destructive verifier, starts one loopback-only server, and records `.runtime/turbofieldfare-launch.json`. It never clones, builds or downloads. Wait for **Owned server ready** before starting the API. Health checks do not infer, install or load another model. See the [operator runbook](docs/turbofieldfare.md) for discovery, provenance limits, fresh-install approvals, start/stop/verify, local checks and Ollama rollback. The installed Ollama GGUF is not a `.gturbo` model.

Start the application in two more terminals, from the project root:

```sh
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

```sh
npm run dev --prefix frontend
```

Before starting the API, set `YOUTUBE_API_KEY` and `SUPADATA_API_KEY` in the root `.env`. Use a server key with **YouTube Data API v3** enabled in its Google project. Create the Supadata key at [dash.supadata.ai](https://dash.supadata.ai/). Restart the API after you change a key. The keys stay on the server.

Open [Focus Play](http://127.0.0.1:5173). Enter the goal, current knowledge, and time, then click **Create my lesson**. Progress shows **Searching YouTube**, **Reading video transcripts**, and **Choosing the best videos**. Click **Play** when the first short is ready. Stop each service with Control-C in its terminal. Ready shorts remain saved. After an interrupted server run, use **Retry** to continue.

## Controls and recovery

- Play, pause, or seek within a ready short. Each short loops rather than advancing automatically. Space controls playback; left/right seek five seconds.
- Use the outline, previous/next controls, up/down keys, or vertical scroll/swipe to select a short. Refresh restores the selected short and audio position without autoplay.
- **Hide captions** reduces reading load; **Full transcript** retains every narration phrase and offers seek buttons at measured phrase boundaries. Long legacy captions and dense visuals scroll instead of truncating or shrinking text. Scroll inside an overflowing reader to read it; scroll elsewhere in the player to switch shorts.
- Like/dislike reactions are saved per short. **Sources** toggles the details pane without interrupting playback.
- Questions have a 20-second content allowance and appear near the end of every third required short. Answer feedback remains available while the short loops. The player has no extra-explanation buttons. Pauses and loops can increase elapsed time.
- **Cancel preparation** preserves ready shorts. After a provider error or interruption, **Retry** keeps ready work and uses valid cached stages. If a completed audio file is missing, use **Repair missing audio**.
- Missing evidence stops that part of a lesson. Retry or use a more focused goal. There is no import, sample, website, or model-knowledge fallback.
- Model JSON failures are reported separately from missing evidence, with the failed stage identified. Malformed or repeating output is retried from a clean prompt; schema/content errors receive targeted repair feedback. An output-token-limit error points to `LLM_MAX_OUTPUT_TOKENS` for TurboFieldfare (`OLLAMA_PREDICT` for a legacy Ollama profile). Evidence and content validation still run on every attempt.

## YouTube sources and saved history

New lessons use official YouTube search plus [Supadata](https://docs.supadata.ai/api-reference/endpoint/transcript/transcript) for existing English captions. The official [caption download API](https://developers.google.com/youtube/v3/docs/captions/download) needs permission to edit a video; a search key does not supply that permission. Supadata reads captions from its own servers, so YouTube does not rate-limit this computer. It runs in `native` mode: it returns existing captions only and never generates paid AI transcripts. The free plan has 100 credits a month and one request a second; the server waits between requests. Missing keys, quota errors, used-up credits, and insufficient evidence give actionable errors. **Retry** preserves ready work and the same persisted source/work allowance; it does not reset credits or search limits. After an allowance is exhausted, check access and start a new, focused learning request.

Each acquisition attempt uses at most two queries. Each query asks for 15 results and drops Shorts, live streams, and videos over 30 minutes. Up to `RANK_CANDIDATES` (default 8) transcripts are then requested per query; each request costs one Supadata credit, including videos without captions, which are skipped. The production path retains up to three captioned videos in YouTube search order, with at most two per channel. It no longer blocks the first video on LLM ranking and repeated ranking repairs; this uses the prior source-order fallback directly. If no usable source remains, the second query runs. The planner and per-short source/teaching review still validate evidence support. Historical `video_rankings` remain readable; no model scores are fabricated for the new selection path. Search and caption caches last one day. Adjacent captions form bounded teaching passages; their time bounds come from the actual caption records. Original caption records are also saved. Video IDs, titles, channels, URLs, and evidence timestamps remain in the lesson.

**Library** is saved lesson history; the player's **Sources** action opens evidence and lesson details. Old imports and original samples keep their labels and records. Old lessons still open. New `POST /api/lessons` requests accept `goal`, `prior_knowledge`, `time_budget_seconds`, `language`, and `request_id`. Source modes and source IDs are rejected. The import endpoint is removed. An extra short, including one added to an old lesson, uses only retrieved YouTube evidence. It searches again if existing YouTube evidence is insufficient.

## Configuration and data

Mixed storyboards support diagrams, small tables, escaped source-code listings (display only), signed zero-inclusive bar charts, and managed local raster images with annotations/attribution. No live asset provider, uploads, footage or code execution is enabled. See [mixed visual contracts, security and offline behavior](docs/mixed-visuals.md) and [fixture/dependency licence notices](fixtures/assets/NOTICE.md).

Saved diagrams retain all nine template types: process, comparison, worked example, timeline, chart, numbered steps, cycle, do vs. don't, and key-fact callout. Layouts adapt to rendered width: comparisons pair when readable, otherwise stack; key facts have a dominant label, timelines retain a rail, and cycles show returning connections. Dense content uses a fixed reading area rather than tiny SVG text. New quantitative scenes use the proper chart renderer rather than legacy mini-bars. The model chooses icons from 218 bundled Lucide icons, so diagrams require no remote images or YouTube playback. Saved lessons without icons remain readable. New lessons use the updated narration and planning; already-ready shorts are not automatically rewritten.

Passage retrieval shares the context across videos, penalises intros and sponsor reads, and includes neighbouring passages. Lessons start with basics and avoid repeated narration. All diagram motion follows the audio clock and honours reduced-motion preferences.

Requested time means one intended pass through **videos plus practice allowances**, not a forced wall-clock timer. New lessons plan in bounded batches and adapt to measured speech, aiming for 90–100% of the original budget when useful source-supported content is available. Narrow or unsupported sessions show an honest shortfall; pauses and replays may take longer. Long sessions are no longer capped at eight shorts. Explicitly approved extra time remains separate. See [session ledger, bounded limits, compatibility and offline utilisation reports](docs/session-duration.md).

See [.env.example](.env.example). Fresh setup selects `LLM_PROVIDER=turbofieldfare`, `LLM_BASE_URL=http://127.0.0.1:8080/v1` and `LLM_MODEL=gemma-4-26b-a4b-it`. The client budget is 16384 context tokens, at most 2200 output tokens, temperature 0, seed 42 (43 for the single compact-authoring repair) and repetition penalty 1.0. Server context/runtime controls are startup settings verified through the owned-process receipt, not per-request switches. Different seeds at temperature zero do not guarantee different output. TurboFieldfare has **no JSON-mode/schema enforcement**: the specialised schema is in the prompt and strict JSON, JSON Schema, Pydantic and domain/evidence validation still run before publication. Thinking is not an exposed API control; the inspected runtime filters thought channels and emits visible answer content. No tools are sent or executed. Ollama retains `format` and `think=false`. The worker runs one model task at a time. Compact production planning, drafting and review share a default 60-second stage budget across at most two attempts. First-video processing has a default 180-second window after dequeue, not a guarantee of successful output. TurboFieldfare I/O is cancelled at the deadline; synchronous acquisition/speech checks it at existing call/unit boundaries. See [the first-video redesign and actual measurements](docs/compact-authoring.md). Production authoring uses a compact contract: 2–4 cited beats with visual labels, one diagram or source-valued chart per short, and an optional checkpoint. The app assigns IDs/layouts and reveal/focus/connection operations, then validates the existing version-2 storyboard. Existing richer saved storyboards and explicit diagnostic calls retain all mixed renderers and their 2–5-beat/1–3-scene contracts. This is deliberately a narrower generation path, not a renderer removal. Operations are timed only after speech measurement. Scene and action times are absolute audio milliseconds, with contiguous half-open scene intervals and a held final frame. Word counts are bounded; measured audio sets the final duration, at most 40 seconds. Kokoro uses `af_heart`, a fixed speech speed of 1, 24 kHz mono PCM WAV, and measured phrase boundaries. Captions use these measured phrase boundaries, not guessed word timestamps. Speech speed, voice, waveform handling and pause policy are unchanged. See [presentation changes, screenshots, audio examples and remaining review limits](docs/presentation-polish.md).

`SPEECH_PROVIDER=macos` selects a labelled development substitute. It uses `say` and `afconvert`. It is not Kokoro. The default and the reported live tests use Kokoro.

`.data/` contains SQLite records, parsed transcripts, managed audio and raster assets, local Hugging Face files, and diagnostics. Bundled assets are repaired locally at startup; saved lessons remain playable offline with the local server running and the whole data directory intact. Cache keys include source identity/content, provider/runtime/verified manifest identity (Ollama digest for rollback), effective settings, prompt/schema/parser versions, storyboard/compiler versions, language and voice. Historical ready provenance is never relabelled. Unfinished lessons reject a different runtime/model/settings profile before new source spending. Same-runtime prompt/parser/authoring fixes may resume an unpublished lesson while preserving its plan, sources, IDs and consumed allowances. Once media or coverage history exists, its profile cannot be rebound; restore the original profile or create a fresh lesson. Missing-audio repair uses saved narration/timestamps and the original speech profile without requiring the old LLM. This data is ignored by Git. Back up the whole data directory while the API is stopped. Do not share it if the transcripts are private. The UI assets and voices need no remote fonts or services after setup.

## Checks

```sh
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python scripts/export_openapi.py
npm run types --prefix frontend
npm run build --prefix frontend
npm exec --prefix frontend -- playwright install chromium
npm test --prefix frontend
# Separate live browser test; YouTube and Supadata keys and local providers must be ready.
FOCUS_LIVE=1 npm test --prefix frontend -- tests/live.spec.ts
```

The Python tests use explicit test providers. Default browser checks use explicit API/audio fixtures; the opt-in real-output playback check below forwards reads to an isolated API serving actual generated content and Kokoro audio. See [storyboard implementation and compatibility](docs/storyboards.md) for the versioned format, measured compiler cost, screenshots, and live-quality limitations. Regenerate the shared storyboard playback fixture with `.venv/bin/python scripts/export_storyboard_fixture.py` after changing its authoring fixture or compiler. They do not establish live source access, model quality, or speech performance. See [YouTube change checks](docs/youtube-source-change.md) for current results and the remaining live-check dependency. [Earlier validation](docs/validation.md) and [earlier performance measurements](docs/performance.md) describe the previous imported-source version. See [design and limitations](docs/design.md) for the current flow.

Readiness now includes durable required audio/images, contiguous remaining media, fair serial worker turns, and a bounded two-short browser preload window. Playback still loops until navigation and is never gated on a startup buffer. See [readiness design, metrics, privacy and limitations](docs/playback-readiness.md).

For reproducible scheduler/consumption fixtures (no source credits):

```sh
.venv/bin/python scripts/benchmark.py --mode fixture --buffer-seconds 60
.venv/bin/python scripts/report_performance.py --input docs/readiness-fixture-runs.json
```

To measure the current YouTube flow, first approve source credits, start local providers, configure both server keys, and verify the cache state. For example, a repeat/cache-reuse evaluation:

```sh
.venv/bin/python scripts/benchmark.py --mode live --approve-source-credits \
  --cache-state partially-cached --budgets 120 300 600 1200 --runs 1
# Use the new provider-specific .runtime/... output printed by the benchmark.
.venv/bin/python scripts/report_performance.py --input .runtime/PROVIDER-readiness-live-TIMESTAMP.json \
  --output .runtime/PROVIDER-readiness-live-measurements.md
```

Cache labels are operator declarations, not forced by the script; inspect actual stage hits. The script creates new request IDs and records acquisition calls, exact provider settings, errors, duration ledgers, stage/cache metrics, and explicitly synthetic one-pass stalls (not observed looping-player stalls). Reports are separate from historical imported-source results. Live source acquisition may cost credits. Do not run other generation tasks during this check.

### Opt-in real-provider and cached-evidence checks

No source credits are used by these commands. They still run real local inference
and speech, so use an explicit preparation budget and avoid competing generation.
Use new report/work paths; existing output is never overwritten.

```sh
.venv/bin/python scripts/provider_check.py --approve-inference \
  --budget-seconds 900 --output .runtime/turbofieldfare-check-NEW.json
# Full Jobs path with actual captions already saved in a prior YouTube lesson:
.venv/bin/python scripts/cached_lesson_check.py --approve-inference \
  --source-lesson SAVED_LESSON_ID --duration-seconds 60 --budget-seconds 900 \
  --work-dir .runtime/turbofieldfare-cached-NEW
```

The cached check reads the existing lesson read-only, preserves its source IDs,
quotes/times/hashes, uses a fresh isolated data directory, reuses the local speech
cache in place, and **disables** new acquisition. An unsupported or broader goal
can fail rather than spend credits; it does not substitute evidence. This is not
proof of fresh YouTube acquisition.

To play a passed mixed-visual provider report through the real frontend:

```sh
.venv/bin/python scripts/export_provider_playback.py \
  --report .runtime/turbofieldfare-check-NEW.json \
  --output-dir .runtime/turbofieldfare-playback-NEW
# Isolated temporary API; do NOT point this at an active worker's data directory.
DATA_DIR=.runtime/turbofieldfare-playback-NEW YOUTUBE_API_KEY= SUPADATA_API_KEY= \
  .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001
# In another terminal; no new generation/acquisition is triggered by this test:
FOCUS_PROVIDER_API=http://127.0.0.1:8001 npm test --prefix frontend -- tests/provider-playback.spec.ts
```

The exporter requires an actually passed storyboard, source/teaching review and
matching measured WAV/cache metadata. It never substitutes a fixture model/audio
or regenerates missing output. Stop the temporary API after inspection; the main
application remains on 8000. See the [migration handback](docs/turbofieldfare-migration.md)
for real results, failed experiments and remaining limits.

## Downloads and licences

- [TurboFieldfare](https://github.com/drumih/turbo-fieldfare): Swift/Metal runtime, Apache-2.0. The verified reusable installation and binary SHA are recorded in the [migration report](docs/turbofieldfare-migration.md). No weights/binaries are committed.
- [Gemma 4 26B-A4B IT 4-bit](https://huggingface.co/mlx-community/gemma-4-26b-a4b-it-4bit): pinned checkpoint `0d77464eeb233a2da68ebf9d7dc4edaac7db956d`, MLX affine 4-bit group 64 with 8-bit router. Weights have separate [Gemma terms](https://ai.google.dev/gemma/terms); preserve upstream model notices and review TurboFieldfare's `THIRD_PARTY_NOTICES.md`. Lower residency is not a measured guarantee of lower heat/power.
- Historical [Qwen3 8B](https://ollama.com/library/qwen3:8b) reports remain historical, not the current primary runtime.
- [Kokoro 82M](https://huggingface.co/hexgrad/Kokoro-82M): `config.json`, `kokoro-v1_0.pth`, and `voices/af_heart.pt`; Apache-2.0 for the model repository and voice asset. The setup script records the exact revision in `.data/speech-download.json`. The tested weight file is about 327 MB and the voice about 510 KB.
- [Kokoro Python](https://github.com/hexgrad/kokoro): Apache-2.0. Misaki English uses its packaged dictionary, spaCy `en_core_web_sm` 3.8.0 (MIT), and the bundled espeak-ng library (GPL-3.0). Python, PyTorch, and other dependencies have their own licences.

Keep the original model notices when you redistribute their files. See the model card for the upstream training data acknowledgements. Generated local lessons have no metered cloud generation fee. The computer, electricity, disk storage, setup time, and YouTube API quota still have costs. This build does not measure electricity or assign those costs a monetary value.
