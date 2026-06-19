# DEPLOYMENT TEAM PERSPECTIVE — CI/CD Pipeline Diagram

Purpose: Shows the continuous integration and deployment pipeline using Forgejo and Argo CD.

---

## DEPLOYMENT TEAM PERSPECTIVE — CI/CD Pipeline Diagram

```mermaid
flowchart LR
    subgraph Dev["????? Developer Workstation"]
        Code["Write Code"]
        Commit["git commit & push"]
    end

    subgraph Forgejo["?? Forgejo (Self-Hosted Git)"]
        Repo["Repository<br>????????????????<br>• nettrades-platform<br>• nettrades-odoo-modules<br>• nettrades-deploy"]
        Webhook["Webhook Trigger"]
    end

    subgraph CI["?? CI Pipeline (Forgejo Actions)"]
        Lint["Lint & Format<br>????????????????<br>• flake8, black<br>• eslint, prettier"]
        Test["Run Tests<br>????????????????<br>• pytest (Python)<br>• jest (JavaScript)"]
        Build["Build Images<br>????????????????<br>• docker build<br>• Tag: latest, commit-sha"]
        Push["Push to Registry<br>????????????????<br>• nettrades/odoo:latest<br>• nettrades/langgraph:latest"]
    end

    subgraph Registry["?? Container Registry"]
        Images["Stored Images<br>????????????????<br>• odoo:latest<br>• langgraph:latest<br>• gpustack:latest<br>• ml-pipeline:latest"]
    end

    subgraph GitOps["?? GitOps (Argo CD)"]
        Manifests["K8s Manifests<br>????????????????<br>• deployments/<br>• services/<br>• configmaps/<br>• secrets/"]
        ArgoCD["Argo CD<br>????????????????<br>• Sync every 3min<br>• Auto-apply changes"]
    end

    subgraph K8s["? Kubernetes Cluster"]
        Pods["Running Pods<br>????????????????<br>• Odoo Pod<br>• LangGraph Pod<br>• GPUStack Pod<br>• PostgreSQL Pod"]
    end

    Code --> Commit
    Commit -->|"git push"| Repo
    Repo -->|"Triggers"| Webhook
    Webhook -->|"Starts"| CI
    
    Lint --> Test
    Test --> Build
    Build --> Push
    Push -->|"Stores"| Images
    
    Repo -->|"Stores"| Manifests
    ArgoCD -->|"Pulls"| Manifests
    ArgoCD -->|"Pulls"| Images
    ArgoCD -->|"Deploys"| Pods

    classDef dev fill:#e3f2fd,stroke:#1565c0;
    classDef forgejo fill:#fff3e0,stroke:#e65100;
    classDef ci fill:#f3e5f5,stroke:#6a1b9a;
    classDef registry fill:#e8f5e9,stroke:#2e7d32;
    classDef gitops fill:#fce4ec,stroke:#c62828;
    classDef k8s fill:#ede7f6,stroke:#4527a0;

    class Dev dev;
    class Forgejo forgejo;
    class CI ci;
    class Registry registry;
    class GitOps gitops;
    class K8s k8s;