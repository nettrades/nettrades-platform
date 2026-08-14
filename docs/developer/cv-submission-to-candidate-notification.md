# CV Submission to Candidate Notification

This document provides a comprehensive overview of the NETTRADES.AI platform architecture.

---

## CV Submission to Candidate Notification

```mermaid
sequenceDiagram
    participant User
    participant Forgejo as Forgejo Git
    participant LangGraph as LangGraph Agent
    participant Dynamo as Dynamo LLM
    participant Odoo as Odoo CRM/ERP
    participant PG as PostgreSQL + pgvector

    User->>LangGraph: Submits CV via web form
    LangGraph->>Dynamo: Sends CV + Job Desc for analysis
    Dynamo-->>LangGraph: Returns match score + reasoning
    LangGraph->>PG: Stores/Queries embeddings via pgvector
    LangGraph->>Odoo: Creates CRM lead for top matches
    Odoo-->>LangGraph: Confirms update
    LangGraph-->>User: Sends email/SMS notification