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


# -----------------------------------------------------------------------------
# Create the scoped `nettrades-service` user if it does not exist,
# and generate an API key for it. The key is written to stdout so the
# caller can capture it and store it in .env.
# -----------------------------------------------------------------------------
import secrets as _secrets

svc = env['res.users'].search([('login', '=', 'nettrades-service')], limit=1)
if not svc:
    print("[configure-odoo-admin] service user not found — creating", file=sys.stderr)
    # Look up the groups that this user needs. They are defined in
    # nettrades_gpu_admin and nettrades_core, both of which are installed.
    svc = env['res.users'].create({
        'name': 'NETTRADES Service',
        'login': 'nettrades-service',
        'password': '!',  # No web login.
        'company_id': env.ref('base.main_company').id,
        'groups_id': [(6, 0, [
            env.ref('base.group_user').id,
            env.ref('nettrades_core.group_nettrades_api').id,
            env.ref('nettrades_gpu_admin.group_gpu_administrator').id,
            env.ref('nettrades_gpu_admin.group_gpu_operator').id,
        ])],
    })
    env.cr.commit()
    print(f"[configure-odoo-admin] service user created (uid={svc.id})", file=sys.stderr)
else:
    print(f"[configure-odoo-admin] service user found (uid={svc.id})", file=sys.stderr)

# Generate a fresh API key for the service user. The `_generate` method
# returns the plaintext key once; we never store it in the database.
try:
    from odoo.addons.base.models.res_users import generate_api_key
    plaintext = env['res.users.apikeys']._generate(
        'nettrades-proxy',
        svc.id,
        'nettrades-service',
        expiration_date=None,
    )
    # Write the plaintext key to stdout in a parseable form. The
    # caller (phase-deploy.sh or install-spokes.sh) reads this line.
    print(f"NETTRADES_SERVICE_API_KEY={plaintext}")
    print(f"NETTRADES_SERVICE_UID={svc.id}")
except Exception as e:
    print(f"[configure-odoo-admin] API key generation failed: {e}", file=sys.stderr)
    sys.exit(1)


PYEOF