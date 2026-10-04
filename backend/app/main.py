import asyncio
import json
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from .config import Settings
from .contracts import LearningRequest, Lesson, Source, SourceList, ExplanationRequest, ProviderHealth, SearchResponse
from .errors import AppError
from .jobs import Jobs, cache_key
from .providers import Ollama, Speech, health
from .store import Store


def create_app(settings=None, model=None, speech=None, youtube=None):
    config = settings or Settings()
    store = Store(config.data)
    llm, tts = model or Ollama(config), speech or Speech(config)
    jobs = Jobs(store, llm, tts, config, youtube)
    @asynccontextmanager
    async def lifespan(app):
        jobs.start()
        yield
        await jobs.stop()
        store.close()
    app = FastAPI(title="Focus Play local API", version="0.1.0", lifespan=lifespan)
    app.state.store, app.state.jobs = store, jobs
    app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"], allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Last-Event-ID"])

    @app.middleware("http")
    async def local_only(request, call_next):
        # A hostile web page cannot write to the local service through a simple form or fetch.
        if request.headers.get("host", "").split(":")[0] not in {"localhost", "127.0.0.1", "testserver"}:
            return JSONResponse({"code": "INVALID_HOST", "message": "Use the local application address."}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin not in {"http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8000", "http://localhost:8000"}:
            return JSONResponse({"code": "INVALID_ORIGIN", "message": "Use the local application page."}, status_code=403)
        if request.method == "POST" and "application/json" not in request.headers.get("content-type", ""):
            return JSONResponse({"code": "JSON_REQUIRED", "message": "Send this request as JSON."}, status_code=415)
        if request.headers.get("content-length", "0").isdigit() and int(request.headers.get("content-length", 0)) > 1_000_000:
            return JSONResponse({"code": "IMPORT_TOO_LARGE", "message": "Use a smaller transcript."}, status_code=413)
        return await call_next(request)

    @app.exception_handler(AppError)
    async def app_error(request, error):
        return JSONResponse({"code": error.code, "message": error.message}, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def bad_request(request, error):
        return JSONResponse({"code": "INVALID_REQUEST", "message": "Check the input fields, file size, and time budget."}, status_code=422)

    @app.get("/api/health", response_model=ProviderHealth)
    async def readiness():
        status=await asyncio.to_thread(health,llm,tts)
        missing=[name for name,value in (("YOUTUBE_API_KEY",config.youtube_key),("SUPADATA_API_KEY",config.supadata_key)) if not value]
        status.youtube_ready=not missing
        status.youtube_message="YouTube search and Supadata transcripts are configured. English captions are checked during lesson preparation." if status.youtube_ready else f"Add {' and '.join(missing)} to the server .env file and restart the server."
        status.ready=status.ready and status.youtube_ready
        status.message+=" "+status.youtube_message
        return status

    @app.get("/api/sources", response_model=SourceList)
    def sources():
        return SourceList(sources=store.sources())

    @app.get("/api/sources/search", response_model=SearchResponse)
    async def search(q: str = Query(min_length=3, max_length=200)):
        key = cache_key({"youtube": q.strip().lower()})
        cached = store.cache_get(key, max_age=86400)
        if cached is not None:
            return {"results": cached, "cached": True, "acquisition": "assisted"}
        result = await asyncio.to_thread(jobs.youtube.search,q)
        store.cache_put(key, result)
        return {"results": result, "cached": False, "acquisition": "assisted"}

    @app.get("/api/lessons", response_model=list[Lesson])
    def lessons():
        return store.history()

    @app.post("/api/lessons", response_model=Lesson, status_code=202)
    async def create(body: LearningRequest):
        return jobs.create(body)

    @app.get("/api/lessons/{lid}", response_model=Lesson)
    def snapshot(lid: str):
        return store.lesson(lid)

    @app.post("/api/lessons/{lid}/cancel", response_model=Lesson)
    async def cancel(lid: str):
        return jobs.cancel(lid)

    @app.post("/api/lessons/{lid}/retry", response_model=Lesson, status_code=202)
    async def retry(lid: str):
        return jobs.retry(lid)

    @app.post("/api/lessons/{lid}/shorts/{sid}/explanations", response_model=Lesson, status_code=202)
    async def explanation(lid: str, sid: str, body: ExplanationRequest):
        return jobs.explain(lid, sid, body)

    @app.get("/api/lessons/{lid}/events")
    async def events(lid: str, request: Request, after: int = 0):
        lesson = store.lesson(lid)
        try:
            cursor = max(0, int(request.headers.get("last-event-id", str(after))))
        except ValueError:
            raise AppError("INVALID_EVENT_ID", "The event ID is invalid. Reload the lesson.")
        async def stream():
            nonlocal cursor
            yield f"event: snapshot\ndata: {lesson.model_dump_json()}\n\n"
            while not await request.is_disconnected():
                rows = store.events(lid, cursor)
                for seq, body in rows:
                    cursor = seq
                    yield f"id: {seq}\nevent: progress\ndata: {json.dumps(body)}\n\n"
                current = store.lesson(lid)
                if current.job.status in {"complete", "failed", "cancelled", "interrupted"} and cursor >= current.job.event_sequence:
                    yield f"event: done\ndata: {current.model_dump_json()}\n\n"
                    return
                yield ": keepalive\n\n"
                await asyncio.sleep(0.5)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/audio/{name}")
    def audio(name: str):
        if not re.fullmatch(r"[a-f0-9]{64}\.wav", name):
            raise AppError("AUDIO_NOT_FOUND", "The audio file is missing. Retry the lesson.", 404)
        path = config.data / "audio" / name
        if not path.is_file() or path.is_symlink():
            raise AppError("AUDIO_NOT_FOUND", "The audio file is missing. Retry the lesson.", 404)
        return FileResponse(path, media_type="audio/wav", headers={"Cache-Control": "private, max-age=31536000, immutable"})

    return app

app = create_app()
