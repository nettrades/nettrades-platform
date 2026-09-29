#!/bin/bash
# =============================================================================
# FILE: scripts/configure-odoo-admin.sh
# =============================================================================
# PURPOSE:
#   Idempotently configures the Odoo admin user (login='admin') for use by
#   external services (langgraph-server, odoo-proxy). Runs INSIDE the Odoo
#   container via `odoo shell`. Called by phase-deploy.sh (after base install)
#   and phase-modules.sh (after GPU modules install so the GPU groups exist).
#
# WHAT IT DOES:
#   1. Sets the admin user's password to $ODOO_ADMIN_PASSWORD via the ORM.
#   2. Adds the admin user to nettrades_gpu_admin.gpu_administrator and
#      gpu_operator groups (if the module is installed).
#   3. Prints `ADMIN_UID=<uid>` on stdout so the caller can persist it in .env.
#
# Idempotent. Safe to re-run.
# =============================================================================

set -euo pipefail

: "${ODOO_ADMIN_PASSWORD:?must be set}"
: "${POSTGRES_PASSWORD:?must be set}"

odoo shell -d odoo \
    --db_host=postgres --db_port=5432 \
    --db_user=odoo --db_password="$POSTGRES_PASSWORD" \
    --no-http <<'PYEOF'
import os, sys

admin_password = os.environ.get('ODOO_ADMIN_PASSWORD')
if not admin_password:
    print("ERROR: ODOO_ADMIN_PASSWORD is not set", file=sys.stderr)
    sys.exit(1)

admin = env['res.users'].search([('login', '=', 'admin')], limit=1)
if not admin:
    print("ERROR: admin user not found", file=sys.stderr)
    sys.exit(1)

# Odoo 19 uses a computed password field; assign to the field, not to
# _set_password (whose signature changed to take no argument).
admin.password = admin_password
env.cr.commit()
print(f"[configure-odoo-admin] password set for uid={admin.id}", file=sys.stderr)

try:
    for xml_id in (
        'nettrades_gpu_admin.group_gpu_administrator',
        'nettrades_gpu_admin.group_gpu_operator',
    ):
        g = env.ref(xml_id, raise_if_not_found=False)
        if g:
            g.write({'user_ids': [(4, admin.id)]})
            print(f"[configure-odoo-admin] added admin to {xml_id}", file=sys.stderr)
    env.cr.commit()
except Exception as e:
    print(f"[configure-odoo-admin] GPU group step skipped: {e}", file=sys.stderr)

print(f"ADMIN_UID={admin.id}")


# Ensure a default LLM company config exists. The factory in
# src/core/tools/llm_factory.py calls get_effective_config(company_id),
# which reads self.provider_id. If no record exists for the company,
# every LLM call fails with MissingError.
try:
    Config = env['nettrades.llm.company.config'].sudo()
    # Odoo typically has at least one company (id=1).
    company = env['res.company'].search([], limit=1)
    if company:
        existing = Config.search([('company_id', '=', company.id)], limit=1)
        if not existing:
            Config.create({
                'company_id': company.id,
                'provider_type': 'openai',      # or whatever the field is
                'model_name': 'deepseek-7b',
                'api_base_url': 'http://dynamo:8000/v1',
                'api_key': 'dummy',
            })
            env.cr.commit()
            print(f"[configure-odoo-admin] created default LLM config for company {company.id}", file=sys.stderr)
except Exception as e:
    print(f"[configure-odoo-admin] LLM config step skipped: {e}", file=sys.stderr)


PYEOF