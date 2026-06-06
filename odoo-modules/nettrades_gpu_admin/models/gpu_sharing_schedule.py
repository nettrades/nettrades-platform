# Section H – Time-based sharing rules.
from odoo import fields, models, api
from datetime import datetime

class GPUSharingSchedule(models.Model):
    _name = 'gpu.sharing.schedule'
    _description = 'GPU Public Sharing Schedule'
    _order = 'day_of_week, start_time'

    cluster_id = fields.Many2one('gpu.cluster', string='Cluster', required=True,
                                  ondelete='cascade')
    day_of_week = fields.Selection([
        ('mon_fri', 'Monday–Friday'),
        ('sat_sun', 'Saturday–Sunday'),
        ('all', 'Every Day'),
    ], string='Day Range', required=True)
    start_time = fields.Float(string='Start Time (24h)', required=True,
                               help='e.g. 22.0 for 10 PM')
    end_time = fields.Float(string='End Time (24h)', required=True,
                             help='e.g. 6.0 for 6 AM')
    is_enabled = fields.Boolean(string='Enabled', default=True)
    min_vram_free_gb = fields.Integer(string='Minimum Free VRAM (GB)', default=8)

    def is_active_now(self):
        """Return True if current time falls within this schedule."""
        now = datetime.now()
        current_hour = now.hour + now.minute / 60.0
        weekday = now.weekday()   # 0=Monday
        is_weekend = weekday >= 5

        if not self.is_enabled:
            return False
        day_match = False
        if self.day_of_week == 'all':
            day_match = True
        elif self.day_of_week == 'mon_fri' and not is_weekend:
            day_match = True
        elif self.day_of_week == 'sat_sun' and is_weekend:
            day_match = True
        if day_match and self.start_time <= current_hour < self.end_time:
            return True
        return False