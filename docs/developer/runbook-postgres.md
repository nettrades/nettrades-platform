# Runbook: PostgreSQL won't start

## Symptoms
- `docker compose ps postgres` shows `Up ... (unhealthy)` for > 5 min
- `pg_isready -U odoo -d odoo` returns "starting up" or "rejecting connections"
- Odoo logs show `could not connect to server`

## Triage (do NOT wipe the volume)

### 1. Check logs
```bash
docker logs docker-postgres-1 --tail 50 2>&1

```

Look for:

* syncing data directory (fsync) — PG17 recovery fsync, can take hours on WSL2

* PANIC: could not locate a valid checkpoint record — WAL corrupted

* FATAL: database "odoo" does not exist — initdb incomplete

2. Check filesystem

```bash

mount | grep ' / '

```

If ro is in the options, the filesystem is read-only. Stop and recover the filesystem first (see runbook-filesystem.md).

3. If fsync is the cause, wait

PG17 recovery fsync can take 4+ hours on WSL2. Do not kill it. Check progress:

```bash

docker logs docker-postgres-1 --tail 5 --follow
```

4. If WAL is corrupted, restore from backup

Do not run pg_resetwal. It will discard data. Restore from restic:

```bash

cd ~/nettrades-platform
# List available snapshots
source deploy/docker/.env
export RESTIC_REPOSITORY RESTIC_PASSWORD AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
restic snapshots --tag nettrades

# Restore the most recent
LATEST=$(restic snapshots --last --json | jq -r '.[0].short_id')
restic restore "$LATEST" --target /tmp/restore

# Stop postgres, replace the volume
docker compose -f deploy/docker/docker-compose.yaml stop postgres
docker compose -f deploy/docker/docker-compose.yaml rm -f postgres
docker volume rm docker_postgres_data
docker compose -f deploy/docker/docker-compose.yaml up -d postgres
sleep 30

# Restore the dump
docker compose -f deploy/docker/docker-compose.yaml exec -T postgres \
    psql -U odoo -d odoo < /tmp/restore/.../dumpall.sql

```

Never do this

* Never docker volume rm docker_postgres_data without a working off-host backup

* Never run pg_resetwal — it discards data

* Never wipe the volume "just to get past it" — you will lose everything

