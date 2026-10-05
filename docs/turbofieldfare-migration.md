# TurboFieldfare migration handback

## Status: mixed-fixture generation through browser playback passed; real-caption Jobs reliability incomplete

TurboFieldfare + Gemma 4 26B-A4B is the configured primary local LLM. There is no
automatic fallback. Automated transport, generation, persistence, media recovery
and player regressions pass. Resumed real mixed-fixture generation now passed
source/teaching review, actual Kokoro and browser playback. **General cached-real-caption
Jobs and fresh-source lesson acceptance remain incomplete.** The original failed
reports are retained below; they were not rewritten as successes. Available-provider
health and mocked contract tests are not live quality acceptance.

The user approved reusing/verifying the installation, starting the server,
updating only LLM configuration and restarting an idle backend. The user declined
paid source calls. No new YouTube/Supadata lesson was generated, no downloads or
builds performed, no installed model/cache/source/ready media deleted, and no
privileged resource/thermal measurements performed. No commit or push was made.

## Resumed implementation and verification

The resumed implementation adds:

- Task-specific plan guidance: short concept IDs, observable outcomes, verbatim
  source example facts, optional empty examples, and checkpoint budgeting.
- Scene-specific storyboard guidance and bounded repair inventories spanning **all**
  successfully parsed scene payloads. Facts/targets are never fabricated; invalid
  output is never silently normalized or accepted.
- A streaming duplicate-key guard. Long repeated-object loops can evade the short
  substring repetition detector; they now fail early, close the response and use
  an existing clean repair. Full JSON/SSE/schema/Pydantic/domain checks and **initial
  plus at most two repairs** remain unchanged.
- Prompt **22**, repair policy **initial-plus-two-3-scene-inventory**, parser
  **strict-json-sse-2-stream-key-guard**. Cache/unfinished-job fingerprints change;
  ready historical work is not rewritten. The passed mixed-fixture report predates
  the streaming key guard and retains its parser-v1 provenance; cached check 3
  demonstrates the current guard's real early-abort and successful clean plan repair.

### Passed: real mixed-fixture output through browser playback

`.runtime/turbofieldfare-provider-check-4.json` used the same original
`fixtures/mixed-visuals.json` evidence and pinned TurboFieldfare/Gemma installation.
All five stages passed on their **first** attempt:

| Stage | Seconds | Outcome |
| --- | ---: | --- |
| ranking | 11.3 | passed |
| planning | 28.1 | passed |
| mixed diagram/table/chart storyboard | 62.3 | passed |
| source/teaching review + Kokoro | 22.7 | passed |
| insufficient evidence | 12.7 | passed |

Actual uncached Kokoro playback measured **23,850 ms**. No generated output,
review, evidence or audio was replaced by a fixture/fallback. This report predates
embedded evidence, so `export_provider_playback.py` received the explicit original
fixture, validated the report/storyboard/review/timeline/audio metadata and matching
measured WAV, and exported isolated `.runtime/turbofieldfare-playback-4`.
**Illustrative evidence is not newly acquired YouTube content.**

The opt-in `frontend/tests/provider-playback.spec.ts` forwarded reads to that real
isolated API and passed browser audio-clock progress, measured duration, all three
visual scenes, measured beat captions, pause/seek, loop setting, refresh restoration
and full transcript checks. Initial test failures were incorrect transcript selectors
and seeking before refresh metadata restoration finished; frontend/media policy
was not weakened. The export did not change the user's library. The temporary API
is stopped after inspection; saved output remains for opt-in replay. This is browser
pipeline verification, not proof of audible speaker quality or sustained thermal behaviour.

### Still blocked: cached real-caption Jobs checks

`cached_lesson_check.py` exercises actual Jobs on an already saved YouTube lesson's
original captions/IDs/times/hashes in a fresh isolated store. It reads the original
store read-only, reuses local HF speech weights in place and disables acquisition.

