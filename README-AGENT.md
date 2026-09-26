# README-AGENT

## 1. What this project is

The NETTRADES Sovereign AI Platform. A distributed, self-hosted AI platform for enterprises and individuals. Combines:

- Odoo CE as the business management plane
- LangGraph as the agent orchestration layer
- NVIDIA Dynamo + llama.cpp RPC as the distributed inference layer
- An Electron Launcher for one-click deployment

## Reading order

1. **`README.md`** — what the platform does, who it's for
2. **`HANDOFF.md`** — says what the codebase is
3. **`BUG-CATALOG.md`** — says what's broken.
4. **`ARCHITECTURE-AND-PLAN.md`** — Mermaid diagrams, distributed
   inference instructions, build plan
5. **`DECISIONS.md`** — architectural decisions with reasons
6. **`KNOWN-ISSUES.md`** — deferred work, do not re-fix
7. **`ENVIRONMENT.md`** — dev environment reference
8. **`VERIFICATION.md`** — acceptance criteria



## 2. Rules you must follow

1. **Always use `git` for every change.** Never edit a file and leave it uncommitted. The user's history matters.

2. **Verify before you commit.** Every Python file must parse with `python3 -c "import ast; ast.parse(open(...).read())"`. Every XML file must parse with `xml.etree.ElementTree`. No non-ASCII characters in `.py`, `.xml`, `.csv` files.

3. **Never use `docker compose restart` after `prepare-odoo-addons.sh`.** The bind mount references the old directory inode. Use `docker compose stop odoo && docker compose rm -f odoo && docker compose up -d odoo`.

4. **Never pipe `install-modules.sh` output through `tail` during execution.** `tail` buffers everything; you won't see failures in real time. Use `2>&1 | tee /tmp/install.log` and read the log after. 

5. **Never bypass `prepare-odoo-addons.sh`.** Its manifest validator is the safety net. If it fails, fix the manifest — do not delete the file it's complaining about. 

6. **Never modify `.env` manually during a run.** The setup scripts manage it. If you need to change secrets, edit the template and re-run setup with `--regenerate-secrets`.

7. **Never assume a model field exists because a view references it.** Grep the model first. Views fail loudly at install time.

8. **Never assume a comodel exists because it's referenced.** Grep `_name = '...'` across `odoo-modules/` to find the model's home module.

9. **When in doubt, ask the user.** Do not guess. Do not "improve" the architecture without discussing it.

10. Always provide honest answers. Not "great job!" — actual status. If something is broken, say so. If a fix is not verified, say so.

11. Do not provide quick fixes. Prefer complete fixes even if they take longer.

12. DO NOT REMOVE EXISTING FUNCTIONALITY THAT IS STILL NEEDED AND WORKING UNLESS ASKED TO DO SO. A very long time and a lot of effort has been invested in building the functionality.

13. DO NOT REMOVE EXISTING COMMENTS. Comments preserve context for future developers and sessions. Every regenerated file has kept its original comments and added new ones. Match this style.

14. Regenerate full files when asked for regenerated code. Keep all the existing comments and functionality that is still needed and working unless asked to remove it.

    

## The one rule that matters most

The user has been through a long debugging session. They are patient but they want you to be efficient. Read the docs above. Understand the state. Fix one thing at a time. Report back with evidence.

If you get stuck, ask the user to paste the full traceback. Do not guess at the cause.

## Reporting template

When you finish a task, report:

1. What you changed (files + one-line summary per file)
2. What you verified (commands + expected outputs)
3. What still fails (if anything)
4. What you'd do next

Keep it short. Show commands and outputs.


If you propose a fix, be explicit about whether it blocks the current milestone. 


### When to do a fix immediately

* Anything that prevents `prepare-odoo-addons.sh` from completing.

* Anything that prevents `install-modules.sh` from exiting 0.

* Anything that changes the verified state (13/13).
    
* Anything that will stop the GPUs from being detected and the distributed inferencing from working. 

### File-level conventions in this codebase

* **Every Python file** has a header comment with `FILE: path/to/file`. Preserve this.

* **Every model** uses `_name` and often `_description` on separate lines.

* **Views** are in `views/`, models in `models/`, security in `security/`, data (cron etc.) in `data/`.

* **Menuitems** should be in a dedicated file, loaded last in the manifest's `data` array. Never inline them before their actions.

* `_inherit` is used for mixins (e.g. `mail.thread`, `mail.activity.mixin`).




## 3. Environment & Toolchain

### Host

- **OS:** Windows 11 + WSL2 (Ubuntu 24.04).
- **Working directory (WSL):** `/home/owner/nettrades-platform`
- **Windows path:** `\\wsl.localhost\Ubuntu-24.04\home\owner\nettrades-platform`
- **GPU:** NVIDIA GeForce RTX 5070 Ti (Blackwell, consumer).
- **Node:** 20.20.2 (npm 10.8.2). Note: some Electron packages warn they
  want Node ≥22. The Launcher still builds; not urgent.
