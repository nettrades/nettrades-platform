from odoo import fields, models

class AskSomeoneConfig(models.TransientModel):
    _name = 'ask.someone.config'
    _inherit = 'res.config.settings'

    distance_weight = fields.Float(default=0.4, config_parameter='ask_someone.distance_weight')
    reputation_weight = fields.Float(default=0.5, config_parameter='ask_someone.reputation_weight')
    online_bonus = fields.Float(default=0.2, config_parameter='ask_someone.online_bonus')
    available_bonus = fields.Float(default=0.1, config_parameter='ask_someone.available_bonus')
    max_distance_km = fields.Integer(default=100, config_parameter='ask_someone.max_distance_km')
    reputation_threshold = fields.Integer(default=100, config_parameter='ask_someone.reputation_threshold')
    geocoding_provider = fields.Selection([('google','Google Maps'),('openstreetmap','OpenStreetMap')], default='openstreetmap', config_parameter='ask_someone.geocoding_provider')
    geocoding_api_key = fields.Char(config_parameter='ask_someone.geocoding_api_key')
    platform_fee_percent = fields.Float(default=15.0, config_parameter='ask_someone.platform_fee_percent')
    default_field_id = fields.Many2one('nettrades.field', config_parameter='ask_someone.default_field_id')