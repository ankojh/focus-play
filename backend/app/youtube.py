"""YouTube search and English captions. Supadata fetches captions from its own servers,
so YouTube does not rate-limit this computer."""
import hashlib
import html
import json
import math
import re
import threading
import time
import httpx
from .contracts import Source, TranscriptSegment
from .errors import AppError
from .providers import check_cancel
from .sources import search_youtube, video_id

PROVIDER = "supadata"
# Saved lessons keep sources read by the earlier provider.
PROVIDERS = {"youtube-transcript-api", PROVIDER}
SOURCE_TTL = 86400
SUPADATA_URL = "https://api.supadata.ai/v1/transcript"
# The free plan allows one request per second.
SUPADATA_INTERVAL = 1.1
_throttle = threading.Lock()
_last_request = [0.0]


def queries(goal, knowledge, focus=None):
    topic = " ".join((focus or goal).split())[:150]
    level = "for beginners" if knowledge == "beginner" else " ".join(knowledge.split())[:60] if knowledge != "some knowledge" else "tutorial"
    return [f"{topic} {level}"[:200], f"{topic} explained tutorial"[:200]]


def require_youtube(source):
    if (source.source_type != "youtube" or source.transcript_provider not in PROVIDERS
            or not source.video_id or source.url != f"https://www.youtube.com/watch?v={source.video_id}"
            or video_id(source.url) != source.video_id or source.transcript_status != "available"
            or not source.segments or any(s.source_id != source.id for s in source.segments)):
        raise AppError("YOUTUBE_SOURCE_REQUIRED", "New content needs automatically retrieved YouTube transcripts. Retry to search YouTube.", 422)


def source_from_transcript(candidate, data):
    """Build a source from a Supadata transcript: content rows carry text, offset and duration in ms."""
    vid = candidate["video_id"]
    if video_id(f"https://www.youtube.com/watch?v={vid}") != vid:
        raise AppError("INVALID_YOUTUBE_TRANSCRIPT", "The transcript video ID is invalid. Retry to find another video.")
    language = data.get("lang")
    if language not in {"en", "en-US", "en-GB"}:
        raise AppError("TRANSCRIPT_UNAVAILABLE", "This video has no supported English transcript.")
    raw = data.get("content")
    if not isinstance(raw, list) or not raw or len(raw) > 10000 or len(json.dumps(raw).encode()) > 500000:
        raise AppError("INVALID_YOUTUBE_TRANSCRIPT", "The video transcript is empty or too large. Retry to find another video.")
    passages, current, start, end, previous = [], "", None, None, -1
    for caption in raw:
        text = " ".join(html.unescape(re.sub(r"<[^>]*>", "", caption["text"])).split())
        begin, duration = caption["offset"], caption["duration"]
        if not all(isinstance(x,(int,float)) and math.isfinite(x) and x >= 0 for x in (begin,duration)) or begin < previous or duration <= 0:
            raise AppError("INVALID_YOUTUBE_TRANSCRIPT", "A video caption has invalid timing. Retry to find another video.")
        previous = begin
        if not text:
            continue
        if len(text) > 280:
            raise AppError("INVALID_YOUTUBE_TRANSCRIPT", "A video caption is too long for this lesson. Retry to find another video.")
        # Adjacent captions form a usable excerpt. Their supplied time bounds remain authoritative.
        if current and (len(current)+len(text)+1 > 280 or (len(current)>120 and re.search(r"[.!?]$",current))):
            passages.append((current,start,end));current="";end=None
        if not current:
            start = round(begin)
        current = (current+" "+text).strip()
        end = max(end or 0, round(begin+duration))
    if current:
        passages.append((current,start,end))
    if not passages or len(passages)>2000 or sum(len(p[0].encode()) for p in passages)>200000:
        raise AppError("INVALID_YOUTUBE_TRANSCRIPT", "The video transcript is outside the supported size. Retry to find another video.")
    digest=hashlib.sha256(json.dumps(passages,ensure_ascii=False).encode()).hexdigest()
    sid="src_"+hashlib.sha256((vid+language+PROVIDER+digest).encode()).hexdigest()[:20]
    source=Source(id=sid,title=candidate["title"],channel=candidate["channel"],source_type="youtube",
        video_id=vid,url=f"https://www.youtube.com/watch?v={vid}",transcript_provider=PROVIDER,
        transcript_status="available",content_hash=digest,
        provenance=f"Existing YouTube captions retrieved by Supadata (native mode); {language}. Caption ranges are supplied by YouTube. Access does not establish reuse rights.",
        segments=[TranscriptSegment(id=f"{sid}_{i}",source_id=sid,text=text,start_ms=start,end_ms=end) for i,(text,start,end) in enumerate(passages)])
    require_youtube(source)
    return source


