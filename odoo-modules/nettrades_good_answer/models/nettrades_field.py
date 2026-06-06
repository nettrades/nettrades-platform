from odoo import fields, models

class NettradesField(models.Model):
    _inherit = 'nettrades.field'

    finetune_provider = fields.Selection([
        ('unsloth', 'Unsloth (single-GPU)'),
        ('axolotl', 'Axolotl (multi-GPU)'),
    ], string='Fine-tuning Backend', default='unsloth')
    base_model = fields.Char('Base Model', default='deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B')
    hyperparameters = fields.Json('Hyperparameters')