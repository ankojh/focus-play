# Focus Play

Learn one point at a time with short local narrated visuals. Enter a goal, your current knowledge, and a time budget. The server searches YouTube and reads video captions automatically. The dark Shorts player uses readable, adaptive visuals and measured phrase captions with an accessible full transcript. Play the first short while the worker prepares later shorts.

The application uses React, TypeScript, Vite, FastAPI, SQLite, a local Ollama model, and Kokoro CPU speech. The local model rewrites transcript content into clear, self-contained teaching narration and question explanations. Narration no longer copies YouTube speech word for word. Transcript quotes and timestamps remain available in Sources for attribution. A local model review checks for contradictions and unsupported claims and requests one rewrite when necessary; it can still miss errors. Diagrams use topic-specific icons, concise detail lines, stable entity colours, labelled semantic roles, and audio-clock-driven highlights and connection reveals. Settled arrows no longer move continuously. Model processing, speech, saved transcripts, lesson records, and audio stay on this computer. New lessons need internet access: the goal and current knowledge go to YouTube search, and video IDs go to the Supadata caption service. Search titles and snippets are not teaching evidence.

## Setup on an Apple Silicon Mac

Use Python 3.12 or 3.13, Node.js 22.12 or later, and Ollama. Allow at least 10 GB free disk space for the first setup. Downloads need internet access. Saved ready shorts can play offline while the local services run. New lessons need YouTube access.

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

Start Ollama in one terminal:

```sh
OLLAMA_NO_CLOUD=1 OLLAMA_NUM_PARALLEL=1 OLLAMA_HOST=127.0.0.1:11434 ollama serve
```

Download the local model in another terminal:

```sh
ollama pull qwen3:8b
```

For the project-local runtime used in this build, replace `ollama` with `.runtime/ollama` and add `OLLAMA_MODELS="$PWD/.data/ollama"` to the serve command. The runtime directory is ignored by Git. Ollama can create its own configuration and key in the user profile. Cloud model names and remote model metadata are rejected by this application.

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
- Model JSON failures are reported separately from missing evidence, with the failed stage identified. Malformed or repeating output is retried from a clean prompt; schema/content errors receive targeted repair feedback. An output-token-limit error points to `OLLAMA_PREDICT`. Evidence and content validation still run on every attempt.

## YouTube sources and saved history

