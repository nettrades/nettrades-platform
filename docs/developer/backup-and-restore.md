
# Backup & Restore Guide

This document provides comprehensive backup and restore procedures for the NETTRADES.AI platform.

---

## Overview

A robust backup strategy is essential for production deployments. This guide covers:

| Component | Backup Method | Restore Method |
|-----------|---------------|----------------|
| **PostgreSQL Database** | `pg_dump` (single VM) / CNPG backups (Kubernetes) | `pg_restore` |
| **Odoo Filestore** | File system backup | File restore |
| **Configuration** | Version control (Git) + manual backup | File restore |
| **Model Weights** | File system backup | File restore |

---

## Backup Strategy

### Single VM (Docker Compose)

#### 1. Database Backup (PostgreSQL)

A daily cron job is automatically configured to dump the database at 2 AM with 7-day retention.

**Manual backup:**

```bash
cd /opt/nettrades-ai
docker exec postgres pg_dump -U odoo nettrades > backups/nettrades_$(date +%Y%m%d).sql
```
