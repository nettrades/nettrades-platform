# =============================================================================
# FILE: deploy/docker/nettrades-ui/app/main.py
# =============================================================================
# PURPOSE:
#   NETTRADES-UI – FastAPI Chat Interface
#   Provides a clean, modern chat interface for interacting with LLMs.
#
#   Features:
#     - Chat with multiple models
#     - Model switching
#     - Conversation history
#     - GPU resource display
#     - Distributed inference support
# =============================================================================

import os
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
import httpx
import uuid

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

APP_NAME = "NETTRADES-UI"
VERSION = "1.0.0"

# Environment variables
DOMAIN = os.getenv("DOMAIN", "localhost")
ODOO_URL = os.getenv("ODOO_URL", "http://odoo:8069")
ODOO_PROXY_URL = os.getenv("ODOO_PROXY_URL", "http://odoo-proxy:8080")
LANGGRAPH_URL = os.getenv("LANGGRAPH_URL", "http://langgraph-server:8000")
LANGGRAPH_API_KEY = os.getenv("LANGGRAPH_API_KEY", "")
ODOO_API_KEY = os.getenv("ODOO_API_KEY", "")
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
SESSION_SECRET = os.getenv("SESSION_SECRET", "changeit")
UI_API_KEY = os.getenv("UI_API_KEY", "")

# Inference endpoints
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://dynamo:8000/v1")
DYNAMO_API_KEY = os.getenv("DYNAMO_API_KEY", "dummy")

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# FastAPI App
# -----------------------------------------------------------------------------

app = FastAPI(
    title=APP_NAME,
    version=VERSION,
    description="NETTRADES Sovereign AI Chat Interface",
)

# Static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str  # user, assistant, system
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None
    stream: Optional[bool] = False
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048

class ChatResponse(BaseModel):
    id: str
    model: str
    choices: List[Dict[str, Any]]
    usage: Optional[Dict[str, int]] = None
    created: int

class ModelInfo(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    capabilities: List[str] = []

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def get_http_client():
    """Get an HTTP client for making requests to the inference backend"""
    return httpx.Client(
        timeout=60.0,
        headers={
            "Authorization": f"Bearer {DYNAMO_API_KEY}",
            "Content-Type": "application/json",
        }
    )

async def get_langgraph_client():
    """Get an HTTP client for LangGraph"""
    return httpx.AsyncClient(
        timeout=120.0,
        headers={
            "Authorization": f"Bearer {LANGGRAPH_API_KEY}",
            "Content-Type": "application/json",
        }
    )

async def get_odoo_proxy_client():
    """Get an HTTP client for Odoo Proxy"""
    return httpx.AsyncClient(
        timeout=30.0,
        headers={
            "X-API-Key": ODOO_API_KEY,
            "Content-Type": "application/json",
        }
    )

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main chat interface"""
    try:
        template = templates.get_template("index.html")
        content = template.render(
            request=request,
            app_name=APP_NAME,
            version=VERSION,
            domain=DOMAIN,
            auth_enabled=AUTH_ENABLED,
        )
        return HTMLResponse(content=content)
    except Exception as e:
        logger.error(f"Template rendering error: {e}")
        # Fallback to a simple page
        html_content = """
        <html>
            <head><title>NETTRADES UI</title></head>
            <body>
                <h1>NETTRADES AI</h1>
                <p>UI is temporarily unavailable. Please check back later.</p>
                <p>Error: {}</p>
            </body>
        </html>
        """.format(str(e))
        return HTMLResponse(content=html_content)


# -----------------------------------------------------------------------------
# API Routes
# -----------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "service": APP_NAME, "version": VERSION}

@app.get("/api/models")
async def list_models():
    """
    List available models from the inference backend.
    This queries Dynamo or llama.cpp for available models.
    """
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
            else:
                # Fallback: return default models
                return [
                    ModelInfo(id="deepseek-1.5b", name="DeepSeek 1.5B", capabilities=["chat"]),
                    ModelInfo(id="qwen-1.5b", name="Qwen 1.5B", capabilities=["chat"]),
                    ModelInfo(id="llama-3.2", name="Llama 3.2", capabilities=["chat"]),
                ]
    except Exception as e:
        logger.error(f"Error listing models: {e}")
        # Return fallback models
        return [
            ModelInfo(id="deepseek-1.5b", name="DeepSeek 1.5B", capabilities=["chat"]),
            ModelInfo(id="qwen-1.5b", name="Qwen 1.5B", capabilities=["chat"]),
        ]

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """
    Send a chat request to the inference backend.
    Supports both streaming and non-streaming responses.
    """
    # Check if we should use LangGraph or direct inference
    use_langgraph = request.model and request.model.startswith("agent-")
    
    if use_langgraph:
        return await chat_with_langgraph(request)
    else:
        return await chat_with_dynamo(request)

async def chat_with_dynamo(request: ChatRequest):
    """Chat with Dynamo/vLLM directly"""
    # Prepare the request
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    
    payload = {
        "model": request.model or "deepseek-1.5b",
        "messages": messages,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "stream": request.stream,
    }

    if request.stream:
        # Streaming response
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
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
    else:
        # Non-streaming response
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{LLM_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {DYNAMO_API_KEY}"},
                json=payload,
                timeout=60.0,
            )
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Inference backend error: {response.text}"
                )

async def chat_with_langgraph(request: ChatRequest):
    """Chat with LangGraph agent"""
    # Extract the agent name from the model ID
    agent_name = request.model.replace("agent-", "") if request.model else "default"
    
    # Prepare the request for LangGraph
    payload = {
        "input": {
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "agent_name": agent_name,
        },
        "config": {
            "configurable": {
                "thread_id": str(uuid.uuid4()),
            }
        }
    }

    if request.stream:
        # Streaming response from LangGraph
        async def stream_generator():
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{LANGGRAPH_URL}/runs/stream",
                    headers={"Authorization": f"Bearer {LANGGRAPH_API_KEY}"},
                    json=payload,
                    timeout=120.0,
                ) as response:
                    async for chunk in response.aiter_bytes():
                        yield chunk
        
        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
    else:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{LANGGRAPH_URL}/runs/stream",
                headers={"Authorization": f"Bearer {LANGGRAPH_API_KEY}"},
                json=payload,
                timeout=60.0,
            )
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"LangGraph error: {response.text}"
                )

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
            else:
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
            else:
                return {"peers": []}
    except Exception as e:
        logger.error(f"Error fetching peers: {e}")
        return {"peers": []}

# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )