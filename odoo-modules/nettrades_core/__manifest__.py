{
    'name': 'NETTRADES Core',
    'version': '1.0.0',
    'category': 'Nettrades',
    'summary': 'Core marketplace and AI integration',
    'description': """
        This module provides the essential building blocks for the
        NETTRADES platform. It defines separate tables for NetTrades users
        and companies, linked to Odoo core models via Many2one fields.
    """,
    'author': 'NETTRADES',
    'website': 'https://nettrades.ai',
    'license': 'AGPL-3',
    'depends': [
        'base',                      # Core Odoo
        'hr_recruitment',            # For job matching
        'crm',                       # For lead management
        'project',                   # For project management
        'website_sale_marketplace',  # For marketplace features
        'auth_signup',               # For self-service onboarding
        'queue_job',                 # For async jobs
    ],
    'data': [
        # Security – must load first
        'security/nettrades_security.xml',
        'security/ir.model.access.csv',

        # Menu – must load before views that reference it
        'views/menu_views.xml',

        # Views
        'views/hr_job_views.xml',
        'views/res_partner_views.xml',
        'views/nettrades_user_views.xml',
        'views/nettrades_company_views.xml',
        'views/nettrades_project_views.xml',
        'views/nettrades_field_views.xml',
        'views/nettrades_review_views.xml',
        'views/nettrades_experience_views.xml',
        'views/nettrades_user_match_views.xml',
        'views/nettrades_core_menu.xml',

        # Data
        'data/nettrades.skill.csv',
        'data/portal_data.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}