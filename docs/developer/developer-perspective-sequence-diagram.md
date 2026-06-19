# DEVELOPER PERSPECTIVE — Sequence Diagram (Question Flow)

Purpose: Shows the chronological interaction between components when a user asks a question, including all API calls, agent processing, and persistence.
---

## DEVELOPER PERSPECTIVE — Sequence Diagram (Question Flow)

```mermaid

sequenceDiagram
    autonumber
    participant User as ?? User
    participant Traefik as ?? Traefik (Gateway)
    participant Odoo as ?? Odoo Web/API
    participant FastAPI as ? FastAPI (LangGraph)
    participant Supervisor as ?? Supervisor Graph
    participant SubAgent as ?? Sub-Agent
    participant GPUStack as ??? GPUStack
    participant PostgreSQL as ??? PostgreSQL
    participant Valkey as ?? Valkey
    participant Stripe as ?? Stripe (External)

    User->>Traefik: 1. POST /api/v1/chatbot/invoke (question)
    Traefik->>Traefik: 2. Validate JWT / Rate Limit
    Traefik->>Odoo: 3. Forward to Odoo JSON-RPC

    Odoo->>Odoo: 4. Authenticate User
    Odoo->>Valkey: 5. Check Session Cache
    Valkey-->>Odoo: 6. Session Valid

    Odoo->>Odoo: 7. Create/Update Conversation Record
    Odoo->>PostgreSQL: 8. Save Conversation State
    PostgreSQL-->>Odoo: 9. State Saved

    Odoo->>FastAPI: 10. POST /invoke (question + context)
    FastAPI->>FastAPI: 11. Load Checkpointer
    FastAPI->>PostgreSQL: 12. Load Previous State (if any)
    PostgreSQL-->>FastAPI: 13. Return State

    FastAPI->>Supervisor: 14. Execute Supervisor Graph
    Supervisor->>Supervisor: 15. classify() ? Intent Detection
    Supervisor->>Supervisor: 16. medical_screening() (if medical/legal)
    Supervisor->>Supervisor: 17. route() ? Dispatch to Sub-Agent

    alt Recruitment Intent
        Supervisor->>SubAgent: 18. Recruitment Agent
        SubAgent->>Odoo: 19. Fetch CVs & Job Postings
        Odoo->>PostgreSQL: 20. Query Data
        PostgreSQL-->>Odoo: 21. Return Data
        Odoo-->>SubAgent: 22. Return Data
        SubAgent->>GPUStack: 23. LLM Inference (Match Scoring)
        GPUStack-->>SubAgent: 24. Match Results
        SubAgent->>Odoo: 25. Save Match Results
        Odoo->>PostgreSQL: 26. Persist Results
    else Freelance Intent
        Supervisor->>SubAgent: 18. Freelance Agent
        SubAgent->>Odoo: 19. Fetch Projects & Freelancers
        Odoo->>PostgreSQL: 20. Query Data
        PostgreSQL-->>Odoo: 21. Return Data
        Odoo-->>SubAgent: 22. Return Data
        SubAgent->>GPUStack: 23. LLM Inference (Match Scoring)
        GPUStack-->>SubAgent: 24. Match Results
        SubAgent->>Odoo: 25. Save Match Results
        Odoo->>PostgreSQL: 26. Persist Results
    else Vision Intent (Image)
        Supervisor->>SubAgent: 18. Vision Agent
        SubAgent->>GPUStack: 19. VLM Inference (Image + Text)
        GPUStack-->>SubAgent: 20. Image Analysis
    else Action Intent (Robotic)
        Supervisor->>SubAgent: 18. Action Agent
        SubAgent->>GPUStack: 19. VLA Inference (Action Planning)
        GPUStack-->>SubAgent: 20. Action Plan (JSON)
        SubAgent->>SubAgent: 21. dispatch() ? ROS 2 / MCP
    else Ask Someone (Consultation)
        Supervisor->>SubAgent: 18. Ask Someone Agent
        SubAgent->>Odoo: 19. Check Expert Availability
        Odoo->>PostgreSQL: 20. Query Experts
        PostgreSQL-->>Odoo: 21. Return Experts
        Odoo-->>SubAgent: 22. Return Experts
        SubAgent->>Stripe: 23. Create Payment Intent (Escrow)
        Stripe-->>SubAgent: 24. Payment Intent Created
        SubAgent->>Odoo: 25. Create Consultation Record
        Odoo->>PostgreSQL: 26. Persist Consultation
    else General Intent
        Supervisor->>SubAgent: 18. General LLM
        SubAgent->>GPUStack: 19. LLM Inference
        GPUStack-->>SubAgent: 20. Response
    end

    SubAgent-->>Supervisor: 27. Return Result
    Supervisor-->>FastAPI: 28. Return Final State
    FastAPI->>PostgreSQL: 29. Save Checkpoint
    PostgreSQL-->>FastAPI: 30. Checkpoint Saved
    FastAPI-->>Odoo: 31. Return Response
    Odoo->>Odoo: 32. Update Conversation Record
    Odoo->>PostgreSQL: 33. Save Updated Conversation
    Odoo-->>Traefik: 34. Return Response
    Traefik-->>User: 35. Return Response (JSON)