# Odoo MCP Server - Examples

This directory contains example scripts demonstrating various capabilities of the Odoo MCP Server.

## Available Examples

### 1. `process_contact_images.py`

Process and export contact images from Odoo with automatic resizing and HTML gallery generation.

**Features:**
- Fetches contacts with images from Odoo
- Resizes images to specified dimensions (default: 100x100)
- Maintains aspect ratio during resizing
- Saves optimized PNG images
- Generates an HTML gallery for easy viewing
- Handles image format conversions (RGBA → RGB)

**Usage:**
```bash
# Make sure you're in the project root
cd /path/to/claude-odoo-api

# Run the script
python examples/process_contact_images.py
```

**Configuration:**
Edit the script to change these settings:
```python
COMPANY = 'bmya'  # Your company name from .env
MAX_SIZE = (100, 100)  # Maximum image dimensions
OUTPUT_DIR = Path(__file__).parent.parent / 'output' / 'contact_images'
```

**Output:**
```
output/
└── contact_images/
    ├── images/
    │   ├── contact_1_Company_Name.png
    │   ├── contact_2_Another_Company.png
    │   └── ...
    └── gallery.html  # Open in browser
```

**Requirements:**
```bash
pip install Pillow requests
```

## Creating Your Own Examples

When creating new example scripts:

1. **Configuration Loading:**
   ```python
   from configparser import ConfigParser
   from pathlib import Path

   def load_config(company_name: str) -> dict:
       config = ConfigParser()
       config_file = Path(__file__).parent.parent / '.env'
       config.read(config_file)
       return {
           'url': config.get(company_name, 'ODOO_URL'),
           'database': config.get(company_name, 'ODOO_DATABASE'),
           'api_key': config.get(company_name, 'ODOO_API_KEY'),
       }
   ```

2. **Making Requests:**
   ```python
   import requests

   headers = {
       'Authorization': f"Bearer {config['api_key']}",
       'X-Odoo-Database': config['database'],
       'Content-Type': 'application/json'
   }

   response = requests.post(
       f"{config['url']}/json/2/model.name/method",
       json={'domain': []},
       headers=headers,
       timeout=30
   )
   ```

3. **Error Handling:**
   ```python
   try:
       response.raise_for_status()
       data = response.json()
   except requests.exceptions.RequestException as e:
       print(f"Error: {e}")
       sys.exit(1)
   ```

## Common Use Cases

### Export Data to CSV
```python
import csv
from odoo_client import fetch_data

contacts = fetch_data('res.partner', [['is_company', '=', True]])

with open('contacts.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['name', 'email', 'phone'])
    writer.writeheader()
    writer.writerows(contacts)
```

### Bulk Update Records
```python
partners = search_read('res.partner', [['email', '=', False]])

for partner in partners:
    if partner.get('phone'):
        update_partner(partner['id'], {
            'email': f"contact_{partner['id']}@example.com"
        })
```

### Generate Reports
```python
from jinja2 import Template

invoices = search_read('account.move', [
    ['move_type', '=', 'out_invoice'],
    ['state', '=', 'posted']
])

template = Template('''
# Invoice Report
Total Invoices: {{ invoices|length }}
Total Amount: ${{ total_amount }}
''')

print(template.render(
    invoices=invoices,
    total_amount=sum(inv['amount_total'] for inv in invoices)
))
```

## Tips & Best Practices

1. **Always use timeouts** when making requests:
   ```python
   response = requests.post(url, json=data, timeout=30)
   ```

2. **Handle large datasets** with pagination:
   ```python
   limit = 100
   offset = 0
   all_records = []

   while True:
       records = search_read(model, domain, limit=limit, offset=offset)
       if not records:
           break
       all_records.extend(records)
       offset += limit
   ```

3. **Validate data** before creating/updating:
   ```python
   def validate_partner(data):
       required = ['name']
       for field in required:
           if field not in data:
               raise ValueError(f"Missing required field: {field}")
   ```

4. **Log operations** for debugging:
   ```python
   import logging

   logging.basicConfig(level=logging.INFO)
   logger = logging.getLogger(__name__)

   logger.info(f"Processing {len(records)} records")
   ```

5. **Use environment variables** for sensitive data:
   ```python
   import os
   from dotenv import load_dotenv

   load_dotenv()
   api_key = os.getenv('ODOO_API_KEY')
   ```

## Additional Resources

- [Odoo External API Documentation](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html)
- [Python Requests Documentation](https://requests.readthedocs.io/)
- [Pillow Documentation](https://pillow.readthedocs.io/)
- [Project Main README](../README.md)
- [Developer Guide](../CLAUDE.md)