- **Python:** 3.12.3 (system) + `.venv` per project.

Also 
- Contabo Dedicated Server
- **OS:** Ubuntu 24.04.


### Infrastructure State

#### Docker / deployment

- **Base image**: `odoo:19.0` (Debian-based).
- **Postgres**: `pgvector/pgvector:pg17`.
- **Compose project name**: `docker` (so containers are `docker-odoo`,
  `docker-postgres-1`, etc.).
- **Compose file**: `deploy/docker/docker-compose.yaml`.
- **Env file**: `deploy/docker/.env` (real secrets, not in git).
- **Template**: `deploy/docker/.env.example`.

#### How modules get into the container

Modules are **baked into the image**, not volume-mounted:

- `prepare-odoo-addons.sh` copies everything into `deploy/docker/odoo-modules/`.
- `Dockerfile.odoo` does `COPY odoo-modules/ /mnt/extra-addons/`.
- Therefore, any change to a module source file requires:
1. `./scripts/prepare-odoo-addons.sh --force`
2. `docker compose build odoo`
3. `docker compose stop odoo && docker compose rm -f odoo && docker compose up -d odoo`

Editing a module source and only recreating the container (without
rebuilding the image) will **not** pick up the change.

#### Dockerfile.odoo structure

Two-stage pip install. **Do not collapse into one stage.**

- **Stage 1**: pre-installs `typing-extensions`, `idna`, `charset-normalizer` with `--ignore-installed` so they shadow the Debian copies. This is needed because Debian installs these without RECORD files, and pip cannot uninstall them.

- **Stage 2**: installs `pandas`, `numpy`, `scikit-learn`, `requests`, `openai`, `anthropic`, `pdfplumber` **without** `--ignore-installed`. Using `--ignore-installed` here forces pip to upgrade `cryptography`, which breaks the Debian-provided `pyOpenSSL 23.2.0` and causes:

```text

AttributeError: module 'lib' has no attribute 'GEN_EMAIL'

```

This was the single biggest time sink of the debugging session.

**Never add `--ignore-installed` to stage 2.**

---

### Shell quirks observed

These are not bugs in the project; they are characteristics of the working environment. A fresh window should be aware of them so it doesn't chase phantom problems.

1. **Terminal paste has occasionally mangled multi-line commands.** In the
   logs, commands like:
   
```
owner@...:~/nettrades-platform/deploy/docker$ "SELECT name, state FROM ir_module_module WHERE name = 'nettrades_onboarding';"
SELECT name, state FROM ir_module_module WHERE name = 'nettrades_onboarding';: command not found

```


This means the newline was lost during paste, so the second line was interpreted as a command. If you see "command not found" for something that looks like valid shell syntax, ask the owner to paste one line at a time. Don't assume the owner is confused.

2. **WSL path escaping.** `cd deploy\docker\odoo-modules` fails because WSL treats backslashes literally. If you ask the owner to run a `cd`, use forward slashes.

3. **Timestamps in logs are UTC.** Local time is UTC+1 (UK BST). When reading logs, the timestamps may not match what the owner thinks of as "now". This is fine; don't try to reconcile.

### Docker environment

- **Compose project name:** `docker` (from the folder name `deploy/docker/`).
- **All containers:** prefixed `docker-`. E.g. `docker-odoo`, `docker-postgres-1`, `docker-traefik-1`.
- **Compose file:** `deploy/docker/docker-compose.yaml`.
- **Most commands:** must be run from `deploy/docker/`, not project root.
- **`prepare-odoo-addons.sh`:** run from project root (it does its own `cd`). It also accepts `--force`.



## 4. Odoo Modules


### How to add a field to a Odoo model and expose it in a view

1. Add the field in `models/*.py`.

2. Add `<field name="X"/>` to the view XML.

3. Add the new XML file to `__manifest__.py` if it's a new view.

4. Check any file that defines both menuitems and actions. Menuitems should be after actions.

### Key commands

Every change to a Odoo module source requires the same three-step dance:

```bash
# 1. From project root: copy sources into Docker build context
./scripts/prepare-odoo-addons.sh --force

# 2. From deploy/docker/: rebuild the image (pip stages are cached)
cd deploy/docker && docker compose build odoo

# 3. From deploy/docker/: recreate the container
docker compose stop odoo && docker compose rm -f odoo && docker compose up -d odoo

# 4. Wait for Odoo to boot, then run the installer
sleep 15
cd ~/nettrades-platform && ./scripts/install-modules.sh --force --auto

```

`Do not skip step 2`. Editing module source and only recreating the container does nothing — modules are baked into the image, not volume-mounted.




