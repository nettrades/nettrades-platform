
## Bridge Architecture

The `nettrades_bridge` module is the core of the NETTRADES Sovereign AI Router. It provides configurable routing between local and remote AI infrastructure.

### Overview

```mermaid
graph TB
    subgraph External["External"]
        User["End User"]
    end

    subgraph Client["Client Company"]
        subgraph Presentation["Presentation Layer"]
            WebUI["Odoo Web UI"]
            Launcher["NETTRADES Launcher"]
            API["API Gateway"]
            NETTRADESUI["NETTRADES UI (Talks to Odoo for Authentication via Odoo-Proxy)"]
        end

        subgraph Bridge["Bridge Layer (nettrades_bridge)"]
            Config["Bridge Config (Global & Company)"]
            Router["Routing Engine (5 Modes)"]
            Logger["Usage Logger"]
            Discovery["mDNS Discovery"]
        end

        subgraph Local["Local AI"]
            LangGraph["LangGraph Supervisor"]
            Dynamo["NVIDIA Dynamo"]
            vLLM["vLLM (GPU)"]
            llama_cpp["llama.cpp (CPU)"]
            Agents["Sub-Agents"]
        end
    end

    subgraph Cloud["NETTRADES.AI (The Hub)"]
        GlobalAPI["Global API"]
        GlobalAgents["Global LangGraph Agents"]
        GlobalGPU["Global GPU Marketplace"]
        TalentPool["Global Talent Pool"]
        SelfImproving["Self-Improving Loop"]
    end

    User --> WebUI
    User --> Launcher
    User --> API
    User --> NETTRADESUI
    WebUI --> Bridge
    Launcher --> Bridge
    API --> Bridge
    NETTRADESUI --> Bridge

    Bridge -->|"Local (default)"| LangGraph
    Bridge -->|"Remote (when needed)"| GlobalAPI
    Bridge -->|"GPU Overflow"| GlobalGPU
    Bridge -->|"Discovery"| Discovery

    LangGraph --> Dynamo
    Dynamo --> vLLM
    Dynamo --> llama_cpp
    LangGraph --> Agents

    GlobalAPI --> GlobalAgents
    GlobalAgents --> TalentPool
    GlobalAgents --> GlobalGPU
    GlobalAPI --> SelfImproving
    SelfImproving -->|"Model Updates"| GlobalAgents

    Logger --> Config
    Config --> Router

```


### Routing Modes


The bridge supports five routing modes, configurable per company:

| Mode | Description | Use Case |
|------|--------|----------|
| **Local Only** | ll requests stay on local infrastructure | Sovereign AI – full data sovereignty |
| **Remote Only** | All requests go to external providers | Testing, no local GPUs available |
| **Hybrid (Local First)** | Try local, fallback to remote if unavailable | High availability, maximise local usage |
| **Hybrid (Remote First)** | Try remote, fallback to local if unavailable | Cost optimisation, use external when cheaper |
| **Auto** | AI agent decides based on context | Dynamic routing based on workload |


### Request Type Routing


Different request types can have different routing modes:

| Request Type | Description | Default | 
|------|--------|----------|
| **Inference** | LLM inference requests | Local |
| **Training** | Model training jobs | Local |
| **Fine-Tuning** | Model fine-tuning jobs | Local |
| **Embedding** | Vector embedding generation | Local |

### Route Decision Engine


```mermaid
graph TD
    Request["Incoming Request"] --> GetRoute["get_route_for_request()"]
    
    GetRoute --> CheckMode["Check Routing Mode"]
    
    CheckMode -->|local_only| Local["Route to Local"]
    CheckMode -->|remote_only| Remote["Route to Remote"]
    CheckMode -->|hybrid| Hybrid["Try Local, Fallback Remote"]
    CheckMode -->|hybrid_remote_first| HybridRemote["Try Remote, Fallback Local"]
    CheckMode -->|auto| Auto["AI Agent Decides"]
    
    Local --> DynamoCheck["Is Dynamo Healthy?"]
    DynamoCheck -->|Yes| DynamoLB["Dynamo Load Balancing"]
    DynamoCheck -->|No| Llama["llama.cpp (CPU)"]
    
    DynamoLB --> RoundRobin["Round Robin"]
    DynamoLB --> Weighted["Weighted"]
    DynamoLB --> Random["Random"]
    DynamoLB --> Priority["Priority"]
    
    Remote --> Marketplace["GPU Marketplace"]
    Remote --> External["External API (OpenAI/Anthropic)"]
    
    Hybrid --> LocalCheck["Is Local Available?"]
    LocalCheck -->|Yes| Local
    LocalCheck -->|No| Remote
    
    HybridRemote --> RemoteCheck["Is Remote Available?"]
    RemoteCheck -->|Yes| Remote
    RemoteCheck -->|No| Local
    
    Auto --> AgentDecision["LangGraph Agent Decides"]
    AgentDecision --> Local
    AgentDecision --> Remote

```


