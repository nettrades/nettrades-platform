
# Troubleshooting Quick Reference

A one-page cheat sheet for the most common issues.

---

## Odoo Issues

| Symptom | Quick Check | Likely Fix |
|---------|-------------|------------|
| Odoo returns 502 | `docker compose ps` | Wait 30s or restart Odoo |
| Blank screen after login | Check Valkey/Redis | Comment out `session_store` in `odoo.conf` |
| Module not showing in Apps | Enable Developer Mode | Update Apps List, remove Apps filter |
| `llm_pgvector` fails | `psql -d nettrades -c "CREATE EXTENSION IF NOT EXISTS vector;"` | Install pgvector extension |

---

## GPU Node Issues

| Symptom | Quick Check | Likely Fix |
|---------|-------------|------------|
| Node not registering | `sudo journalctl -u nettrades-agent -f` | Check API key, Odoo endpoint |
| GPU not detected | `nvidia-smi` | Install NVIDIA drivers |
| WireGuard tunnel down | `sudo wg show` | `sudo wg-quick up wg0` |
| GPUStack worker not starting | `journalctl -u gpustack-worker -f` | Check server URL, token |

---

## Authentication Issues

| Symptom | Quick Check | Likely Fix |
|---------|-------------|------------|
| 401 Unauthorised | Check `LANGGRAPH_API_KEY` | Update API key in `.env` |
| 402 Payment Required | Token balance | Top up tokens |

---

## Connection Issues

| Symptom | Quick Check | Likely Fix |
|---------|-------------|------------|
| SSL certificate error | `curl -v https://domain` | Ensure port 80 is open, DNS correct |
| PostgreSQL connection refused | `sudo systemctl status postgresql` | Start PostgreSQL |
| Redis/Valkey connection | `docker compose exec valkey redis-cli ping` | Restart Valkey |

---

## Log Locations

| Component | Log Location |
|-----------|--------------|
| **Odoo** | `/var/log/odoo/odoo.log` or `docker compose logs odoo` |
| **LangGraph** | `docker compose logs langgraph` |
| **GPU Node Agent** | `sudo journalctl -u nettrades-agent -f` |
| **GPUStack Worker** | `journalctl -u gpustack-worker -f` |
| **PostgreSQL** | `/var/log/postgresql/postgresql-*.log` |

---

## Common Docker Commands

```bash
# Check all services
docker compose ps

# View logs
docker compose logs --tail=100 <service>

# Restart a service
docker compose restart <service>

# Update and restart all
docker compose pull && docker compose up -d

# Execute a command in a container
docker compose exec odoo bash
