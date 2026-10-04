# Bundled visual fixture notices

`lookup-illustration.png` is an original Focus Play project illustration created for this delivery. The fixture authors dedicate the original illustration to the public domain under **CC0 1.0 Universal**: https://creativecommons.org/publicdomain/zero/1.0/ . Inclusion, modification and redistribution are permitted; no third-party footage, photographs or product screenshots were copied. It is labeled as an illustration rather than a real screenshot or measured dataset. Suggested attribution: “Focus Play lookup illustration · CC0 1.0”. The runtime provenance record carries this text even though CC0 does not require attribution.

The original illustrative diagnostic passages and synthetic table/chart data authored in `scripts/export_visual_fixture.py` / `fixtures/mixed-visuals.json` are likewise supplied under CC0 1.0. They are **test fixtures**, not third-party source measurements, benchmarking evidence or live teaching-quality results. This dedication does not change the licences of other repository files.

## New software dependency

Raster verification and canonicalization use **Pillow**, locked to 11.3.0 in `backend/uv.lock` (compatible range `>=11.0,<12`). Pillow uses the MIT-CMU licence. Its wheel includes notices for linked image/font/compression libraries. The complete notice distributed with the installed Pillow wheel is retained at [`docs/licenses/Pillow-11.3.0.txt`](../../docs/licenses/Pillow-11.3.0.txt). Retain that notice when distributing the dependency; other platform wheels may contain different bundled-library notices.

This software is based in part on the work of the Independent JPEG Group and the FreeType Team (https://www.freetype.org/), via Pillow. PNG handling uses Pillow and the libraries described in the retained notices. No new paid dependency or remote media provider was introduced.

The UI still uses the existing Lucide dependency and its existing ISC-licensed icons. Diagnostic application screenshots in `docs/visual-screenshots/` depict this project's fixture UI, not acquired third-party software screenshots. They are review artifacts, not runtime assets or proof of live factual teaching quality.
