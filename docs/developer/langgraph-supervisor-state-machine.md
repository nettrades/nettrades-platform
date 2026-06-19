# LangGraph Supervisor State Machine (Detailed)
This document provides a comprehensive overview of the NETTRADES.AI platform architecture.

---

## LangGraph Supervisor State Machine (Detailed)

```mermaid
stateDiagram-v2
    [*] --> classify
    classify --> medical_screening: intent=medical/legal
    classify --> route: else
    
    state medical_screening {
        [*] --> CheckSufficiency
        CheckSufficiency --> AskFollowUp: insufficient context
        AskFollowUp --> CheckSufficiency
        CheckSufficiency --> ScreeningDone: sufficient
    }
    
    medical_screening --> route: screening_done
    route --> recruitment_agent: recruit
    route --> freelance_agent: freelance
    route --> lead_gen_agent: lead
    route --> gpu_management_agent: gpu
    route --> vision_agent: vision
    route --> action_agent: action
    route --> general_inference: general