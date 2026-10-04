# Automatic YouTube source change

Checked on 4 October 2026. Full live acceptance is pending the server search key.

## Behavior

The dark Shorts interface now has only the goal, current knowledge, and time fields. New creation sends no source mode, source IDs, uploaded transcript, pasted source text, or video URL. The backend rejects legacy source-selection fields and has no import endpoint.

The saved job searches YouTube and retrieves public English captions automatically. Progress uses **Searching YouTube** and **Reading video transcripts**. The existing local model, local Kokoro voice, audio-clock player, time allowances, sequence, progressive delivery, cancellation, and retry remain in use.

Only validated YouTube transcripts enter new generation, including questions, answer explanations, and extra shorts. Search titles and snippets do not enter teaching evidence. Extra shorts check the available YouTube evidence and search again if it is insufficient. Non-YouTube sources are never a fallback.

Saved imports, original samples, and existing lessons retain their records and source types. Opening them does not create new work. Adding a new short to an old lesson appends YouTube evidence while keeping its previous source history.

## Provider and limits

Search uses [YouTube Data API v3](https://developers.google.com/youtube/v3/docs/search/list) and the server's `YOUTUBE_API_KEY`. Captions use [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api) 1.2.4, which is included in the Python lockfile. No paid caption service, cookies, proxy, translation, or access-token workaround was added. The official [caption download API](https://developers.google.com/youtube/v3/docs/captions/download) needs video edit permission; the search key does not give general caption download access.

Each worker acquisition attempt has two query variants, six search results per query, at most eight distinct video attempts including already attached videos, and at most two new transcripts per query. A search request has a 15-second timeout. Caption requests have a ten-second request timeout and a 25-second deadline checked between requests. Search and caption caches last one day.

Unavailable captions are skipped. Access blocks or missing provider access stop the job with a setup error. No usable captions and insufficient evidence have separate errors. All failures retain retry. Public access does not establish reuse rights or source accuracy.

Adjacent captions form passages of at most 280 characters. Each passage keeps the first actual caption start and last actual caption end. Raw caption records also remain in the cache. Metadata includes the video ID, canonical URL, title, channel, provider, content hash, and caption provenance. Evidence links include the supplied time when available.

## Automated results

- **47 backend checks passed.** They include automatic source acquisition, query bounds, missing credentials, quota and access errors, skipped captions, insufficient evidence, extra-short expansion, source restrictions, questions, legacy requests, old saved records, metadata and time validation, plus the existing job and player-contract checks.
- **10 browser fixture checks passed.** They include form submission with no source library, absence of manual entry, timed source links, setup error and retry, opening an imported saved lesson, progressive snapshots, playback, seek, refresh, questions, extra allowances, keyboard controls, reduced motion, all five diagram templates, and mobile width.
- **OpenAPI types and production UI build passed.** API types were regenerated from the new public request and saved-request schemas.

These checks use explicit test providers and browser fixtures. They do not establish actual YouTube search access or live teaching quality. The FastAPI test client emits one dependency deprecation warning; the tests pass.

## Real checks and remaining dependency

Public caption retrieval passed on this Mac for video `RufupUDBtYY`, **Database Indexes - You Might Be Using Them Wrong**, channel **LearnThatStack**. The actual provider returned 70 grouped passages in 1.498 seconds, with supplied caption bounds from 320 ms to 1,118,160 ms. This was a direct caption-access check, not a goal-to-lesson search check. [Recorded result](youtube-live-check.json).

The updated local API accepted a three-field learning request, then returned `YOUTUBE_KEY_MISSING` at **Searching YouTube**. It attached no sources or shorts. Retry returned HTTP 202 and gave the same setup error while the key was absent. The live API returned saved source history. All **38 legacy source rows** and **47 existing lesson rows** remained byte-for-byte unchanged after the server update. The real browser shows the new form and YouTube setup message. An existing imported lesson opened and its saved local audio played after the update.

**The full live goal → YouTube search → captions → playable short check is blocked.** The exact missing dependency is a server `YOUTUBE_API_KEY` for a Google project with YouTube Data API v3 enabled. Put it in the ignored root `.env`, then restart the API. Do not put the key in chat. The local model and Kokoro voice are ready. Caption access passed for one public video; access to other search results still needs live verification.

The live browser test now uses actual search and captions:

```sh
FOCUS_LIVE=1 npm test --prefix frontend -- tests/live.spec.ts
```

Run it after the key is configured. It checks real playback, saved position, source IDs and timed links, question evidence, budget, and request idempotency. It is not counted among the ten fixture checks. Earlier imported-source latency and content-review results remain historical and do not describe the new YouTube flow.
