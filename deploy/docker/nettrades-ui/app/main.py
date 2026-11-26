# =============================================================================
# FILE: deploy/docker/nettrades-ui/app/main.py
# =============================================================================
#
# Copyright (c) 2026 NETTRADES FOUNDATION. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-NETTRADES-Commercial
# =============================================================================
# PURPOSE:
#   NETTRADES-UI – FastAPI chat interface.
#
# FEATURES:
#   - Streaming chat with llama.cpp / Dynamo (OpenAI-compatible)
#   - Agent routing through LangGraph /runs
#   - Multimodal image attachments (base64 data URLs, llama.cpp libmtmd)
#   - Client-side PDF text extraction + server-side fallback
#   - Voice-to-text via a local ASR microservice (FunASR SenseVoice)
#   - Per-user thread namespacing so checkpoints are isolated
#   - Light / dark theme (client-side, persisted)
#   - Admin console mounted at /admin (login-gated)
# =============================================================================

import os
import json
import logging
import tempfile
import uuid
from typing import Optional, List, Dict, Any, Union
from datetime import datetime

import httpx
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import (
    HTMLResponse, JSONResponse, StreamingResponse, RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn
from starlette.middleware.sessions import SessionMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

# -----------------------------------------------------------------------------
# Configuration (must be defined BEFORE app / middleware / routers)
#
# ORDER MATTERS: these variables must be defined BEFORE app = FastAPI(...),
# because the SessionMiddleware below reads SESSION_SECRET, and the admin
# router needs the app object. 
# -----------------------------------------------------------------------------
APP_NAME = "NETTRADES-UI"
VERSION = "1.1.0"

DOMAIN = os.getenv("DOMAIN", "localhost")
ODOO_URL = os.getenv("ODOO_URL", "http://odoo:8069")
ODOO_PROXY_URL = os.getenv("ODOO_PROXY_URL", "http://odoo-proxy:8080")
LANGGRAPH_URL = os.getenv("LANGGRAPH_URL", "http://langgraph-server:8000")
LANGGRAPH_API_KEY = os.getenv("LANGGRAPH_API_KEY", "")
ODOO_API_KEY = os.getenv("ODOO_API_KEY", "")
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
SESSION_SECRET = os.getenv("SESSION_SECRET", "changeit")
UI_API_KEY = os.getenv("UI_API_KEY", "")

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://llama-cpp:8080/v1")
DYNAMO_API_KEY = os.getenv("DYNAMO_API_KEY", "dummy")
DEFAULT_MODEL = os.getenv("MODEL_NAME", "deepseek-7b")

ASR_SERVICE_URL = os.getenv("ASR_SERVICE_URL", "http://asr:9000")
ASR_MODEL = os.getenv("ASR_MODEL", "sensevoice-q8")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# FastAPI app
# -----------------------------------------------------------------------------
app = FastAPI(
    title=APP_NAME,
    version=VERSION,
    description="NETTRADES Sovereign AI Chat Interface",
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# -----------------------------------------------------------------------------
# Exception handler: redirect browser 401s to the login page
# -----------------------------------------------------------------------------
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """
    A browser navigating to a page that raises 401 should be redirected to
    the login form. A fetch() or curl call should still get JSON.
    """
    accept = request.headers.get("accept", "")
    wants_html = "text/html" in accept
    if exc.status_code == 401 and wants_html:
        next_url = request.url.path
        if request.url.query:
            next_url += "?" + request.url.query
        return RedirectResponse(url=f"/admin/login?next={next_url}", status_code=303)
    from fastapi.exception_handlers import http_exception_handler as default_handler
    return await default_handler(request, exc)

# -----------------------------------------------------------------------------
# Middleware (AFTER app is created)
# -----------------------------------------------------------------------------
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="nettrades_admin_session",
    max_age=60 * 60 * 8,
    same_site="strict",
    https_only=DOMAIN.startswith("https"),
)

# -----------------------------------------------------------------------------
# Routers
# -----------------------------------------------------------------------------
from app.admin import router as admin_router
app.include_router(admin_router)

# -----------------------------------------------------------------------------
# Startup: warm up inference
# -----------------------------------------------------------------------------
@app.on_event("startup")
async def warm_up_llama_cpp():
    """
    Send one tiny request to the inference backend at startup so the model
    is already in memory when the user's first chat arrives.
    """
    import asyncio
    await asyncio.sleep(5)
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            r = await client.post(
                f"{LLM_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {DYNAMO_API_KEY}"},
                json={
                    "model": f"/models/{DEFAULT_MODEL}.gguf"
                             if not DEFAULT_MODEL.endswith(".gguf")
                             else f"/models/{DEFAULT_MODEL}",
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 1,
                },
            )
            logger.info(f"llama.cpp warm-up: HTTP {r.status_code}")
    except Exception as e:
        logger.warning(f"llama.cpp warm-up failed: {type(e).__name__}: {e}")

