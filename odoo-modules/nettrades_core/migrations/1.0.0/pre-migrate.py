from odoo import api, fields, models, tools

def migrate(cr, version):
    """
    Migration script to move data from core Odoo tables to new NetTrades tables.
    """
    # Create new NetTrades user records from existing Odoo partners
    cr.execute("""
        INSERT INTO nettrades_user (
            partner_id,
            username,
            karma_score,
            reputation_score,
            is_verified,
            is_online,
            is_active,
            create_date,
            write_date
        )
        SELECT
            id,
            email,
            COALESCE(nettrades_karma, 0),
            COALESCE(nettrades_reputation, 0.0),
            COALESCE(nettrades_is_verified, FALSE),
            COALESCE(nettrades_is_online, FALSE),
            TRUE,
            create_date,
            write_date
        FROM res_partner
        WHERE nettrades_karma IS NOT NULL
           OR nettrades_reputation IS NOT NULL
    """)

    # Create new NetTrades company records
    cr.execute("""
        INSERT INTO nettrades_company (
            partner_id,
            is_active,
            industry,
            website,
            description,
            create_date,
            write_date
        )
        SELECT
            id,
            COALESCE(nettrades_is_active, TRUE),
            nettrades_industry,
            nettrades_website,
            nettrades_description,
            create_date,
            write_date
        FROM res_partner
        WHERE is_company = TRUE
          AND (nettrades_industry IS NOT NULL
            OR nettrades_website IS NOT NULL)
    """)