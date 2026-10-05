# TurboFieldfare operator runbook

Focus Play's primary LLM is **TurboFieldfare + Gemma 4 26B-A4B IT**. All
planning, drafting, source/teaching review and model repairs use the same selected
adapter. There is no automatic Ollama/cloud fallback. Speech remains Kokoro CPU,
`af_heart`, speed 1, 24 kHz mono PCM. Player controls/navigation are unchanged.

## Discover and reuse before installing

The implementing machine has an existing clean checkout and release executables:

- Checkout: `/Users/ankojh/ank/turbo-fieldfare`
- Inspected checkout revision: `6c044011c24dd55595af823cfef10f26b525cfca`
- Server/verifier: `.build/release/TurboFieldfareServer` and `TurboFieldfareRepack`
- Model: `/Users/ankojh/ank/turbo-fieldfare/scratch/gemma4.gturbo`

These paths are examples for this machine, not portable defaults. Inspect PATH,
active process arguments and targeted user checkout/application locations first.
Ask the operator for a location if targeted discovery fails; do not scan unrelated
private files. A GUI installation can share weights but may lack a server binary.
Do not move/copy the weights, convert the Ollama GGUF, start a second model owner,
upgrade/downgrade a checkout, or download without necessity and approval.

Check architecture/OS, `xcode-select -p`, `swift --version`, `df -h`,
`memory_pressure -Q`, current lesson jobs and process ownership before starting.
Apple Silicon, macOS 26/Metal 4 and Xcode 26/Swift 6.2+ are required. Text storage
is about 14.3 GB, initial transfer about 15 GB; reserve additional build/dependency,
speech and scratch space. Two GB advertised residency is not a workload RAM cap
or a guarantee of low heat/power. Increasing context allocates more FP16 KV memory.

Inspect the **chosen checkout's** README, `docs/OPENAI_SERVER.md`,
`docs/RUNTIME_CONTROLS.md`, request validator, stream/decoder/disconnect code and
model/licence notices. The handoff reference is
`77e8f9c02ec5345f4d9b633961c938bbafefb757`; compatibility, not matching it byte for
byte, is required. Pin the actual clean revision and binary SHA, not moving main.
The existing binary's exact build commit may be unavailable: the launcher labels
that limitation, records the inspected checkout separately and uses its binary
SHA as authoritative build identity. It does **not** claim the checkout proves
which commit built that binary.

Non-destructive verification with an already built compatible verifier:

```sh
/absolute/checkout/.build/release/TurboFieldfareRepack --help
/absolute/checkout/.build/release/TurboFieldfareRepack \
  --verify-install --input-gturbo /absolute/model.gturbo
```

This hashes weights without inference or network, validates layout/manifest,
and refreshes upstream `verified-install.json` (does not change weights).

If the binary alone is missing, obtain approval for a compatible server build,
reuse the verified model and build only the needed product:
`swift build -c release --product TurboFieldfareServer`. If weights are truly
absent/incompatible, ask before approximately 15 GB transfer or replacement.
Use the inspected revision's documented installer/resume flags; never default to
`--overwrite`/discarding valid partial data. No optional vision installation is
needed. API startup and health never install/build/download/start a model.

## Start, ownership and identity

Use the explicit foreground launcher from Focus Play's repository root:

```sh
.venv/bin/python scripts/turbofieldfare_server.py \
  --checkout /Users/ankojh/ank/turbo-fieldfare \
  --model /Users/ankojh/ank/turbo-fieldfare/scratch/gemma4.gturbo \
  --runtime-revision 6c044011c24dd55595af823cfef10f26b525cfca
```

It refuses an occupied port or another detected TurboFieldfare/MLX model owner,
runs the existing verifier, starts one child on **127.0.0.1:8080**, waits for health
and model discovery, then writes a mode-0600 receipt to
`.runtime/turbofieldfare-launch.json`. It does not stop an existing service.
Ollama's daemon is not equivalent to an active model: inspect `/api/ps` and ask
before unloading active models. Independently inspect memory pressure; process
name checks cannot detect every possible inference product.

