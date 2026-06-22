# -*- coding: utf-8 -*-
# Section H – GPUStack Adapter
{
    'name': 'NETTRADES GPUStack Adapter',
    'version': '1.0',
    'category': 'Nettrades',
    'summary': 'NETTRADES GPUStack Adapter',
    'description': """
        NETTRADES GPUStack Adapter.
    """,
    'author': 'Nettrades',
    'website': 'https://nettrades.ai',
    'license': 'AGPL-3',
    'depends': ['nettrades_gpu_admin'],
    'data': [],
    'controllers': ['controllers/gpustack_api.py'],
    'installable': True,
}