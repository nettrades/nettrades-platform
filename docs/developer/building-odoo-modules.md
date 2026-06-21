# Building Odoo Modules

This guide explains how to create new Odoo modules for the NETTRADES.AI platform.

---

## Overview

Odoo modules extend the platform with new business functionality. Each module is a self-contained directory with:

- Models (data structures)
- Views (UI)
- Security (access control)
- Data (seed data)
- Controllers (API endpoints)

---

## Module Structure

odoo-modules/nettrades_custom/

├── init.py

├── manifest.py

├── models/

│ ├── init.py

│ └── custom_model.py

├── views/

│ └── custom_views.xml

├── security/

│ └── ir.model.access.csv

└── data/

└── custom_data.xml

## Manifest File (`__manifest__.py`)

```python
{
    'name': 'NETTRADES Custom Module',
    'version': '1.0',
    'depends': ['nettrades_core'],
    'data': [
        'security/ir.model.access.csv',
        'views/custom_views.xml',
        'data/custom_data.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}

```

### Key Fields

| Field | Purpose |
|-------|-------------|
| `name` | Human-readable module name |
| `version` | Semantic version |
| `depends` | List of required modules |
| `data` | Data files to load on install |
| `installable` | True to allow installation |
| `application` | True to appear in Apps menu |
| `license` | LGPL-3 (for NETTRADES modules) |

### Model Definition (models/custom_model.py)


```python

from odoo import fields, models, api, _

class CustomModel(models.Model):
    _name = 'custom.model'
    _description = 'Custom Model'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Name',
        required=True,
        help='Name of the record'
    )
    description = fields.Text(
        string='Description',
        help='Detailed description'
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner'
    )
    field_id = fields.Many2one(
        'nettrades.field',
        string='Professional Field'
    )
    status = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('completed', 'Completed')
    ], default='draft')
    active = fields.Boolean(
        default=True,
        help='False to archive the record'
    )

    @api.model
    def _cron_custom_task(self):
        """Scheduled cron job for custom task."""
        records = self.search([('status', '=', 'active')])
        for record in records:
            # Process record
            pass

    def action_custom_action(self):
        """Custom button action."""
        for record in self:
            record.status = 'completed'
```

### Common Field Types

| Field Type | Purpose |
|-------|-------------|
| `Char` | Text field |
| `Text` | Large text field |
| `Integer` | Whole number |
| `Float` | Decimal number |
| `Boolean` | True/False |
| `Date` | Date only |
| `Datetime` | Date and time |
| `Selection` | Dropdown list |
| `Many2one` | Foreign key to another model |
| `One2many` | Inverse of Many2one |
| `Many2many` | Many-to-many relationship |
| `Binary` | File attachment |


## View Definition (views/custom_views.xml)

### Tree View (List)

```xml

<odoo>
    <record id="view_custom_model_tree" model="ir.ui.view">
        <field name="name">custom.model.tree</field>
        <field name="model">custom.model</field>
        <field name="arch" type="xml">
            <tree>
                <field name="name"/>
                <field name="partner_id"/>
                <field name="field_id"/>
                <field name="status"/>
                <field name="active" widget="boolean"/>
            </tree>
        </field>
    </record>
</odoo>
```

### Form View
```xml

<odoo>
    <record id="view_custom_model_form" model="ir.ui.view">
        <field name="name">custom.model.form</field>
        <field name="model">custom.model</field>
        <field name="arch" type="xml">
            <form>
                <header>
                    <button name="action_custom_action"
                            type="object"
                            string="Complete"
                            class="oe_highlight"/>
                </header>
                <sheet>
                    <group>
                        <field name="name"/>
                        <field name="description"/>
                    </group>
                    <group>
                        <field name="partner_id"/>
                        <field name="field_id"/>
                        <field name="status"/>
                        <field name="active"/>
                    </group>
                </sheet>
            </form>
        </field>
    </record>
</odoo>
```

### Action and Menu
```xml

<odoo>
    <record id="action_custom_model" model="ir.actions.act_window">
        <field name="name">Custom Model</field>
        <field name="res_model">custom.model</field>
        <field name="view_mode">tree,form</field>
        <field name="help">Manage custom records</field>
    </record>

    <menuitem id="menu_custom_model"
              name="Custom Model"
              parent="base.menu_administration"
              action="action_custom_model"/>
</odoo>
```

### Security (security/ir.model.access.csv)
```csv

id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_custom_model_user,custom.model.user,model_custom_model,base.group_user,1,0,0,0
access_custom_model_manager,custom.model.manager,model_custom_model,nettrades_core.group_manager,1,1,1,1
```

### Access Rights

| Column | Purpose |
|-------|-------------|
| `perm_read` | View records |
| `perm_write` | Edit records |
| `perm_create` | Create records |
| `perm_unlink` | Delete records |


### Example: Creating the nettrades.experience Model

This is a real example from the NETTRADES platform. The nettrades.experience model stores a user's work history.

