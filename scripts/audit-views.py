#!/usr/bin/env python3
# FILE: scripts/audit-views.py
"""
Audit NETTRADES view files against their model definitions.

Uses proper XML parsing (ElementTree) instead of regex on the whole file,
so only <field name="X"/> references inside a view's <arch> block are
checked. Also knows about the fields inherited from mail.thread and
mail.activity.mixin.

Usage:
    cd ~/nettrades-platform
    python3 scripts/audit-views.py                    # all modules
    python3 scripts/audit-views.py nettrades_core     # single module
"""
import sys
import re
import glob
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path("odoo-modules")

# -----------------------------------------------------------------------------
# 1. Field sets the script should treat as universally available
# -----------------------------------------------------------------------------

# Fields every Odoo model has automatically.
BASE_FIELDS = {
    "id", "display_name",
    "create_date", "write_date", "create_uid", "write_uid",
    "active", "sequence",
}

# Fields inherited from mail.thread.
MAIL_THREAD_FIELDS = {
    "message_ids", "message_follower_ids", "message_attachment_count",
    "message_main_attachment_id", "message_is_follower",
    "message_needaction", "message_needaction_counter",
    "message_has_error", "message_has_error_counter",
    "message_has_sms_error", "message_unread",
    "message_unread_counter", "message_partner_ids",
    "message_channel_ids", "website_message_ids",
    "email_from", "author_id", "author_avatar", "author_guest_id",
    "partner_email", "rating_ids", "rating_last_value",
}

# Fields inherited from mail.activity.mixin.
MAIL_ACTIVITY_FIELDS = {
    "activity_ids", "activity_state", "activity_user_id",
    "activity_type_id", "activity_type_icon",
    "activity_date_deadline", "activity_summary", "activity_note",
    "activity_date_done", "activity_done_datetime",
    "activity_feedback", "activity_calendar_event_id",
    "activity_plan_id", "activity_plan_template_id",
}

MAIL_MIXIN_FIELDS = MAIL_THREAD_FIELDS | MAIL_ACTIVITY_FIELDS


# -----------------------------------------------------------------------------
# 2. Build a map: model_name -> set of declared field names
# -----------------------------------------------------------------------------

def parse_model_fields() -> dict[str, set[str]]:
    model_fields: dict[str, set[str]] = {}

    for py_file in glob.glob(str(BASE / "nettrades_*" / "models" / "*.py")):
        text = Path(py_file).read_text(errors="ignore")

        # Match only real "_name = '...'" declarations (anchored to line start)
        for match in re.finditer(
            r"^\s*_name\s*=\s*['\"]([a-zA-Z0-9_.]+)['\"]",
            text, re.MULTILINE,
        ):
            model_name = match.group(1)
            start = match.end()
            nxt = re.search(r"^\s*_name\s*=", text[start:], re.MULTILINE)
            end = start + nxt.start() if nxt else len(text)
            block = text[start:end]

            # Field declarations: `name = fields.X(...)` at start of a line
            fields = set(re.findall(
                r"^[ \t]{0,8}([a-z_][a-z0-9_]*)[ \t]*=[ \t]*fields\.",
                block, re.MULTILINE,
            ))

            model_fields.setdefault(model_name, set()).update(fields)
            model_fields[model_name].update(BASE_FIELDS)

            # If this model inherits mail mixins, add the mixin fields
            inherit_match = re.search(
                r"_inherit\s*=\s*\[([^\]]*)\]", block, re.MULTILINE,
            )
            if inherit_match:
                inherited = inherit_match.group(1)
                if "mail.thread" in inherited:
                    model_fields[model_name].update(MAIL_THREAD_FIELDS)
                if "mail.activity.mixin" in inherited:
                    model_fields[model_name].update(MAIL_ACTIVITY_FIELDS)

    return model_fields


# -----------------------------------------------------------------------------
# 3. Scan view files — only inside <arch> blocks
# -----------------------------------------------------------------------------

def strip_comments(xml_text: str) -> str:
    return re.sub(r"<!--.*?-->", "", xml_text, flags=re.DOTALL)


def check_view_file(xml_file: Path, model_fields: dict) -> list[tuple]:
    issues: list[tuple] = []
    raw = xml_file.read_text(errors="ignore")
    text = strip_comments(raw)

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        issues.append((str(xml_file), "XML_PARSE_ERROR", str(exc)))
        return issues

    # Only inspect <record model="ir.ui.view"> records — that's where the
    # view's <arch> block lives.
    for record in root.iter("record"):
        if record.get("model") != "ir.ui.view":
            continue

        model_elem = record.find('field[@name="model"]')
        if model_elem is None or not model_elem.text:
            continue
        target_model = model_elem.text.strip()

        # Skip models we don't own (e.g. res.partner, hr.job)
        if target_model not in model_fields:
            continue

        declared = model_fields[target_model]

        arch_elem = record.find('field[@name="arch"]')
        if arch_elem is None:
            continue

        # Only check <field name="X"> inside <arch>, not anywhere else
        for field_elem in arch_elem.findall(".//field"):
            ref = field_elem.get("name")
            if ref is None:
                continue
            if ref not in declared:
                issues.append((str(xml_file), target_model, ref))

    return issues


# -----------------------------------------------------------------------------
# 4. Main
# -----------------------------------------------------------------------------

def main() -> None:
    module_filter = sys.argv[1] if len(sys.argv) > 1 else None

    model_fields = parse_model_fields()

    pattern = str(BASE / "nettrades_*" / "views" / "*.xml")
    if module_filter:
        pattern = str(BASE / module_filter / "views" / "*.xml")

    all_issues: list[tuple] = []
    for xml_file in sorted(glob.glob(pattern)):
        all_issues.extend(check_view_file(Path(xml_file), model_fields))

    if not all_issues:
        print("✅ No view-to-model field mismatches found.")
        return

    print(f"❌ {len(all_issues)} field mismatches found:\n")
    print(f"{'View file':<70} {'Model':<35} {'Missing field'}")
    print("-" * 130)
    for path, model, ref in all_issues:
        print(f"{path:<70} {model:<35} {ref}")


if __name__ == "__main__":
    main()