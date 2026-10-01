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
#   2. Adds the admin user to nettrades_gpu_admin.gpu_administrator,
#      gpu_operator, and nettrades_core.group_nettrades_api (if the modules
#      are installed).
#   3. Creates a scoped `nettrades-service` user for the control plane.
#   4. Generates an API key for the service user.
#   5. Prints `ADMIN_UID=<uid>`, `NETTRADES_SERVICE_UID=<uid>`, and
#      `NETTRADES_SERVICE_API_KEY=<key>` on stdout for the caller to capture.
#
# IDEMPOTENT. Safe to re-run.
#
# ORDERING NOTE (2026-10):
#   This script runs twice in a deployment:
#     1. From phase-deploy.sh BEFORE install-modules.sh. At that point, the
#        nettrades_* modules do not exist, so their xml IDs cannot be
#        resolved. Every ref() to a nettrades_* group uses
#        raise_if_not_found=False so a missing group is a silent skip.
#     2. From phase-modules.sh AFTER install-modules.sh. All modules exist,
#        and this run adds the missing groups to the existing service user.
#
#   The previous version used raise_if_not_found=True, which raised
#   ValueError on the first run and aborted the entire deployment with:
#       ValueError: External ID not found in the system:
#       nettrades_core.group_nettrades_api
#
# ODOO 20 COMPATIBILITY (2026-10):
#   - res.users `groups_id` field renamed to `group_ids`.
#   - llm.company.config creation uses `provider_id` (Many2one), not the
#     non-existent `provider_type` string field.
#
# API KEY GENERATION FIX (2026-10):
#   Odoo 19's `res.users.apikeys._generate()` signature changed. Calling it
#   with 3 positional args + expiration_date=None raised:
#       ResUsersApikeys._generate() got multiple values for argument
#       'expiration_date'
#   because the 3rd positional argument was being bound to `expiration_date`
#   AND the keyword was being supplied. The fix below inspects the method's
#   actual signature at runtime and passes only parameters it accepts, using
#   keyword arguments exclusively.
#
#   API key generation failure is now a WARNING, not a fatal error. The
#   service user is still created, and the admin can generate a key later
#   via Settings -> Users -> NETTRADES Service -> API Keys. Aborting the
#   whole deployment because a convenience feature failed is wrong.
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

# -----------------------------------------------------------------------------
# Add admin to NETTRADES groups if the modules are installed.
# -----------------------------------------------------------------------------
# Every ref() uses raise_if_not_found=False. On the first call (before
# install-modules.sh), only base.group_user resolves; the nettrades_* groups
# are skipped. On the second call (after install-modules.sh), all of them
# resolve and the admin is added.
# -----------------------------------------------------------------------------
try:
    for xml_id in (
        'nettrades_gpu_admin.group_gpu_administrator',
        'nettrades_gpu_admin.group_gpu_operator',
        'nettrades_core.group_nettrades_api',
    ):
        g = env.ref(xml_id, raise_if_not_found=False)
        if g:
            g.write({'user_ids': [(4, admin.id)]})
            print(f"[configure-odoo-admin] added admin to {xml_id}", file=sys.stderr)
        else:
            print(
                f"[configure-odoo-admin] {xml_id} not yet available "
                f"(module not installed); will retry after module install",
                file=sys.stderr,
            )
    env.cr.commit()
except Exception as e:
    print(f"[configure-odoo-admin] GPU group step skipped: {e}", file=sys.stderr)

print(f"ADMIN_UID={admin.id}")


# -----------------------------------------------------------------------------
# Ensure a default LLM company config exists.
# -----------------------------------------------------------------------------
# The factory in src/core/tools/llm_factory.py calls get_effective_config(
# company_id), which reads self.provider_id. If no record exists for the
# company, every LLM call fails with MissingError.
#
# FIX (2026-10): the previous version created the config with
# `provider_type='openai'`, but `provider_type` is not a field on
# nettrades.llm.company.config. The actual field is `provider_id` (Many2one
# to llm.provider). The create() would have raised ValueError. Now we look
# up an existing llm.provider and use its id, or skip.
# -----------------------------------------------------------------------------
try:
    Config = env['nettrades.llm.company.config'].sudo()
    company = env['res.company'].search([], limit=1)
    if company:
        existing = Config.search([('company_id', '=', company.id)], limit=1)
        if not existing:
            provider = env['llm.provider'].sudo().search([], limit=1)
            if provider:
                Config.create({
                    'company_id': company.id,
                    'provider_id': provider.id,
                    'model_name': 'deepseek-7b',
                    'api_base_url': 'http://dynamo:8000/v1',
                    'api_key': 'dummy',
                    'override_model': True,
                    'override_api_base_url': True,
                    'override_api_key': True,
                })
                env.cr.commit()
                print(
                    f"[configure-odoo-admin] created default LLM config "
                    f"for company {company.id} using provider {provider.id}",
                    file=sys.stderr,
                )
            else:
                print(
                    "[configure-odoo-admin] no llm.provider found; "
                    "skipping default LLM config creation",
                    file=sys.stderr,
                )
except Exception as e:
    print(f"[configure-odoo-admin] LLM config step skipped: {e}", file=sys.stderr)


# -----------------------------------------------------------------------------
# Create the scoped `nettrades-service` user if it does not exist,
# and generate an API key for it.
# -----------------------------------------------------------------------------
# The service user has NO web login capability (password is '!'). It is
# granted only the groups required by the control plane:
#   - base.group_user                             (standard internal user)
#   - nettrades_core.group_nettrades_api          (API access)
#   - nettrades_gpu_admin.group_gpu_administrator (write layer_assignment)
#   - nettrades_gpu_admin.group_gpu_operator      (read GPU state)
#
# Because this script runs BEFORE install-modules.sh on the first pass, not
# all of those groups exist yet. Every ref() uses raise_if_not_found=False
# and the list is built dynamically. The second call from phase-modules.sh
# re-runs this block and adds any groups that were missed the first time.
# -----------------------------------------------------------------------------
svc = env['res.users'].search([('login', '=', 'nettrades-service')], limit=1)

_wanted_group_xml_ids = [
    'base.group_user',
    'nettrades_core.group_nettrades_api',
    'nettrades_gpu_admin.group_gpu_administrator',
    'nettrades_gpu_admin.group_gpu_operator',
]
_resolved_groups = []
for _xml_id in _wanted_group_xml_ids:
    _g = env.ref(_xml_id, raise_if_not_found=False)
    if _g:
        _resolved_groups.append(_g.id)
    else:
        print(
            f"[configure-odoo-admin] group {_xml_id} not yet available "
            f"(module not installed); skipping for now",
            file=sys.stderr,
        )

if not svc:
    print("[configure-odoo-admin] service user not found — creating", file=sys.stderr)
    # Odoo 20 renamed `groups_id` to `group_ids` on res.users.
    svc = env['res.users'].create({
        'name': 'NETTRADES Service',
        'login': 'nettrades-service',
        'password': '!',  # No web login.
        'company_id': env.ref('base.main_company').id,
        'group_ids': [(6, 0, _resolved_groups)],
    })
    env.cr.commit()
    print(
        f"[configure-odoo-admin] service user created (uid={svc.id}, "
        f"groups={len(_resolved_groups)})",
        file=sys.stderr,
    )
else:
    # Existing service user — make sure it has all groups that currently
    # resolve. This is the "second pass" path that runs after
    # install-modules.sh has brought the nettrades_* modules online.
    _added = 0
    for _gid in _resolved_groups:
        svc.write({'group_ids': [(4, _gid)]})
        _added += 1
    if _added:
        env.cr.commit()
    print(
        f"[configure-odoo-admin] service user found (uid={svc.id}); "
        f"reconciled {_added} groups",
        file=sys.stderr,
    )


# -----------------------------------------------------------------------------
# Generate a fresh API key for the service user.
# -----------------------------------------------------------------------------
# The `_generate` method returns the plaintext key exactly once. We never
# store the plaintext in the database, so if this call fails, the admin must
# generate a new key manually through the Odoo UI.
#
# SIGNATURE-AWARE CALL (2026-10):
#   Odoo 18 and Odoo 19 ship different signatures for _generate. Rather than
#   hard-code the order, we inspect the method at runtime and pass only the
#   parameters it actually accepts. This avoids the "multiple values for
#   argument 'expiration_date'" error that arose when the 3rd positional
#   argument silently bound to `expiration_date` on our Odoo 19 build.
# -----------------------------------------------------------------------------
_apikey_plaintext = None
try:
    import inspect
    apikeys_model = env['res.users.apikeys']
    sig = inspect.signature(apikeys_model._generate)
    param_names = set(sig.parameters.keys())

    call_kwargs = {}
    # Odoo uses either `scope` or `name` for the human-readable key name.
    if 'name' in param_names:
        call_kwargs['name'] = 'nettrades-service'
    if 'scope' in param_names:
        call_kwargs['scope'] = 'nettrades-proxy'
    if 'user_id' in param_names:
        call_kwargs['user_id'] = svc.id
    if 'expiration_date' in param_names:
        call_kwargs['expiration_date'] = None

    _apikey_plaintext = apikeys_model._generate(**call_kwargs)
    print(
        f"[configure-odoo-admin] API key generated "
        f"(params={sorted(call_kwargs.keys())})",
        file=sys.stderr,
    )
except Exception as e:
    print(
        f"[configure-odoo-admin] API key generation failed: {e}. "
        f"The service user exists but has no API key. You can generate one "
        f"manually: Settings -> Users -> NETTRADES Service -> API Keys.",
        file=sys.stderr,
    )

# Emit outputs to stdout. The caller reads these lines with grep/cut.
# When API key generation failed, we still print the UID so the caller
# can record it; the API key line is simply omitted.
print(f"NETTRADES_SERVICE_UID={svc.id}")
if _apikey_plaintext:
    print(f"NETTRADES_SERVICE_API_KEY={_apikey_plaintext}")


PYEOF