## 5. Daily Workflow

Every time you edit a module and want to test:

```bash

cd ~/nettrades-platform

# 1. Verify the file parses (Python)

python3 -c "import ast; ast.parse(open('odoo-modules/<mod>/models/<file>.py').read())" && echo "OK"

# 2. Verify the file parses (XML)

python3 -c "import xml.etree.ElementTree as ET; ET.parse('odoo-modules/<mod>/views/<file>.xml')" && echo "OK"

# 3. Verify no non-ASCII crept in

grep -nP '[^\x00-\x7F]' odoo-modules/<mod>/models/<file>.py odoo-modules/<mod>/views/<file>.xml

# 4. Rebuild the deploy tree (validator will fail loudly if manifests drift)

./scripts/prepare-odoo-addons.sh --force

# 5. Restart Odoo (bind mounts must be re-attached after prepare)

cd deploy/docker
docker compose stop odoo && docker compose rm -f odoo && docker compose up -d odoo
sleep 12
cd ../..

# 6. Install just the module you changed

./scripts/install-modules.sh --force --auto --modules=<mod> 2>&1 | tail -30

# 7. If it fails, read the log

LATEST=$(ls -t logs/install-modules-*.log | head -1)
LINE=$(grep -n "Traceback\|AssertionError\|ValueError\|ParseError" "$LATEST" | head -1 | cut -d: -f1)
sed -n "$((LINE - 20)),$((LINE + 40))p" "$LATEST"

```


**Critical:** Always use `docker compose stop/rm/up`, not docker compose restart. The bind mount to `deploy/docker/odoo-modules/` references an inode. After `prepare-odoo-addons.sh` deletes and recreates the directory, the old inode is gone and `restart` doesn't re-attach. Stop/rm/up forces a fresh mount.






### Pre-Flight Validation for Odoo Modules (`prepare-odoo-addons.sh`)

Run this **before** any `docker compose build`. If it fails, do not rebuild.

### Checks that run, in order

1. **Manifest validation**: every file referenced in every `__manifest__.py` exists. Fail-loud. Aborts.
2. **XML parse**: every `.xml` parses with Python's ElementTree. Aborts.
3. **Python compile**: every `.py` compiles. Aborts.
4. **`attrs=` / `states=` check**: two-tier. Strips XML comments first, then looks for the literal attribute names. Warns (does not abort). See below. 
5. **`<group expand>` check**: warns only.
6. **UTF-8 verification**: two-tier. Aborts on project-owned files, warns on  vendored files. See §4.2.
7. **Line-ending conversion** (dos2unix).
8. **Module count**.

### The attrs= check is advisory

Odoo 19 still loads views with `attrs=` and emits a deprecation warning. Only `<group expand="0">` inside `<search>` is a hard failure. Blocking the build on `attrs=` was tried and reverted — it prevented the UTF-8 check from running.

**Current state**: all six previously-flagged files are now clean. The check still runs; it should produce no output.

### The UTF-8 check is two-tier

This is important and not obvious.

- **`nettrades_*` files** (project-owned): hard error on non-UTF-8. Aborts.
- **Everything else** (vendored): warning. Does not abort.

The rationale: a non-UTF-8 byte in project code is a bug you introduced and want to catch. A non-UTF-8 byte in vendored code is an upstream defect that only matters if the module is loaded. It should not block your build.

The check catches:
- Windows-1252 em-dash (`0x97`)
- Windows-1252 en-dash (`0x96`)
- Curly quotes (`0x91`–`0x94`, `0x96`–`0x97`)
- Any other non-UTF-8 byte

**If Odoo ever reports `manifest not found` for a module that visibly has a manifest**, run this:

```bash
docker compose exec -T odoo python3 -c "
import ast
with open('/mnt/extra-addons/MODULE/__manifest__.py', 'rb') as f:
  content = f.read()
try:
  ast.literal_eval(content.decode('utf-8'))
  print('Parses OK')
except Exception as e:
  print('PARSE ERROR:', type(e).__name__, '-', e)
"
```

That is the exact same code path Odoo uses. If it fails, you have a non-UTF-8 byte. This diagnostic found the problem in minutes after four rounds of guessing.

### What the pre-flight does NOT catch

* **Duplicate XML IDs across files.** If `config_views.xml` and `self_improving_config_views.xml` both declare `id="view_self_improving_config_form"`, only the one in the manifest matters. See §5 for a live instance of this.

* **Nested view model mismatch.** A `<field>` inside a nested list is checked against the outer model by the audit script. False positives for One2many/Many2many views.

* **Missing method references in buttons.** `action_parse_cv` on a button is only validated when the button is clicked, not at install.





### Diagnose a module that fails to install

1. Read the last 40 lines of the install log at logs/install-modules-*.log.

