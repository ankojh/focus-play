# Measured local performance

Historical record for the previous imported-source version. These results do not verify the automatic YouTube flow. See [current change checks](youtube-source-change.md).

Measured on 4 October 2026, on an Apple M5 Pro with 48 GB unified memory. This is a small sample on one computer. It is not a general hardware promise.

## Method

One cold run, five warm uncached runs, and one cached run. The cold run used a new API process, a new Kokoro pipeline, and an unloaded Ollama model. Setup downloads and the operating system file cache were outside that cold measure. Each uncached run used the same original transcript under a distinct source identity. No other language-model requests ran during these measurements. Browser control tests ran briefly during the cold run.

The goal requested three learning points: compare a scan with an index, explain lookup, and show an email example. The original budget was 300 seconds. Each run completed three ready shorts and a question. The worker published shorts separately. The measured planned content was about 69 seconds including a 20-second question allowance. Learner pauses are outside this content budget.

## Individual results

| Run | Accept (s) | Import (s) | Plan (s) | First playable (s) | All ready (s) | Longest derived wait (s) | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Cold | 0.001 | 0.002 | 5.744 | 21.852 | 52.388 | 0.000 | complete |
| Warm 1 | 0.001 | 0.001 | 4.239 | 17.671 | 48.691 | 0.000 | complete |
| Warm 2 | 0.001 | 0.001 | 4.161 | 17.469 | 49.278 | 0.000 | complete |
| Warm 3 | 0.001 | 0.002 | 4.490 | 18.432 | 51.656 | 2.524 | complete |
| Warm 4 | 0.001 | 0.003 | 4.373 | 18.707 | 52.400 | 0.318 | complete |
| Warm 5 | 0.001 | 0.002 | 4.266 | 18.567 | 51.584 | 0.000 | complete |
| Cached | 0.002 | 0.000 | 0.000 | 0.008 | 0.022 | 0.000 | complete |

Wait is derived from actual publish times and measured audio lengths, assuming immediate continuous playback and the planned 20-second question allowance. It is not a recording of a person’s pauses. A ready short does not wait for later generation.

## Five warm uncached runs

| Measure | Median (s) | Maximum (s) |
| --- | ---: | ---: |
| Accepted request | 0.001 | 0.001 |
| Source import | 0.002 | 0.003 |
| Provider readiness | 0.006 | 0.006 |
| Source retrieval | 0.000 | 0.000 |
| Planning | 4.266 | 4.490 |
| First playable short | 18.432 | 18.707 |
| Total preparation | 51.584 | 52.400 |
| Model generation, all shorts | 32.489 | 33.256 |
| Model source review, all shorts | 10.348 | 10.686 |
| Speech, all shorts | 4.122 | 4.246 |

No p95 is reported for five warm samples. Import and retrieval are separate from provider loading. Model generation is the main preparation cost. Each short’s stage and ready times are saved in the raw report.

## Targets

The accepted request returned its saved job in less than one second in every measured run. Every warm run made the first playable short ready within 30 seconds. Later shorts were usually ready before their expected playback start. Two runs had a derived wait; see the table. The strict target of no waiting did not pass every run. These measurements cover this sample, this model, and this voice.

## Exact providers

- Ollama runtime: 0.35.1, loopback, cloud disabled, one parallel task. Model: `qwen3:8b`. Quantization: `Q4_K_M`.
- Model digest: `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41`.
- Context: 8192 tokens. Output limit: 2200 tokens. Temperature: 0. Seed: 42. Thinking: False. Prompt version: 13. Schema version: 1.
- Speech: Kokoro 0.9.4 / Misaki 0.9.4, CPU, voice `af_heart`, speed 1, 24 kHz mono PCM WAV. No system voice substitute was used.
- Speech model revision: `f3ff3571791e39611d31c381e3a41a3af07b4987`.
- Voice SHA-256: `0ab5709b8ffab19bfd849cd11d98f75b60af7733253ad0d67b12382a102cb4ff`.

## Quality and limits

Earlier tests exposed invalid model references and an unsupported paraphrased claim. The final implementation uses constrained source excerpts and template-generated cues. The earlier measurements are retained in `development-runs/`. They are not included in the final median. Manual review covers the final comparison, worked example, and process clip; see `validation.md`.

Qwen3 8B passed the final original-sample checks with these constrained contracts. This does not establish quality for every imported source or learning goal. No larger model was installed or compared. General paraphrasing is outside this release after the source review failure. Some sample shorts are about 16–18 seconds, below the preferred 20–40 second range. They use fixed natural speech speed and stay below the 40-second maximum.

## Workload and cost

The model download is 5,225,388,164 bytes. Kokoro model and voice files are about 327 MB and 510 KB. Local runtime, environment, cache, and media use are in `workload.json`. That snapshot is not a peak memory or energy measurement. Ollama reports its model allocation separately from the API process. GPU shared memory and total operating system pressure were not independently profiled.

Local inference, local speech, and SVG playback have no metered cloud generation fee in this build. Hardware, electricity, storage, setup time, and any optional source-service charges remain costs. Electricity and money costs were not measured.

Raw measurements: [performance-runs.json](performance-runs.json).
