"""Local-first FastAPI app for PitchPulse AI."""
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import logging
import time
from urllib.parse import urlparse
import httpx
from fastapi import FastAPI, HTTPException, Request, Query, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .config import Settings
from .providers import SportsSources
from .brain import answer, detect_sport
from .speech import transcribe, STTFailure, MAX_AUDIO_BYTES

ROOT = Path(__file__).resolve().parent
settings = Settings()
requests_by_ip = defaultdict(deque)
logger = logging.getLogger("pitchpulse")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # HTTPS only, provider timeouts, redirects not followed.
    limits = httpx.Limits(max_connections=12, max_keepalive_connections=6)
    async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=5.0),
                                 limits=limits, headers={"User-Agent": "PitchPulseAI/1.0 (sports-feed-reader)"}) as client:
        app.state.sources = SportsSources(settings, client)
        app.state.http_client = client
        yield


app = FastAPI(title="PitchPulse AI", version="1.3.0", lifespan=lifespan,
              docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    # Rate limit browser-exposed chat to prevent accidental spend for local deployments.
    if request.url.path in ("/api/chat", "/api/transcribe"):
        ip = request.client.host if request.client else "unknown"
        recent = requests_by_ip[ip]
        now = time.monotonic()
        while recent and now - recent[0] > 60:
            recent.popleft()
        if len(recent) >= 12:
            return JSONResponse({"detail": "Too many requests. Try again in a minute."}, status_code=429)
        recent.append(now)
    if request.url.path == "/api/transcribe":
        try:
            if int(request.headers.get("content-length", "0")) > MAX_AUDIO_BYTES + 65536:
                return JSONResponse({"detail": "Recording exceeds 8 MB."}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "Invalid request size."}, status_code=400)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'none'; "
        "form-action 'self'; frame-ancestors 'none'"
    )
    return response


class ChatTurn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=700)


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=750)
    sport: str = Field(default="all", pattern="^(all|cricket|football)$")
    language: str = Field(default="en-IN", pattern="^(en-IN|hi-IN|en-US)$")
    history: list[ChatTurn] = Field(default_factory=list, max_length=6)


@app.get("/")
async def home():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/health")
async def health():
    return {"ok": True, "version": "1.3.0", "time_utc": datetime.now(timezone.utc).isoformat(),
            "llm_ready": settings.ai_ready,
            "llm_provider": settings.llm_provider if settings.ai_ready else "news_reader",
            "stt_ready": settings.stt_backend != "none",
            "stt_backend": settings.stt_backend,
            "cricket_ready": bool(settings.cricket_api_key),
            "football_ready": bool(settings.football_api_key),
            "cricket_cache_seconds": settings.cricket_cache_seconds}


@app.get("/api/news")
async def get_news(request: Request, sport: str = Query("all", pattern="^(all|cricket|football)$"),
                   q: str = Query("", max_length=90), limit: int = Query(16, ge=1, le=30)):
    try:
        return await request.app.state.sources.news(sport=sport, query=q, limit=limit)
    except Exception:
        raise HTTPException(503, "Sports news feeds temporarily unavailable")


@app.get("/api/matches")
async def get_matches(request: Request, sport: str = Query("cricket", pattern="^(cricket|football)$")):
    try:
        return (await request.app.state.sources.cricket() if sport == "cricket"
                else await request.app.state.sources.football())
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            raise HTTPException(502, "Sports API key invalid or your subscription lacks access")
        if exc.response.status_code == 429:
            raise HTTPException(503, "Sports provider quota reached; retry later")
        raise HTTPException(503, "Score provider unavailable")
    except Exception:
        raise HTTPException(503, "Score provider temporarily unavailable")


@app.post("/api/chat")
async def chat(payload: ChatRequest, request: Request):
    sport = detect_sport(payload.message, payload.sport)
    try:
        return await answer(payload.message.strip(), sport, payload.language,
                            [h.model_dump() for h in payload.history],
                            request.app.state.sources, settings, request.app.state.http_client)
    except Exception:
        # Log the real reason locally, but never leak API tokens, tracebacks or
        # arbitrary exception text to the browser.
        logger.exception("Unexpected failure in /api/chat")
        raise HTTPException(503, "Chat temporarily unavailable. See the server console for details.")


@app.post("/api/transcribe")
async def transcribe_recording(request: Request, audio: UploadFile = File(...),
                               language: str = Query("en-IN", pattern="^(en-IN|hi-IN|en-US)$")):
    if settings.stt_backend == "none":
        raise HTTPException(503, "Recording transcription is not configured. Add OPENAI_API_KEY or run setup_offline_voice.ps1.")
    mime = (audio.content_type or "").split(";", 1)[0].lower().strip()
    if mime not in {"audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav"}:
        raise HTTPException(415, "Unsupported audio format; try Chrome or Edge.")
    data = await audio.read(MAX_AUDIO_BYTES + 1)
    await audio.close()
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Recording exceeds 8 MB.")
    try:
        transcript = await transcribe(data, mime, language.split("-")[0], settings, request.app.state.http_client)
        return {"text": transcript, "provider": settings.stt_backend}
    except STTFailure as exc:
        raise HTTPException(503, str(exc))
