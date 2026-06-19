
---

## File: `docs/appendix/database-schema.md` (With Schema Diagram)

```markdown
# Database Schema

This document provides the consolidated database schema for the NETTRADES.AI platform.

---

## Schema Diagram

```mermaid
erDiagram
    res_partner ||--o{ good_answer_vote : "casts vote"
    res_partner ||--o{ good_answer_vote : "receives (answerer_id)"
    nettrades_field ||--o{ good_answer_vote : "is voted on"
    good_answer_vote ||--o| llm_feedback : "generates"

    res_partner ||--o{ user_field_reputation : "has reputation in"
    nettrades_field ||--o{ user_field_reputation : "tracks reputation"

    nettrades_field ||--o{ ft_dataset : "has dataset"
    ft_dataset ||--o{ ft_training_job : "is used in"

    res_partner ||--o{ qualified_professional : "is qualified in"
    nettrades_field ||--o{ qualified_professional : "has experts"

    res_partner ||--o{ expert_session : "requests (requester_id)"
    res_partner ||--o{ expert_session : "provides (expert_id)"
    nettrades_field ||--o{ expert_session : "categorises (field_id)"
    expert_session ||--|| escrow_hold : "has"

    gpu_cluster ||--o{ gpu_node : contains
    gpu_cluster ||--o{ gpu_cluster_subnet : registers
    gpu_cluster ||--o{ gpu_sharing_schedule : "sharing schedule"
    res_company ||--o{ gpu_cluster : owns