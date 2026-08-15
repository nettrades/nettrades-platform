
# API Reference

This document provides comprehensive API reference for the NETTRADES.AI platform.

## LangGraph `/invoke` API

**Endpoint:** `POST /invoke`

**Authentication:** `X-API-Key` header (must match `LANGGRAPH_API_KEY`)

### Request Body

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
```

### Response

```json

{
    "output": {
        "messages": [
            {"role": "assistant", "content": "I found 5 candidates..."}
        ],
        "intent": "recruitment",
        "route_source": "local"
    },
    "thread_id": "unique-session-id"
}
```

### Error Response

```json

{
    "error": "Authentication failed",
    "detail": "Invalid API key"
}

```


## Odoo JSON-RPC API


### GPU Management

| Endpoint | Method | Description |
|--------|-------------|-----------|
| `/api/v1/gpu/nodes` | GET | List all GPU nodes |
| `/api/v1/gpu/register` | POST | Register a new GPU node |
| `/api/v1/gpu/bookings` | GET | List GPU bookings |
| `/api/v1/gpu/book` | POST | Book a GPU |


### Bridge Routing


| Endpoint | Method | Description |
|--------|-------------|-----------|
| `/api/bridge/route/decide` | POST | Get a route decision |
| `/api/bridge/config` | GET | Get effective configuration |
| `/api/bridge/usage` | GET | Get usage logs |
| `/api/bridge/discovery/peers` | GET | Get discovered peers |
| `/api/bridge/discovery/status` | GET | Get discovery service status |

## NVIDIA Dynamo API


NVIDIA Dynamo provides an OpenAI-compatible API.


### Chat Completions


**Endpoint:** `POST /v1/chat/completions`

**Authentication:** `Authorization: Bearer <DYNAMO_API_KEY>`


```json

{
    "model": "deepseek-1.5b",
    "messages": [
        {"role": "user", "content": "Hello"}
    ],
    "temperature": 0.7,
    "max_tokens": 1024,
    "stream": false
}
```

### List Models

**Endpoint:** `GET /v1/models`

**Authentication:** `Authorization: Bearer <DYNAMO_API_KEY>`


## Training API

### Start Training

**Endpoint:** `POST /runs/stream`

**Authentication:** `X-API-Key` header (must match `LANGGRAPH_API_KEY`)

```json

{
    "input": {
        "dataset": "good-answers",
        "model": "deepseek-1.5b",
        "method": "unsloth",
        "params": {
            "epochs": 3,
            "learning_rate": 2e-4
        },
        "action": "start_training"
    },
    "config": {
        "configurable": {
            "thread_id": "training-789"
        }
    }
}

```


### Training Status

**Endpoint:** `GET /training/status`

**Authentication:** `X-API-Key` header (must match `LANGGRAPH_API_KEY`)


## Ask Someone API

### Submit Question

**Endpoint:** `POST /runs/stream`

**Authentication:** `X-API-Key` header (must match `LANGGRAPH_API_KEY`)

```json

{
    "input": {
        "question": "How do I deploy a LangGraph agent?",
        "category": "technical",
        "urgency": "medium",
        "action": "ask_someone"
    },
    "config": {
        "configurable": {
            "thread_id": "ask-123"
        }
    }
}

```


## Good Answer API


### Submit Good Answer Vote


**Endpoint:** `POST /runs/stream`

**Authentication:** `X-API-Key` header (must match `LANGGRAPH_API_KEY`)

```json

{
    "input": {
        "question": "How do I deploy a LangGraph agent?",
        "answer": "Use the LangGraph CLI...",
        "rating": 5,
        "action": "good_answer"
    },
    "config": {
        "configurable": {
            "thread_id": "vote-456"
        }
    }
}

```

## Error Codes


| Code	| Description |
|--------|-------------|
| 200	| 	Success |
| 400	| 	Bad Request – Invalid input |
| 401	| 	Unauthorised – Invalid API key |
| 403	| 	Forbidden – Insufficient permissions |
| 404	| 	Not Found – Resource does not exist |
| 429	| 	Too Many Requests – Rate limit exceeded |
| 500	| 	Internal Server Error |
| 503	| 	Service Unavailable – Backend unavailable |