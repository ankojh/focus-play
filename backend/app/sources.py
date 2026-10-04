import hashlib
import html
import re
from urllib.parse import urlparse, parse_qs
import httpx
from .contracts import ImportRequest, Source, TranscriptSegment
from .errors import AppError


def video_id(url: str | None) -> str | None:
    if not url:
        return None
    u = urlparse(url)
    if u.scheme not in {"https", "http"}:
        raise AppError("INVALID_VIDEO_URL", "Use a valid YouTube video URL.")
    host = (u.hostname or "").lower()
    if host in {"youtu.be", "www.youtu.be"}:
        value = u.path.strip("/")
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        value = parse_qs(u.query).get("v", [""])[0] if u.path == "/watch" else u.path.split("/")[-1] if u.path.startswith(("/shorts/", "/embed/")) else ""
    else:
        value = ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        raise AppError("INVALID_VIDEO_URL", "Use a valid YouTube video URL.")
    return value


def millis(value: str) -> int:
    parts = value.replace(",", ".").split(":")
    try:
        if len(parts) not in {2, 3} or not re.fullmatch(r"(?:\d+:)?\d{2}:\d{2}[.,]\d{3}", value):
            raise ValueError()
        seconds = float(parts[-1])
        minutes = int(parts[-2])
        if seconds >= 60 or minutes >= 60:
            raise ValueError()
        return round((int(parts[0]) * 3600 if len(parts) == 3 else 0) * 1000 + minutes * 60000 + seconds * 1000)
    except ValueError:
        raise AppError("INVALID_TRANSCRIPT", "A transcript time is invalid. Check the SRT or VTT file.")


def parse_transcript(request: ImportRequest) -> Source:
    content = request.text.replace("\r\n", "\n").replace("\r", "\n").strip().lstrip("\ufeff")
    if len(content.encode("utf-8")) > 200_000:
        raise AppError("IMPORT_TOO_LARGE", "Use a transcript smaller than 200 KB.")
    vid = video_id(request.youtube_url)
    digest = hashlib.sha256(content.encode()).hexdigest()
    sid = "src_" + hashlib.sha256((digest + request.format + request.title + (vid or "") + request.provenance).encode()).hexdigest()[:20]
    segments = []
    if request.format == "txt":
        chunks = re.split(r"\n\s*\n", content)
        chunks = [chunk.strip() for chunk in chunks if chunk.strip()]
        for chunk in chunks:
            for offset in range(0, len(chunk), 1800):
                segments.append(TranscriptSegment(id=f"{sid}_{len(segments)}", source_id=sid, text=chunk[offset:offset + 1800].strip()))
    else:
        blocks = re.split(r"\n\s*\n", content)
        previous_start = -1
        for block in blocks:
            lines = block.splitlines()
            if lines[0].startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
                continue
            timing = next((i for i, line in enumerate(lines) if "-->" in line), None)
            if timing is None:
                raise AppError("INVALID_TRANSCRIPT", "A caption has no time range. Check the file format.")
            left, right = lines[timing].split("-->", 1)
            start, end = millis(left.strip()), millis(right.strip().split()[0])
            text = html.unescape(re.sub(r"<[^>]*>", "", " ".join(lines[timing + 1:]))).strip()
            if not text or len(text) > 1800 or start < previous_start or end <= start:
                raise AppError("INVALID_TRANSCRIPT", "Caption text or time order is invalid. Check the file.")
            previous_start = start
            segments.append(TranscriptSegment(id=f"{sid}_{len(segments)}", source_id=sid, text=text, start_ms=start, end_ms=end))
    if not segments or len(segments) > 2000:
        raise AppError("INVALID_TRANSCRIPT", "Use a transcript with 1 to 2000 text segments.")
    return Source(id=sid, title=request.title, source_type="import", video_id=vid,
                  url=f"https://www.youtube.com/watch?v={vid}" if vid else None,
                  transcript_status="available", provenance=request.provenance, content_hash=digest, segments=segments)


def retrieve(sources: list[Source], goal: str, limit: int = 12) -> list[TranscriptSegment]:
    stop = {"the", "a", "an", "to", "of", "and", "me", "help", "understand", "learn", "what", "is", "about", "how"}
    words = set(re.findall(r"[a-z0-9]+", goal.lower())) - stop
    candidates = [s for source in sources for s in source.segments]
    ranked = sorted(enumerate(candidates), key=lambda pair: (-len(words & set(re.findall(r"[a-z0-9]+", pair[1].text.lower()))), pair[0]))
    selected, length = [], 0
    for _, segment in ranked[:limit]:
        if length + len(segment.text) > 10000:
            break
        selected.append(segment)
        length += len(segment.text)
    return selected


SEARCH_RESULTS = 15
# Shorts rarely teach a full point; long lectures exceed the transcript bounds.
MIN_SECONDS, MAX_SECONDS = 61, 1800


def youtube_get(path: str, params: dict) -> httpx.Response:
    try:
        response = httpx.get(f"https://www.googleapis.com/youtube/v3/{path}", params=params, timeout=15, follow_redirects=False, trust_env=False)
    except httpx.HTTPError:
        raise AppError("SOURCE_NETWORK_FAILED", "YouTube search failed. Check the internet connection, then retry.", 503)
    if response.status_code == 403:
        raise AppError("YOUTUBE_QUOTA_OR_ACCESS", "YouTube rejected the request. Check the API quota and key, then retry.", 503)
    if not response.is_success:
        raise AppError("SOURCE_SEARCH_FAILED", "YouTube search failed. Check the server API key, then retry.", 503)
    return response


def iso_seconds(value: str) -> int | None:
    match = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", value or "")
    if not match or value in {"P", "PT"}:
        return None
    days, hours, minutes, seconds = (int(x or 0) for x in match.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def search_youtube(query: str, key: str) -> list[dict]:
    if not key:
        raise AppError("YOUTUBE_KEY_MISSING", "YouTube search needs YOUTUBE_API_KEY in the server .env file. Add the key, restart the server, then retry.", 503)
    # search.list costs 100 quota units regardless of maxResults; videos.list costs 1.
    response = youtube_get("search", {"key": key, "part": "snippet", "type": "video", "maxResults": SEARCH_RESULTS, "relevanceLanguage": "en", "q": query})
    results = []
    try:
        for item in response.json().get("items", [])[:SEARCH_RESULTS]:
            vid = item.get("id", {}).get("videoId", "")
            if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid) and item["snippet"].get("liveBroadcastContent", "none") == "none":
                results.append({"video_id": vid, "title": html.unescape(item["snippet"]["title"]), "channel": html.unescape(item["snippet"]["channelTitle"]), "url": f"https://www.youtube.com/watch?v={vid}", "transcript_status": "needed"})
    except (ValueError,KeyError,TypeError,AttributeError):
        raise AppError("SOURCE_SEARCH_FAILED", "YouTube returned invalid search data. Retry to search again.",503)
    if not results:
        return results
    details = youtube_get("videos", {"key": key, "part": "contentDetails", "id": ",".join(r["video_id"] for r in results)})
    try:
        durations = {item["id"]: iso_seconds(item["contentDetails"]["duration"]) for item in details.json().get("items", [])}
    except (ValueError,KeyError,TypeError,AttributeError):
        raise AppError("SOURCE_SEARCH_FAILED", "YouTube returned invalid video data. Retry to search again.",503)
    kept = []
    for result in results:
        seconds = durations.get(result["video_id"])
        if seconds is not None and MIN_SECONDS <= seconds <= MAX_SECONDS:
            kept.append({**result, "duration_seconds": seconds})
    return kept