| Local work directory | Scope | Outcome |
| --- | --- | --- |
| `.runtime/turbofieldfare-cached-lesson-1` | original broad skydiving goal | Three planning attempts; disabled adapter blocked a requested search, **no actual paid call**, 0 ready shorts. |
| `.runtime/turbofieldfare-cached-lesson-2` | narrower body-position/stability goal | Three planning attempts exhausted output limit on repeated JSON fields; `MODEL_OUTPUT_INVALID`, 0 ready shorts. |
| `.runtime/turbofieldfare-cached-lesson-3` | same narrower goal, key guard enabled | Repeat aborted early; a clean repair produced a valid plan. All three storyboard attempts failed strict JSON syntax. Failed after **431.7s**, 0 ready shorts, **0 source provider calls**. |

These are genuine failures, not successful real-caption lesson acceptance. No
invalid short was published and the job retry cap was not reset to get success.
Runs have distinct output directories and preparation budgets. Remaining failures
include extra closing array brackets on longer real-caption/context storyboards.
Fixed-evidence success does not establish general authoring reliability. Further
work needs a separately bounded investigation; do not strip brackets/fields,
insert substitute output, add hidden attempts, or switch the selected runtime/model.

### Current verification and remaining gates

- **334 backend tests passed** (one existing Starlette/httpx deprecation warning).
- Default frontend: **71 passed / 2 opt-in skipped**; the real-output browser test
  passed separately against the actual isolated export.
- Frontend TypeScript/build, regenerated API schema/types and `git diff --check`
  passed. No dependency download, paid source call, commit or push.
- Existing library's **5 lessons / 16 ready shorts** and `gemma4:12b-mlx` provenance
  are preserved; saved playback is not a migration rewrite.
- Fresh YouTube/Supadata end-to-end acceptance remains unrun without paid-source
  approval. General cached-real-caption Jobs acceptance remains failed as above.
- Sustained thermal/resource comparison and exact binary source revision remain
  unproved; no lower-heat/power claim. Original observations follow.

## Reused installation and identity

| Component | Observed identity/action |
| --- | --- |
| Hardware | Apple M3 Max, arm64, 48 GiB unified memory |
| OS/toolchain | macOS 27.0.1; Swift 6.4; `/Applications/Xcode.app/Contents/Developer` |
| Preflight storage/pressure | 383 GiB available; `memory_pressure -Q`: 76% system-wide free (snapshot, not peak) |
| Checkout | Reused `/Users/ankojh/ank/turbo-fieldfare`, clean revision `6c044011c24dd55595af823cfef10f26b525cfca` |
| Server | Reused `/Users/ankojh/ank/turbo-fieldfare/.build/release/TurboFieldfareServer` |
| Verifier | Reused sibling `TurboFieldfareRepack`; installed `--help` and verification behaviour inspected |
| Weights | Reused `/Users/ankojh/ank/turbo-fieldfare/scratch/gemma4.gturbo` in place |
| Verification | Installed verifier validated 37 files / 14,291,915,755 bytes and refreshed `verified-install.json`; weights unchanged |
| Storage | `du -sh`: model 13 GiB (rounded), `.build` 842 MiB (whole existing build directory, not marginal install cost) |
| Source checkpoint | `mlx-community/gemma-4-26b-a4b-it-4bit`, revision `0d77464eeb233a2da68ebf9d7dc4edaac7db956d` |
| Quantisation | MLX affine group 64, 4-bit embedding/attention/shared/routed experts, 8-bit router; BF16 scales/biases |
| Model manifest SHA256 | `1cb53c2423f05dfa673e5f0d9a3407aa355b8227b621f8f8e575830a2bb7fa91` |
| Source snapshot/index hash | `sha256:bf198c9f5ea6462addca1966e5dd669c407537a876e82cf06db9084c5c850b13` |
| Existing server binary SHA256 | `688a850507c729a963ebff664d3af9c6593c243894cc4500b762ebf718ea5e86` |
| Built/resumed/downloaded | **None**; no clone, upgrade, downgrade, repack, copy, optional vision pack or Swift dependency download |

The installed checkout differs from handoff reference
`77e8f9c02ec5345f4d9b633961c938bbafefb757`. Its ancestry relative to that reference
was not established locally (the reference object is absent), so no newer/older
claim is made. Its inspected API supports the required request fields, rejects
unknown/structured-output options, emits finish + usage + `[DONE]`, filters
thought channels, and cancels on disconnect. This checkout advertises up to 64K
context; the integration only uses 16K and does not depend on later long-context
features. The existing binary's exact **build commit is unknown**: the fingerprint
labels checkout provenance separately and identifies the actual build by binary
SHA, not an invented commit. Its executable help and real endpoint behaviour were
checked. Checkpoint revision binding uses the validated source snapshot hash and
the inspected pinned upstream source definition.

