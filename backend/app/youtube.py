"""YouTube search and public English captions. No paid service, cookies, or proxy."""
import hashlib
import html
import json
import math
import re
import time
from urllib.parse import urlparse
from requests import Session, RequestException
from youtube_transcript_api import (YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound,
    VideoUnavailable, VideoUnplayable, AgeRestricted, RequestBlocked, IpBlocked, PoTokenRequired,
    CouldNotRetrieveTranscript)
from .contracts import Source, TranscriptSegment
from .errors import AppError
from .providers import check_cancel
from .sources import search_youtube, video_id

PROVIDER = "youtube-transcript-api"
SOURCE_TTL = 86400


def queries(goal, knowledge, focus=None):
    topic = " ".join((focus or goal).split())[:150]
    level = "for beginners" if knowledge == "beginner" else " ".join(knowledge.split())[:60] if knowledge != "some knowledge" else "tutorial"
    return [f"{topic} {level}"[:200], f"{topic} explained tutorial"[:200]]


def require_youtube(source):
    if (source.source_type != "youtube" or source.transcript_provider != PROVIDER
            or not source.video_id or source.url != f"https://www.youtube.com/watch?v={source.video_id}"
            or video_id(source.url) != source.video_id or source.transcript_status != "available"
            or not source.segments or any(s.source_id != source.id for s in source.segments)):
        raise AppError("YOUTUBE_SOURCE_REQUIRED", "New content needs automatically retrieved YouTube transcripts. Retry to search YouTube.", 422)


def source_from_transcript(candidate, fetched):
    vid = candidate["video_id"]
    if video_id(f"https://www.youtube.com/watch?v={vid}") != vid or fetched.video_id != vid:
        raise AppError("INVALID_YOUTUBE_TRANSCRIPT", "The transcript video ID is invalid. Retry to find another video.")
    if fetched.language_code not in {"en", "en-US", "en-GB"}:
        raise AppError("TRANSCRIPT_UNAVAILABLE", "This video has no supported English transcript.")
    raw = fetched.to_raw_data()
    if not raw or len(raw) > 10000 or len(json.dumps(raw).encode()) > 500000:
        raise AppError("INVALID_YOUTUBE_TRANSCRIPT", "The video transcript is empty or too large. Retry to find another video.")
    passages, current, start, end, previous = [], "", None, None, -1
    for caption in raw:
        text = " ".join(html.unescape(re.sub(r"<[^>]*>", "", caption["text"])).split())
        begin, duration = caption["start"], caption["duration"]
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
            start = round(begin*1000)
        current = (current+" "+text).strip()
        end = max(end or 0, round((begin+duration)*1000))
    if current:
        passages.append((current,start,end))
    if not passages or len(passages)>2000 or sum(len(p[0].encode()) for p in passages)>200000:
        raise AppError("INVALID_YOUTUBE_TRANSCRIPT", "The video transcript is outside the supported size. Retry to find another video.")
    digest=hashlib.sha256(json.dumps(passages,ensure_ascii=False).encode()).hexdigest()
    sid="src_"+hashlib.sha256((vid+fetched.language_code+PROVIDER+digest).encode()).hexdigest()[:20]
    source=Source(id=sid,title=candidate["title"],channel=candidate["channel"],source_type="youtube",
        video_id=vid,url=f"https://www.youtube.com/watch?v={vid}",transcript_provider=PROVIDER,
        transcript_status="available",content_hash=digest,
        provenance=f"Public YouTube {'automatic' if fetched.is_generated else 'creator'} captions. {PROVIDER} 1.2.4; {fetched.language_code}. Caption ranges are supplied by YouTube. Access does not establish reuse rights.",
        segments=[TranscriptSegment(id=f"{sid}_{i}",source_id=sid,text=text,start_ms=start,end_ms=end) for i,(text,start,end) in enumerate(passages)])
    require_youtube(source)
    return source


class CaptionSession(Session):
    def __init__(self,cancel):
        super().__init__();self.cancel=cancel;self.deadline=time.monotonic()+25;self.trust_env=False
    def request(self,method,url,**kwargs):
        check_cancel(self.cancel)
        remaining=self.deadline-time.monotonic()
        if remaining<=0:
            raise AppError("TRANSCRIPT_TIMEOUT", "Video transcript retrieval timed out. Retry to try other videos.",503)
        parsed=urlparse(url)
        if parsed.scheme!="https" or parsed.hostname not in {"www.youtube.com","youtube.com"}:
            raise AppError("TRANSCRIPT_ACCESS_REQUIRED", "The transcript provider requested an unsupported address. Check provider access, then retry.",503)
        kwargs["timeout"]=min(10,remaining)
        kwargs["allow_redirects"]=False
        response=super().request(method,url,**kwargs)
        check_cancel(self.cancel)
        if 300<=response.status_code<400:
            raise AppError("TRANSCRIPT_ACCESS_REQUIRED", "YouTube requires different transcript access. Check provider access, then retry.",503)
        return response


class YouTubeSources:
    def __init__(self,store,settings):
        self.store,self.settings=store,settings
    def search(self,query):
        if not self.settings.youtube_key:
            return search_youtube(query,"")
        key=hashlib.sha256(("youtube-search-v2:"+query.lower()).encode()).hexdigest()
        cached=self.store.cache_get(key,max_age=SOURCE_TTL)
        if cached is not None:
            return cached
        candidates=search_youtube(query,self.settings.youtube_key)
        self.store.cache_put(key,candidates)
        return candidates
    def transcript(self,candidate,cancel):
        check_cancel(cancel)
        vid=candidate["video_id"]
        video_id(f"https://www.youtube.com/watch?v={vid}")
        key=hashlib.sha256((f"youtube-caption-v1:{PROVIDER}:{vid}:en").encode()).hexdigest()
        cached=self.store.cache_get(key,max_age=SOURCE_TTL)
        if cached is not None:
            source=Source.model_validate(cached["source"])
            require_youtube(source)
            if source.video_id!=vid:
                raise AppError("YOUTUBE_SOURCE_REQUIRED","The cached video ID does not match. Retry to retrieve the source.",422)
            return source
        try:
            with CaptionSession(cancel) as session:
                fetched=YouTubeTranscriptApi(http_client=session).fetch(vid,languages=["en","en-US","en-GB"])
            source=source_from_transcript(candidate,fetched)
        except (TranscriptsDisabled,NoTranscriptFound,VideoUnavailable,VideoUnplayable,AgeRestricted):
            raise AppError("TRANSCRIPT_UNAVAILABLE","This video has no accessible English transcript.",422)
        except (RequestBlocked,IpBlocked,PoTokenRequired):
            raise AppError("TRANSCRIPT_ACCESS_REQUIRED","YouTube blocked public transcript access or requires a token. Check transcript provider access, then retry. No other source type was used.",503)
        except (ValueError,KeyError,TypeError):
            raise AppError("INVALID_YOUTUBE_TRANSCRIPT","The video transcript data is invalid. Another video will be tried.",422)
        except (CouldNotRetrieveTranscript,RequestException):
            raise AppError("TRANSCRIPT_UNAVAILABLE","The public transcript could not be read. Another video will be tried.",503)
        check_cancel(cancel)
        self.store.put_source(source)
        self.store.cache_put(key,{"source":source.model_dump(),"captions":fetched.to_raw_data()})
        return source
