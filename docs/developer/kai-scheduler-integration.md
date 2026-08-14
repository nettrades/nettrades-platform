# KAI Scheduler Integration (Future)

**Status:** Planned

This document outlines the future integration of KAI Scheduler for advanced GPU job scheduling.

## Overview

KAI Scheduler is a GPU scheduling system that provides:

- **Advanced job scheduling** – Priority, preemption, and fair share
- **GPU cluster management** – Health checking, failover
- **Resource optimisation** – Maximises GPU utilisation
- **Multi-tenant support** – Isolates workloads

## Integration Architecture

```mermaid
graph TB
    subgraph NETTRADES["NETTRADES Platform"]
        Odoo["Odoo 19 CE"]
        Dynamo["NVIDIA Dynamo"]
        Launcher["NETTRADES Launcher"]
    end

    subgraph KAI["KAI Scheduler"]
        Scheduler["Job Scheduler"]
        Resource["Resource Manager"]
        Queue["Job Queue"]
    end

    subgraph GPUs["GPU Cluster"]
        GPU1["GPU Node 1"]
        GPU2["GPU Node 2"]
        GPU3["GPU Node N"]
    end

    Odoo -->|"Submit Job"| Scheduler
    Launcher -->|"Submit Job"| Scheduler
    Scheduler --> Queue
    Queue --> Resource
    Resource --> GPU1
    Resource --> GPU2
    Resource --> GPU3
    GPU1 -->|"Status"| Resource
    GPU2 -->|"Status"| Resource
    GPU3 -->|"Status"| Resource
    Resource -->|"Capacity"| Odoo

```

## Benefits

| Benefit | Description |
|---------|----------------------|
| ** Better Utilisation ** | Maximises GPU usage across the cluster |
| ** Fair Scheduling ** | Allocates resources fairly across tenants |
| ** Priority Support ** | Critical jobs get priority |
| ** Preemption ** | Low-priority jobs can be preempted |
| ** Health Monitoring ** | Detects and handles failed nodes |


## API Integration


```python

# Integration point in Odoo
class KAIJob(models.Model):
    _name = 'nettrades.kai.job'
    _description = 'KAI Scheduler Job'

    name = fields.Char('Job Name', required=True)
    job_type = fields.Selection([
        ('inference', 'Inference'),
        ('training', 'Training'),
        ('fine_tuning', 'Fine Tuning'),
    ], string='Job Type')
    priority = fields.Integer('Priority')
    gpu_count = fields.Integer('GPU Count', default=1)
    status = fields.Selection([
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ], string='Status')


```


```mermaid

graph TB
    subgraph KAI["KAI Scheduler Architecture"]
        subgraph Core["Core Entities"]
            PodGroup["PodGroup (Gang Scheduling)"]
            Queue["Queue (Hierarchical Fairness)"]
            Priority["Priority Class"]
        end

        subgraph Features["Key Features"]
            Gang["Gang Scheduling"]
            GPU_Share["Fractional GPU (Sharing)"]
            Topology["Topology-Aware Placement"]
            Elastic["Elastic Workloads"]
            Preemption["Preemption"]
        end

        subgraph Integration["Integration with NETTRADES"]
            Odoo_Jobs["Odoo Jobs (Training/Inference)"]
            LangGraph_Jobs["LangGraph Agent Workloads"]
            Dynamo_Workers["Dynamo Worker Groups"]
        end

        PodGroup --> Gang
        Queue --> GPU_Share
        Queue --> Topology
        Queue --> Elastic
        Priority --> Preemption

        Odoo_Jobs --> PodGroup
        LangGraph_Jobs --> PodGroup
        Dynamo_Workers --> PodGroup

        Gang --> Dynamo_Workers
        GPU_Share --> Odoo_Jobs
        Topology --> Dynamo_Workers
        Elastic --> LangGraph_Jobs
    end

```


## KAI Scheduler Benefits for NETTRADES:


| Feature | Description | NETTRADES Use Case |
|---------|--------|---------|
| **Gang Scheduling** | All pods in a group start together | Distributed training jobs |
| **Hierarchical Queues** | GPU quotas by team/department | Multi-tenant enterprise |
| **Fractional GPU** | GPU sharing with hard isolation | Inference workloads, cost optimisation |
| **Topology-Aware** | NVLink-aware placement | Multi-GPU inference/training |
| **Elastic Workloads** | Scale between min/max pods | Dynamic inference demand |


## Next Steps

* [NVIDIA Dynamo Integration](nvidia-dynamo-integration.md) – Current inference engine

* [GPU Node Deployment](gpu-node-deployment.md) – GPU node setup

* [Performance Tuning](performance-tuning.md) – Optimisation