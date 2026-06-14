# -*- coding: utf-8 -*-
# Section H � GPU Administration Panel
{
    'name': 'NETTRADES GPU Administration Panel',
    'version': '1.0',
   'category': 'Tools',
   'summary': 'Network administrator dashboard for managing GPU clusters',
    'depends': ['base', 'web', 'bus', 'nettrades_core'],
    'data': [
        'security/ir.model.access.csv',
        'security/gpu_admin_security.xml',
        'views/gpu_cluster_views.xml',
        'views/gpu_node_views.xml',
        'views/gpu_schedule_views.xml',
        'views/gpu_token_economics_views.xml',
        'views/gpu_dashboard_templates.xml',
        'views/menu_items.xml',
        'views/multimodal_config_views.xml',   # new
        'data/cron.xml',
   ],
    'assets': {
       'web.assets_backend': [
            'nettrades_gpu_admin/static/src/js/dashboard.js',
            'nettrades_gpu_admin/static/src/js/node_manager.js',
            'nettrades_gpu_admin/static/src/js/network_scan.js',
            'nettrades_gpu_admin/static/src/js/wireguard_manager.js',
            'nettrades_gpu_admin/static/src/scss/dashboard.scss',
        ],
    },
    'controllers': ['controllers/main.py'],
    'installable': True,
    'application': True,
    'auto_install': False,
}