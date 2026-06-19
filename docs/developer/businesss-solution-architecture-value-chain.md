# Business Solution Architecture (Value Chain)

This document provides a comprehensive overview of the NETTRADES.AI platform architecture.

---

## Business Solution Architecture (Value Chain)

```mermaid
graph TB
    subgraph Personas[User Personas]
        JS[Job Seeker] & FR[Freelancer] & CO[Company] & PA[Partner/Researcher]
    end

    subgraph ValueStreams[Value Streams]
        JobMatch[Job Matching] & FreelanceMatch[Freelance Matching]
        LeadGen[Lead Generation] & Collab[Project Collaboration]
        Review[Review & Rating] & GPUSharing[GPU Capacity Sharing]
        ExpertHelp[Ask Someone]
    end

    subgraph BusinessCapabilities[Business Capabilities - NETTRADES Platform]
        BC1[Multi-vendor Marketplace Odoo]
        BC2[AI Matching LangGraph+GPUStack]
        BC3[CRM & Lead Mgmt Odoo]
        BC4[Project/Task Mgmt Odoo]
        BC5[Accounting & Payments Odoo]
        BC6[Workflow Automation LangGraph]
        BC7[Distributed LLM Inference GPUStack+WireGuard+gVisor]
        BC8[Git-based Collaboration Forgejo]
        BC9[Review & Reputation Odoo]
        BC10[GPU Resource Marketplace Odoo]
        BC11[Expert Matching & Escrow Stripe]
        BC12[Continuous AI Training Axolotl/Unsloth]
    end

    subgraph Outcomes[Business Outcomes]
        O1[Faster time-to-hire] & O2[Reduced cost per hire]
        O3[Automated lead qualification] & O4[Seamless collaboration]
        O5[Data privacy] & O6[Trust through verified reviews]
        O7[Monetised idle GPU capacity] & O8[Self-improving AI]
        O9[Access to expert knowledge]
    end

    JS -- Job Search --> JobMatch --> BC2
    FR -- Find Work --> FreelanceMatch --> BC1
    CO -- Find Talent/Leads --> LeadGen --> BC3
    CO -- Share Idle GPUs --> GPUSharing --> BC10 & BC7
    PA -- Find Research Partners --> Collab --> BC4 & BC8
    User -- Need Expert Help --> ExpertHelp --> BC11 & BC9
    Review --> BC9

    BC1 & BC2 & BC3 & BC4 & BC5 --> BC6 --> BC7
    BC7 --> BC10 & O7
    BC9 --> O6
    BC2 --> O1 & O2
    BC3 --> O3
    BC4 --> O4
    BC7 --> O5
    BC9 & BC12 --> O8
    BC11 --> O9