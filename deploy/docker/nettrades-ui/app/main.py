import os
import secrets
import httpx
from fastapi import FastAPI, Request, HTTPException, Depends, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.cors import CORSMiddleware
import json
from urllib.parse import urlencode

app = FastAPI(title="NETTRADES Simple UI")

# Configuration
DOMAIN = os.getenv("DOMAIN", "nettrades.ai")
ODOO_URL = os.getenv("ODOO_URL", "http://odoo:8069")
ODOO_PROXY_URL = os.getenv("ODOO_PROXY_URL", "http://odoo-proxy:8080")
LANGGRAPH_URL = os.getenv("LANGGRAPH_URL", "http://langgraph-server:8000")
LANGGRAPH_API_KEY = os.getenv("LANGGRAPH_API_KEY", "changeit")
ODOO_API_KEY = os.getenv("ODOO_API_KEY", "changeit")
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
SESSION_SECRET = os.getenv("SESSION_SECRET", secrets.token_urlsafe(32))

# Odoo OAuth 2.0 Configuration (from .env)
ODOO_OAUTH_CLIENT_ID = os.getenv("ODOO_OAUTH_CLIENT_ID", "")
ODOO_OAUTH_CLIENT_SECRET = os.getenv("ODOO_OAUTH_CLIENT_SECRET", "")
ODOO_OAUTH_AUTHORIZE_URL = os.getenv("ODOO_OAUTH_AUTHORIZE_URL", f"{ODOO_URL}/restapi/1.0/common/oauth2/authorize")
ODOO_OAUTH_TOKEN_URL = os.getenv("ODOO_OAUTH_TOKEN_URL", f"{ODOO_URL}/restapi/1.0/common/oauth2/access_token")
ODOO_OAUTH_USERINFO_URL = os.getenv("ODOO_OAUTH_USERINFO_URL", f"{ODOO_URL}/restapi/1.0/common/oauth2/userinfo")
ODOO_OAUTH_REDIRECT_URI = os.getenv("ODOO_OAUTH_REDIRECT_URI", f"https://{DOMAIN}/api/auth/callback/odoo")

# HTTP client for proxying requests
client = httpx.AsyncClient(timeout=60.0)

# Session middleware (required for OAuth session storage)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

# Templates
templates = Jinja2Templates(directory="templates")

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/css", StaticFiles(directory="static/css"), name="css")
app.mount("/js", StaticFiles(directory="static/js"), name="js")

# Root route – serves the chat UI
@app.get("/")
async def index():
    return FileResponse("static/index.html")

# CORS (if needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Authentication Helpers
# ============================================================================

async def get_current_user(request: Request):
    """Get the current user from session (OAuth) or API key (backend)."""
    if not AUTH_ENABLED:
        return {"id": 1, "name": "Anonymous", "email": "anonymous@nettrades.ai"}
    
    # Check for OAuth session
    user = request.session.get("user")
    if user:
        return user
    
    # Check for API key (backend-to-backend)
    api_key = request.headers.get("X-API-Key")
    if api_key and api_key == ODOO_API_KEY:
        return {"id": 1, "name": "API User", "email": "api@nettrades.ai"}
    
    raise HTTPException(status_code=401, detail="Not authenticated")

async def get_access_token(request: Request):
    """Get OAuth access token from session."""
    token = request.session.get("access_token")
    if not token and AUTH_ENABLED:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return token

# ============================================================================
# OAuth 2.0 Routes (Replicates NextAuth.js)
# ============================================================================

@app.get("/api/auth/login")
async def login(request: Request):
    """Start OAuth flow – redirect to Odoo authorization endpoint."""
    if not AUTH_ENABLED:
        return RedirectResponse(url="/")
    
    # Generate state and store in session
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    
    # Build OAuth authorization URL
    params = {
        "client_id": ODOO_OAUTH_CLIENT_ID,
        "redirect_uri": ODOO_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "state": state,
        "scope": "openid profile email"
    }
    auth_url = f"{ODOO_OAUTH_AUTHORIZE_URL}?{urlencode(params)}"
    return RedirectResponse(url=auth_url)

