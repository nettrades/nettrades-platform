# "Ask Someone" Architecture

The architecture uses Odoo’s bus module for real?time notifications and Valkey for session state storage. All matching and field inference is performed server?side, with the LangGraph agent optionally called for LLM?based classification.

---

## "Ask Someone" Architecture

```mermaid
graph LR
    subgraph Frontend
        Button[Ask Someone Button] --> Chat[Live Session UI]
    end

    Button --> API[API Endpoints]

    API --> FieldInf[Field Inference LLM]
    FieldInf --> LLM[LangGraph / NVIDIA Dynamo]

    FieldInf --> Matching[Matching Algorithm]

    Matching --> Escrow[Escrow Stripe]
    Escrow --> Stripe[Stripe API]

    API --> WebSocket[WebSocket]
    WebSocket --> Chat
    WebSocket --> Valkey[(Valkey/Redis)]