# -----------------------------------------------------------------------------
# Pydantic models
# -----------------------------------------------------------------------------
class ChatContentPart(BaseModel):
    type: str  # "text" | "image_url"
    text: Optional[str] = None
    image_url: Optional[Dict[str, str]] = None

class ChatMessage(BaseModel):
    role: str
    # Content is either a plain string (text-only) or a list of OpenAI-style
    # multimodal parts. llama.cpp accepts both shapes on /v1/chat/completions.
    content: Union[str, List[ChatContentPart]]

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None
    thread_id: Optional[str] = None
    stream: Optional[bool] = False
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048
    system_prompt: Optional[str] = None 

class ModelInfo(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    capabilities: List[str] = []

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _get_user(request: Request) -> Optional[dict]:
    return request.session.get("user")

def _thread_id_for(request: Request, client_thread_id: Optional[str]) -> str:
    """
    Namespace the thread ID per user.

    This is what makes per-user checkpoint isolation real: two users can both
    use thread_id "conv-1" and their LangGraph state will be stored under
    "u5:conv-1" and "u6:conv-1" respectively. Anonymous users get a
    session-scoped namespace so their history does not collide with anyone
    else's in the same browser profile.
    """
    user = _get_user(request)
    if user:
        prefix = f"u{user['uid']}"
    else:
        anon = request.session.get("anon_id")
        if not anon:
            anon = str(uuid.uuid4())
            request.session["anon_id"] = anon
        prefix = f"anon{anon}"
    cid = client_thread_id or str(uuid.uuid4())
    return f"{prefix}:{cid}"

def _auth_headers_for_asr() -> Dict[str, str]:
    headers = {"Accept": "application/json"}
    if UI_API_KEY:
        headers["X-API-Key"] = UI_API_KEY
    return headers

def _content_to_openai(content: Union[str, List[ChatContentPart]]) -> Any:
    """Normalise the incoming content to the OpenAI wire format."""
    if isinstance(content, str):
        return content
    out = []
    for part in content:
        if part.type == "text" and part.text is not None:
            out.append({"type": "text", "text": part.text})
        elif part.type == "image_url" and part.image_url:
            out.append({"type": "image_url", "image_url": part.image_url})
    return out

# -----------------------------------------------------------------------------
# Page routes
# -----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the chat interface with auth + admin context."""
    try:
        user = _get_user(request)
        is_authenticated = bool(user)
        is_admin = bool(user and user.get("is_admin"))
        template = templates.get_template("index.html")
        content = template.render(
            request=request,
            app_name=APP_NAME,
            version=VERSION,
            domain=DOMAIN,
            auth_enabled=AUTH_ENABLED,
            user=user,
            is_authenticated=is_authenticated,
            is_admin=is_admin,
            asr_enabled=bool(ASR_SERVICE_URL),
        )
        return HTMLResponse(content=content)
    except Exception as e:
        logger.error(f"Template rendering error: {e}")
        return HTMLResponse(content=f"<html><body><h1>UI Error</h1><p>{e}</p></body></html>")

# -----------------------------------------------------------------------------
# Auth identity
# -----------------------------------------------------------------------------
@app.get("/api/auth/me")
async def whoami(request: Request):
    user = _get_user(request)
    if not user:
        return {"authenticated": False, "user": None}
    return {
        "authenticated": True,
        "user": {
            "uid": user.get("uid"),
            "username": user.get("username"),
            "name": user.get("name"),
            "is_admin": bool(user.get("is_admin")),
        },
    }

# -----------------------------------------------------------------------------
# Health & models
# -----------------------------------------------------------------------------
@app.get("/api/health")
async def health():
    return {"status": "ok", "service": APP_NAME, "version": VERSION}

@app.get("/api/models")
async def list_models():
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{LLM_BASE_URL}/models",
                headers={"Authorization": f"Bearer {DYNAMO_API_KEY}"},
                timeout=10.0,
            )
            if response.status_code == 200:
                data = response.json()
                models = []
                for model in data.get("data", []):
                    models.append(ModelInfo(
                        id=model.get("id", "unknown"),
                        name=model.get("id", "unknown"),
                        description=f"Available on {LLM_BASE_URL}",
                        capabilities=["chat", "completion"],
                    ))
                return models
            return [
                ModelInfo(id=DEFAULT_MODEL,
                          name=DEFAULT_MODEL.replace("-", " ").title(),
                          capabilities=["chat"]),
            ]
    except Exception as e:
        logger.warning(f"Model list fetch failed: {type(e).__name__}: {e}")
        return [
            ModelInfo(id=DEFAULT_MODEL,
                      name=DEFAULT_MODEL.replace("-", " ").title(),
                      capabilities=["chat"]),
        ]

