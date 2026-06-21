
# Job Matching & Freelancing

This guide covers how companies and freelancers use NETTRADES.AI to find and match talent.

---

## Overview

NETTRADES.AI combines the functionalities of **LinkedIn**, **Fiverr**, **Upwork**, and **Freelancer**, with AI-powered matching.

| Role | What You Can Do |
|------|-----------------|
| **Company** | Post jobs, find candidates, manage hiring pipelines |
| **Freelancer** | Find projects, submit proposals, manage milestones |
| **Job Seeker** | Find jobs, apply with one click, track applications |

---

## User Journey: CV Submission to Candidate Notification

This diagram shows the complete flow from a candidate submitting a CV to the employer receiving a notification.

```mermaid
sequenceDiagram
    participant User
    participant Forgejo as Forgejo Git
    participant LangGraph as LangGraph Agent
    participant GPUStack as GPUStack LLM
    participant Odoo as Odoo CRM/ERP
    participant PG as PostgreSQL + pgvector

    User->>LangGraph: Submits CV via web form
    LangGraph->>GPUStack: Sends CV + Job Desc for analysis
    GPUStack-->>LangGraph: Returns match score + reasoning
    LangGraph->>PG: Stores/Queries embeddings via pgvector
    LangGraph->>Odoo: Creates CRM lead for top matches
    Odoo-->>LangGraph: Confirms update
    LangGraph-->>User: Sends email/SMS notification
```
