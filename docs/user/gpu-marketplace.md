
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
        DynamoCentral["Dynamo Server (v2.1.2)"]
        WGCtrl["WireGuard Peer Manager (wgctrl-go)"]
    end

    subgraph CompanyA["Company A – Trusted Mode"]
        WGMeshA["WireGuard Full Mesh<br>10.100.1.0/24"]
        DynamoCompanyA["Dynamo Server (Company)"]
        NodeA1["GPU Node 1<br>(Internal Pool)"]
        NodeA2["GPU Node 2<br>(Public Pool)"]
    end

    subgraph Freelancers["Freelancers – Untrusted Mode"]
        WGSpoke["WireGuard Hub-Spoke<br>(Controller only)"]
        NodeF1["GPU Node<br>(gVisor Container)"]
        NodeF2["GPU Node<br>(gVisor Container)"]
    end

    OdooCentral --> DynamoCentral
    LangGraphCentral --> DynamoCentral
    DynamoCentral --> NodeF1 & NodeF2 & DynamoCompanyA
    NodeF1 & NodeF2 --> WGCtrl
    NodeA1 & NodeA2 --> DynamoCompanyA
