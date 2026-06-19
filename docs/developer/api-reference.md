
---

## File 15: `docs/developer/api-reference.md`

```markdown
# API Reference

This document provides comprehensive API reference for the NETTRADES.AI platform.

---

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