2. If the error is manifest not found, run the ast.literal_eval check from §4.2.

3. If the error mentions an XML file at a line number, look at that exact line. Common causes: `attrs=` inside `<field>`, references to

4. non-existent fields, menuitem before action.

    If the module is marked `not installable, skipped`, reset its DB state:
```sql

    UPDATE ir_module_module SET state = 'uninstalled' WHERE name = 'MODULE';
```
    Then rerun the installer.

### Confirm that a module actually installed (not just reported as success)

Before `install-modules.sh` had the grep check, it would report success on modules that Odoo skipped. Now it catches them. But to double-check:

```bash

docker compose exec -T postgres psql -U odoo -d odoo -c \
  "SELECT name, state FROM ir_module_module WHERE name LIKE 'nettrades_%' ORDER BY name;"
```

Every row should have `state = 'installed'`.



### Troubleshooting Playbook for Odoo Modules

Use this when a module fails to install. The classes of error are finite; each has a signature.

### Error Class 1 — `No matching record found for external id 'model_xxx'`

**Symptom:**

```text

Exception: Module loading <mod> failed: file <mod>/security/ir.model.access.csv could not be processed:
No matching record found for external id 'model_xxx'

```

**Cause:** The CSV's `model_id:id` column references a model that doesn't exist, or the model's _name doesn't match.

**Fix:**

1.     Grep for the actual `_name` values in the module:
```bash

    grep -hE "^\s*_name\s*=" odoo-modules/<mod>/models/*.py | sed -E "s/.*'([a-z_.]+)'.*/\1/"
```
2. For each, the correct XML ID is `model_<name_with_underscores>`.

3. Update the CSV accordingly.

Recent examples fixed: `nettrades_good_answer`, `nettrades_data_collection`, `nettrades_llm_config`.

### Error Class 2 — `Field "X" does not exist in model "Y"`

**Symptom:**

```text

odoo.tools.convert.ParseError: while parsing .../views/<file>.xml
Error while validating view near:
    <field name="X"/>
Field "X" does not exist in model "Y"
```

**Cause:** A view references a field that the model doesn't declare.

**Fix — three options:**

1. **Rename in the view** — the field exists under a different name:

```bash

    grep -n "def _name\|= fields\." odoo-modules/<mod>/models/<model>.py | grep -i "keyword"
```

2. **Add the field to the model** if it's genuinely needed.

3. **Remove the field from the view** if it's obsolete.

**Recent examples fixed:** `last_audit_date` on `nettrades.fairness.config` (added as computed field), `response_id` on `nettrades.fairness.audit` (changed to Integer).

### Error Class 3 — `AssertionError: Field X with unknown comodel_name 'Y'`

**Symptom:**

```text

File ".../fields_relational.py", line 93, in setup_nonrelated
    assert self.comodel_name in model.pool, \
AssertionError: Field <model>.<field> with unknown comodel_name '<comodel>'

```

**Cause:** A Many2one, One2many, or Many2many field points at a model that isn't loaded.

**Fix — two options:**

1. **Add the module containing the comodel to** `depends`:

```bash

    grep -rn "_name = '<comodel>'" odoo-modules/

```

That tells you which module owns it. Add that module to depends.

2. **Change the comodel** to a model that's already loaded, or remove the field.

**Recent examples fixed:** `simulation.session` in `nettrades_data_collection`, `llm.assistant.message` in `nettrades_fairness`.


### Error Class 4 — `AssertionError` (bare) in `add_to_registry`

**Symptom:**

```text

File ".../model_classes.py", line 157, in add_to_registry
    assert is_model_definition(model_def)
AssertionError
```


**Cause:** A class in the module's namespace inherits a base model with an invalid _name / _inherit combination. **This is what's currently blocking** nettrades_gpu_admin.

**Fix:** See above for the full diagnostic flow. The most common causes:

* Model declared with _name twice

* Class inheriting both models.Model and models.TransientModel

* _inherit set to a Python class rather than a string

* Model name clashes with an already-loaded module

### Error Class 5 — ValueError: Invalid field 'X' in 'model'

**Symptom:**

```text

File ".../odoo/orm/models.py", line 4660, in create
    raise ValueError(f"Invalid field {field_name!r} in {self._name!r}")
ValueError: Invalid field 'X' in 'model'

```

**Cause:** Usually in an XML data file — a <record> or <field> that references a nonexistent field on the model. In res.groups specifically, Odoo 19 removed category_id.

**Fix:** Remove the invalid field reference from the XML.

**Recent example fixed:** `category_id` in `nettrades_fairness/security/fairness_security.xml` (three occurrences).

### Error Class 6 — Syntax errors

**Symptom:**

```text

SyntaxError: 'return' outside function
```

or

```text

SyntaxError: invalid syntax
```

