# Database Schema (Key Tables)

This document provides a comprehensive overview of the NETTRADES.AI platform architecture.

---

## Database Schema (Key Tables)

```mermaid
erDiagram
    res_partner ||--o{ user_field_reputation : "has reputation in"
    res_partner ||--o{ expert_session : "can be requester or expert"
    res_partner ||--o{ good_answer_vote : "casts vote"
    res_partner ||--o{ gpu_node : "owns"
    
    nettrades_field ||--o{ user_field_reputation : "is tracked for"
    nettrades_field ||--o{ good_answer_vote : "is voted on"
    nettrades_field ||--o{ qualified_professional : "has experts"
    nettrades_field ||--o{ ft_dataset : "has fine-tuning dataset"
    
    expert_session ||--|| escrow_hold : "has"
    expert_session ||--o{ expert_agreement : "requires"
    
    good_answer_vote ||--o| llm_feedback : "generates"
    
    gpu_cluster ||--o{ gpu_node : "contains"
    gpu_cluster ||--o{ gpu_cluster_subnet : "has"
    gpu_cluster ||--o{ gpu_sharing_schedule : "defines"
    
    gpu_node ||--o{ ai_gpu_api_key : "uses"
    
    ft_dataset ||--o{ ft_training_job : "is used in"