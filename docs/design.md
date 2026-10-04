# Design and limits

## Data flow

1. Accept the goal, knowledge, and time budget. Persist the request ID and return the lesson ID immediately. Reject source-mode and source-ID input. The request handler does not run search or the model.
2. Search YouTube using the goal and knowledge. Read accessible English captions with youtube-transcript-api 1.2.4. Bound queries, candidates, timeouts, and transcript size. Skip unavailable captions. Preserve metadata and supplied times. Group adjacent captions into bounded passages and save raw captions. New generation receives only these YouTube passages. There is no manual or sample fallback.
3. Select a bounded set of text passages. Ask the local model for ordered objectives and check the content budget.
4. Generate one short. Each short has two narration phrases. The model selects one supporting segment ID and an exact source excerpt for each phrase. Question answers and explanations also use exact source excerpts. The JSON Schema limits these choices to retrieved IDs and real source text. The server copies exact source text and real timestamps into the evidence record. Validate Pydantic fields, diagram references, quotes, and supplied times. Permit at most two schema repairs.
5. Review support with the same local model. This review can miss errors. It is not independent fact verification.
6. Generate semantic speech units on the CPU. Join the exact samples. Compute caption and cue boundaries from sample counts. If speech exceeds 40 seconds, request one shorter script and review it again. Speech speed stays fixed.
7. Write the audio file atomically. Only then publish the completed short and its timeline. Start the next short.

SVG diagrams use process, comparison, example, timeline, and chart templates. The model supplies bounded labels, nodes, and connections. The server compiles appear, highlight, and connection cues from these validated relationships. It matches caption words and labels in the supporting passage for highlights. It adds locally matched source references for diagram labels; this is lexical support selection, not independent fact verification. Cached factual content is compiled again with the current cue rules. The scene contract and player also support disappear and movement actions. Nodes have four fixed layout slots. Text and element counts are bounded. Moves can only use a free slot. The model cannot supply executable code, SVG markup, or arbitrary links. React escapes displayed text. The audio element supplies the playback time. Captions, visibility, highlights, movement, and connections are pure functions of this time. Reduced motion removes interface animation.

## Jobs and persistence

One bounded priority queue admits up to eight lessons. One worker performs blocking provider calls on a background thread. New first shorts and optional explanations have priority over later work. A later short finishes before the worker checks the next queued task; active model requests are not preempted for priority changes.

SQLite stores lesson snapshots, job transitions, ordered event sequences, request IDs, and cache entries. SSE delivers saved event IDs. The browser reads a snapshot after each progress event and on reconnection. A snapshot request cannot create a job. The browser also checks a snapshot every five seconds while a job is active. Snapshot sequence checks reject older responses.

Cancellation sets a thread event, cancels queued work, and closes active model streaming at the next received chunk. A stream read has a ten-second timeout. CPU speech can finish its current phrase before it sees cancellation. Late results cannot publish to a cancelled lesson. Ready shorts remain available. A retry can be refused briefly while the previous call stops. Try again after it stops.

On server start, interrupted jobs are marked explicitly. They need a user retry; they do not start silently. A retry preserves complete ready outputs and reuses validated draft and speech caches when their keys match. It rechecks the current local model settings. Settings recorded on each ready short explain which model and voice produced it.

Required content reserves up to 40 seconds per unfinished short plus 20 seconds for every third required short's question. Measured durations replace those reservations. Optional explanations need an explicit 40-second additional allowance and are limited to three per lesson. Question reservations belong to their original short, so inserting an extra short does not move the question.

## Local boundary

The API and UI bind to loopback. The API rejects other hosts and web origins. Writes need JSON. CORS permits only the local UI. Model calls use loopback with proxy environment variables disabled. Remote Ollama model metadata and cloud model tags are rejected. The intended Ollama start command also disables cloud access. Managed audio delivery accepts only a SHA-256 filename and refuses symlinks. Search calls a fixed YouTube endpoint. Caption requests use HTTPS YouTube addresses with bounded timeouts and no redirects or environment proxies. Video URLs are validated and rebuilt as known YouTube URLs.

Saved playback requires the local UI and API; ready audio is local. Model weights, voice, English language data, Python packages, and UI packages come from setup. The application does not request missing speech assets during a lesson. It offers an explicit setup error. No remote fonts or media are required. New lessons require YouTube search and transcript access. Search sends the goal and knowledge to YouTube. Model and voice processing stay local.

## Limits

- English, one local user, and one model worker. There are no accounts, billing, cloud deployment, MP4 export, 3D scenes, or voice cloning.
- New generation uses automated YouTube sources. Public English captions can be unavailable or blocked. A server search key and API quota are required. See the current change report for live verification status.
- Narration and correct answer explanations are extractive. This is a deliberate limit after a manual review found an unsupported claim in model paraphrasing. The model still selects, orders, and diagrams the material.
- Source provenance checks establish that quoted text exists. They do not establish that the source is true. The local support review can miss misleading narration, conflicting versions, or missing context. Manual content review remains necessary.
- Simple lexical retrieval can miss relevant passages. A source may be valid but insufficient for a broad goal. There is no vector database.
- Fixed slots and bounded text provide a small visual vocabulary. Charts accept source numeric values only. There is no generated code or arbitrary visual layout.
- Captions have measured phrase boundaries. Word alignment is not implemented.
- One language model candidate and one Kokoro voice are evaluated. See the measured report for failures and waiting times. The latency targets are engineering targets.
- Old imported sources, retrieved captions, and completed lessons remain on disk. Automatic retention, removal, and storage quotas are not implemented. Watch disk use and back up needed work.
- The development server is the documented local interface. Public hosting and remote access are outside this release.

The constrained schema couples each narration excerpt and correct answer to its actual source segment. A real excerpt with a wrong citation is invalid. Factual speech is copied from source text. The independent validity of that source and the teaching quality of diagrams still need human review.
