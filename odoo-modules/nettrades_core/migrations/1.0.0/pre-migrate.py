from odoo import api, fields, models, tools

def migrate(cr, version):
    """
    Migration script to move data from core Odoo tables to new NetTrades tables.
    FIXED: Creates the tables if they don't exist, then inserts data.
    """

    # -------------------------------------------------------------------------
    # 1. Ensure nettrades_user table exists
    # -------------------------------------------------------------------------
    cr.execute("""
        CREATE TABLE IF NOT EXISTS nettrades_user (
            id SERIAL PRIMARY KEY,
            partner_id INTEGER NOT NULL UNIQUE,
            username VARCHAR,
            wallet_address VARCHAR,
            karma INTEGER DEFAULT 100,
            karma_score INTEGER DEFAULT 0,
            reputation_score FLOAT DEFAULT 0.0,
            is_verified BOOLEAN DEFAULT FALSE,
            is_online BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            is_qualified BOOLEAN DEFAULT FALSE,
            qualification_reason TEXT,
            gpu_reputation FLOAT DEFAULT 0.0,
            token_balance FLOAT DEFAULT 0.0,
            is_expert BOOLEAN DEFAULT FALSE,
            expert_rate FLOAT,
            expert_bio TEXT,
            worker_agent VARCHAR,
            worker_context JSONB,
            worker_started BOOLEAN DEFAULT FALSE,
            is_lead BOOLEAN DEFAULT FALSE,
            create_date TIMESTAMP DEFAULT NOW(),
            write_date TIMESTAMP DEFAULT NOW()
        );
    """)

    # Add foreign key constraint if not already present (optional)
    cr.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'nettrades_user_partner_id_fkey'
            ) THEN
                ALTER TABLE nettrades_user
                ADD CONSTRAINT nettrades_user_partner_id_fkey
                FOREIGN KEY (partner_id) REFERENCES res_partner(id) ON DELETE CASCADE;
            END IF;
        END $$;
    """)

    # -------------------------------------------------------------------------
    # 2. Ensure nettrades_company table exists
    # -------------------------------------------------------------------------
    cr.execute("""
        CREATE TABLE IF NOT EXISTS nettrades_company (
            id SERIAL PRIMARY KEY,
            partner_id INTEGER NOT NULL UNIQUE,
            is_active BOOLEAN DEFAULT TRUE,
            industry VARCHAR,
            website VARCHAR,
            description TEXT,
            create_date TIMESTAMP DEFAULT NOW(),
            write_date TIMESTAMP DEFAULT NOW()
        );
    """)

    # Add foreign key constraint if not already present
    cr.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'nettrades_company_partner_id_fkey'
            ) THEN
                ALTER TABLE nettrades_company
                ADD CONSTRAINT nettrades_company_partner_id_fkey
                FOREIGN KEY (partner_id) REFERENCES res_partner(id) ON DELETE CASCADE;
            END IF;
        END $$;
    """)

    # -------------------------------------------------------------------------
    # 3. Insert data into nettrades_user from res_partner
    # -------------------------------------------------------------------------
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
        ON CONFLICT (partner_id) DO UPDATE SET
            karma_score = EXCLUDED.karma_score,
            reputation_score = EXCLUDED.reputation_score
    """)

    # -------------------------------------------------------------------------
    # 4. Insert data into nettrades_company from res_partner
    # -------------------------------------------------------------------------
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
        ON CONFLICT (partner_id) DO UPDATE SET
            industry = EXCLUDED.industry,
            website = EXCLUDED.website
    """)