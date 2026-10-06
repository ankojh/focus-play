"""Openly licensed cover photos for shorts: Openverse first, Wikimedia Commons as fallback.

A cover is decorative context, not teaching evidence. It never enters the reviewed
storyboard or playback readiness, and any search/download failure leaves the short
without a cover. Downloads are downscaled, then stored through the managed asset path.
"""
import io
import re
from urllib.parse import urlparse
import warnings
import httpx
from PIL import Image
from .contracts import CoverPhoto
from .llm.compact import QUERY_STOP

OPENVERSE = "https://api.openverse.org/v1/images/"
COMMONS = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "FocusPlay/0.1 (local learning app; cover photos)"
# Outcome verbs from the planner say nothing about what a photo should show.
VERBS = {"explain", "identify", "compare", "trace", "predict", "apply", "describe", "understand",
         "use", "using", "work", "works", "does", "how", "why", "what", "when", "which", "its", "their", "between", "into"}
MAX_DOWNLOAD = 15_000_000
MAX_SIDE = 1280
MAX_DOWNLOADS = 3


def words(text):
    return [w for w in re.findall(r"[A-Za-z0-9]+", text) if len(w) > 2 and w.lower() not in QUERY_STOP | VERBS]


def photo_queries(goal, objective):
    """Most specific first: goal topic plus the short's focus, then the topic alone."""
    topic = words(goal)[:3]
    seen = {w.lower() for w in topic}
    focus = [w for w in words(objective) if w.lower() not in seen][:3]
    queries = [topic + focus, topic + focus[:1], topic or focus]
    return list(dict.fromkeys(" ".join(q) for q in queries if q))


def license_label(code, version=""):
    code = (code or "").lower()
    if code == "pdm":
        return "Public Domain Mark"
    if code == "cc0":
        return "CC0 1.0"
    return f"CC {code.upper()} {version}".strip()


def safe_url(url):
    parts = urlparse(url or "")
    return parts.scheme == "https" and parts.hostname not in {None, "localhost", "127.0.0.1", "::1"}


def plain(html, limit):
    text = " ".join(re.sub(r"<[^>]+>", " ", html or "").split())
    return text[:limit].strip()


class PhotoSearch:
    def __init__(self, assets, timeout=6.0):
        self.assets, self.timeout = assets, timeout

    def openverse(self, client, query):
        # Exclude no-derivatives licences: the player crops and pans the photo.
        response = client.get(OPENVERSE, params={"q": query, "page_size": 8, "mature": "false",
                                                 "extension": "jpg,png", "license_type": "modification"})
        response.raise_for_status()
        hits = []
        for r in response.json().get("results", []):
            if r.get("mature") or (r.get("width") or 640) < 600 or (r.get("height") or 400) < 400:
                continue
            title, creator = plain(r.get("title") or "Untitled photo", 120), plain(r.get("creator") or "Unknown creator", 100)
            label = license_label(r.get("license"), r.get("license_version") or "")
            hits.append({"url": r.get("url"), "source": r.get("foreign_landing_url") or r.get("url"),
                         "title": title, "creator": creator, "license": label, "license_url": r.get("license_url"),
                         "provider": r.get("source") or r.get("provider") or "Openverse"})
        return hits

    def commons(self, client, query):
        response = client.get(COMMONS, params={"action": "query", "format": "json", "generator": "search",
            "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": 6, "gsrlimit": 8, "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata", "iiurlwidth": MAX_SIDE})
        response.raise_for_status()
        pages = sorted(response.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
        hits = []
        for page in pages:
            info = (page.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata", {})
            label = plain(meta.get("LicenseShortName", {}).get("value"), 60)
            free = label.lower().startswith(("cc", "public domain")) and not re.search(r"\bnd\b", label.lower())
            if not free or info.get("mime") not in {"image/jpeg", "image/png"} or info.get("width", 0) < 600 or info.get("height", 0) < 400:
                continue
            title = plain(meta.get("ObjectName", {}).get("value") or page.get("title", "").removeprefix("File:"), 120) or "Untitled photo"
            hits.append({"url": info.get("thumburl") or info.get("url"), "source": info.get("descriptionurl") or info.get("url"),
                         "title": title, "creator": plain(meta.get("Artist", {}).get("value"), 100) or "Unknown creator",
                         "license": label, "license_url": plain(meta.get("LicenseUrl", {}).get("value"), 500) or None,
                         "provider": "Wikimedia Commons"})
        return hits

    def download(self, client, url):
        if not safe_url(url):
            raise ValueError("Only public HTTPS photo URLs are fetched.")
        with client.stream("GET", url) as response:
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_bytes():
                data += chunk
                if len(data) > MAX_DOWNLOAD:
                    raise ValueError("Photo download is too large.")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            try:
                with Image.open(io.BytesIO(bytes(data)), formats=("JPEG", "PNG")) as image:
                    image.thumbnail((MAX_SIDE, MAX_SIDE))
                    output = io.BytesIO()
                    image.convert("RGB").save(output, format="JPEG", quality=88)
            except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
                raise ValueError("Photo is not a usable JPEG/PNG image.") from exc
        return output.getvalue()

    def cover(self, goal, objective, exclude=frozenset(), cancel=None):
        downloads = 0
        with httpx.Client(timeout=self.timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True, trust_env=False) as client:
            for query in photo_queries(goal, objective):
                hits = []
                for search in (self.openverse, self.commons):
                    try:
                        hits = search(client, query)
                    except (httpx.HTTPError, ValueError):
                        continue
                    if hits:
                        break
                for hit in hits:
                    if hit["source"] in exclude or not hit["url"]:
                        continue
                    if downloads >= MAX_DOWNLOADS:
                        return None
                    downloads += 1
                    try:
                        data = self.download(client, hit["url"])
                    except (httpx.HTTPError, ValueError):
                        continue
                    title = hit["title"]
                    record = self.assets.register_bytes(data, kind="image", original_source=hit["source"][:500],
                        creator=hit["creator"], permission_basis=f"{hit['license']} licence, found through {hit['provider']}.",
                        attribution=f"“{title[:80]}” by {hit['creator'][:80]} · {hit['license']}",
                        source_context=f"Cover photo for “{objective[:120]}”, searched as “{query}”: {title}"[:300],
                        illustrative=False, license_url=hit["license_url"], cancel=cancel)
                    return CoverPhoto(asset=record, alt=title[:240], query=query)
        return None