**Cause:** Editing accidents — a `def` line was deleted, indentation was wrong, or a stray character crept in.

**Fix:** Run Python's parser on the file:

```bash

python3 -c "import ast; ast.parse(open('<file>').read())"
```

That gives you the exact line number.

Recent examples fixed: `nettrades_ask_someone/controllers/main.py`, `nettrades_fairness/models/fairness_config.py`.

### Error Class 7 — XML schema / RNG validation

**Symptom:**

```text

odoo.tools.convert: The XML file '<file>' does not fit the required schema!
AssertionError: Element odoo has extra content: <tag>, line N
```

**Cause:** The XML has a construct that Odoo 19's RelaxNG schema rejects. Common culprits:

    CDATA blocks in `<field name="help">` (must be plain XML)

    Deprecated `<tree>` tag (use `<list>` in Odoo 17+)

    Unescaped `<`, `>`, `&` inside attribute values (use `&lt;`, `&gt;`, `&amp;`)

**Fix:** Reorder, escape, or remove.

**Recent examples fixed:** `nettrades_core` view files (CDATA removed, `<tree>` → `<list>`).

### Error Class 8 — Duplicate XML ID

**Symptom:**

```text

Duplicate id '<xmlid>' in module <module>
```

**Cause:** Two files in the same module declare the same id on a <record>, <menuitem>, etc.

**Fix:**

```bash

grep -rn 'id="<xmlid>"' odoo-modules/<module>/
```

Remove one of them.

Recent example fixed: `menu_fairness_audit_log` declared in both `fairness_dashboard_views.xml` and `fairness_config_views.xml`.

### Error Class 9 — Non-UTF-8 characters

**Symptom:**

```text

UnicodeDecodeError: 'utf-8' codec can't decode byte 0x97 in position NNN
```

or

```text

grep: <file>: binary file matches
file: <file>: Non-ISO extended-ASCII text
```

**Cause:** A file was saved with Windows-1252 encoding instead of UTF-8. Usually from pasting from a browser or Word.

**Fix:** Run the normalization script (see scripts/normalize-encoding.py if it exists; otherwise re-save the file from WSL VS Code):

```bash

python3 -c "
from pathlib import Path
p = Path('<file>')
text = p.read_bytes().decode('cp1252', errors='replace')
for a, b in [('\u2014', '-'), ('\u2019', \"'\"), ('\u201c', '\"'), ('\u201d', '\"'), ('\u00d7', 'x')]:
    text = text.replace(a, b)
p.write_text(text, encoding='utf-8')
print('Fixed:', p)
"
```

### Error Class 10 — `Module not found` for a dependency

**Symptom:**

```text

module <mod>: <dep> is not installed
```

or the module silently fails with no visible error.

**Cause:** The depends list references a module that isn't installed and isn't in the install order.

**Fix:** Check install-modules.sh:

```bash

grep -A15 "MODULES=(" scripts/install-modules.sh
```

Add the missing dependency before the module that needs it.



### Diagnostic Playbook for Odoo Modules

Symptom → action. Ordered by frequency across the session.

| Symptom | First check | Likely cause |
|---|---|---|
| `manifest not found` for a module with a visible manifest | `ast.literal_eval` UTF-8 check (see below) | Non-UTF-8 byte (Windows-1252 em-dash, etc.) |
| `AttributeError: module 'lib' has no attribute 'GEN_EMAIL'` |	`docker exec odoo python3 -c "import cryptography, OpenSSL; print(cryptography.__version__, OpenSSL.__version__)"` | `cryptography 50.x` shadowing `pyOpenSSL 23.2.0`. See `HANDOFF.md §2` for the fix — never re-add `--ignore-installed` to stage 2 of `Dockerfile.odoo`. |
| `ParseError: Since 17.0, the "attrs" and "states" attributes are no longer used` | grep for `attrs=` in the offending file | Migrate to `invisible="not x"` |
| `RELAXNG_ERR_INVALIDATTR: Invalid attribute expand for element group` | Search for `<group expand=` inside `<search>` | Remove the `<group>` wrapper; promote filters to top level |
| `External ID not found in the system: <module>.<action>` | Check if the `<menuitem>` appears before its `<action>` in the same file, or if the action is in a later-loaded file | Move menuitems to end of file or to a dedicated `menu_views.xml` loaded last |
| `ValueError: Invalid field 'doall' in 'ir.cron'` | grep for `doall numbercall` in the cron XML | Both fields removed in Odoo 17 |
| `ValueError: Invalid field name 'access_...'` | Check the first line of the CSV | ir.model.access.csv missing header row |
| `WARNING: module X: not installable, skipped` and no error | 	Query `ir_module_module` for its state | Stuck in `to install` from a prior failure. Reset with SQL (see below). |
| `AttributeError: 'x' object has no attribute '_y'` on model class | grep for `def __init__` in the model | Odoo 19 forbids instance state on models. Move to module-level dict. |
| Button does nothing on click | grep for the button's `name=` in the model | Button calls a controller method or a method that doesn't exist |
| `Python syntax error` in a file  | `that looked fine` | `python3 -m py_compile <file>` | Unterminated string, usually a missing quote |