def fetch_supadata(vid,key,cancel,audit=None):
    if not key:
        raise AppError("TRANSCRIPT_ACCESS_REQUIRED","Video transcripts need SUPADATA_API_KEY in the server .env file. Add the key, restart the server, then retry.",503)
    with _throttle:
        wait=_last_request[0]+SUPADATA_INTERVAL-time.monotonic()
        if wait>0:
            cancel.wait(wait)
        check_cancel(cancel)
        _last_request[0]=time.monotonic()
    # Native mode only returns existing captions. Generated transcripts cost extra credits.
    # chunkSize keeps each row within the 280 character passage bound.
    if audit:
        audit("supadata")
    try:
        response=httpx.get(SUPADATA_URL,params={"url":f"https://www.youtube.com/watch?v={vid}","lang":"en","mode":"native","chunkSize":250},
            headers={"x-api-key":key},timeout=30,follow_redirects=False,trust_env=False)
    except httpx.TimeoutException:
        raise AppError("TRANSCRIPT_TIMEOUT","Video transcript retrieval timed out. Retry to try other videos.",503) from None
    except httpx.HTTPError:
        raise AppError("TRANSCRIPT_NETWORK_FAILED","The transcript service could not be reached. Check your connection, then retry within the remaining acquisition allowance.",503) from None
    check_cancel(cancel)
    if response.status_code in {401,403}:
        raise AppError("TRANSCRIPT_ACCESS_REQUIRED","Supadata rejected the API key. Check SUPADATA_API_KEY, restart the server, then retry.",503)
    if response.status_code==402:
        raise AppError("TRANSCRIPT_ACCESS_REQUIRED","Supadata credits are used up. Add credits or wait for the monthly reset, then retry.",503)
    if response.status_code==429:
        raise AppError("TRANSCRIPT_ACCESS_REQUIRED","Supadata rate or credit limit reached. Wait, then retry.",503)
    # 202 is an AI generation job and 206 means no captions. Native mode should not start jobs.
    if response.status_code!=200:
        raise AppError("TRANSCRIPT_UNAVAILABLE","This video has no accessible English transcript.",422)
    try:
        data=response.json()
    except ValueError:
        raise AppError("INVALID_YOUTUBE_TRANSCRIPT","The video transcript data is invalid. Another video will be tried.",422) from None
    if not isinstance(data,dict) or "jobId" in data:
        raise AppError("TRANSCRIPT_UNAVAILABLE","This video has no accessible English transcript.",422)
    return data


class YouTubeSources:
    def __init__(self,store,settings):
        self.store,self.settings=store,settings
    def search_cached(self, query):
        key = hashlib.sha256(("youtube-search-v2:" + query.lower()).encode()).hexdigest()
        return bool(self.settings.youtube_key) and self.store.cache_get(key, max_age=SOURCE_TTL) is not None
    def transcript_cached(self, candidate):
        key = hashlib.sha256((f"youtube-caption-v2:{PROVIDER}:{candidate['video_id']}:en").encode()).hexdigest()
        return self.store.cache_get(key, max_age=SOURCE_TTL) is not None
    def search(self,query,audit=None):
        if not self.settings.youtube_key:
            return search_youtube(query,"",audit)
        key=hashlib.sha256(("youtube-search-v2:"+query.lower()).encode()).hexdigest()
        cached=self.store.cache_get(key,max_age=SOURCE_TTL)
        if cached is not None:
            if audit:
                audit("search_cache_hit")
            return cached
        candidates=search_youtube(query,self.settings.youtube_key,audit)
        self.store.cache_put(key,candidates)
        return candidates
    def transcript(self,candidate,cancel,audit=None):
        check_cancel(cancel)
        vid=candidate["video_id"]
        video_id(f"https://www.youtube.com/watch?v={vid}")
        key=hashlib.sha256((f"youtube-caption-v2:{PROVIDER}:{vid}:en").encode()).hexdigest()
        cached=self.store.cache_get(key,max_age=SOURCE_TTL)
        if cached is not None:
            source=Source.model_validate(cached["source"])
            require_youtube(source)
            if source.video_id!=vid:
                raise AppError("YOUTUBE_SOURCE_REQUIRED","The cached video ID does not match. Retry to retrieve the source.",422)
            if audit:
                audit("transcript_cache_hit")
            return source
        data=fetch_supadata(vid,self.settings.supadata_key,cancel,audit)
        try:
            source=source_from_transcript(candidate,data)
        except (ValueError,KeyError,TypeError):
            raise AppError("INVALID_YOUTUBE_TRANSCRIPT","The video transcript data is invalid. Another video will be tried.",422) from None
        check_cancel(cancel)
        self.store.put_source(source)
        self.store.cache_put(key,{"source":source.model_dump(),"captions":data["content"]})
        return source
