# Distributed GPU Network (Trusted vs Untrusted)

This document provides a comprehensive overview of the NETTRADES.AI platform architecture.

---

## Distributed GPU Network (Trusted vs Untrusted)

```mermaid
graph TB
    subgraph Central[NETTRADES Central]
        OdooCentral[Odoo + GPU Admin]
        LangGraphCentral[LangGraph Supervisor]
        NVIDIAdynamoCentral[NVIDIA Dynamo Server]
        WGCtrl[WireGuard Peer Manager]
    end

    subgraph CompanyA[Company A Trusted]
        WGMeshA[WireGuard Mesh]
        NVIDIAdynamoCompanyA[NVIDIA Dynamo Server company]
        NodeA1[GPU Node] & NodeA2[GPU Node]
    end

    subgraph Freelancers[Freelancers Untrusted]
        WGSpoke[WireGuard Hub?Spoke]
        NodeF1[GPU Node gVisor] & NodeF2[GPU Node gVisor]
    end

    OdooCentral --> NVIDIAdynamoCentral
    LangGraphCentral --> NVIDIAdynamoCentral
    NVIDIAdynamoCentral --> NodeF1 & NodeF2 & NVIDIAdynamoCompanyA
    NodeF1 & NodeF2 --> WGCtrl
    NodeA1 & NodeA2 --> NVIDIAdynamoCompanyA