Only the intended TurboFieldfare server model owner was started. The existing
Ollama daemon remained untouched and `/api/ps` reported no resident model during
preflight. Owned endpoint: `127.0.0.1:8080`; `/health` reports `status=ok`,
`vision=missing`; `/v1/models` serves only `gemma-4-26b-a4b-it`, text capability.
No LAN bind, authentication key, proxy or tunnel was introduced.

## Code boundaries and policy

- `backend/app/providers.py`: `GenerationService` shares specialised schemas,
  prompts, bounded repairs and strict JSON/JSON Schema/Pydantic/domain validation;
  narrow Ollama rollback transport retained. Factory selects one adapter.
- `backend/app/llm/`: bounded incremental UTF-8/SSE decoder, supported-field-only
  TurboFieldfare transport, usage/cache metrics and local owned-process identity.
  Async stream cancellation/deadline works during prefill without detached
  inference threads. No OpenAI SDK, hidden retries, tools or schema-enforcement
  claims were added.
- `backend/app/config.py`: fresh TurboFieldfare defaults, explicit legacy mapping,
  deterministic new-setting precedence and local URL/model/context/output/timeouts.
- `backend/app/main.py`: factory, existing test injection and API lifecycle. No
  installer/model launcher runs at API import/startup.
- `backend/app/jobs.py`: pins identity before new source spending, compares later
  turns without relabelling historical records; ranking keys now include full
  provenance. Keeps reserved three-call units and numeric attempt/repair/token/
  cache counters. Existing source ranking-order fallback for **content** failure
  remains, but provider/config/transport failure is not swallowed.
- Missing-audio recovery precedes LLM/source checks and reuses the saved script,
  speech identity, key, visuals and exact phrase/duration checks.
- `backend/app/visuals.py`: one error-message improvement identifies the offending
  scene/kind/target and its allowed targets. **Validation policy is unchanged.**
  Pydantic repair feedback no longer includes input dumps/diagnostic URLs.
- Health adds compatible `provider` metadata and uses no Ollama digest requirement.
  OpenAPI and generated frontend types refreshed. No player code was redesigned.
- Explicit launcher and real-provider check/smoke scripts; `.env.example`, README,
  [operator runbook](turbofieldfare.md), ignored local receipts/reports/backups.

Requests contain only model, messages, stream, stream_options.include_usage,
temperature, seed, repetition_penalty and max_completion_tokens. No JSON mode,
response-format schema, Ollama options, tools, thinking/reasoning parameter or
JSON-delimiter stop sequence. The inspected no-tool template closes an empty
thought channel and the runtime decoder filters thoughts; there is no API switch.
Both finish reason and `[DONE]` are required, usage trailers are consumed, length
is truncation, early EOF and unexpected tools/refusal/reasoning fail. Fences,
prose, duplicate keys/non-finite constants and unsupported claims are rejected,
not stripped or repaired through invented defaults.

Caches use runtime binary/manifest/tokenizer/checkpoint/quantisation/profile,
adapter/parser/repair/prompt/schema versions and effective settings plus the
existing evidence/task/compiler/teaching/planning boundaries. Receipt PID/paths
are not stable cache keys; PID/start/argv/listening port and file metadata bind
identity locally. Health does not rehash 14 GB, perform inference or spawn a model.
Operator-local receipt/OS trust is explicit; this is not remote attestation.
Historical ready records remain historical. Legacy incomplete Ollama profiles
compare every saved field; incompatible new work fails with an actionable mismatch.
No source allowance is reset. Ready playback does not require the selected LLM.

## Active profile and controlled changes

Server: 16384 context, 16 LFU expert slots, prefill on, chunk 128, read advice off,
single-prefix prompt cache. No cache-slot/power/driver experiment was conducted.

Client initial baseline: 2200 output tokens, temperature 0, seed 42 (43/44 repairs),
repetition penalty 1.0; connect/read/per-attempt limits 5/120/300 seconds.

