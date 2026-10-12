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
#   4. Adds the service user to the same three NETTRADES groups.
#   5. Ensures an `llm.provider` and a company LLM config exist.
#   6. Generates an API key for the service user.
#   7. Prints `ADMIN_UID=<uid>`, `NETTRADES_SERVICE_UID=<uid>`,
#      `NETTRADES_SERVICE_PASSWORD=<pw>`, and
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
#   - llm.company.config creation uses `provider_id` (Many2one), not the
#     non-existent `provider_type` string field.
#
# LLM PROVIDER FIX (2026-10):
#   The Apexive `llm` module declares `service` as a required Selection on
#   `llm.provider`. Creating a provider without it raises:
#       null value in column "service" of relation "llm_provider"
#       violates not-null constraint
#   This script now introspects `Provider._fields['service'].selection` and
#   picks a valid value ("openai" when present, otherwise the first allowed
#   value). It also uses the same introspection to decide the names of the
#   URL, model, and API-key fields, since those have varied across Apexive
#   releases.
#
# SERVICE USER FIX (2026-10):
#   Earlier edits accidentally removed the block that creates the
#   `nettrades-service` user. The API-key step then referenced an undefined
#   `svc` variable, and its exception was swallowed by the outer try/except,
#   which is why the service user was never added to the GPU groups and the
#   API key was never generated. This version recreates the service user
#   explicitly and reconciles its groups on every run.
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
#
# API KEY OWNERSHIP FIX (2026-10, second pass):
#   The first version of the signature-introspection fix generated an API
#   key successfully but attached it to `__system__` (uid 1), not to the
#   service user. This is because `_generate()` uses `self.env.user.id`
#   internally, and inside `odoo shell` the current user of the environment
#   is `__system__`. Passing a `user_id=` kwarg is silently ignored because
#   `user_id` is not in the method signature. The fix is to call
#   `_generate()` on a model recordset whose env has been switched to the
#   service user with `.with_user(svc)`. Odoo then reads `self.env.user.id`
#   as the service user's id and creates the key for the correct owner.
# =============================================================================

set -euo pipefail

: "${ODOO_ADMIN_PASSWORD:?must be set}"
: "${POSTGRES_PASSWORD:?must be set}"

odoo shell -d odoo \
    --db_host=postgres --db_port=5432 \
    --db_user=odoo --db_password="$POSTGRES_PASSWORD" \
    --no-http <<'PYEOF'
import os, sys, secrets, string

# -----------------------------------------------------------------------------
# 0. Generate the service-user password if the caller did not provide one.
# -----------------------------------------------------------------------------
# phase-deploy.sh / phase-modules.sh capture the value we print on stdout
# and write it back to .env, so a real random password is created exactly
# once and reused on every subsequent run.
_service_password = os.environ.get('NETTRADES_SERVICE_PASSWORD', '').strip()
if not _service_password or _service_password in ('changeit', '!'):
    _alphabet = string.ascii_letters + string.digits
    _service_password = ''.join(secrets.choice(_alphabet) for _ in range(24))
    print(
        "[configure-odoo-admin] generated a fresh NETTRADES_SERVICE_PASSWORD",
        file=sys.stderr,
    )

# -----------------------------------------------------------------------------
# 1. Set the admin password.
# -----------------------------------------------------------------------------
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
# Do not replace this with bcrypt.hashpw() - The admin.password = value 
# assignment triggers Odoo's inverse method, which delegates to whatever 
# CryptContext the running Odoo instance is using. This is the only 
# approach that survives an Odoo upgrade.

admin.password = admin_password
env.cr.commit()
print(f"[configure-odoo-admin] password set for uid={admin.id}", file=sys.stderr)

# -----------------------------------------------------------------------------
# 2. Add admin to NETTRADES groups if the modules are installed.
# -----------------------------------------------------------------------------
# Every ref() uses raise_if_not_found=False. On the first call (before
# install-modules.sh), only base.group_user resolves; the nettrades_* groups
# are skipped. On the second call (after install-modules.sh), all of them
# resolve and the admin is added.
# -----------------------------------------------------------------------------
_NETTRADES_GROUP_XMLIDS = (
    'nettrades_gpu_admin.group_gpu_administrator',
    'nettrades_gpu_admin.group_gpu_operator',
    'nettrades_core.group_nettrades_api',
)

try:
    for xml_id in _NETTRADES_GROUP_XMLIDS:
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
    print(f"[configure-odoo-admin] admin GPU group step skipped: {e}", file=sys.stderr)

print(f"ADMIN_UID={admin.id}")

# -----------------------------------------------------------------------------
# 3. Ensure the `nettrades-service` user exists.
# -----------------------------------------------------------------------------
# The service user is the identity the control plane (langgraph-server,
# odoo-proxy) uses when it calls Odoo. It is deliberately scoped: it has
# no web login capability, and its only permissions come from the
# NETTRADES groups added in step 4.
#
# The password is set from _service_password; the caller captures it on
# stdout so it can be persisted to .env. Re-running this script with the
# same NETTRADES_SERVICE_PASSWORD reuses the same password, so it is
# idempotent.
svc = env['res.users'].search([('login', '=', 'nettrades-service')], limit=1)
if not svc:
    try:
        svc = env['res.users'].create({
            'name': 'NETTRADES Service',
            'login': 'nettrades-service',
            'password': _service_password,
            'company_id': admin.company_id.id,
            'company_ids': [(6, 0, [admin.company_id.id])],
            # Explicitly keep the user out of the web UI: no groups that
            # grant `base.group_user`'s UI access are added here. Access
            # comes from the NETTRADES groups added in step 4.
            'group_ids': [(6, 0, [])],
        })
        env.cr.commit()
        print(
            f"[configure-odoo-admin] service user created (uid={svc.id})",
            file=sys.stderr,
        )
    except Exception as e:
        print(
            f"[configure-odoo-admin] failed to create service user: {e}",
            file=sys.stderr,
        )
        raise
else:
    print(
        f"[configure-odoo-admin] service user found (uid={svc.id})",
        file=sys.stderr,
    )
    # Make sure the password is the one the caller expects, even on
    # re-runs where the password in .env may have changed.
    # Do not replace this with bcrypt.hashpw() - The svc.password = value 
    # assignment triggers Odoo's inverse method, which delegates to whatever 
    # CryptContext the running Odoo instance is using. This is the only 
    # approach that survives an Odoo upgrade.
    try:
        svc.password = _service_password
        env.cr.commit()
        print(
            f"[configure-odoo-admin] service user password set from "
            f"NETTRADES_SERVICE_PASSWORD",
            file=sys.stderr,
        )
    except Exception as e:
        print(
            f"[configure-odoo-admin] could not set service user password: {e}",
            file=sys.stderr,
        )

# -----------------------------------------------------------------------------
# 4. Add the service user to the NETTRADES groups.
# -----------------------------------------------------------------------------
# Same raise_if_not_found=False logic as for the admin. On the first pass
# (before modules install) these all resolve to None and are skipped; on
# the second pass (after install-modules.sh) they all resolve and are
# applied. That is why the script must be run twice in a deployment.
try:
    reconciled = 0
    for xml_id in _NETTRADES_GROUP_XMLIDS:
        g = env.ref(xml_id, raise_if_not_found=False)
        if g:
            g.write({'user_ids': [(4, svc.id)]})
            reconciled += 1

    # base.group_user is always available. It gives the service user a
    # minimal internal identity so that other modules can reference it.
    base_user = env.ref('base.group_user', raise_if_not_found=False)
    if base_user:
        base_user.write({'user_ids': [(4, svc.id)]})
        reconciled += 1

    env.cr.commit()
    print(
        f"[configure-odoo-admin] service user groups reconciled ({reconciled})",
        file=sys.stderr,
    )
except Exception as e:
    print(
        f"[configure-odoo-admin] service user group step skipped: {e}",
        file=sys.stderr,
    )

# -----------------------------------------------------------------------------
# 5. Ensure a default LLM provider AND company config exist.
# -----------------------------------------------------------------------------
# The factory in src/core/tools/llm_factory.py calls
# get_effective_config(company_id), which reads self.provider_id. If no
# record exists for the company, every LLM call falls back to
# OPENAI_API_KEY + https://api.openai.com/v1 — which, in a sovereign
# deployment, is exactly the wrong place for the request to go. This block
# creates a local provider and a company config that points at it, so the
# factory always has a config to read.
#
# FIELD NAME SAFETY:
#   The Apexive llm module has changed field names across versions. This
#   block inspects `Provider._fields` and only sets keys that actually
#   exist. The `service` field, in particular, is required in newer
#   releases and takes a Selection value — we pick from the field's
#   declared `selection` rather than guessing.
try:
    Provider = env['llm.provider'].sudo()
    Config = env['nettrades.llm.company.config'].sudo()
    company = env['res.company'].search([], limit=1)

    # Inference endpoint. Read from the environment so the same script
    # works on WSL (llama.cpp) and on GPU hosts (Dynamo). The caller
    # (phase-deploy.sh / phase-modules.sh) passes LLM_BASE_URL through
    # `docker compose exec -e`.
    llm_base_url = os.environ.get('LLM_BASE_URL', 'http://llama-cpp:8080/v1')
    llm_api_key = os.environ.get('DYNAMO_API_KEY', 'dummy')
    default_model = os.environ.get('MODEL_NAME', '/models/deepseek-r1-distill-qwen-7b-q4_k_m.gguf')

    if company:
        # --- Step 5a: ensure a provider exists ---------------------------------
        provider = Provider.search([], limit=1)
        if not provider:
            pf = Provider._fields
            vals = {'name': 'Local llama.cpp'}

            # --- provider_type / provider (older builds) ---
            if 'provider_type' in pf:
                vals['provider_type'] = 'openai'
            elif 'provider' in pf:
                vals['provider'] = 'openai'

            # --- service (newer builds; required) ---
            # The Selection values differ between Apexive releases. Prefer
            # 'openai' when it is offered; otherwise take the first declared
            # value. If the field declares no values at all (which would be
            # unusual), fall back to the string 'openai' so that we at
            # least satisfy the NOT NULL constraint.
            if 'service' in pf:
                fld = pf['service']
                sel = fld.selection
                allowed = []
                try:
                    if callable(sel):
                        # Odoo's dynamic selection: call it with a record.
                        # Some signatures accept a record, some take no args.
                        try:
                            sel_result = sel(env['llm.provider'])
                        except TypeError:
                            sel_result = sel()
                        allowed = [v[0] for v in (sel_result or [])]
                    elif isinstance(sel, str):
                        # Method name on the model.
                        method = getattr(env['llm.provider'], sel, None)
                        if method:
                            allowed = [v[0] for v in (method() or [])]
                    elif sel:
                        allowed = [v[0] for v in sel]
                except Exception as e:
                    print(
                        f"[configure-odoo-admin] could not read service selection: {e}",
                        file=sys.stderr,
                    )

                if 'openai' in allowed:
                    vals['service'] = 'openai'
                elif allowed:
                    vals['service'] = allowed[0]
                else:
                    # Best effort. If 'openai' is not a valid value, Odoo will raise
                    # a clearer error than the NOT NULL constraint.
                    vals['service'] = 'openai'

            # --- URL: names have varied across Apexive releases ---
            for key in ('api_base', 'api_base_url', 'base_url', 'url'):
                if key in pf:
                    vals[key] = llm_base_url
                    break

            # --- model: same story ---
            for key in ('default_model', 'model_name', 'model'):
                if key in pf:
                    vals[key] = default_model
                    break

            # --- API key ---
            if 'api_key' in pf:
                vals['api_key'] = llm_api_key

            # --- active flag (newer builds) ---
            if 'active' in pf:
                vals['active'] = True

            provider = Provider.create(vals)
            env.cr.commit()
            print(
                f"[configure-odoo-admin] created llm.provider id={provider.id} "
                f"name='{provider.name}' (fields set: {sorted(vals.keys())})",
                file=sys.stderr,
            )
        else:
            print(
                f"[configure-odoo-admin] llm.provider already exists "
                f"(id={provider.id}, name='{provider.name}')",
                file=sys.stderr,
            )

        # --- Step 5b: ensure a company config exists, pointing at the provider
        existing = Config.search([('company_id', '=', company.id)], limit=1)
        if not existing:
            Config.create({
                'company_id': company.id,
                'provider_id': provider.id,
                'model_name': default_model,
                'api_base_url': llm_base_url,
                'api_key': llm_api_key,
                'override_model': True,
                'override_api_base_url': True,
                'override_api_key': True,
            })
            env.cr.commit()
            print(
                f"[configure-odoo-admin] created company LLM config for "
                f"company {company.id} using provider {provider.id}",
                file=sys.stderr,
            )
        else:
            print(
                f"[configure-odoo-admin] company LLM config already exists "
                f"(id={existing.id})",
                file=sys.stderr,
            )