File: odoo-modules/nettrades_core/models/nettrades_experience.py
```python

# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError

class NettradesExperience(models.Model):
    _name = 'nettrades.experience'
    _description = 'Work Experience'
    _order = 'start_date DESC'

    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=True,
        ondelete='cascade',
        help="The user who owns this experience record."
    )

    job_title = fields.Char(
        string='Job Title',
        required=True,
        help="The title of the role (e.g., 'Senior Python Developer')."
    )

    company = fields.Char(
        string='Company',
        required=True,
        help="The name of the company or organisation."
    )

    start_date = fields.Date(
        string='Start Date',
        required=True,
        help="The date the user started this role."
    )

    end_date = fields.Date(
        string='End Date',
        help="The date the user ended this role. If empty, this is the current role."
    )

    description = fields.Text(
        string='Description',
        help="A brief description of responsibilities, achievements, and skills used."
    )

    is_current = fields.Boolean(
        string='Current Position',
        compute='_compute_is_current',
        store=True,
        help="True if this is the current job (end_date is empty)."
    )

    @api.depends('end_date')
    def _compute_is_current(self):
        for record in self:
            record.is_current = not bool(record.end_date)

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for record in self:
            if record.start_date and record.end_date and record.end_date < record.start_date:
                raise ValidationError(_("End date cannot be earlier than start date."))
```

### Example: Creating the nettrades.review Model

This is another real example from the NETTRADES platform. The nettrades.review model stores user ratings and comments.

File: odoo-modules/nettrades_core/models/nettrades_review.py
```python

# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError

class NettradesReview(models.Model):
    _name = 'nettrades.review'
    _description = 'User Review'
    _order = 'create_date DESC'

    reviewer_id = fields.Many2one(
        'res.partner',
        string='Reviewer',
        required=True,
        help="The user who wrote this review (must be a valid partner)."
    )

    reviewed_partner_id = fields.Many2one(
        'res.partner',
        string='Reviewed Partner',
        required=True,
        help="The user who received this review."
    )

    project_id = fields.Many2one(
        'project.project',
        string='Project',
        help="The project for which this review was given (optional)."
    )

    rating = fields.Integer(
        string='Rating',
        required=True,
        default=5,
        help="Rating from 1 (poor) to 5 (excellent)."
    )

    comment = fields.Text(
        string='Comment',
        help="A written comment or feedback about the reviewed user."
    )

    create_date = fields.Datetime(
        string='Created',
        readonly=True,
        default=fields.Datetime.now,
        help="Timestamp when the review was created."
    )

    @api.constrains('rating')
    def _check_rating(self):
        for record in self:
            if not (1 <= record.rating <= 5):
                raise ValidationError(_("Rating must be between 1 and 5."))

    @api.constrains('reviewer_id', 'reviewed_partner_id')
    def _check_not_self(self):
        for record in self:
            if record.reviewer_id.id == record.reviewed_partner_id.id:
                raise ValidationError(_("You cannot review yourself."))
```

### Updating the Module Manifest

When adding new models, update the module's __manifest__.py to include any new dependencies and ensure the models are imported in models/__init__.py.

Example __manifest__.py:
```python

{
    'name': 'NETTRADES Core',
    'version': '1.0',
    'depends': ['base', 'hr_recruitment', 'crm', 'project', 'website_sale_marketplace'],
    # ... rest of manifest
}
```

Example models/__init__.py:

```python

from . import res_partner
from . import hr_job
from . import project_project
from . import nettrades_user_match
from . import nettrades_skill
from . import nettrades_field
from . import nettrades_experience      # NEW
from . import nettrades_review          # NEW
```

### Controllers (API Endpoints)
```python

# controllers/custom_controller.py
from odoo import http
from odoo.http import request
import json

class CustomController(http.Controller):

    @http.route('/api/v1/custom/endpoint', type='json', auth='user', methods=['POST'])
    def custom_endpoint(self, **kwargs):
        """Custom API endpoint."""
        data = request.params
        # Process request
        result = request.env['custom.model'].search([
            ('name', 'ilike', data.get('search', ''))
        ])
        return {
            'success': True,
            'data': result.read(['name', 'description'])
        }

```

### Integrating with LangGraph

To make your Odoo models accessible to LangGraph agents, add them to odoo_tools.py:

```python

# src/core/tools/odoo_tools.py

async def custom_model_search(domain: list, fields: list = None) -> list:
    """Search custom.model records."""
    return await _call_odoo(
        "search_read",
        "custom.model",
        {"args": [domain, fields or []]}
    )

async def custom_model_create(values: dict) -> dict:
    """Create a custom.model record."""
    return await _call_odoo(
        "create",
        "custom.model",
        {"args": [values]}
    )
```

### Testing Your Module

#### Install the Module
```bash

python third-party/odoo/odoo-bin -c odoo.conf -i nettrades_custom --stop-after-init
```

#### Update the Module
```bash

python third-party/odoo/odoo-bin -c odoo.conf -u nettrades_custom --stop-after-init
```

#### Run Odoo Shell
```bash

python third-party/odoo/odoo-bin -c odoo.conf shell
```

#### Best Practices

    `Follow OCA conventions` – Use Odoo Community Association standards.

    `Prefix XML IDs` – Use module name prefix to avoid conflicts.

    `Write translations` – Use _() for all user-facing strings.

    `Add help text` – Use help= parameter on fields.

    `Write tests` – Add unit tests for critical functionality.

    `Document models` – Add docstrings to models and methods.