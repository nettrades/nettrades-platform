
## Change List for Other Docs

I don't have the current contents of these, so here's what should change — apply manually.

### `KNOWN-ISSUES.md`

**Move from "Open" to "Recently Fixed":**
- "nettrades_gpu_admin model registration AssertionError" → actually was an XML `attrs=` migration issue, not model registration.
- Any items about `attrs=`, `states=`, `<group expand>`, `doall`, `numbercall`.
- Any items about encoding / BOM / manifest-not-found.
- Any items about `DiscoveryService.__init__`.

**Add to "Open":**
- BUG-041 (duplicate IDs in dead `config_views.xml`).
- BUG-042 (audit script false positive).
- BUG-043 (thread-safety latent issue).

**Update the "P1.5" reference** to point at BUG-003 in the new catalog.

### `DECISIONS.md`

**Add an ADR** for the two-stage Dockerfile. Something like:

> **ADR-011: Two-stage pip install in Dockerfile.odoo**
>
> **Context:** `pdfplumber` (needed by `nettrades_onboarding`) pulls
> `pdfminer.six`, which depends on `cryptography`. Installing everything in
> one `pip3 install` with `--ignore-installed` broke Debian's `pyOpenSSL
> 23.2.0`. Removing `--ignore-installed` broke `typing-extensions`
> uninstall.
>
> **Decision:** Two-stage install. Stage 1 uses `--ignore-installed` for
> pure-Python packages Debian ships without RECORD files. Stage 2 uses
> normal pip.
>
> **Consequences:** Every future Python dependency must be classified
> before being added: does it need to shadow a Debian package? If yes,
> stage 1. If no, stage 2. Adding to the wrong stage will re-break the
> build.

**Add an ADR** for the two-tier UTF-8 check. Same shape.

### `COMPONENT-MAP.md`

Update the `prepare-odoo-addons.sh` entry to mention: XML parse, Python
compile, UTF-8 check, `attrs=` check, `<group expand>` check.

Update the `install-modules.sh` entry to mention the grep for silent
skips.

Add `nettrades_bridge/views/menu_views.xml` to the file list for that
module.

Add `nettrades_onboarding/models/res_partner_skill.py` and
`res_partner_experience.py`.

### `VERIFICATION.md`

Add to the acceptance criteria:

- `prepare-odoo-addons.sh --force` must complete with `N modules prepared`
  (not abort at the UTF-8 check).
- `install-modules.sh --force --auto` must exit 0 with `ALL MODULES
  INSTALLED SUCCESSFULLY`.
- The install summary table must show `Failed modules: 0` AND every module
  in the log must be followed by `✓` (not `skipped`).

### `README-AGENT.md`

Add a rule:

> **Never trust `install-modules.sh` exit code 0 alone.** The script
> captures output and greps for `not installable, skipped` — if the grep
> fires, it returns 1 even though Odoo itself returned 0. If you are
> inspecting the log manually, look for the `✓` marker per module, not
> the summary line.

Also add:

> **Before any `docker compose build odoo`,** run `./scripts/prepare-odoo-addons.sh
> --force`. If it aborts, fix the reported files. Do not proceed.

---

## Final Note

The state described here is the first **clean 13/13 install** of this
project. Everything before it was partial. Treat this as a baseline. Save
it:

```bash
cd ~/nettrades-platform
git add -A
git commit -m "13/13 modules install cleanly after encoding + Odoo 17 syntax fixes"

# Or if git isn't in use:
tar czf ~/nettrades-platform-baseline-$(date +%Y%m%d).tar.gz \
    --exclude='.venv' --exclude='node_modules' --exclude='third-party/odoo' \
    -C ~ nettrades-platform