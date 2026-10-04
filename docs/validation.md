# Validation results

Historical record for the previous imported-source version. These results do not verify the automatic YouTube flow. See [current change checks](youtube-source-change.md).

Checked on 4 October 2026, on the Mac described in the performance report.

## Automated checks

- Python: 29 focused checks passed. They cover SRT/VTT parsing, source and time validation, import limits, lexical retrieval, bounded schema repairs, native excerpt/segment coupling, extractive claims, chart values, cue/source selection, duration reservations, idempotency, publication, cancellation, retry, partial failure, restart recovery, managed audio, quota/network errors, and missing/remote models.
- Browser fixtures: eight checks passed. They cover play, pause, seeking, replay, short changes, caption/diagram time, refresh, SSE reconnection, request errors, source import, question feedback, extra-time approval, keyboard controls, reduced motion, all five templates, and a 390-pixel viewport.
- Production build and generated OpenAPI types passed. The API types are generated from the Pydantic OpenAPI contract.
- The Python tests use explicit test providers. Browser fixture tests intercept API and audio requests. These tests do not measure live model quality.

The current FastAPI test client emits a dependency deprecation warning for its HTTP client. The tests pass. A migration of the test client is not required for local application operation.

## Real local providers

Kokoro 0.9.4 ran on the CPU with `af_heart`, its downloaded model and voice, Misaki English data, and the bundled espeak-ng library. It produced real 24 kHz speech. No macOS system voice was used for these results.

Ollama 0.35.1 ran Qwen3 8B locally with cloud access disabled. One cold, five warm uncached, and one cached lesson completed. All seven produced ready audio, valid timelines, real source references, and a content budget below five minutes. See [performance measurements](performance.md) and the raw provider settings in [performance-runs.json](performance-runs.json).

All nine browser checks passed together. After the visual cue correction, the live browser test passed again in 51.6 seconds. The live test imported the original sample under a new source identity to prevent a cached lesson from replacing generation. It used real model and speech work. It verified that the first short played while later shorts were incomplete, then checked pause, seek, refresh, completion, source references, the budget, and a repeated request ID. It did not use API fixtures.

The offline check passed with external Python socket connections blocked and `HF_HUB_OFFLINE=1`. It used the already downloaded model and voice, a local source, and a real process diagram. There were no blocked external connection attempts. The Ollama server had cloud access disabled. See [offline-check.json](offline-check.json). This is a controlled network check, not a physical disconnection of the computer.

The mobile playback check used real audio, blocked external browser requests, and a 390 × 844 viewport. It checked caption seeking, audio time, the seek control, and page width. Frame measurements are in [playback-check.json](playback-check.json). It is a short headless browser sample, not a complete foreground device or energy profile.

## Manual source review

The comparison and worked example use the original `database-indexes.txt` source. The process clip is the real offline-check output. This review checks the generated content against that source. It does not establish the independent truth of an imported source.

| Review | Actual content | Source support | Result and limit |
| --- | --- | --- | --- |
| Comparison | A scan can read many rows and test a condition. An email index can help find entries without testing every row. | Original scan paragraph and email example paragraph. The narration is an exact excerpt. | Supported. The diagram compares the methods. Related storage labels need the index cost paragraph; the application adds a locally matched reference for such labels. No measured speed claim is made. |
| Process | Ordered B-tree keys, a key or range lookup, matching entries, and rows. The next phrase connects this to an email index. | B-tree paragraph and email example paragraph. The process diagram follows structure → lookup → matching entries → row retrieval. | Supported. It is a general concept diagram and is not a product-specific implementation guide. |
| Worked example | The users table has id, email, and name. The query asks for `ada@example.test`. An email index can help find matching entries. | Original worked example paragraph. | Supported. The question’s correct answer and explanation copy that source. Incorrect choices include an index-use guarantee, which the source does not support. |

An earlier paraphrased draft claimed fewer disk reads. Its local model review accepted that unsupported detail. That result failed manual review. The final release therefore uses exact source excerpts for narration and correct answer explanations. The model still selects and orders the material and supplies diagram relationships and question choices. Diagram relevance and source reliability still require human review.

The final visual review also found an incorrect highlight: a scan explanation mentioned an index as absent, and a word match highlighted the index. Cue selection now also checks labels in the full supporting passage. A regression check confirms that the scan phrase highlights the scan and the next index phrase highlights the index. This remains a simple text match, not full semantic understanding.

## Remaining limits

- Live YouTube discovery was not checked with a configured key. Missing-key, quota, and network errors were checked. Discovery needs a permitted transcript import.
- The original sample checks passed. This does not establish quality for every topic, source, software version, or language. English is the supported language.
- Sample shorts can be about 16–18 seconds. This is below the preferred 20–40 second range. Natural speech speed is fixed, and the 40-second maximum is enforced.
- Two warm runs had derived waiting time before a later short. The largest wait was about 2.5 seconds. The first-short target passed; the strict no-wait target did not pass every run.
- There is no word-level caption alignment, MP4 export, automatic public-caption access, or peak energy profile.