### Load Balancing Strategies


The bridge provides load balancing for NVIDIA Dynamo nodes:


| Strategy | Description | Use Case |
|------|--------|----------|
| **Round Robin** | Distributes requests evenly across healthy nodes | Simple, even distribution |
| **Weighted** | Distributes based on node weight | Prioritise faster nodes |
| **Random** | Random distribution | Simple, no state tracking |
| **Priority** | Highest priority node first | Primary/backup configuration |

### Health Checking

The bridge continuously monitors the health of all routes:

```mermaid
graph LR
    HealthCheck["Health Check Cron"] --> CheckRoute["For Each Route"]
    CheckRoute --> Endpoint["GET /health"]
    Endpoint -->|200| Healthy["Status: Healthy"]
    Endpoint -->|Timeout/Error| Unhealthy["Status: Unhealthy"]
    Healthy --> Update["Update last_health_check"]
    Unhealthy --> Update
    Update --> Store["Store in Database"]
```    

Health Check Configuration:

| Setting | Default | Description |
|------|--------|----------|
| `health_check_enabled` | True | Enable/disable health checking |
| `health_check_endpoint` | `/health` | Health check endpoint URL |
| `health_check_interval` | 30s | How often to check |
| `health_check_timeout` | 5s | Timeout for each check |


## mDNS Discovery


The bridge uses mDNS/Avahi for automatic node discovery:


```mermaid
graph TB
    subgraph NodeA["Node A (NETTRADES)"]
        AvahiA["Avahi daemon"]
        ServiceA["_nettrades._tcp service"]
    end
    
    subgraph NodeB["Node B (NETTRADES)"]
        AvahiB["Avahi daemon"]
        ServiceB["_nettrades._tcp service"]
    end
    
    ServiceA -->|"mDNS multicast"| AvahiB
    ServiceB -->|"mDNS multicast"| AvahiA
    AvahiA -->|"Discover Node B"| DiscoveryA["Discovery Service"]
    AvahiB -->|"Discover Node A"| DiscoveryB["Discovery Service"]
    DiscoveryA -->|"Register Node B"| BridgeA["nettrades_bridge"]
    DiscoveryB -->|"Register Node A"| BridgeB["nettrades_bridge"]

```


## TXT Records Advertised:


| Field | Description |
|------|--------|
| `version` | Platform version |
| `gpus` | Number of available GPUs |
| `models` | Number of available models |
| `capabilities` | JSON of capabilities |

## GPU Marketplace Integration

The bridge can route requests to the GPU marketplace:

```mermaid
graph TB
    Request["Inference Request"] --> Bridge["nettrades_bridge"]
    Bridge --> CheckMode["Check Routing Mode"]
    CheckMode -->|"Marketplace"| Marketplace["GPU Marketplace"]
    Marketplace --> Filter["Filter by Rating & Price"]
    Filter --> Select["Select Best Node"]
    Select --> Route["Route to Node"]
    Route --> Response["Return Response"]

```

### Marketplace Settings:

| Setting | Description |
|------|--------|
| `marketplace_min_rating` | Minimum GPU rating (0-5) |
| `marketplace_max_price` | Maximum price per hour ($) |
| `marketplace_preferred_nodes` | Preferred node IDs (comma-separated) |


## External API Integration

The bridge can route requests to external APIs:

| Provider | API URL | Model Format |
|------|--------|----------|
| **OpenAI** | `https://api.openai.com/v1` | `gpt-4`, `gpt-3.5-turbo` |
| **Anthropic** | `https://api.anthropic.com/v1` | `claude-3-opus`, `claude-3-sonnet` |
| **Custom** | User-defined | User-defined |


## API Endpoints
		

| Endpoint | Method | Description |
|------|--------|----------|
| `/api/bridge/route/decide` | POST | Get a route decision for a request |
| `/api/bridge/config` | GET | Get effective configuration |
| `/api/bridge/usage` | GET | Get usage logs |
| `/api/bridge/discovery/peers` | GET | Get discovered mDNS peers |
| `/api/bridge/discovery/status` | GET | Get discovery service status |


## Valkey as Configuration Cache

The bridge routing engine reads operational mode settings from Valkey cache:

```mermaid
graph LR
    Admin["Admin Updates Mode"] --> Odoo["Odoo"]
    Odoo -->|"Writes JSON"| Valkey["Valkey Cache"]
    Valkey -->|"Microsecond read"| Router["LangGraph Router"]
    Router -->|"Apply routing"| Dynamo["NVIDIA Dynamo"]
```


## Next Steps

[Building Agents](building-agents.md) – Create custom LangGraph agents

[Building Odoo Modules](building-odoo-modules.md) – Extend the bridge

[API Reference](api-reference.md) – API documentation

[Troubleshooting](troubleshooting.md) – Common issues and solutions