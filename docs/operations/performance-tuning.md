
---

## File: `docs/operations/performance-tuning.md`

```markdown
# Performance Tuning Guide

This document provides guidelines for optimising the NETTRADES.AI platform for production workloads.

---

## Overview

Performance tuning is a balance between **resource utilisation**, **response time**, and **throughput**. Start with the default configurations and adjust based on your workload.

---

## 1. Odoo Tuning

### 1.1 Worker Configuration

Odoo uses `workers` to handle concurrent requests.

**Single VM (Docker Compose):**

```ini
# In odoo.conf
workers = 4  # Number of worker processes