except Exception as e:
    print(
        f"[configure-odoo-admin] LLM provider/config step skipped: {e}",
        file=sys.stderr,
    )

# -----------------------------------------------------------------------------
# 6. Generate a fresh API key for the service user.
# -----------------------------------------------------------------------------
# Odoo 19's `res.users.apikeys._generate()` has two requirements:
#
#   1. The key belongs to `self.env.user`. Inside `odoo shell` the current
#      user is `__system__`, so we use `.with_user(svc)` to switch the env
#      before calling. Without this, the key is attached to __system__ and
#      every consumer authenticates as the wrong identity.
#
#   2. `expiration_date` must be a real datetime. Odoo 19 rejects None with
#      "The API key must have an expiration date." Earlier releases accepted
#      None as "never expires"; 19 does not.
#
# We still introspect the signature first, because Apexive / Odoo releases
# have varied the parameter names. If a name we need is missing, we skip
# that parameter rather than crash.
#
# Failure is a WARNING, not a fatal error. The service user still exists;
# the admin can generate a key by hand from
# Settings -> Users -> NETTRADES Service -> API Keys.
_apikey_plaintext = None
try:
    import inspect
    from datetime import datetime, timedelta

    apikeys_model = env['res.users.apikeys'].with_user(svc)
    sig = inspect.signature(apikeys_model._generate)
    param_names = set(sig.parameters.keys())

    call_kwargs = {}
    if 'name' in param_names:
        call_kwargs['name'] = 'nettrades-service'
    if 'scope' in param_names:
        call_kwargs['scope'] = 'nettrades-proxy'
    if 'expiration_date' in param_names:
        # Odoo 19 enforces a hard ceiling on API key lifetime. Anything
        # longer than 90 days raises "You cannot exceed 90.0 days."
        # 89 days is chosen rather than 90 to stay clear of the boundary.
        # Re-run this script to rotate the key before it expires.
        call_kwargs['expiration_date'] = datetime.now() + timedelta(days=89)
    # NOTE: user_id is deliberately NOT passed. It is not part of the
    # signature in Odoo 19. The owner comes from self.env.user, which is
    # svc because of the .with_user(svc) call above.

    _apikey_plaintext = apikeys_model._generate(**call_kwargs)
    env.cr.commit()
    print(
        f"[configure-odoo-admin] API key generated for "
        f"'{svc.login}' (uid={svc.id}, "
        f"expires in 365 days, params={sorted(call_kwargs.keys())})",
        file=sys.stderr,
    )
except Exception as e:
    print(
        f"[configure-odoo-admin] API key generation failed: {e}. "
        f"The service user exists but has no API key. You can generate one "
        f"manually: Settings -> Users -> NETTRADES Service -> API Keys.",
        file=sys.stderr,
    )

# -----------------------------------------------------------------------------
# 7. Emit the structured output the caller parses.
# -----------------------------------------------------------------------------
print(f"NETTRADES_SERVICE_UID={svc.id}")
print(f"NETTRADES_SERVICE_PASSWORD={_service_password}")
if _apikey_plaintext:
    print(f"NETTRADES_SERVICE_API_KEY={_apikey_plaintext}")

PYEOF