### The ast.literal_eval UTF-8 diagnostic

When Odoo says "manifest not found" but `ls` shows the file exists:

```bash

docker compose exec -T odoo python3 -c "
import ast
with open('/mnt/extra-addons/MODULE/__manifest__.py', 'rb') as f:
    content = f.read()
print('File size:', len(content), 'bytes')
print('First 20 bytes (hex):', content[:20].hex())
try:
    manifest = ast.literal_eval(content.decode('utf-8'))
    print('Parses OK. Keys:', sorted(manifest.keys()))
    print('installable:', manifest.get('installable'))
except Exception as e:
    print('PARSE ERROR:', type(e).__name__, '-', e)
"
```

This is the exact code path Odoo uses. If it says `PARSE ERROR: UnicodeDecodeError`, you have a non-UTF-8 byte. The position in the error message tells you where.
Resetting a stuck module state

```bash

docker compose exec -T postgres psql -U odoo -d odoo -c \
  "UPDATE ir_module_module SET state = 'uninstalled' WHERE name = 'MODULE';"
```

Only do this if the module's manifest has been fixed and the file is verified to be valid. Otherwise the module will be skipped again. Confirming a module is actually installed (not just "reported as installed")

```bash

docker compose exec -T postgres psql -U odoo -d odoo -c \
  "SELECT name, state FROM ir_module_module WHERE name LIKE 'nettrades_%' ORDER BY name;"
```

Every row should say installed.




4. Non-UTF-8 bytes in vendored code — one found, likely more.

5. Fields referenced in views but not in models — the `audit-views.py` script catches these but produces false positives on nested lists.

6. Models defined in the wrong place — `qualified_professional` was once defined in two modules. Check for duplicate `_name` values across modules.



### Two truths about this project:

1. Any change to a module's source file requires a full image rebuild. Do not skip the `docker compose build odoo` step.

2. The pre-flight script is your first line of defense. If it fails, do not attempt to build. The cost of debugging a broken build in the container is 10–20x the cost of fixing the file locally.



### Reading Odoo logs

* Odoo writes to stdout inside the container. Docker Compose captures it.

* `docker compose logs --tail=N odoo` shows the last N lines.

* The install script writes a copy to `logs/install-modules-*.log`. That log has the complete run, not just the last N lines.

* Odoo's per-module load line is: `Module X loaded in N.NNs, N queries`. If a module is skipped, you'll see not installable, skipped instead.


### Verifying changes

The owner's workflow for the Odoo modules is:

* Edit source.

* Run `prepare-odoo-addons.sh --force`. 

* Read the output. If any check fails, stop. Fix locally. Do not build.

* Rebuild the image.

* Recreate the container.

* Run the installer.

* Read the installer's final summary.
    
For other issues it is:

* Edit source.

* Run a full redeploy using ./scripts/nettrades-setup.sh all --force 

* Read the output. If any check fails. 

* Provide the output and the files impacted

* Fix locally. 


For the Odoo Modules deployment do not skip prepare-odoo-addons.sh --force . The pre-flight is cheap. The rebuild is not.





### Order to Install Modules (do not reorder)

The `scripts/install-modules.sh` file contains the correct order. The key
constraint: a module must come AFTER everything it depends on.

Verified dependency edges:

  nettrades_core          → (none)
  nettrades_queue         → (none)
  nettrades_notifications → nettrades_core
  nettrades_llm_config    → nettrades_core, llm
  nettrades_ask_someone   → nettrades_core, payment, mail
  nettrades_good_answer   → nettrades_core, llm, mail
  nettrades_fairness      → nettrades_core, nettrades_good_answer
  nettrades_data_collection → nettrades_core, nettrades_good_answer,
                              nettrades_ask_someone
  nettrades_loop          → nettrades_core, nettrades_data_collection
  nettrades_self_improving_config → nettrades_core,
                                     nettrades_data_collection,
                                     nettrades_loop
  nettrades_gpu_admin     → nettrades_core
  nettrades_bridge        → nettrades_core, nettrades_gpu_admin
  nettrades_trigger       → nettrades_data_collection
  nettrades_wireguard     → nettrades_core
  nettrades_onboarding    → nettrades_core

If you add a new module, add it to this list after all its dependencies.




## 5. Anti-Patterns Observed

These cost time in the session. A fresh window should avoid repeating them.

### 1. Guessing at Dockerfile fixes and rebuilding

Three rounds of Dockerfile edits each introduced new failures:

