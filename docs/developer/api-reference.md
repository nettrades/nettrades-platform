
# API Reference

This document provides comprehensive API reference for the NETTRADES.AI platform.

---

## LangGraph `/invoke` API

**Endpoint:** `POST /invoke`

**Authentication:** `X-API-Key` header (must match `LANGGRAPH_API_KEY`)

**Request Body:**

```json
{
  "input": {
    "messages": [
      {"role": "user", "content": "Find me a Python developer"}
    ],
    "image_base64": "data:image/png;base64,..."  // Optional, for vision agent
  },
  "config": {
    "configurable": {
      "thread_id": "unique-session-id"  // For checkpointing
    }
  }
}



## Authentication Endpoints

### Login

**Endpoint:** `POST /api/auth/login`

**Request Body:**
```json
{
    "username": "admin",
    "password": "your-password"
}
```

**Response:**

```json
{
    "success": true,
    "message": "Login successful",
    "session_id": "uuid-token",
    "user_id": 1,
    "username": "admin"
}
```

### Logout

**Endpoint:** POST /api/auth/logout

## Authentication Status

### Endpoint: GET /api/auth/status

## Operational Mode Endpoints

### Update Mode

**Endpoint:** POST /api/mode/update

**Request Body:**
```json

{
    "mode": "red"  // or "yellow" or "green"
}
```
**Response:**
```json

{
    "success": true,
    "message": "Mode updated to RED",
    "mode": "red"
}
```
Get Current Mode

**Endpoint:** GET /api/mode/status

**Response:**
```json

{
    "mode": "red",
    "description": "100% Sovereign AI - All inference runs on local GPUs.",
    "local_gpus": true,
    "marketplace": false,
    "external_apis": false,
    "external_providers": []
}
```
Get Available Modes

**Endpoint:** GET /api/mode/modes

**Response:** List of all three modes with descriptions and features.
text