Initial storyboard generation emitted fenced output, then exhausted 2200 tokens
on both repairs. Based on this observation, active `.env` now uses a bounded
**3000 output tokens**, within the existing 4096 maximum. Prompt version moved
20 -> **21** for explicit raw, compact JSON instructions; schema remains
`6-session-planning`. Repair policy is
`initial-plus-two-2-field-feedback` for concise Pydantic/renderer/identifier errors.
The example retains 2200 as the controlled starting baseline; these changes are
not a guarantee of generation quality. None increased the three-attempt limit,
changed temperature/model/provider, loosened evidence checks or bypassed review.

`.env` backup: `.runtime/env-before-turbofieldfare.backup`, mode 0600; source and
speech settings untouched. Receipt: `.runtime/turbofieldfare-launch.json`. Local
logs: `.runtime/turbofieldfare-server.log`, `.runtime/backend-turbofieldfare.log`.
They can contain local metadata and must not be committed/shared indiscriminately.

## Original automated results (before resumed implementation)

Final commands:

- `.venv/bin/python -m pytest backend/tests -q`: **319 passed**, one existing
  Starlette/httpx deprecation warning.
- `scripts/export_openapi.py` and `npm run types --prefix frontend`: passed.
- `npm run build --prefix frontend`: passed.
- `npm test --prefix frontend`: **71 passed, 1 skipped** (opt-in paid live test).
- `git diff --check`: passed.

Coverage includes provider/env precedence, loopback/path/redirect/model/receipt
checks; actual specialised ranking/plan/storyboard/mixed visual/review contracts;
UTF-8/SSE byte boundaries, heartbeat/null/usage/finish/DONE, HTTP failures and
unexpected channels; clean/targeted repairs, domain rejection, bounded prefill/
stream/repair/deadline cancellation; cache/pinning and missing-audio recovery
without old LLM/source calls. Existing teaching/duration/readiness/player tests
were retained, not weakened.

One earlier full-suite run while live inference was active failed the timing-
sensitive cancellation/source-reservation fixture
`test_job_idempotency_publication_retry_cancel_and_events`. The isolated test and
subsequent full reruns passed. The reservation policy/test assertions were not
relaxed to hide it; this timing-sensitive path remains a limitation to watch.

## Original real same-evidence failures (not mocked)

Three explicitly bounded sequential runs used original local illustrative
`fixtures/mixed-visuals.json` passages. No fixture-provider substitution, paid
acquisition, library insertion or cache deletion. Full local output/attempt/usage
records remain ignored:

- `.runtime/turbofieldfare-provider-check-1.json` (baseline prompt 20 / 2200)
- `.runtime/turbofieldfare-provider-check-2.json` (prompt 21 / 3000)
- `.runtime/turbofieldfare-provider-check-3.json` (prompt 21 / 3000 / targeted feedback)

| Stage | Baseline result | Final bounded run |
| --- | --- | --- |
| Ranking | First pass, 17.0 s; prompt/output 672/181; TTFT 10.27 s | First pass, 12.1 s |
| Version-3 planning | First pass, 16.4 s; prompt/output 1438/195; TTFT 8.94 s | Failed after 3 attempts, 60.2 s |
| Diagram/table/chart storyboard | Failed after 3 attempts, 358.8 s; first fenced output, then two length finishes at 2200 | Failed after 3 validation attempts, 150.3 s; no length finish |
| Source/teaching review + Kokoro | Not run: no valid storyboard; explicitly reported failure | Not run: no valid storyboard; explicitly reported failure |
| Intentionally insufficient evidence | Correctly returned unsupported/no plan | First pass, 12.4 s; unsupported/no plan |

Final planning failures: example facts were not exact supplied source excerpts;
then `signed_value_comparison` exceeded the 20-character concept-ID constraint.
Final storyboard failures: unexpected `source` property on a semantic operation,
missing explicit diagram connect, then `node_0`/`node_1` used in a table instead
of `row_0`/`row_1`. These are **output/schema/content failures, not evidence
exhaustion or adapter protocol failures**. Every invalid candidate was rejected.
The first baseline plan success does not establish consistent quality under the
revised profile.

