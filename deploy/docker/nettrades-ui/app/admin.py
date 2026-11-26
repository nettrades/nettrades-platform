# =============================================================================
# FILE: deploy/docker/nettrades-ui/app/admin.py
# =============================================================================
# PURPOSE:
#   Admin console router. Serves the multi-tab admin UI (Backup, Containers,
#   LangGraph Studio, Voice, Nodes, Cluster, Routing) and the JSON API behind it.
#
# AUTH:
#   Every route requires an authenticated session where user["is_admin"] is
#   True. A logged-in normal user gets 403; an anonymous user gets 401, which
#   main.py's exception handler turns into a redirect to /admin/login.
#
# VOICE:
#   The admin can configure the ASR service URL and model, test the connection,
#   and see which model is loaded. The chat UI uses the same service through
#   /api/voice/transcribe in main.py.
# =============================================================================
import os
import json
import asyncio
import logging
from fastapi import APIRouter, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List

import httpx

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")

ADMIN_WEB_ENABLED = os.getenv("ADMIN_WEB_ENABLED", "true").lower() == "true"
ENV_FILE = os.getenv("NETTRADES_ENV_FILE", "/app/deploy/docker/.env")
PROJECT_ROOT = os.getenv("PROJECT_ROOT", "/app")
COMPOSE_FILE = os.getenv("NETTRADES_COMPOSE_FILE", "/app/deploy/docker/docker-compose.yaml")

ODOO_URL = os.getenv("ODOO_URL", "http://odoo:8069")
ODOO_DB = os.getenv("ODOO_DB", "odoo")
ASR_SERVICE_URL = os.getenv("ASR_SERVICE_URL", "http://asr:9000")
LANGGRAPH_STUDIO_URL = os.getenv("LANGGRAPH_STUDIO_URL", "")
LANGGRAPH_URL = os.getenv("LANGGRAPH_URL", "http://langgraph-server:8000")
LANGGRAPH_API_KEY = os.getenv("LANGGRAPH_API_KEY", "")


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _safe_next(value: Optional[str]) -> str:
    """Reject absolute URLs to prevent open redirect."""
    if not value or not value.startswith("/") or value.startswith("//"):
        return "/admin"
    return value


def _oauth_enabled() -> bool:
    cid = os.getenv("ODOO_OAUTH_CLIENT_ID", "").strip()
    return bool(cid and cid != "changeit")

async def _odoo_authenticate(login: str, password: str) -> Optional[dict]:
    """
    Authenticate against Odoo via /web/session/authenticate.
    """
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {"db": ODOO_DB, "login": login, "password": password},
        "id": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(f"{ODOO_URL}/web/session/authenticate", json=payload)
        if r.status_code != 200:
            return None
        body = r.json()
        if body.get("error"):
            return None
        result = body.get("result") or {}
        uid = result.get("uid")
        if not uid:
            return None

        odoo_session_id = r.cookies.get("session_id")
        
        # 1. UID 1 is __system__, UID 2 is usually the root admin. 
        # Treat them as admins automatically.
        is_admin = (uid <= 2)
        
        # 2. If not the root admin, check the standard Odoo system group
        # and the specific NETTRADES admin group.
        if not is_admin:
            groups_payload = {
                "jsonrpc": "2.0", "method": "call",
                "params": {
                    "service": "object", "method": "execute_kw",
                    "args": [
                        ODOO_DB, uid, password,
                        "res.users", "has_group",
                        ["base.group_system"],  # Standard Odoo Admin
                    ],
                }, "id": 2,
            }
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    gr = await client.post(f"{ODOO_URL}/jsonrpc", json=groups_payload)
                if gr.status_code == 200:
                    is_admin = bool(gr.json().get("result"))
            except Exception:
                pass
            
            # Fallback: check the specific NETTRADES group
            if not is_admin:
                groups_payload["params"]["args"][4] = ["nettrades_gpu_admin.group_gpu_administrator"]
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        gr = await client.post(f"{ODOO_URL}/jsonrpc", json=groups_payload)
                    if gr.status_code == 200:
                        is_admin = bool(gr.json().get("result"))
                except Exception:
                    pass

        return {
            "uid": uid,
            "username": result.get("username") or login,
            "name": result.get("name") or login,
            "is_admin": is_admin,
            "odoo_session_id": odoo_session_id,
        }
    except Exception as e:
        logger.error(f"Odoo auth request failed: {type(e).__name__}: {e}")
        return None

def require_admin(request: Request):
    """
    Dependency: admin console requires an authenticated *admin* session.

    A logged-in normal user is rejected with 403. An anonymous user is
    rejected with 401, which main.py's exception handler turns into a
    redirect to /admin/login for browser requests.
    """
    if not ADMIN_WEB_ENABLED:
        raise HTTPException(status_code=404)
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return user

# -----------------------------------------------------------------------------
# Login / logout
# -----------------------------------------------------------------------------
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/admin"):
    if request.session.get("user"):
        # Already logged in � send admins to the console, everyone else home.
        user = request.session["user"]
        if user.get("is_admin"):
            return RedirectResponse(url=_safe_next(next), status_code=303)
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"next": _safe_next(next), "error": None, "oauth_enabled": _oauth_enabled()},
    )


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/admin"),
):
    safe_next = _safe_next(next)
    user = await _odoo_authenticate(username, password)
    if not user:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "next": safe_next,
                "error": "Invalid username or password.",
                "oauth_enabled": _oauth_enabled(),
            },
            status_code=401,
        )
    request.session["user"] = user
    logger.info(f"Login: {user['username']} (uid={user['uid']}, admin={user['is_admin']})")
    if user.get("is_admin"):
        return RedirectResponse(url=safe_next, status_code=303)
    return RedirectResponse(url="/", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/admin/login", status_code=303)


# -----------------------------------------------------------------------------
# Admin index
# -----------------------------------------------------------------------------
@router.get("", response_class=HTMLResponse)
async def admin_index(request: Request, user=Depends(require_admin)):
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "user": user,
            "asr_service_url": ASR_SERVICE_URL,
            "langgraph_studio_url": LANGGRAPH_STUDIO_URL,
        },
    )

# -----------------------------------------------------------------------------
# Container Management
# -----------------------------------------------------------------------------
@router.get("/api/containers")
async def list_containers(user=Depends(require_admin)):
    """Run `docker ps` and return the parsed list."""
    cmd = "docker ps -a --format '{{json .}}'"
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            return {"containers": [], "error": err.decode("utf-8", "replace")}
        lines = [ln for ln in out.decode("utf-8", "replace").splitlines() if ln.strip()]
        containers = []
        for ln in lines:
            try:
                c = json.loads(ln)
            except json.JSONDecodeError:
                continue
            
            # Docker names look like /docker-nettrades-ui-1
            name = c.get("Names", "").lstrip("/")
            # Extract service name (remove project prefix and replica suffix)
            parts = name.split("-")
            service = parts[-2] if len(parts) > 2 and parts[-1].isdigit() else name
            
            containers.append({
                "name": name,
                "service": service,
                "state": c.get("State") or "?",
                "status": c.get("Status") or "",
                "health": c.get("Health") or "",
            })
        return {"containers": containers, "error": None}
    except Exception as e:
        return {"containers": [], "error": f"{type(e).__name__}: {e}"}

@router.post("/api/containers/{action}/{service}")
async def container_action(action: str, service: str, user=Depends(require_admin)):
    """Start, stop, or restart a specific container."""
    if action not in ("start", "stop", "restart"):
        raise HTTPException(status_code=400, detail="Invalid action")
    
    try:
        # 1. Find the actual container name using the compose service label
        find_cmd = f"docker ps -a --filter 'label=com.docker.compose.service={service}' --format '{{{{.Names}}}}'"
        proc = await asyncio.create_subprocess_shell(
            find_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        container_name = out.decode("utf-8", "replace").strip()
        
        if not container_name:
            return {"success": False, "error": f"Container for service '{service}' not found."}
        
        # 2. Perform the action on that container
        cmd = f"docker {action} {container_name}"
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        
        if proc.returncode != 0:
            return {"success": False, "error": err.decode("utf-8", "replace")}
            
        return {"success": True, "output": out.decode("utf-8", "replace")}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

# -----------------------------------------------------------------------------
# Nodes / Cluster / Routing Proxy (to LangGraph)
# -----------------------------------------------------------------------------
@router.get("/api/nodes")
async def get_nodes(user=Depends(require_admin)):
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{LANGGRAPH_URL}/nodes", headers={"X-API-Key": LANGGRAPH_API_KEY})
            if r.status_code == 200:
                return r.json()
            return {"nodes": [], "error": f"LangGraph HTTP {r.status_code}"}
    except Exception as e:
        return {"nodes": [], "error": str(e)}


@router.get("/api/cluster")
async def get_cluster(user=Depends(require_admin)):
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{LANGGRAPH_URL}/cluster/1", headers={"X-API-Key": LANGGRAPH_API_KEY})
            if r.status_code == 200:
                return r.json()
            return {"error": f"LangGraph HTTP {r.status_code}"}
    except Exception as e:
        return {"error": str(e)}

@router.post("/api/cluster/relaunch")
async def relaunch_cluster(user=Depends(require_admin)):
    """Trigger a cluster relaunch via LangGraph."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{LANGGRAPH_URL}/rpc/relaunch", 
                headers={"X-API-Key": LANGGRAPH_API_KEY},
                json={"cluster_id": 1}
            )
            if r.status_code == 200:
                return r.json()
            return {"success": False, "error": f"LangGraph HTTP {r.status_code}: {r.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/api/routing")
async def get_routing(user=Depends(require_admin)):
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{LANGGRAPH_URL}/routing/events?limit=50", headers={"X-API-Key": LANGGRAPH_API_KEY})
            if r.status_code == 200:
                return r.json()
            return {"events": [], "error": f"LangGraph HTTP {r.status_code}"}
    except Exception as e:
        return {"events": [], "error": str(e)}


# -----------------------------------------------------------------------------
# Voice / ASR
# -----------------------------------------------------------------------------
class VoiceConfig(BaseModel):
    service_url: str
    model: str


@router.get("/api/voice/config")
async def get_voice_config(user=Depends(require_admin)):
    return {
        "service_url": os.getenv("ASR_SERVICE_URL", "http://asr:9000"),
        "model": os.getenv("ASR_MODEL", "audar-asr"),
    }


@router.post("/api/voice/config")
async def save_voice_config(cfg: VoiceConfig, user=Depends(require_admin)):
    # Persist to .env so the value survives container restarts.
    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r") as f:
            lines = f.readlines()
    found_url, found_model = False, False
    for i, line in enumerate(lines):
        if line.startswith("ASR_SERVICE_URL="):
            lines[i] = f"ASR_SERVICE_URL='{cfg.service_url}'\n"
            found_url = True
        if line.startswith("ASR_MODEL="):
            lines[i] = f"ASR_MODEL='{cfg.model}'\n"
            found_model = True
    if not found_url:
        lines.append(f"ASR_SERVICE_URL='{cfg.service_url}'\n")
    if not found_model:
        lines.append(f"ASR_MODEL='{cfg.model}'\n")
    with open(ENV_FILE, "w") as f:
        f.writelines(lines)
    return {"success": True}


@router.post("/api/voice/test")
async def test_voice(user=Depends(require_admin)):
    url = os.getenv("ASR_SERVICE_URL", "http://asr:9000")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{url}/health")
        if r.status_code == 200:
            return {"ok": True, "message": f"ASR service reachable: {r.text[:120]}"}
        return {"ok": False, "message": f"ASR HTTP {r.status_code}"}
    except Exception as e:
        return {"ok": False, "message": f"{type(e).__name__}: {e}"}


# -----------------------------------------------------------------------------
# Backup Config
# -----------------------------------------------------------------------------
class BackupConfig(BaseModel):
    repository: str
    schedule: str


@router.get("/api/backup/config")
async def get_backup_config(user=Depends(require_admin)):
    env = {"repository": "", "schedule": "0 2 * * *"}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r") as f:
            for line in f:
                if line.startswith("BACKUP_REPOSITORY="):
                    env["repository"] = line.split("=", 1)[1].strip().strip("'\"")
                if line.startswith("BACKUP_SCHEDULE="):
                    env["schedule"] = line.split("=", 1)[1].strip().strip("'\"")
    return env


@router.post("/api/backup/config")
async def save_backup_config(cfg: BackupConfig, user=Depends(require_admin)):
    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r") as f:
            lines = f.readlines()
    repo_found, sched_found = False, False
    for i, line in enumerate(lines):
        if line.startswith("BACKUP_REPOSITORY="):
            lines[i] = f"BACKUP_REPOSITORY='{cfg.repository}'\n"
            repo_found = True
        if line.startswith("BACKUP_SCHEDULE="):
            lines[i] = f"BACKUP_SCHEDULE='{cfg.schedule}'\n"
            sched_found = True
    if not repo_found:
        lines.append(f"BACKUP_REPOSITORY='{cfg.repository}'\n")
    if not sched_found:
        lines.append(f"BACKUP_SCHEDULE='{cfg.schedule}'\n")
    with open(ENV_FILE, "w") as f:
        f.writelines(lines)
    return {"success": True}


@router.post("/api/backup/test")
async def test_backup(user=Depends(require_admin)):
    return {"ok": True, "message": "Restic connection successful (simulated)"}


@router.get("/api/backups")
async def list_backups(user=Depends(require_admin)):
    backup_dir = "/app/backups"
    backups = []
    if os.path.exists(backup_dir):
        for f in os.listdir(backup_dir):
            if f.startswith("nettrades-backup-") and f.endswith(".tar.gz"):
                path = os.path.join(backup_dir, f)
                stat = os.stat(path)
                backups.append({
                    "name": f, "path": path,
                    "size": stat.st_size, "created": stat.st_mtime,
                })
    return sorted(backups, key=lambda x: x["created"], reverse=True)


@router.post("/api/backup/run")
async def run_backup(remote: bool = False, user=Depends(require_admin)):
    async def stream_logs():
        flag = "--remote" if remote else ""
        cmd = f"bash /app/scripts/backup.sh {flag} --auto"
        yield f"data: [INFO] Executing: {cmd}\n\n"
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except Exception as e:
            yield f"data: [ERROR] {type(e).__name__}: {e}\n\n"
            return
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            yield f"data: {line.decode('utf-8', errors='replace').strip()}\n\n"
        await proc.wait()
        yield f"data: [DONE] exit={proc.returncode}\n\n"
    return StreamingResponse(stream_logs(), media_type="text/event-stream")


class RestoreRequest(BaseModel):
    backup_path: str

# -----------------------------------------------------------------------------
# Backup / restore execution (SSE)
# -----------------------------------------------------------------------------
@router.post("/api/restore")
async def run_restore(req: RestoreRequest, user=Depends(require_admin)):
    async def stream_logs():
        cmd = f"bash /app/scripts/restore.sh {req.backup_path} --auto"
        yield f"data: [INFO] Executing: {cmd}\n\n"
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except Exception as e:
            yield f"data: [ERROR] {type(e).__name__}: {e}\n\n"
            return
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            yield f"data: {line.decode('utf-8', errors='replace').strip()}\n\n"
        await proc.wait()
        yield f"data: [DONE] exit={proc.returncode}\n\n"
    return StreamingResponse(stream_logs(), media_type="text/event-stream")