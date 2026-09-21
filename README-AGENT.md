# README-AGENT

## What this project is

The NETTRADES Sovereign AI Platform. A distributed, self-hosted AI
platform for enterprises and individuals. Combines:

- Odoo CE as the business management plane
- LangGraph as the agent orchestration layer
- NVIDIA Dynamo + llama.cpp RPC as the distributed inference layer
- An Electron Launcher for one-click deployment

## Reading order

1. **`README.md`** — what the platform does, who it's for
2. **`HANDOFF.md`** — current state, error classes, daily workflow
3. **`ARCHITECTURE-AND-PLAN.md`** — Mermaid diagrams, distributed
   inference instructions, build plan
4. **`DECISIONS.md`** — architectural decisions with reasons
5. **`KNOWN-ISSUES.md`** — deferred work, do not re-fix
6. **`ENVIRONMENT.md`** — dev environment reference
7. **`VERIFICATION.md`** — acceptance criteria

## The current blocker

As of the last update (2026-09-18), the platform installs 10 of 12
modules. Two failures remain:

- `nettrades_gpu_admin` — `AssertionError: is_model_definition(model_def)`
  during model registration. See `HANDOFF.md` §3 for the diagnostic flow.
- `nettrades_bridge` — cascades from `nettrades_gpu_admin` (it's a
  dependency).

Fix `nettrades_gpu_admin` first. Then `nettrades_bridge` will install.

## Rules you must follow

1. **Always use `git` for every change.** Never edit a file and leave
   it uncommitted. The user's history matters.

2. **Verify before you commit.** Every Python file must parse with
   `python3 -c "import ast; ast.parse(open(...).read())"`. Every XML
   file must parse with `xml.etree.ElementTree`. No non-ASCII characters
   in `.py`, `.xml`, `.csv` files.

3. **Never use `docker compose restart` after `prepare-odoo-addons.sh`.**
   The bind mount references the old directory inode. Use
   `docker compose stop odoo && docker compose rm -f odoo && docker compose up -d odoo`.

4. **Never pipe `install-modules.sh` output through `tail` during
   execution.** `tail` buffers everything; you won't see failures in
   real time. Use `2>&1 | tee /tmp/install.log` and read the log after.

5. **Never bypass `prepare-odoo-addons.sh`.** Its manifest validator
   is the safety net. If it fails, fix the manifest — do not delete
   the file it's complaining about.

6. **Never modify `.env` manually during a run.** The setup scripts
   manage it. If you need to change secrets, edit the template and
   re-run setup with `--regenerate-secrets`.

7. **Never assume a model field exists because a view references it.**
   Grep the model first. Views fail loudly at install time.

8. **Never assume a comodel exists because it's referenced.** Grep
   `_name = '...'` across `odoo-modules/` to find the model's home
   module.

9. **When in doubt, ask the user.** Do not guess. Do not "improve"
   the architecture without discussing it.

10. Always provide honest answers.

## The one rule that matters most

The user has been through a long debugging session. They are patient
but they want you to be efficient. Do not repeat the same error twice.
Read the docs above. Understand the state. Fix one thing at a time.
Report back with evidence.

If you get stuck, ask the user to paste the full traceback. Do not
guess at the cause.

## Reporting template

When you finish a task, report:

1. What you changed (files + one-line summary per file)
2. What you verified (commands + expected outputs)
3. What still fails (if anything)
4. What you'd do next

Keep it short. Show commands and outputs.