Initial fixed profile: context 16384, 16 LFU expert slots, prefill on, chunk 128,
read advice off, single-prefix prompt cache. Changes require an explicit restart;
no diagnostic memory bypass, fan/power/driver adjustments or privileged sensors.
Only one app model worker is active. Queue capacity is not a fairness workaround.
Server flags are validated by the installed runtime.

The receipt binds endpoint -> listening PID -> process start time/full argv ->
absolute server/model files. The launcher's upstream verification and file
metadata snapshots establish installation identity; health cheaply checks process,
port and file metadata, not 14 GB hashes. Changes require reverification/relaunch.
Binary SHA, validated manifest SHA, source snapshot hash, pinned checkpoint,
quantisation, tokenizer hashes and server profile are stable cache provenance.
PID/start time/path are not cache keys, so identical verified restarts can reuse
valid output. This trusts operator-owned local files and the OS; it is not remote
attestation. `/health` itself does **not** attest weights/context.

A stopped/stale receipt, changed files/process, wrong endpoint, wrong model ID or
client context exceeding the launch profile fails clearly. There is no unverified
model-name-only cache mode. For an already running compatible server, do not launch
a second copy: inspect it and arrange a trustworthy equivalent ownership receipt;
the supplied launcher only creates receipts for its own child. Ask before an
approved restart under the launcher when no existing trustworthy receipt exists.

Control-C or SIGTERM on the **launcher** gracefully terminates only its child.
A bounded cleanup escalates only for that owned PID, never `killall`. Keep the
server alive across browser tabs; stopping the model does not invalidate saved
ready media. No authentication/TLS is provided: no 0.0.0.0, LAN, tunnels or proxies.

## Configure and activate

Back up `.env` locally (it contains source secrets; never report its values),
drain or explicitly cancel/pause active jobs, and select:

```dotenv
LLM_PROVIDER=turbofieldfare
LLM_BASE_URL=http://127.0.0.1:8080/v1
LLM_MODEL=gemma-4-26b-a4b-it
LLM_CONTEXT=16384
LLM_MAX_OUTPUT_TOKENS=2200
LLM_IDENTITY_RECEIPT=.runtime/turbofieldfare-launch.json
LLM_CONNECT_TIMEOUT=5
LLM_READ_TIMEOUT=120
LLM_ATTEMPT_TIMEOUT=300
```

`LLM_BASE_URL` includes `/v1`: health is `/health`, discovery is `/v1/models`,
completion is `/v1/chat/completions`. Only literal loopback HTTP hosts with an
explicit port, the provider's expected path and no credentials/query/fragment are
accepted. Clients use `trust_env=False`, do not follow redirects and need no key.

Precedence: explicit `Settings` values > `LLM_*` environment > `OLLAMA_*` **only
for Ollama** > provider-specific defaults. Without `LLM_PROVIDER`, the presence
of legacy `OLLAMA_*` selects Ollama, preserving old installations; otherwise fresh
configuration selects TurboFieldfare. Explicit TurboFieldfare never inherits
Ollama's model/URL/context. Unknown providers, wrong model/base path and unsupported
context/output/timeouts fail at configuration, before generation. Keep speech and
source keys unchanged. Client context is a declared budget, not a tokenizer-based
proof of prompt fit; the server checks the actual rendered token count. App context
is bounded to 16K and output 512–4096, below context. Only measured truncation
justifies changing the output limit; record it and its effect on repairs.

After server readiness, start the API on 8000 and Vite on 5173, then check
`http://127.0.0.1:8000/api/health`. Model, speech and YouTube flags remain separate;
missing vision is acceptable. Health does not perform inference.

## Protocol, validation and bounds

`GenerationService` in `backend/app/providers.py` owns task-specialised schemas,
prompts, task-specific authoring guidance and all-scene repair inventories. A
streaming key guard rejects long duplicate-field loops early. Full strict JSON
parsing (including duplicate/non-finite rejection), JSON Schema, Pydantic and
domain validation remain mandatory. Ollama retains NDJSON/format/think=false;
`backend/app/llm/turbofieldfare.py` sends only model/messages/stream/stream_options,
temperature 0, seed 42+attempt, repetition_penalty 1.0 and max_completion_tokens.
No schema enforcement/JSON mode, Ollama fields, reasoning switch or tools are sent.