@app.get("/api/auth/callback/odoo")
async def oauth_callback(request: Request, code: str = None, state: str = None):
    """OAuth callback – exchange code for token."""
    if not AUTH_ENABLED:
        return RedirectResponse(url="/")
    
    # Verify state
    session_state = request.session.get("oauth_state")
    if not session_state or session_state != state:
        raise HTTPException(status_code=400, detail="Invalid state parameter")
    
    # Exchange code for access token
    token_data = {
        "client_id": ODOO_OAUTH_CLIENT_ID,
        "client_secret": ODOO_OAUTH_CLIENT_SECRET,
        "redirect_uri": ODOO_OAUTH_REDIRECT_URI,
        "code": code,
        "grant_type": "authorization_code"
    }
    
    try:
        resp = await client.post(ODOO_OAUTH_TOKEN_URL, data=token_data)
        token_response = resp.json()
        
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Token exchange failed")
        
        access_token = token_response.get("access_token")
        refresh_token = token_response.get("refresh_token")
        
        # Get user info
        user_resp = await client.get(
            ODOO_OAUTH_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        user_info = user_resp.json()
        
        # Store in session
        request.session["access_token"] = access_token
        request.session["refresh_token"] = refresh_token
        request.session["user"] = {
            "id": user_info.get("id"),
            "email": user_info.get("email"),
            "name": user_info.get("name", user_info.get("email")),
        }
        
        return RedirectResponse(url="/")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth error: {str(e)}")

@app.get("/api/auth/logout")
async def logout(request: Request):
    """Log out – clear session."""
    request.session.clear()
    return RedirectResponse(url="/")

@app.get("/api/auth/session")
async def get_session(request: Request, user: dict = Depends(get_current_user)):
    """Get current session info (replaces NextAuth.js session endpoint)."""
    return {
        "user": user,
        "authenticated": bool(request.session.get("access_token")),
        "auth_enabled": AUTH_ENABLED,
    }

# ============================================================================
# API Routes (Chat, GPU, etc.)
# ============================================================================

@app.post("/api/chat")
async def chat(request: Request, user: dict = Depends(get_current_user)):
    """Forward chat requests to LangGraph."""
    try:
        data = await request.json()
        
        # Extract message
        message = data.get("message", "")
        
        # Add user context if authenticated
        if user:
            data["user_id"] = user.get("id")
            data["user_email"] = user.get("email")
        
        # Forward to LangGraph
        resp = await client.post(
            f"{LANGGRAPH_URL}/invoke",
            json=data,
            headers={
                "Authorization": f"Bearer {LANGGRAPH_API_KEY}",
                "X-API-Key": ODOO_API_KEY,
            }
        )
        
        if resp.status_code != 200:
            return JSONResponse(
                status_code=resp.status_code,
                content={"error": f"LangGraph error: {resp.status_code}"}
            )
        
        return resp.json()
    
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Inference timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/gpu/status")
async def gpu_status(user: dict = Depends(get_current_user)):
    """Get GPU node status from Odoo via odoo-proxy."""
    try:
        resp = await client.get(
            f"{ODOO_PROXY_URL}/models/nettrades.gpu.node",
            headers={"X-API-Key": ODOO_API_KEY}
        )
        return resp.json()
    except Exception as e:
        return {"error": str(e), "nodes": []}

@app.get("/api/gpu/nodes")
async def gpu_nodes(user: dict = Depends(get_current_user)):
    """Get list of available GPU nodes."""
    try:
        resp = await client.post(
            f"{ODOO_PROXY_URL}/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "service": "object",
                    "method": "execute_kw",
                    "args": [
                        "odoo",
                        user.get("id", 2),
                        "",
                        "nettrades.gpu.node",
                        "search_read",
                        [[]],
                        ["id", "name", "gpu_model", "vram_gb", "status", "price_per_hour"]
                    ]
                }
            },
            headers={"X-API-Key": ODOO_API_KEY}
        )
        return resp.json()
    except Exception as e:
        return {"error": str(e), "result": []}

@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "simple-ui", "auth_enabled": AUTH_ENABLED}

# ============================================================================
# Frontend Routes
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main chat interface."""
    user = request.session.get("user")
    authenticated = bool(user) if AUTH_ENABLED else True
    
    # Render the HTML with auth state embedded
    with open("static/index.html", "r") as f:
        html = f.read()
    
    # Inject auth state into the HTML
    auth_state = {
        "authenticated": authenticated,
        "auth_enabled": AUTH_ENABLED,
        "user": user if authenticated else None,
    }
    
    # Replace the auth state placeholder
    html = html.replace(
        'window.__AUTH_STATE__ = null',
        f'window.__AUTH_STATE__ = {json.dumps(auth_state)}'
    )
    
    return HTMLResponse(content=html)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Serve the login page (only shown if AUTH_ENABLED)."""
    if not AUTH_ENABLED:
        return RedirectResponse(url="/")
    return templates.TemplateResponse("login.html", {"request": request})

# ============================================================================
# Catch-all for client-side routing
# ============================================================================

@app.get("/{path:path}")
async def catch_all(path: str):
    """Serve index.html for all routes (SPA)."""
    if path.startswith("_next") or path.startswith("favicon"):
        raise HTTPException(status_code=404)
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())