# -----------------------------------------------------------------------------
# Chat
# -----------------------------------------------------------------------------
@app.post("/api/chat")
async def chat(request: ChatRequest, http_request: Request):
    use_langgraph = bool(request.model and request.model.startswith("agent-"))
    if use_langgraph:
        return await chat_with_langgraph(request, http_request)
    return await chat_with_dynamo(request, http_request)

async def chat_with_dynamo(request: ChatRequest, http_request: Request):
    messages = []
    # Inject system prompt if provided
    if request.system_prompt:
        messages.append({"role": "system", "content": request.system_prompt})
        
    for m in request.messages:
        messages.append({
            "role": m.role,
            "content": _content_to_openai(m.content),
        })

    payload = {
        "model": request.model or DEFAULT_MODEL,
        "messages": messages,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "stream": request.stream,
    }
    
    # Request token usage for streaming
    if request.stream:
        payload["stream_options"] = {"include_usage": True}

    if request.stream:
        async def stream_generator():
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{LLM_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {DYNAMO_API_KEY}"},
                    json=payload,
                    timeout=120.0,
                ) as response:
                    async for chunk in response.aiter_bytes():
                        yield chunk
        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
    else:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{LLM_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {DYNAMO_API_KEY}"},
                json=payload,
                timeout=60.0,
            )
            if response.status_code == 200:
                return response.json()
            raise HTTPException(status_code=response.status_code, detail=f"Inference backend error: {response.text}")

async def chat_with_langgraph(request: ChatRequest, http_request: Request):
    agent_name = request.model.replace("agent-", "") if request.model else "default"
    thread_id = _thread_id_for(http_request, request.thread_id)

    # Inject system prompt if provided
    lc_messages = []
    if request.system_prompt:
        lc_messages.append({"role": "system", "content": request.system_prompt})
        
    for m in request.messages:
        lc_messages.append({
            "role": m.role,
            "content": m.content if isinstance(m.content, str) else " ".join(p.text or "" for p in m.content if p.type == "text")
        })

    payload = {
        "messages": lc_messages,
        "agent_name": agent_name,
        "thread_id": thread_id,
    }

    if request.stream:
        async def stream_generator():
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{LANGGRAPH_URL}/runs",
                        headers={
                            "Authorization": f"Bearer {LANGGRAPH_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                        timeout=600.0,
                    )
                if response.status_code != 200:
                    err_body = response.text[:200]
                    err_chunk = {
                        "choices": [{"delta": {"content": f"[LangGraph HTTP {response.status_code}: {err_body}]"}}]
                    }
                    yield f"data: {json.dumps(err_chunk)}\n\n"
                    yield "data: [DONE]\n\n"
                    return
                data = response.json()
                reply = ""
                msgs = data.get("messages") or []
                if isinstance(msgs, list) and msgs and msgs[0].get("content"):
                    reply = msgs[0]["content"]
                elif data.get("analysis"):
                    reply = data["analysis"]
                elif data.get("response"):
                    reply = data["response"]
                else:
                    reply = "(no response)"
                chunk = {"choices": [{"delta": {"content": reply}}]}
                yield f"data: {json.dumps(chunk)}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                import traceback
                logger.error(f"LangGraph streaming failed: {type(e).__name__}: {e!r}")
                logger.error(traceback.format_exc())
                err_chunk = {"choices": [{"delta": {"content": f"[LangGraph error: {type(e).__name__}: {e or '(no message)'}]"}}]}
                yield f"data: {json.dumps(err_chunk)}\n\n"
                yield "data: [DONE]\n\n"
        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{LANGGRAPH_URL}/runs",
                headers={
                    "Authorization": f"Bearer {LANGGRAPH_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=600.0,
            )
            if response.status_code == 200:
                return response.json()
            raise HTTPException(
                status_code=response.status_code,
                detail=f"LangGraph error: {response.text}",
            )

