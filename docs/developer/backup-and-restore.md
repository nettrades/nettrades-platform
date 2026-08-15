# Backup & Restore Guide

This document provides comprehensive backup and restore procedures for the NETTRADES.AI platform.

## Overview

A robust backup strategy is essential for production deployments.

| Component | Backup Method | Restore Method |
|-----------|---------------|----------------|
| **PostgreSQL Database** | `pg_dump` (single VM) / CNPG backups (Kubernetes) | `pg_restore` |
| **Odoo Filestore** | File system backup | File restore |
| **Configuration** | Version control (Git) + manual backup | File restore |
| **Model Weights** | File system backup | File restore |
| **NVIDIA Dynamo Models** | File system backup | File restore |

## Backup Strategy

### Single VM (Docker Compose)

#### 1. Database Backup (PostgreSQL)

A daily cron job is automatically configured to dump the database at 2 AM with 7-day retention.

**Manual backup:**

```bash
cd /root/nettrades-platform/deploy/docker
docker exec postgres pg_dump -U odoo odoo > backups/nettrades_$(date +%Y%m%d).sql
```

#### 2. Odoo Filestore Backup

```bash

cd /root/nettrades-platform/deploy/docker
tar -czf backups/filestore_$(date +%Y%m%d).tar.gz ./odoo-data/
```

#### 3. Model Weights Backup

```bash

cd /root/nettrades-platform/deploy/docker
tar -czf backups/models_$(date +%Y%m%d).tar.gz ./dynamo-data/models/
```

#### 4. Full Backup Script

```bash

cd /root/nettrades-platform
./scripts/backup.sh
```


This creates a complete backup in ~/.nettrades/backups/.

### Kubernetes (CNPG)

```bash

# Take a full cluster backup
kubectl apply -f backup-cnpg.yaml

# List available backups
kubectl get backups.postgresql.cnpg.io -n nettrades


# Restore from backup

```
kubectl apply -f restore-cnpg.yaml
```

## Restore Procedure

### Single VM

```bash

cd /root/nettrades-platform
./scripts/restore.sh ~/.nettrades/backups/nettrades-backup-YYYYMMDD_HHMMSS.tar.gz
```


### Manual Restore

#### Stop services:

```bash

cd /root/nettrades-platform/deploy/docker
docker compose down
```

#### Restore database:

```bash

docker compose up -d postgres
docker exec -i postgres psql -U odoo < backups/nettrades_YYYYMMDD.sql
```

#### Restore filestore:

```bash

tar -xzf backups/filestore_YYYYMMDD.tar.gz -C ./

```

#### Restore models:

```bash

tar -xzf backups/models_YYYYMMDD.tar.gz -C ./dynamo-data/

```

#### Start services:

```bash

docker compose up -d

```

### Retention Policy

| Backup Type | Retention Period |
|-----------|---------------|
| Daily database dumps | 7 days |
| Weekly filestore backups | 30 days |
| Monthly full backups | 12 months |
| Model weights | Indefinite (keep latest 3 versions) |

### Restore Verification

After restoring, verify:

* Odoo is accessible: `curl http://localhost:8069`

* LangGraph is healthy: `curl http://localhost:8000/health`

* NVIDIA Dynamo is running: `curl http://localhost:8001/v1/models`

* Data integrity: Check key records in Odoo


### Disaster Recovery

In case of complete server failure:

* **Provision a new server** with Ubuntu 24.04

* **Clone the repository** and run deployment

* **Restore from the latest backup** using the restore script

* **Verify all services** are operational