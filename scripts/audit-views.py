#!/usr/bin/env python3
"""
Audit NETTRADES view files against their model definitions.
Reports every <field name="X"/> reference in a view where X is not
a field declared on the view's target model.

Does NOT include references inside XML comments (<!-- ... -->) or
inside the string attribute of <field name="arch">.
"""
import os
import re
import glob
from pathlib import Path

BASE = Path("odoo-modules")

# ------------------------------------------------------------------
# 1. Build a map of model_name -> set of declared field names
# ------------------------------------------------------------------
model_fields: dict[str, set[str]] = {}
# Standard Odoo fields every model has, plus relational auto-fields
BASE_FIELDS = {
    "id", "display_name",
    "create_date", "write_date", "create_uid", "write_uid",
    "active", "sequence",
}

for py_file in glob.glob(str(BASE / "nettrades_*" / "models" / "*.py")):
    text = Path(py_file).read_text(errors="ignore")

    # Find every _name = '...' and the block that follows it up to the next _name
    for match in re.finditer(r"_name\s*=\s*['\"]([a-zA-Z0-9_.]+)['\"]", text):
        model_name = match.group(1)
        start = match.end()
        # Stop at the next _name declaration, or end of file
        nxt = re.search(r"_name\s*=", text[start:])
        end = start + nxt.start() if nxt else len(text)
        block = text[start:end]

        # Field declarations: `name = fields.X(...)` at the start of a line
        fields = set(re.findall(
            r"^\s{0,8}([a-z_][a-z0-9_]*)\s*=\s*fields\.",
            block, re.MULTILINE,
        ))
        model_fields.setdefault(model_name, set()).update(fields)
        model_fields[model_name].update(BASE_FIELDS)

# ------------------------------------------------------------------
# 2. Scan every view file and check field references
# ------------------------------------------------------------------
def strip_comments(xml: str) -> str:
    return re.sub(r"<!--.*?-->", "", xml, flags=re.DOTALL)

issues = []
for xml_file in sorted(glob.glob(str(BASE / "nettrades_*" / "views" / "*.xml"))):
    raw = Path(xml_file).read_text(errors="ignore")
    text = strip_comments(raw)

    # Target model of this view
    m = re.search(r"<field\s+name=\"model\">([a-zA-Z0-9_.]+)</field>", text)
    if not m:
        continue
    model_name = m.group(1)

    # Skip models we don't own (e.g. res.partner, hr.job)
    if model_name not in model_fields:
        continue

    declared = model_fields[model_name]

    # Collect every <field name="X" ... /> except structural ones
    for fm in re.finditer(r"<field\s+name=\"([a-zA-Z0-9_]+)\"", text):
        ref = fm.group(1)
        if ref in ("model", "arch", "name", "inherit_id", "view_mode", "attrs", "states"):
            continue
        if ref not in declared:
            issues.append((xml_file, model_name, ref))

# ------------------------------------------------------------------
# 3. Report
# ------------------------------------------------------------------
if not issues:
    print("✅ No view-to-model field mismatches found.")
else:
    print(f"❌ {len(issues)} field mismatches found:\n")
    print(f"{'View file':<70} {'Model':<30} {'Missing field'}")
    print("-" * 130)
    for path, model, ref in issues:
        print(f"{path:<70} {model:<30} {ref}")