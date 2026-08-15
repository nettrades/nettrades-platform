# API Usage Examples

This document provides practical, runnable examples for using the NETTRADES.AI APIs.

## Overview

The NETTRADES.AI platform exposes several APIs:

| API | Purpose | Protocol |
|-----|---------|----------|
| **LangGraph `/invoke`** | AI inference and agent orchestration | HTTP (REST) |
| **Odoo JSON-RPC** | Business data operations | HTTP (JSON-RPC) |
| **NVIDIA Dynamo API** | OpenAI-compatible inference | HTTP (REST) |
| **WebSocket Bus** | Real-time notifications | WebSocket |
| **GPU Node Registration** | GPU node onboarding | HTTP (REST) |

## 1. LangGraph `/invoke` API

### Endpoint

```text
POST /invoke

```


### Authentication

```text
X-API-Key: <LANGGRAPH_API_KEY>

```

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

### Example: Recruitment Query

```bash

curl -X POST http://localhost:8000/invoke \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-langgraph-api-key" \
  -d '{
    "input": {
        "messages": [
            {"role": "user", "content": "Find me a Python developer with 5+ years experience"}
        ]
    },
    "config": {
        "configurable": {
            "thread_id": "recruitment-123"
        }
    }
}'
```

### Example: Medical Screening

```bash

curl -X POST http://localhost:8000/invoke \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-langgraph-api-key" \
  -d '{
    "input": {
        "messages": [
            {"role": "user", "content": "I have a headache and fever"}
        ]
    },
    "config": {
        "configurable": {
            "thread_id": "medical-456"
        }
    }
}'

```

## 2. NVIDIA Dynamo API (OpenAI-Compatible)

### Endpoint

```text
http://dynamo:8000/v1/chat/completions
```

### Authentication

```text
Authorization: Bearer <DYNAMO_API_KEY>
```

### Example: Chat Completion

```bash

curl -X POST http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-dynamo-api-key" \
  -d '{
    "model": "deepseek-1.5b",
    "messages": [
        {"role": "user", "content": "Hello, how are you?"}
    ],
    "temperature": 0.7,
    "max_tokens": 1024
}'

```

## 3. Odoo JSON-RPC API


### Endpoint

```text

POST /api/v1/gpu/nodes
```

### Authentication

```text

X-API-Key: <ODOO_API_KEY>

```

### Example: List GPU Nodes

```bash

curl -X GET http://localhost:8090/api/v1/gpu/nodes \
  -H "X-API-Key: your-odoo-api-key"

```

### Example: Register GPU Node

```bash

curl -X POST http://localhost:8090/api/v1/gpu/register \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-odoo-api-key" \
  -d '{
    "name": "gpu-node-01",
    "gpu_model": "NVIDIA A100",
    "vram_gb": 80,
    "compute_capability": "8.0",
    "price_per_hour": 1.50
}'

```

## 4. Bridge Route API


### Endpoint

```text

POST /api/bridge/route/decide

```

### Authentication

```text

X-API-Key: <ODOO_API_KEY>

```

### Example: Get Route Decision

```bash

curl -X POST http://localhost:8090/api/bridge/route/decide \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-odoo-api-key" \
  -d '{
    "request_type": "inference",
    "request_data": {
        "priority": 100,
        "gpu_memory_required": 40
    }
}'

```

### Response

```json

{
    "target_url": "http://dynamo:8000/v1",
    "target_type": "dynamo",
    "api_key": "your-dynamo-api-key",
    "route_id": 42,
    "routing_mode": "local_only",
    "fallback_url": "http://llama-cpp:8080/v1"
}

```

## 5. mDNS Discovery API


### Endpoint

```text

GET /api/bridge/discovery/peers

```

### Example: Get Discovered Peers

```bash

curl -X GET http://localhost:8090/api/bridge/discovery/peers \
  -H "X-API-Key: your-odoo-api-key"

```

### Response

```json

{
    "peers": [
        {
            "name": "NETTRADES-abc123",
            "host": "192.168.1.100",
            "port": 3002,
            "last_seen": "2026-08-11T10:30:00",
            "capabilities": {
                "gpus": 2,
                "models": ["deepseek-1.5b", "qwen-1.5b"]
            }
        }
    ]
}

```

## 6. Training API

### Endpoint

```

POST /api/training/start

```

### Example: Start Training

```bash

curl -X POST http://localhost:8000/runs/stream \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-langgraph-api-key" \
  -d '{
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
}'

```


---

