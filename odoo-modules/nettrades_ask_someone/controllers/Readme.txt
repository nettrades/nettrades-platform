Don’t know which one to used for main.py
nettrades-platform\odoo-modules\nettrades_ask_someone\controllers\main.py:
or
nettrades-platform\odoo-modules\nettrades_ask_someone\controllers\main1.py
or
nettrades-platform\odoo-modules\nettrades_ask_someone\controllers\main2.py
or
nettrades-platform\odoo-modules\nettrades_ask_someone\controllers\main3.py

When the "Ask Someone" button is clicked and the field is restricted (e.g., medicine with only_qualified=True), the matching algorithm in _match_experts applies a hard filter. Only professionals who have been manually verified by an administrator and have an active qualified_professional record for that field are shown as candidates.
This filter was added to nettrades_ask_someone/controllers/main.py:
python
field = request.env['nettrades.field'].browse(field_id)
if field.only_qualified:
    qualified_ids = request.env['qualified.professional'].search([
        ('field_id', '=', field_id),
        ('is_active', '=', True),
    ]).mapped('partner_id.id')
    candidates = candidates.filtered(lambda c: c.id in qualified_ids)
A medical question therefore reaches only verified doctors — not the general pool of freelancers. If no qualified professional is online, the user receives "No experts available at this time."