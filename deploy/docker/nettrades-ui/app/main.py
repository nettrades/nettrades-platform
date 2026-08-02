import os
import secrets
import json
import httpx
from urllib.parse import urlencode
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.cors import CORSMiddleware

app = FastAPI(title="NETTRADES API")

# Configuration
DOMAIN = os.getenv("DOMAIN", "nettrades.ai")
ODOO_URL = os.getenv("ODOO_URL", "http://odoo:8069")
ODOO_PROXY_URL = os.getenv("ODOO_PROXY_URL", "http://odoo-proxy:8080")
LANGGRAPH_URL = os.getenv("LANGGRAPH_URL", "http://langgraph-server:8000")
LANGGRAPH_API_KEY = os.getenv("LANGGRAPH_API_KEY", "changeit")
ODOO_API_KEY = os.getenv("ODOO_API_KEY", "changeit")
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
SESSION_SECRET = os.getenv("SESSION_SECRET", secrets.token_urlsafe(32))

# Odoo OAuth 2.0
ODOO_OAUTH_CLIENT_ID = os.getenv("ODOO_OAUTH_CLIENT_ID", "")
ODOO_OAUTH_CLIENT_SECRET = os.getenv("ODOO_OAUTH_CLIENT_SECRET", "")
ODOO_OAUTH_AUTHORIZE_URL = os.getenv("ODOO_OAUTH_AUTHORIZE_URL", f"{ODOO_URL}/restapi/1.0/common/oauth2/authorize")
ODOO_OAUTH_TOKEN_URL = os.getenv("ODOO_OAUTH_TOKEN_URL", f"{ODOO_URL}/restapi/1.0/common/oauth2/access_token")
ODOO_OAUTH_USERINFO_URL = os.getenv("ODOO_OAUTH_USERINFO_URL", f"{ODOO_URL}/restapi/1.0/common/oauth2/userinfo")
ODOO_OAUTH_REDIRECT_URI = os.getenv("ODOO_OAUTH_REDIRECT_URI", f"https://{DOMAIN}/api/auth/callback/odoo")

client = httpx.AsyncClient(timeout=60.0)

# Session middleware
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

# Templates (only for login page)
templates = Jinja2Templates(directory="templates")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# ROOT ROUTE – serves the static UI
# ============================================================================
@app.get("/")
async def index():
    return FileResponse("static/index.html")

# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================
@app.get("/api/auth/login")
async def login(request: Request):
    if not AUTH_ENABLED:
        return RedirectResponse(url="/")
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
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
    if not AUTH_ENABLED:
        return RedirectResponse(url="/")
    session_state = request.session.get("oauth_state")
    if not session_state or session_state != state:
        raise HTTPException(status_code=400, detail="Invalid state parameter")
    token_data = {
        "client_id": ODOO_OAUTH_CLIENT_ID,
        "client_secret": ODOO_OAUTH_CLIENT_SECRET,
        "redirect_uri": ODOO_OAUTH_REDIRECT_URI,
        "code": code,
        "grant_type": "authorization_code"
    }
    resp = await client.post(ODOO_OAUTH_TOKEN_URL, data=token_data)
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Token exchange failed")
    token_response = resp.json()
    access_token = token_response.get("access_token")
    refresh_token = token_response.get("refresh_token")
    user_resp = await client.get(
        ODOO_OAUTH_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"}
    )
    user_info = user_resp.json()
    request.session["access_token"] = access_token
    request.session["refresh_token"] = refresh_token
    request.session["user"] = {
        "id": user_info.get("id"),
        "email": user_info.get("email"),
        "name": user_info.get("name", user_info.get("email")),
    }
    return RedirectResponse(url="/")

@app.get("/api/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")

@app.get("/api/auth/session")
async def get_session(request: Request):
    user = request.session.get("user")
    authenticated = bool(user) if AUTH_ENABLED else False
    return {
        "user": user,
        "authenticated": authenticated,
        "auth_enabled": AUTH_ENABLED,
    }

# ============================================================================
# CHAT API
# ============================================================================
@app.post("/api/chat")
async def chat(request: Request):
    try:
        data = await request.json()
        message = data.get("message", "")
        resp = await client.post(
            f"{LANGGRAPH_URL}/invoke",
            json={"message": message},
            headers={"Authorization": f"Bearer {LANGGRAPH_API_KEY}"}
        )
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/gpu/status")
async def gpu_status():
    try:
        resp = await client.get(
            f"{ODOO_PROXY_URL}/models/nettrades.gpu.node",
            headers={"X-API-Key": ODOO_API_KEY}
        )
        return resp.json()
    except Exception as e:
        return {"error": str(e), "nodes": []}

# ============================================================================
# HEALTH CHECK
# ============================================================================
@app.get("/health")
async def health():
    return {"status": "ok", "service": "nettrades-api"}

# ============================================================================
# LOGIN PAGE (served as template)
# ============================================================================
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if not AUTH_ENABLED:
        return RedirectResponse(url="/")
    return templates.TemplateResponse("login.html", {"request": request})