New lessons use official YouTube search plus [Supadata](https://docs.supadata.ai/api-reference/endpoint/transcript/transcript) for existing English captions. The official [caption download API](https://developers.google.com/youtube/v3/docs/captions/download) needs permission to edit a video; a search key does not supply that permission. Supadata reads captions from its own servers, so YouTube does not rate-limit this computer. It runs in `native` mode: it returns existing captions only and never generates paid AI transcripts. The free plan has 100 credits a month and one request a second; the server waits between requests. Missing keys, quota errors, used-up credits, and insufficient evidence give an error and **Retry**.

Each acquisition attempt uses at most two queries. Each query asks for 15 results and drops Shorts, live streams, and videos over 30 minutes. Up to `RANK_CANDIDATES` (default 8) transcripts are then requested per query; each request costs one Supadata credit, including videos without captions, which are skipped. The local model scores each transcript from 1 to 5 for relevance, fit to the learner's current knowledge, teaching quality, on-topic density, and caption quality. The server keeps the three best videos with relevance of at least 3, level fit of at least 2, and at most two per channel. If no video passes, the second query runs. If the model cannot rank, YouTube's order is used. Scores and reasons are saved in the lesson as `video_rankings`. Search and caption caches last one day. Adjacent captions form bounded teaching passages; their time bounds come from the actual caption records. Original caption records are also saved. Video IDs, titles, channels, URLs, and evidence timestamps remain in the lesson.

**Library** is saved lesson history; the player's **Sources** action opens evidence and lesson details. Old imports and original samples keep their labels and records. Old lessons still open. New `POST /api/lessons` requests accept `goal`, `prior_knowledge`, `time_budget_seconds`, `language`, and `request_id`. Source modes and source IDs are rejected. The import endpoint is removed. An extra short, including one added to an old lesson, uses only retrieved YouTube evidence. It searches again if existing YouTube evidence is insufficient.

## Configuration and data

Mixed storyboards support diagrams, small tables, escaped source-code listings (display only), signed zero-inclusive bar charts, and managed local raster images with annotations/attribution. No live asset provider, uploads, footage or code execution is enabled. See [mixed visual contracts, security and offline behavior](docs/mixed-visuals.md) and [fixture/dependency licence notices](fixtures/assets/NOTICE.md).

Saved diagrams retain all nine template types: process, comparison, worked example, timeline, chart, numbered steps, cycle, do vs. don't, and key-fact callout. Layouts adapt to rendered width: comparisons pair when readable, otherwise stack; key facts have a dominant label, timelines retain a rail, and cycles show returning connections. Dense content uses a fixed reading area rather than tiny SVG text. New quantitative scenes use the proper chart renderer rather than legacy mini-bars. The model chooses icons from 218 bundled Lucide icons, so diagrams require no remote images or YouTube playback. Saved lessons without icons remain readable. New lessons use the updated narration and planning; already-ready shorts are not automatically rewritten.

Passage retrieval shares the context across videos, penalises intros and sponsor reads, and includes neighbouring passages. Lessons start with basics and avoid repeated narration. All diagram motion follows the audio clock and honours reduced-motion preferences.

See [.env.example](.env.example). `OLLAMA_MODEL` selects an installed local model. The default uses 8192 context tokens, at most 2200 output tokens, temperature 0, seed 42 (43 and 44 for the two bounded retries), repetition penalty 1.0, and disabled thinking. The JSON schema is sent both as Ollama's `format` and in the prompt for backends that do not enforce structured output. The worker runs one model task at a time. New shorts use version-2 storyboards with 2–5 cited narration beats (normally 3–5) and 1–3 controlled mixed visual scenes. Explicit reveal/focus/connect/hide/move/state-change operations are compiled only after speech measurement. Scene and action times are absolute audio milliseconds, with contiguous half-open scene intervals and a held final frame. Word counts are bounded; measured audio sets the final duration, at most 40 seconds. Kokoro uses `af_heart`, a fixed speech speed of 1, 24 kHz mono PCM WAV, and measured phrase boundaries. Captions use these measured phrase boundaries, not guessed word timestamps. Speech speed, voice, waveform handling and pause policy are unchanged. See [presentation changes, screenshots, audio examples and remaining review limits](docs/presentation-polish.md).

`SPEECH_PROVIDER=macos` selects a labelled development substitute. It uses `say` and `afconvert`. It is not Kokoro. The default and the reported live tests use Kokoro.

`.data/` contains SQLite records, parsed transcripts, managed audio and raster assets, local Hugging Face files, and diagnostics. Bundled assets are repaired locally at startup; saved lessons remain playable offline with the local server running and the whole data directory intact. Cache keys include source identity and content, model digest, prompt/schema versions, storyboard/compiler versions, language, and voice settings. This data is ignored by Git. Back up the whole data directory while the API is stopped. Do not share it if the transcripts are private. The UI assets and voices need no remote fonts or services after setup.

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

The Python tests use explicit test providers. The browser checks use explicit API and audio fixtures. See [storyboard implementation and compatibility](docs/storyboards.md) for the versioned format, measured compiler cost, screenshots, and live-quality limitations. Regenerate the shared storyboard playback fixture with `.venv/bin/python scripts/export_storyboard_fixture.py` after changing its authoring fixture or compiler. They do not establish live source access, model quality, or speech performance. See [YouTube change checks](docs/youtube-source-change.md) for current results and the remaining live-check dependency. [Earlier validation](docs/validation.md) and [earlier performance measurements](docs/performance.md) describe the previous imported-source version. See [design and limitations](docs/design.md) for the current flow.

To measure the current YouTube flow, start all providers and configure the server key:

```sh
.venv/bin/python scripts/benchmark.py
```

The script repeats the same YouTube goal with new request IDs. It records actual source acquisition, provider settings, errors, and per-short cache flags. Repeats can reuse search, captions, plans, and audio. These are not forced uncached or cold measurements. The output is separate from the earlier imported-source measurements. Do not run other generation tasks during this check.

## Downloads and licences

- [Qwen3 8B](https://ollama.com/library/qwen3:8b): 5.2 GB, Q4_K_M in the tested download; Apache-2.0. The full tested digest is in the performance report.
- [Kokoro 82M](https://huggingface.co/hexgrad/Kokoro-82M): `config.json`, `kokoro-v1_0.pth`, and `voices/af_heart.pt`; Apache-2.0 for the model repository and voice asset. The setup script records the exact revision in `.data/speech-download.json`. The tested weight file is about 327 MB and the voice about 510 KB.
- [Kokoro Python](https://github.com/hexgrad/kokoro): Apache-2.0. Misaki English uses its packaged dictionary, spaCy `en_core_web_sm` 3.8.0 (MIT), and the bundled espeak-ng library (GPL-3.0). Python, PyTorch, and other dependencies have their own licences.

Keep the original model notices when you redistribute their files. See the model card for the upstream training data acknowledgements. Generated local lessons have no metered cloud generation fee. The computer, electricity, disk storage, setup time, and YouTube API quota still have costs. This build does not measure electricity or assign those costs a monetary value.
