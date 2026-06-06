from odoo import fields, models

class FTTrainingJob(models.Model):
    _name = 'ft.training.job'
    _description = 'Fine-tuning Training Job'

    dataset_id = fields.Many2one('ft.dataset', required=True)
    field_id = fields.Many2one('nettrades.field', required=True)
    provider = fields.Char()
    base_model = fields.Char()
    fine_tuned_model_id = fields.Char()
    status = fields.Selection([('pending','Pending'),('running','Running'),('completed','Completed'),('failed','Failed')], default='pending')
    started_at = fields.Datetime()
    completed_at = fields.Datetime()
    hyperparameters = fields.Json()
    metrics = fields.Json()
    error_message = fields.Text()