The inspected no-tool Gemma template opens and immediately closes an empty thought channel (the runtime's thinking-disabled template), and its decoder routes any thought channels away from visible content. This is inspected runtime behaviour, not a request parameter or a claim derived from a prompt.
Focus Play consumes only delta.content and rejects unexpected tools/refusal/
reasoning channels. It does not strip arbitrary preambles/fences or guess fields.
The incremental SSE decoder handles fragmented UTF-8, CR/LF, comments, multiline
data and usage trailers. Both stop/length finish and `[DONE]` are required. Early
EOF, malformed/bounded frames, post-finish content and unexpected choices fail.
Length is output truncation, never insufficient source evidence. Usage cached
prompt tokens are measured, not assumed: only one retained prompt prefix exists.

Production tasks use [compact authoring](compact-authoring.md), prompt version 24,
with **one** repair and a shared `LLM_TASK_TIMEOUT=60` second stage deadline.
The planner writes outcomes and numbered dependencies. The storyboard author writes
2–4 cited beats/visual items; code assigns IDs and selected-template mechanics,
then runs the existing storyboard, evidence and teaching validators. Review sends
each source passage once rather than repeating its quote per beat. LLM ranking
is skipped in favour of channel-diverse search order. Existing rich renderer
contracts and explicit diagnostic calls retain at most two repairs.
Evidence is unchanged, there are no SDK retries or tool workarounds, and invalid
JSON is never normalized or salvaged. Parser version 3 guards duplicate keys,
container nesting and trailing content. Seeds at temperature zero alone do not
repair deterministic output. HTTP/config/identity failures and cancellation
do not retry. Diagnostics retain up to 100 attempt summaries locally; last-error
output is bounded to 10000 characters and not public telemetry. Jobs persist
numeric attempt/repair/token/cache counters plus existing reserved three-call
units and work/source allowances. Invalid JSON/content is never published.

TurboFieldfare I/O is async inside the serial synchronous job boundary; polling
cancellation closes/awaits the active stream even during prefill, with a hard
per-attempt deadline, capped by the production stage and first-video deadlines.
`FIRST_PLAYABLE_TIMEOUT=180` bounds the first-video processing window after dequeue;
source/speech operations observe it at their existing synchronous call/unit boundaries,
so this is not a universal exact wall-clock interruption guarantee. It stops work,
not guarantees a successful video. Tests assert bounded client cleanup before the next request. Live disconnect returned in 0.308s, but the server finished GPU/prefill cancellation in 10.359s; the next request queued and ran after that release. This is not proof of instant GPU interruption or a universal server-release bound. The
retained Ollama rollback transport keeps its original synchronous read-bound
cancellation/deadline limitation (up to read timeout during prefill); it is not
advertised as hard-interruptible. Neither adapter increases model concurrency.

## Persistence, caches and rollback

Draft/plan/ranking keys include the selected provider fingerprint and bounded
specialised task/evidence. Model names across runtimes/quantisations do not collide.
Transcript/source caches and acquisition ledgers are untouched. A lesson pins its
profile before source acquisition. Every later LLM turn compares it; mismatch
fails `PROVIDER_SETTINGS_MISMATCH` without relabelling historical ready shorts.
Exception: same-runtime prompt/parser/repair/authoring releases may rebind a lesson
with no authored media or coverage history. Its committed plan, IDs, saved sources
and consumed allowances remain intact. Model/runtime/settings changes still fail.
Legacy Ollama fingerprints compare every saved field under explicit Ollama; extra
new fields do not rewrite them. Ready lessons remain readable/playable with either
provider or neither model online. Fresh work has new provenance.

Missing-audio recovery runs before LLM checks or source acquisition, uses the
saved key/narration/original speech identity, and requires identical measured
phrase bounds/duration. It never regenerates visuals or rewrites LLM provenance.

Rollback: finish/stop active generation, preserve the whole data directory and
configuration backup, stop only the owned TurboFieldfare launcher if appropriate,
and explicitly replace active LLM settings with:

```dotenv
LLM_PROVIDER=ollama
LLM_BASE_URL=http://127.0.0.1:11434
LLM_MODEL=gemma4:12b-mlx
LLM_CONTEXT=8192
LLM_MAX_OUTPUT_TOKENS=2200
```

Start/verify the original local Ollama model, restart the Focus Play backend and
create a **fresh** lesson if needed. Legacy-only `OLLAMA_*` remains supported when
new LLM overrides are removed. Incomplete TurboFieldfare jobs cannot silently
resume under Ollama. No cache/weight/source deletion is necessary. Never run two
API writers on the same data directory.

## Checks and limits

Default pytest/Playwright tests use scripted transports/current lesson fixtures,
not live weights or paid acquisition. See README's build/type commands.

Opt-in same-evidence live checks (real inference; no source service calls):

```sh
.venv/bin/python scripts/provider_check.py --approve-inference \
  --budget-seconds 900 --output .runtime/turbofieldfare-provider-check-NEW.json
.venv/bin/python scripts/offline_check.py --approve-inference \
  --budget-seconds 600 --output .runtime/turbofieldfare-offline-NEW.json
.venv/bin/python scripts/provider_smoke.py --approve-inference \
  --output .runtime/turbofieldfare-disconnect-NEW.json
```

`provider_smoke.py` checks client disconnect/next-request release and exact READY output, not JSON lesson quality. See the [migration handback](turbofieldfare-migration.md) for failed experiments, resumed real-output success and remaining acceptance gates. The structured checks record actual first-pass/domain outcomes, attempts, TTFT, elapsed time,
reported token/cache usage and measured storyboard/Kokoro media. Review must pass
before compilation. Original local illustrative fixture evidence is labelled;
there is no fixture-provider substitution and no insertion into the user's library.
Outputs must be new paths. Blocking Python sockets does **not** sandbox Swift.

`benchmark.py --mode live` still requires `--approve-source-credits` and declared
cache state. Its default live report is provider-specific/timestamped under
`.runtime/`; explicit existing live output paths are refused. Actual stage hits,
provider provenance, reserved allowances and failures are recorded. Obtain source
credit approval separately; expand 5/10/20-minute workloads only with budgets.

`cached_lesson_check.py` also supports an opt-in full Jobs check using actual captions
already saved in a YouTube lesson. It reads the original store read-only, writes only a
fresh isolated directory, reuses speech weights in place and disables new acquisition.
It is not a fresh-source test. `export_provider_playback.py` can export a passed local
provider report and its matching measured WAV to another isolated store. The optional
frontend `provider-playback.spec.ts` forwards reads to that actual isolated API rather
than substituting generated text/audio fixtures. See README for exact commands. Never
start a second API writer on an active worker's data directory; stop temporary playback
APIs after inspection.

A short smoke run is not sustained thermal evaluation. Distinguish process RSS
from total unified memory/filesystem cache/peak pressure, cold/warm/page/prompt
cache, useful unique playback duration from loops, CPU/GPU utilisation from watts,
and subjective comfort from sensor temperatures. Power/energy/fan readings need
appropriate tools and any required privileged approval. Report unavailable
measurements; do not infer low heat from advertised RAM savings.

## Notices

TurboFieldfare is Apache-2.0; weights are governed separately by Gemma terms.
Checkpoint: `mlx-community/gemma-4-26b-a4b-it-4bit` revision
`0d77464eeb233a2da68ebf9d7dc4edaac7db956d`; affine group-64 4-bit weights, 8-bit
router. Preserve runtime `THIRD_PARTY_NOTICES.md`, checkpoint/model-card notices
and the exact resolved Swift dependency notices. Speech/source/asset notices are
unchanged. No weights, secrets, runtime binaries or private diagnostics go in Git.