Usage trailers were received. Most calls reported cached_tokens=0; one retained-
prefix repair reported 6205 cached prompt tokens (second run), demonstrating
actual limited prefix reuse, not universal conversation caching. TTFT/usage and
repair counts for each attempt are in local reports. Wall time includes queue/
prefill/decoding; there is no sustained useful-lesson throughput result because
no lesson completed.

## Real cancellation/release check

`scripts/provider_smoke.py` sent a 4522-token prompt, disconnected during prefill,
then sent a small text request using the same server. Local report:
`.runtime/turbofieldfare-disconnect-smoke.json`.

- Client cancellation/stream cleanup returned in **0.308 s**.
- Server log recorded the cancelled request at **10.359 s**; GPU/prefill cleanup
  was **not** instantaneous. The next request queued, then generated only after
  the prior one released the slot (one active generation).
- Next request completed in **10.429 s**, prompt/output 18/3 tokens, finish stop,
  both terminal markers consumed. Text was `READY.` rather than exact `READY`;
  the script's exact-output assertion **failed**. Transport/release worked, but
  that instruction-following mismatch is not labelled a passing exact smoke.

Client hard cancellation does not guarantee immediate GPU interruption. The app
worker remains serial; any following request is subject to the server's queue and
bounded client deadline/read timeout. One observed release delay is not a bound
for every workload. Cancellation records a clear failure; no content repair is
attempted and no detached client stream survives it.

## Resources and unverified gates

During inference, a `ps` snapshot showed server RSS 1,723,616 KiB (about 1.64 GiB);
later snapshots were about 1.61 GiB. These are **process RSS snapshots, not peak
total unified memory or Metal/filesystem residency**, and must not be compared
uncritically with the upstream advertised two GB. No sustained peak/SSD read/
CPU/GPU power/energy/fan/temperature measurements, subjective comfort review or
historical 12B comparison were performed. No lower-heat/power conclusion is made.

Current acceptance gaps (updated after resumed verification):

1. General longer-context real-caption Jobs authoring remains unreliable: the
   cached checks failed as detailed above. Fixed mixed-evidence generation passed.
2. Source/teaching review → Kokoro → measured media → frontend playback **is now
   established for actual mixed-fixture output**, not for a completed real-caption Jobs lesson.
3. Paid YouTube/Supadata end-to-end lesson gate was deliberately not run because
   approval was declined. Existing ready playback/regressions remain intact.
4. Sustained useful-lesson resource/thermal evaluation remains unavailable.
5. Existing build commit cannot be proven; binary SHA is the honest build pin.

Smallest proposed next step is a separately budgeted, same-model authoring/profile
investigation of longer real-caption/context storyboard syntax and instruction/
repair effectiveness, preserving every schema/source/semantic guard. Do not add a fourth hidden repair, strip arbitrary
content, bypass reviews, enable tools, switch runtime/model, or declare migration
acceptance green. All resumed checks reached terminal state; no inference experiment
is left running at handback.

## Operations and rollback

See [the runbook](turbofieldfare.md) for reproducible verify/start/stop, optional
fresh installation approvals, receipt trust, notices and explicit Ollama rollback.
The idle main backend was gracefully restarted after resumed verification to load
prompt 22 and the streaming key guard; resumed PID **42286**, log
`.runtime/backend-turbofieldfare-resumed.log`. The temporary playback API on 8001
was gracefully stopped. All diagnostic workers reached terminal state. Verify
current process identity before signalling any PID.

Final health reports TurboFieldfare/Gemma 4 with model, Kokoro and YouTube readiness true (availability, not structured-quality acceptance). The existing library still contains 5 lessons / 16 ready shorts, all retaining historical `gemma4:12b-mlx` provenance; a saved ready audio request returned HTTP 200. Primary server and backend were left running with the approved profile. Stop only
the owned launcher/backend gracefully when requested. Back up all data/config
before changes. Restoring the original Ollama profile does not require deleting
anything; incomplete TurboFieldfare jobs cannot resume under it silently, and
ready lessons from either runtime remain playable.

TurboFieldfare source is Apache-2.0; model weights remain under separate Gemma
terms. Installed runtime `THIRD_PARTY_NOTICES.md`, checkpoint/model card and Swift
resolved dependency notices were inspected; Kokoro/source/asset notices remain
unchanged. No secrets, model weights or compiled binaries are included in changes.