# -----------------------------------------------------------------------------
# Attachments
# -----------------------------------------------------------------------------
@app.post("/api/attachments/extract")
async def extract_attachment(file: UploadFile = File(...)):
    """
    Extract plain text from a PDF or text file.

    Images are handled client-side (read as DataURL and sent inline).
    PDFs are sent here so the browser does not need pdf.js.
    """
    suffix = os.path.splitext(file.filename or "")[1].lower()
    data = await file.read()

    if suffix in (".txt", ".md", ".csv", ".json", ".log", ".py", ".js",
                  ".ts", ".html", ".css", ".yaml", ".yml", ".xml"):
        try:
            return {"text": data.decode("utf-8", "replace"), "filename": file.filename}
        except Exception as e:
            return {"text": "", "filename": file.filename, "error": str(e)}

    if suffix == ".pdf":
        try:
            import pdfplumber
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(data)
                tmp_path = tmp.name
            text_parts = []
            with pdfplumber.open(tmp_path) as pdf:
                for page in pdf.pages:
                    text_parts.append(page.extract_text() or "")
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return {"text": "\n\n".join(text_parts), "filename": file.filename}
        except Exception as e:
            logger.warning(f"PDF extraction failed: {e}")
            return {"text": "", "filename": file.filename,
                    "error": f"PDF extraction failed: {e}"}

    return {"text": "", "filename": file.filename,
            "error": f"Unsupported file type: {suffix}"}

# -----------------------------------------------------------------------------
# Voice transcription
# -----------------------------------------------------------------------------
@app.post("/api/voice/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Proxy an audio blob to the local ASR microservice.

    The ASR service (FunASR SenseVoice by default) accepts a multipart
    upload and returns {"text": "..."}.
    """
    if not ASR_SERVICE_URL:
        raise HTTPException(status_code=503, detail="ASR service not configured")
    data = await file.read()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                f"{ASR_SERVICE_URL}/transcribe",
                files={"file": (file.filename or "audio.webm", data,
                                file.content_type or "audio/webm")},
                headers=_auth_headers_for_asr(),
            )
        if r.status_code != 200:
            raise HTTPException(status_code=502,
                                detail=f"ASR service error: {r.text[:200]}")
        body = r.json()
        return {"text": body.get("text", "")}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ASR request failed: {e}")

# -----------------------------------------------------------------------------
# GPU / discovery (unchanged behaviour)
# -----------------------------------------------------------------------------
@app.get("/api/gpu/status")
async def get_gpu_status():
    """
    Get GPU status from the GPU admin module.
    This queries Odoo for GPU node status.
    """
    try:
        async with httpx.AsyncClient() as client:
            # Query Odoo via the proxy
            response = await client.get(
                f"{ODOO_PROXY_URL}/api/gpu/nodes",
                headers={"X-API-Key": ODOO_API_KEY},
                timeout=10.0,
            )
            if response.status_code == 200:
                return response.json()
            return {"error": "Failed to fetch GPU status"}
    except Exception as e:
        logger.error(f"Error fetching GPU status: {e}")
        return {"error": str(e)}

@app.get("/api/discovery/peers")
async def get_discovered_peers():
    """
    Get discovered peers from the bridge discovery service.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{ODOO_PROXY_URL}/api/bridge/discovery/peers",
                headers={"X-API-Key": ODOO_API_KEY},
                timeout=10.0,
            )
            if response.status_code == 200:
                return response.json()
            return {"peers": []}
    except Exception as e:
        logger.error(f"Error fetching peers: {e}")
        return {"peers": []}

# =============================================================================
# Entry point
# =============================================================================
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )