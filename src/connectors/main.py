#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES.AI - Odoo JSON-RPC Proxy (Updated)
# =============================================================================
# FILE: src/core/odoo_proxy/main.py
# PURPOSE: This FastAPI service provides a secure HTTP API that proxies calls
#          to the configured enterprise backend (Odoo, Salesforce, SAP, etc.)
#          via the Universal Enterprise Proxy Framework.
#
# UPDATES (2026-08):
#   - Integrated with Universal Enterprise Proxy Framework
#   - Supports multiple backends (Odoo, Salesforce, SAP, Oracle)
#   - Backend can be switched via environment variable
#   - All API endpoints are backend-agnostic
# =============================================================================

import json
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

import httpx
from fastapi import FastAPI, Request, Response, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Import authentication and mode modules
from auth import router as auth_router, init_auth
from mode import router as mode_router, init_mode

# Import universal proxy framework
from connectors import ConnectorRegistry, OdooConnector, SalesforceConnector, SAPConnector

# =============================================================================
# LOGGING SETUP
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Backend selection - which enterprise system to use
BACKEND = os.getenv("ENTERPRISE_BACKEND", "odoo").lower()

# Odoo Configuration
ODOO_URL = os.getenv("ODOO_URL", "http://odoo:8069")
ODOO_DB = os.getenv("ODOO_DB", "odoo")
ODOO_USER = int(os.getenv("ODOO_USER", "1"))
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD", "admin")
ODOO_API_KEY = os.getenv("ODOO_API_KEY")
PROXY_API_KEY = os.getenv("PROXY_API_KEY")

# Salesforce Configuration (optional)
SF_INSTANCE_URL = os.getenv("SF_INSTANCE_URL")
SF_CLIENT_ID = os.getenv("SF_CLIENT_ID")
SF_CLIENT_SECRET = os.getenv("SF_CLIENT_SECRET")
SF_USERNAME = os.getenv("SF_USERNAME")
SF_PASSWORD = os.getenv("SF_PASSWORD")

# =============================================================================
# STARTUP VALIDATION
# =============================================================================

if not PROXY_API_KEY:
    logger.critical("PROXY_API_KEY environment variable is not set")
    sys.exit(1)

WEAK_KEYS = ["change_me_in_production", "changeit", "password", "admin", "test"]
if PROXY_API_KEY in WEAK_KEYS:
    logger.critical(f"PROXY_API_KEY is set to a known weak value: {PROXY_API_KEY}")
    sys.exit(1)

logger.info(f"✅ Credentials validated at startup")
logger.info(f"✅ Backend selected: {BACKEND}")

# =============================================================================
# REGISTER CONNECTORS
# =============================================================================

ProxyRegistry.register('odoo', OdooConnector)
ProxyRegistry.register('salesforce', SalesforceConnector)
ProxyRegistry.register('sap', SAPConnector)

logger.info(f"Registered connectors: {ProxyRegistry.list_connectors()}")

# =============================================================================
# CONNECTOR CONFIGURATION
# =============================================================================

BACKEND_CONFIG = {
    'odoo': {
        'base_url': ODOO_URL,
        'db': ODOO_DB,
        'username': 'admin',
        'password': ODOO_PASSWORD,
    },
    'salesforce': {
        'instance_url': SF_INSTANCE_URL,
        'client_id': SF_CLIENT_ID,
        'client_secret': SF_CLIENT_SECRET,
        'username': SF_USERNAME,
        'password': SF_PASSWORD,
    },
    'sap': {
        'base_url': os.getenv("SAP_BASE_URL"),
        'client': os.getenv("SAP_CLIENT", "100"),
        'username': os.getenv("SAP_USERNAME"),
        'password': os.getenv("SAP_PASSWORD"),
    },
}

def get_connector():
    """
    Dependency that returns the configured enterprise connector.
    
    The connector is cached and reused for the lifetime of the application.
    """
    try:
        return ProxyRegistry.get_connector(BACKEND, BACKEND_CONFIG.get(BACKEND, {}))
    except ValueError as e:
        logger.error(f"Failed to get connector: {e}")
        raise HTTPException(status_code=503, detail=f"Backend '{BACKEND}' not available")

# =============================================================================
# FASTAPI APPLICATION
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - initialize modules on startup."""
    # Initialize auth module
    init_auth(ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD)
    logger.info("Authentication module initialized")
    
    # Initialize mode module
    valkey_host = os.getenv("VALKEY_HOST", "valkey")
    valkey_port = int(os.getenv("VALKEY_PORT", "6379"))
    init_mode(ODOO_URL, ODOO_API_KEY, valkey_host, valkey_port)
    logger.info("Mode module initialized")
    
    # Test the backend connection
    try:
        connector = get_connector()
        health = connector.health()
        logger.info(f"Backend health check: {health}")
    except Exception as e:
        logger.warning(f"Backend health check failed: {e}")
    
    yield
    
    # Cleanup on shutdown
    logger.info("Shutting down...")

app = FastAPI(
    title="NETTRADES Universal Enterprise Proxy",
    description="Secure API gateway for enterprise backends (Odoo, Salesforce, SAP, Oracle)",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(mode_router)

# =============================================================================
# MODEL WHITELIST (security)
# =============================================================================

ALLOWED_MODELS = {
    "res.partner", "sale.order", "project.project", "hr.employee",
    "nettrades.field", "data.episode", "gpu.node", "gpu.cluster",
    "nettrades.gpu.node", "nettrades.job", "nettrades.model",
    "nettrades.user", "nettrades.company", "nettrades.notification",
    "AI_Job__c", "GPU_Node__c", "AI_Model__c",  # Salesforce objects
}

def is_model_allowed(model: str) -> bool:
    """Check if a model is allowed for access."""
    # Allow any model starting with 'nettrades_' or 'AI_' or ending with '__c'
    if model.startswith('nettrades_'):
        return True
    if model.startswith('AI_'):
        return True
    if model.endswith('__c'):
        return True
    return model in ALLOWED_MODELS

# =============================================================================
# RATE LIMITING
# =============================================================================

from collections import defaultdict
failed_attempts = defaultdict(list)
MAX_ATTEMPTS = 5
WINDOW_MINUTES = 15

async def authenticate(request: Request) -> bool:
    """Validate the API key from request headers with rate limiting."""
    client_ip = request.client.host
    api_key = request.headers.get("X-API-Key")
    auth_header = request.headers.get("Authorization")
    
    # Rate limiting check
    now = datetime.now()
    attempts = failed_attempts[client_ip]
    attempts = [t for t in attempts if (now - t).total_seconds() < WINDOW_MINUTES * 60]
    failed_attempts[client_ip] = attempts
    
    if len(attempts) >= MAX_ATTEMPTS:
        logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        raise HTTPException(status_code=429, detail="Too many failed attempts")
    
    # Check API key
    if api_key:
        if api_key == PROXY_API_KEY:
            return True
        failed_attempts[client_ip].append(now)
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Check Bearer token
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if token == PROXY_API_KEY:
            return True
        failed_attempts[client_ip].append(now)
        raise HTTPException(status_code=401, detail="Invalid token")
    
    failed_attempts[client_ip].append(now)
    raise HTTPException(status_code=401, detail="Missing API key")

# =============================================================================
# HEALTH ENDPOINT
# =============================================================================

@app.get("/api/v1/health")
async def health(connector=Depends(get_connector)):
    """Health check endpoint."""
    result = connector.health()
    return {"status": "ok", "backend": BACKEND, "details": result}

# =============================================================================
# AUTHENTICATION ENDPOINTS
# =============================================================================

@app.post("/api/v1/auth/login")
async def login(username: str, password: str, connector=Depends(get_connector)):
    """Authenticate a user against the enterprise backend."""
    try:
        result = connector.authenticate(username, password)
        if result.get('success'):
            return {"status": "success", "data": result}
        else:
            raise HTTPException(status_code=401, detail=result.get('error', 'Authentication failed'))
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/auth/validate")
async def validate_session(token: str, connector=Depends(get_connector)):
    """Validate an existing session."""
    try:
        result = connector.validate_session(token)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

@app.post("/api/v1/auth/logout")
async def logout(token: str, connector=Depends(get_connector)):
    """Logout and invalidate session."""
    try:
        result = connector.logout(token)
        return {"status": "success", "data": {"logged_out": result}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# CRUD ENDPOINTS
# =============================================================================

@app.get("/api/v1/db/{model}")
async def search_records(
    model: str,
    domain: Optional[str] = None,
    fields: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    order: Optional[str] = None,
    authenticated: bool = Depends(authenticate),
    connector=Depends(get_connector),
):
    """Search for records in any model."""
    if not is_model_allowed(model):
        raise HTTPException(status_code=403, detail=f"Model '{model}' not allowed")
    
    try:
        domain_list = json.loads(domain) if domain else []
        field_list = fields.split(',') if fields else None
        result = connector.search(model, domain_list, field_list, limit, offset, order)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/db/{model}")
async def create_record(
    model: str,
    data: Dict[str, Any],
    authenticated: bool = Depends(authenticate),
    connector=Depends(get_connector),
):
    """Create a new record."""
    if not is_model_allowed(model):
        raise HTTPException(status_code=403, detail=f"Model '{model}' not allowed")
    
    try:
        result = connector.create(model, data)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Create error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/db/{model}/{record_id}")
async def read_record(
    model: str,
    record_id: str,
    fields: Optional[str] = None,
    authenticated: bool = Depends(authenticate),
    connector=Depends(get_connector),
):
    """Read a single record."""
    if not is_model_allowed(model):
        raise HTTPException(status_code=403, detail=f"Model '{model}' not allowed")
    
    try:
        field_list = fields.split(',') if fields else None
        result = connector.read(model, record_id, field_list)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Read error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/v1/db/{model}/{record_id}")
async def update_record(
    model: str,
    record_id: str,
    data: Dict[str, Any],
    authenticated: bool = Depends(authenticate),
    connector=Depends(get_connector),
):
    """Update a record."""
    if not is_model_allowed(model):
        raise HTTPException(status_code=403, detail=f"Model '{model}' not allowed")
    
    try:
        result = connector.update(model, record_id, data)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/v1/db/{model}/{record_id}")
async def delete_record(
    model: str,
    record_id: str,
    authenticated: bool = Depends(authenticate),
    connector=Depends(get_connector),
):
    """Delete a record."""
    if not is_model_allowed(model):
        raise HTTPException(status_code=403, detail=f"Model '{model}' not allowed")
    
    try:
        result = connector.delete(model, record_id)
        return {"status": "success", "data": {"deleted": result}}
    except Exception as e:
        logger.error(f"Delete error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# AI-SPECIFIC ENDPOINTS
# =============================================================================

@app.post("/api/v1/jobs")
async def create_job(
    job_data: Dict[str, Any],
    authenticated: bool = Depends(authenticate),
    connector=Depends(get_connector),
):
    """Create a new inference/training job."""
    try:
        result = connector.create_job(job_data)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Create job error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/jobs/{job_id}")
async def get_job(
    job_id: str,
    authenticated: bool = Depends(authenticate),
    connector=Depends(get_connector),
):
    """Get job details."""
    try:
        result = connector.get_job(job_id)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Get job error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/v1/jobs/{job_id}")
async def update_job_status(
    job_id: str,
    status: str,
    result_data: Optional[Dict] = None,
    authenticated: bool = Depends(authenticate),
    connector=Depends(get_connector),
):
    """Update job status."""
    try:
        result = connector.update_job_status(job_id, status, result_data)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Update job error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/jobs")
async def list_jobs(
    filters: Optional[str] = None,
    authenticated: bool = Depends(authenticate),
    connector=Depends(get_connector),
):
    """List jobs."""
    try:
        filter_dict = json.loads(filters) if filters else None
        result = connector.list_jobs(filter_dict)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"List jobs error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# GPU NODE ENDPOINTS
# =============================================================================

@app.get("/api/v1/gpu/nodes")
async def get_gpu_nodes(
    filters: Optional[str] = None,
    authenticated: bool = Depends(authenticate),
    connector=Depends(get_connector),
):
    """Get GPU nodes."""
    try:
        filter_dict = json.loads(filters) if filters else None
        result = connector.get_gpu_nodes(filter_dict)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Get GPU nodes error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/gpu/nodes")
async def register_gpu_node(
    node_data: Dict[str, Any],
    authenticated: bool = Depends(authenticate),
    connector=Depends(get_connector),
):
    """Register a GPU node."""
    try:
        result = connector.register_gpu_node(node_data)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Register GPU node error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/v1/gpu/nodes/{node_id}")
async def update_gpu_node(
    node_id: str,
    data: Dict[str, Any],
    authenticated: bool = Depends(authenticate),
    connector=Depends(get_connector),
):
    """Update a GPU node."""
    try:
        result = connector.update_gpu_node(node_id, data)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Update GPU node error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/gpu/nodes/{node_id}/heartbeat")
async def gpu_heartbeat(
    node_id: str,
    status: Dict[str, Any],
    authenticated: bool = Depends(authenticate),
    connector=Depends(get_connector),
):
    """Send a GPU node heartbeat."""
    try:
        result = connector.heartbeat(node_id, status)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Heartbeat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# MODEL ENDPOINTS
# =============================================================================

@app.get("/api/v1/models")
async def list_models(
    filters: Optional[str] = None,
    authenticated: bool = Depends(authenticate),
    connector=Depends(get_connector),
):
    """List AI models."""
    try:
        filter_dict = json.loads(filters) if filters else None
        result = connector.list_models(filter_dict)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"List models error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/models/download")
async def download_model(
    model_name: str,
    model_type: str,
    authenticated: bool = Depends(authenticate),
    connector=Depends(get_connector),
):
    """Download an AI model."""
    try:
        result = connector.download_model(model_name, model_type)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Download model error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/v1/models/{model_id}")
async def delete_model(
    model_id: str,
    authenticated: bool = Depends(authenticate),
    connector=Depends(get_connector),
):
    """Delete an AI model."""
    try:
        result = connector.delete_model(model_id)
        return {"status": "success", "data": {"deleted": result}}
    except Exception as e:
        logger.error(f"Delete model error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# USER ENDPOINTS
# =============================================================================

@app.get("/api/v1/users")
async def list_users(
    company_id: Optional[str] = None,
    authenticated: bool = Depends(authenticate),
    connector=Depends(get_connector),
):
    """List users."""
    try:
        result = connector.list_users(company_id)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"List users error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/users/me")
async def get_current_user(
    authenticated: bool = Depends(authenticate),
    connector=Depends(get_connector),
):
    """Get the current authenticated user."""
    try:
        result = connector.get_current_user()
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Get current user error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/users/{user_id}")
async def get_user(
    user_id: str,
    authenticated: bool = Depends(authenticate),
    connector=Depends(get_connector),
):
    """Get a user by ID."""
    try:
        result = connector.get_user(user_id)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Get user error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# COMPANY ENDPOINTS
# =============================================================================

@app.get("/api/v1/companies/{company_id}")
async def get_company(
    company_id: str,
    authenticated: bool = Depends(authenticate),
    connector=Depends(get_connector),
):
    """Get company details."""
    try:
        result = connector.get_company(company_id)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Get company error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# TRANSACTION ENDPOINTS (Optional)
# =============================================================================

@app.post("/api/v1/transactions/begin")
async def begin_transaction(
    authenticated: bool = Depends(authenticate),
    connector=Depends(get_connector),
):
    """Begin a transaction."""
    try:
        transaction_id = connector.begin_transaction()
        return {"status": "success", "data": {"transaction_id": transaction_id}}
    except Exception as e:
        logger.error(f"Begin transaction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/transactions/{transaction_id}/commit")
async def commit_transaction(
    transaction_id: str,
    authenticated: bool = Depends(authenticate),
    connector=Depends(get_connector),
):
    """Commit a transaction."""
    try:
        result = connector.commit_transaction(transaction_id)
        return {"status": "success", "data": {"committed": result}}
    except Exception as e:
        logger.error(f"Commit transaction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/transactions/{transaction_id}/rollback")
async def rollback_transaction(
    transaction_id: str,
    authenticated: bool = Depends(authenticate),
    connector=Depends(get_connector),
):
    """Rollback a transaction."""
    try:
        result = connector.rollback_transaction(transaction_id)
        return {"status": "success", "data": {"rolled_back": result}}
    except Exception as e:
        logger.error(f"Rollback transaction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)