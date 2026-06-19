
---

## File: `docs/user/gpu-marketplace.md` (With Token Flow and Distributed GPU Network Diagrams)

```markdown
# GPU Marketplace

This guide covers how to share idle GPUs and rent GPU capacity on NETTRADES.AI.

---

## Overview

The **Distributed GPU Marketplace** connects GPU providers with users who need GPU capacity for inference and fine-tuning.

| User Type | What You Can Do |
|-----------|-----------------|
| **GPU Provider** | Share idle GPUs, earn tokens |
| **GPU Consumer** | Rent GPU capacity for inference or fine-tuning |

---

## Distributed GPU Network Architecture

```mermaid
graph TB
    subgraph Central["NETTRADES Central Infrastructure"]
        OdooCentral["Odoo 19 CE + GPU Admin Panel"]
        LangGraphCentral["LangGraph Supervisor (Provider Router)"]
        GPUStackCentral["GPUStack Server (v2.1.2)"]
        WGCtrl["WireGuard Peer Manager (wgctrl-go)"]
    end

    subgraph CompanyA["Company A – Trusted Mode"]
        WGMeshA["WireGuard Full Mesh<br>10.100.1.0/24"]
        GPUStackCompanyA["GPUStack Server (Company)"]
        NodeA1["GPU Node 1<br>(Internal Pool)"]
        NodeA2["GPU Node 2<br>(Public Pool)"]
    end

    subgraph Freelancers["Freelancers – Untrusted Mode"]
        WGSpoke["WireGuard Hub-Spoke<br>(Controller only)"]
        NodeF1["GPU Node<br>(gVisor Container)"]
        NodeF2["GPU Node<br>(gVisor Container)"]
    end

    OdooCentral --> GPUStackCentral
    LangGraphCentral --> GPUStackCentral
    GPUStackCentral --> NodeF1 & NodeF2 & GPUStackCompanyA
    NodeF1 & NodeF2 --> WGCtrl
    NodeA1 & NodeA2 --> GPUStackCompanyA