* Round 1: `pip install --ignore-installed ... pdfplumber` → broke OpenSSL.

* Round 2: removed `--ignore-installed` → broke `typing-extensions` uninstall.

* Round 3: two-stage install with `--ignore-installed` on specific packages → worked.

Each round cost ~30–60s of build time plus container recreation. The diagnostic that would have saved all three rounds: **check the versions inside the container first**.

```bash

docker compose exec -T odoo python3 -c \
  "import cryptography; print(cryptography.__version__)"
docker compose exec -T odoo python3 -c \
  "import OpenSSL; print(OpenSSL.__version__)"
```

If they don't match a known-good pair, that's your bug. The Dockerfile edit is trivial once you know what's wrong.

### 2. Assuming `md5sum` matching means the file is valid

`md5sum` proves two files are byte-identical. It does not prove they are valid UTF-8, valid Python, or valid XML. In the manifest-not-found bug, `md5sum` matched host and container perfectly — but both were Windows-1252.

### 3. Assuming `cat` reveals encoding problems

Terminals substitute non-UTF-8 bytes with visually similar characters. An em-dash in Windows-1252 looks exactly like an em-dash in UTF-8 when printed. Only a hexdump or a parse test reveals the difference.

### 4. Trusting exit code 0 from `docker compose exec`

Odoo returns 0 when a module is "not installable, skipped". `install-modules.sh` now greps for these signals, but any new script that wraps Odoo must do the same.

### 5. Adding `--ignore-installed` to a `pip install`

On a Debian-based image (like `odoo:19.0`), `--ignore-installed` forces pip to reinstall packages that Debian manages. Some Debian packages lack the RECORD files that pip needs to uninstall them cleanly. Others (like `cryptography`) have version constraints enforced by other packages (`pyOpenSSL`). Either way, it breaks something.

If you need to override a Debian package, install it alone with `--ignore-installed` in a separate `RUN` layer. Then everything downstream sees the new version and pip leaves it alone.

### 6. Editing a file without knowing why

Several rounds of "let's try this" changes made the state worse. Every fix
should trace to a specific error message or a specific verified diagnostic.
"No, wait, let's try..." costs a rebuild cycle.





## 6. Key Files and Their Purpose



### Files That Are Sacred — Do Not Delete

* `scripts/prepare-odoo-addons.sh` — the fail-loud validator. Recently hardened.

* `scripts/install-modules.sh` — the ordered installer. Recently fixed.

* `odoo-modules/nettrades_core/models/nettrades_vote.py` — was missing; unblocks 10 modules.

* `odoo-modules/nettrades_ask_someone/security/nettrades_ask_someone_security.xml` — moved from core.



	

| Path | Purpose |
|---|---|
| `scripts/nettrades-setup.sh` | Master orchestrator (phases 0–5) |
| `scripts/prepare-odoo-addons.sh` | Copies modules to Docker build context, validates manifests (fails loudly) |
| `scripts/install-modules.sh` | Installs modules one at a time in dependency order |
| `scripts/audit-views.py` | Scans views for field-reference errors |
| `odoo-modules/` | Source of truth for Odoo modules |
| `deploy/docker/odoo-modules/` | Copy used by the Odoo container (rebuilt by prepare-odoo-addons.sh) |
| `deploy/docker/docker-compose.yaml` | Full stack definition |
| `deploy/docker/.env` | Generated secrets, domains, ports |
| `src/core/` | LangGraph supervisor, checkpointing, node health |
| `src/core/odoo_proxy/` | Enterprise gateway (connectors) |
| `installer/` | Electron launcher |
| `logs/install-modules-*.log` | Per-run install logs |




## 7. Launcher Notes

The Launcher (Electron app in `installer/`) has a **Modules** tab that reads module state from Odoo's `ir.module.module` table. If it shows modules as "Available" instead of "Installed", that's because the module install failed. Fix the module in Odoo, and the Launcher will show it correctly.

The Launcher's **System Check** tab runs `install-modules.sh` in the background. When it succeeds, all modules in the install list will be green.

The Launcher's **Deploy** tab offers five profiles (Sovereign in a Box, Sovereign AI Router, Production, Kubernetes, Custom). All current deployments use the first profile.



## 8. Contact Points for Deep-Dive questions and for any code review

