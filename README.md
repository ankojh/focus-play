# Focus Play

Learn one point at a time with short local narrated diagrams. Enter a goal, your current knowledge, and a time budget. The server searches YouTube and reads video captions automatically. The dark Shorts interface is unchanged. Play the first short while the worker prepares later shorts.

The application uses React, TypeScript, Vite, FastAPI, SQLite, a local Ollama model, and Kokoro CPU speech. The local model rewrites transcript content into clear, self-contained teaching narration and question explanations. Narration no longer copies YouTube speech word for word. Transcript quotes and timestamps remain available in Sources for attribution. A local model review checks for contradictions and unsupported claims and requests one rewrite when necessary; it can still miss errors. Diagrams use topic-specific icons, explanatory detail lines, colour-coded roles, and audio-synchronised highlights and arrows. Model processing, speech, saved transcripts, lesson records, and audio stay on this computer. New lessons need internet access: the goal and current knowledge go to YouTube search, and video IDs go to the Supadata caption service. Search titles and snippets are not teaching evidence.

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

- Play, pause, replay, or seek within a ready short. On the player, Space controls playback and the arrow keys seek five seconds.
- Use the outline or previous/next controls to select a short. Refresh restores the selected short and audio position. Audio waits for a click.
- Questions have a 20-second content allowance. Questions appear at the end of every third required short. Answer feedback includes an explanation.
- After preparation finishes, **Show an example** or **Explain again** offers one additional short. Approve the visible 40-second allowance before it starts. The original time budget is shown separately. Pauses can increase elapsed time.
- **Cancel preparation** preserves ready shorts. After a provider error or interruption, **Retry** keeps ready work and uses valid cached stages. If a completed audio file is missing, use **Repair missing audio**.
- Missing evidence stops that part of a lesson. Retry or use a more focused goal. There is no import, sample, website, or model-knowledge fallback.

## YouTube sources and saved history

New lessons use official YouTube search plus [Supadata](https://docs.supadata.ai/api-reference/endpoint/transcript/transcript) for existing English captions. The official [caption download API](https://developers.google.com/youtube/v3/docs/captions/download) needs permission to edit a video; a search key does not supply that permission. Supadata reads captions from its own servers, so YouTube does not rate-limit this computer. It runs in `native` mode: it returns existing captions only and never generates paid AI transcripts. The free plan has 100 credits a month and one request a second; the server waits between requests. Missing keys, quota errors, used-up credits, and insufficient evidence give an error and **Retry**.

Each acquisition attempt uses at most two queries. Each query asks for 15 results and drops Shorts, live streams, and videos over 30 minutes. Up to `RANK_CANDIDATES` (default 8) transcripts are then requested per query; each request costs one Supadata credit, including videos without captions, which are skipped. The local model scores each transcript from 1 to 5 for relevance, fit to the learner's current knowledge, teaching quality, on-topic density, and caption quality. The server keeps the three best videos with relevance of at least 3, level fit of at least 2, and at most two per channel. If no video passes, the second query runs. If the model cannot rank, YouTube's order is used. Scores and reasons are saved in the lesson as `video_rankings`. Search and caption caches last one day. Adjacent captions form bounded teaching passages; their time bounds come from the actual caption records. Original caption records are also saved. Video IDs, titles, channels, URLs, and evidence timestamps remain in the lesson.

**Sources** is saved history. Old imports and original samples keep their labels and records. Old lessons still open. New `POST /api/lessons` requests accept `goal`, `prior_knowledge`, `time_budget_seconds`, `language`, and `request_id`. Source modes and source IDs are rejected. The import endpoint is removed. An extra short, including one added to an old lesson, uses only retrieved YouTube evidence. It searches again if existing YouTube evidence is insufficient.

## Configuration and data

Diagrams have nine layouts: process, comparison, worked example, timeline, chart, numbered steps, cycle, do vs. don't, and key-fact callout. The model chooses icons from 218 bundled Lucide icons, so diagrams require no remote images or YouTube playback. Saved lessons without icons remain readable. New lessons use the updated narration and planning; already-ready shorts are not automatically rewritten.

Passage retrieval shares the context across videos, penalises intros and sponsor reads, and includes neighbouring passages. Lessons start with basics and avoid repeated narration. All diagram motion follows the audio clock and honours reduced-motion preferences.

See [.env.example](.env.example). `OLLAMA_MODEL` selects an installed local model. The default uses 8192 context tokens, at most 2200 output tokens, temperature 0, seed 42, and disabled thinking. The worker runs one model task at a time. Each short has two measured narration phrases. Word counts are bounded; measured audio sets the final duration. Kokoro uses `af_heart`, a fixed speech speed of 1, 24 kHz mono PCM WAV, and measured phrase boundaries. Captions are phrase aligned.

`SPEECH_PROVIDER=macos` selects a labelled development substitute. It uses `say` and `afconvert`. It is not Kokoro. The default and the reported live tests use Kokoro.

`.data/` contains SQLite records, parsed transcripts, managed audio, local Hugging Face files, and diagnostics. Cache keys include source identity and content, model digest, prompt/schema versions, language, and voice settings. This data is ignored by Git. Back up the whole data directory while the API is stopped. Do not share it if the transcripts are private. The UI assets and voices need no remote fonts or services after setup.

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

The Python tests use explicit test providers. The browser checks use explicit API and audio fixtures. They do not establish live source access, model quality, or speech performance. See [YouTube change checks](docs/youtube-source-change.md) for current results and the remaining live-check dependency. [Earlier validation](docs/validation.md) and [earlier performance measurements](docs/performance.md) describe the previous imported-source version. See [design and limitations](docs/design.md) for the current flow.

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
