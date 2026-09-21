# -*- coding: utf-8 -*-
{
    'name': 'NETTRADES Self-Improving',
    'version': '1.0.0',
    'category': 'Nettrades',
    'summary': 'Self-improving AI loop: triggers, cycles, training pipeline, configuration',
    'description': """
        Merged module for the self-improving AI system.

        Contains:
        - trigger.config, trigger.event   (Analyze phase)
        - training.pipeline               (Plan phase, backend-agnostic)
        - loop.cycle, loop.orchestrator   (Execute phase, resumable state machine)
        - self.improving.config           (admin configuration singleton)
        - data.episode extension          (quality signals: fairness, future signals)

        Replaces nettrades_trigger, nettrades_loop, and
        nettrades_self_improving_config.
    """,
    'author': 'NETTRADES',
    'website': 'https://nettrades.ai',
    'license': 'AGPL-3',
    'depends': [
        'base',
        'mail',
        'web',
        'queue_job',
        'nettrades_core',
        'nettrades_data_collection',
        # Provides llm.training.dataset, llm.training.job, llm.provider.
        # If your installation uses a different module name for these
        # models, update this line.
        'llm_training',
    ],
    'data': [
        'security/nettrades_self_improving_security.xml',
        'security/ir.model.access.csv',
        'views/trigger_config_views.xml',
        'views/trigger_event_views.xml',
        'views/training_pipeline_views.xml',
        'views/loop_cycle_views.xml',
        'views/self_improving_config_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}