| Topic | Where to Look |
|---|---|
| Odoo module structure | `docs/developer/building-odoo-modules.md` |
| Bridge architecture | `docs/developer/bridge-architecture.md` |
| LangGraph supervisor | `src/core/supervisor.py, docs/developer/langgraph-supervisor-state-machine.md` |
| Enterprise gateway | `src/core/odoo_proxy/main.py, src/connectors/*.py` |
| Hub/spoke topology | `docs/operations/deployment-perspective-network-diagram.md` |
| GPU admin | `odoo-modules/nettrades_gpu_admin/, docs/developer/nvidia-dynamo-integration.md` |
| Self-improving loop | `docs/developer/self-improving-loop.md` |
| Overall deployment | `deploy/docker/docker-compose.yaml`, `deploy/docker/Dockerfile.odoo` |
| Env vars | `deploy/docker/.env.example` |
| Module list and install order | `scripts/install-modules.sh` (the `MODULES` array) |
| Pre-flight checks | `scripts/prepare-odoo-addons.sh` |
| Audit tool | `scripts/audit-views.py` |
| Individual module structure | `odoo-modules/nettrades_*/__manifest__.py` |




## 9. Project Narrative — The Pivot

The owner shared a critical piece of context that a fresh window needs to understand: the project pivoted.

### Original direction

A marketplace platform in the shape of LinkedIn / Upwork / Fiverr but with AI matching. Two-sided matching, escrow, freelancer profiles, project management using distributed inferencing.

### Current direction

A sovereign AI platform with distributed inferencing and training on local hardware or on a GPU marketplace if configured to do so.

Creating a self improving loop by capturing specialized human knowledge (doctors, lawyers, engineers) and training models on it locally or on a GPU marketplace, recruiting experts and allowing users and other professionals in their specialty to vote of their answers and then using the data to train new models. 


### What that means for the codebase

The pivot has left **artifacts of the old direction** in the tree:

* `nettrades_project`, `nettrades_crm`, `nettrades_marketplace` were designed to decompose the old platform. They were never built — the owner was advised not to, and didn't. Don't resurrect them.

* `qualified_professional` (the model) was going to be extended with credential fields (licence number, registration body, expiry). Some of that was done. Check before assuming.

* `nettrades.experience` (a model for professional history) was written in the old design. Whether it's actually needed for the new direction is unclear.

* `website_sale_marketplace` (a third-party module) is in third-party/. It is loaded but not used.


### What survives the pivot

* `nettrades_ask_someone` — expert recruitment. Central to the new direction.

* `nettrades_good_answer` — answer quality scoring. Still relevant.

* `nettrades_data_collection` — training data collection. Central.

* `nettrades_self_improving` — training pipeline. Central.

* `nettrades_gpu_admin` — GPU management. Relevant for local inference.

### What you should NOT propose

* Building marketplace features (projects, CRM, freelancer matching).

* Adding lead scoring, proposal management, or job matching.

* Anything that assumes the platform is a two-sided marketplace.

The pivot is real and irreversible. Treat the sovereign AI direction as
the only one that matters.




### What to ask

The first questions should be:

1. What is the current milestone? — Nothing ships until you know what "done" means for this week.

2. What changed since the last session? — The owner may have fixed or broken something that isn't in the docs.

3. Which BUG is the priority? — The catalog has a recommended order, but the owner may have a specific target.

4. Is there anything you tried that didn't work? — Save time by not re-suggesting something already rejected.

5. Any new files or logs to share? — New context is more valuable than re-reading old docs.


## 10. Meta 

The platform's plumbing is solid. Thirteen modules install. The stack starts, health checks pass, logs are clean, errors are handled. This is genuinely hard-won

### What is actually working (but has never run)

Most of the functional code (agent logic, GPU management, expert sessions, self-improving loop) has never been exercised with real traffic.

It compiles, it loads, but it has not been tested. Expect bugs in this layer — some will be trivial, some will be structural.

### What Worked and What Didn't

Across the debugging session that produced this state:

### What worked:

* Bisecting failures one at a time. Fix one thing, rebuild, observe.

* The pre-flight checks in `prepare-odoo-addons.sh`. They caught issues before the build every time they ran.

* The `ast.literal_eval` UTF-8 diagnostic. Once we knew what to look for, the fix was instant.

* Narrowing the problem: is it code, config, or environment? The `OpenSSL OK` check isolated the Docker image as the culprit immediately.

### What didn't:

* Guessing at fixes and rebuilding. The three rounds of Dockerfile edits each introduced new problems (typo, then `--ignore-installed`, then `idna`). Every fix should be verified locally before rebuild.

* Assuming `md5sum` matching means the file is correct. It means the two copies are identical, not that they're valid.

* Trusting `install-modules.sh` exit codes alone. `not installable, skipped` returns 0. It needed the grep check.
    

### What to be skeptical of

* Documentation that hasn't been touched in a session. It may be stale.

* Claims in comments ("this works", "TODO", "fixed in commit X"). Verify.

* The audit-views.py output. It has false positives.

* "13/13 installed" — verify by querying ir_module_module.

#### The most important things:

Do not burden the developer with noise. Be honest and direct. Be specific. Be wrong less often. When you're wrong, say so immediately and learn. Do not remove comments or functionality that is still needed and working. Do not guess, ask for files and run scripts to versify. 


