import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Simple and efficient LLM migration:
    Migrate messages from old subtypes to new subtypes using direct batch updates.
    The llm_role field will auto-compute based on the new subtype_id.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})

    _logger.info("Starting LLM migration...")

    # Migrate messages from old subtypes to new subtypes
    migrations = [
        ("llm_mail_message_subtypes.mt_llm_user", "llm.mt_user"),
        ("llm_mail_message_subtypes.mt_llm_assistant", "llm.mt_assistant"),
        ("llm_mail_message_subtypes.mt_llm_tool_result", "llm.mt_tool"),
    ]

    total_migrated = 0

    for old_xmlid, new_xmlid in migrations:
        try:
            # Get old and new subtype references
            old_subtype = env.ref(old_xmlid, raise_if_not_found=False)
            new_subtype = env.ref(new_xmlid, raise_if_not_found=False)

            if not old_subtype:
                _logger.info(f"Old subtype {old_xmlid} not found, skipping")
                continue

            if not new_subtype:
                _logger.warning(f"New subtype {new_xmlid} not found, skipping")
                continue

            # Find and migrate messages
            messages = env["mail.message"].search([("subtype_id", "=", old_subtype.id)])

            if messages:
                _logger.info(
                    f"Migrating {len(messages)} messages from {old_xmlid} to {new_xmlid}"
                )
                messages.write({"subtype_id": new_subtype.id})
                total_migrated += len(messages)
                _logger.info(f"✓ Successfully migrated {len(messages)} messages")
            else:
                _logger.info(f"No messages found for {old_xmlid}")

        except Exception as e:
            _logger.error(f"Error migrating {old_xmlid}: {str(e)}")
            continue

    _logger.info(f"LLM migration completed. Total messages migrated: {total_migrated}")

    # Clear cache to ensure role computation works properly
    try:
        env["mail.message"].get_llm_roles.clear_cache(env["mail.message"])
        _logger.info("Cleared LLM role cache")
    except Exception as e:
        _logger.warning(f"Could not clear cache: {str(e)}")
