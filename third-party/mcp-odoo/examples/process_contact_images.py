#!/usr/bin/env python3
"""
Example script to process contact images from Odoo.
Demonstrates image processing capabilities with Pillow.

Usage:
    python examples/process_contact_images.py

Requirements:
    - Pillow
    - requests
    - configparser (built-in)
"""

import base64
import json
import os
import sys
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image
from configparser import ConfigParser


def load_config(company_name: str) -> dict:
    """Load configuration for a specific company"""
    config = ConfigParser()
    config_file = Path(__file__).parent.parent / '.env'

    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_file}")

    config.read(config_file)

    if company_name not in config.sections():
        raise ValueError(f"Company '{company_name}' not found in configuration")

    return {
        'url': config.get(company_name, 'ODOO_URL'),
        'database': config.get(company_name, 'ODOO_DATABASE'),
        'api_key': config.get(company_name, 'ODOO_API_KEY'),
    }


def fetch_contacts_with_images(config: dict, limit: int = 50) -> list:
    """Fetch contacts with images from Odoo"""
    headers = {
        'Authorization': f"Bearer {config['api_key']}",
        'X-Odoo-Database': config['database'],
        'Content-Type': 'application/json'
    }

    url = f"{config['url']}/json/2/res.partner/search_read"
    payload = {
        'domain': [['is_company', '=', True], ['image_1920', '!=', False]],
        'fields': ['name', 'image_1920', 'vat', 'email'],
        'limit': limit,
        'order': 'name asc'
    }

    response = requests.post(url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def process_image(image_base64: str, max_size: tuple = (100, 100)) -> Image.Image:
    """Process and resize image from base64 string"""
    # Decode base64
    image_data = base64.b64decode(image_base64)

    # Open image
    image = Image.open(BytesIO(image_data))

    # Convert to RGB if necessary (some images may be RGBA, P, etc.)
    if image.mode != 'RGB':
        image = image.convert('RGB')

    # Resize maintaining aspect ratio
    image.thumbnail(max_size, Image.Resampling.LANCZOS)

    return image


def save_images(contacts: list, output_dir: Path, max_size: tuple = (100, 100)):
    """Save processed images to directory"""
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_count = 0
    skipped_count = 0

    for contact in contacts:
        contact_id = contact['id']
        contact_name = contact['name']

        if not contact.get('image_1920'):
            print(f"⊘ Skipping {contact_name} (ID: {contact_id}) - No image")
            skipped_count += 1
            continue

        try:
            # Process image
            image = process_image(contact['image_1920'], max_size)

            # Save image
            filename = f"contact_{contact_id}_{contact_name[:30]}.png"
            # Clean filename
            filename = "".join(c for c in filename if c.isalnum() or c in (' ', '_', '-', '.')).rstrip()
            filepath = output_dir / filename

            image.save(filepath, 'PNG', optimize=True)

            print(f"✓ Saved: {filename} ({image.size[0]}x{image.size[1]})")
            saved_count += 1

        except Exception as e:
            print(f"✗ Error processing {contact_name} (ID: {contact_id}): {e}")
            skipped_count += 1

    return saved_count, skipped_count


def generate_html_gallery(contacts: list, output_dir: Path, image_dir: Path):
    """Generate HTML gallery of contact images"""
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Odoo Contacts Gallery</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        h1 {
            color: #333;
            text-align: center;
            margin-bottom: 40px;
        }
        .gallery {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 20px;
        }
        .contact-card {
            background: white;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            transition: transform 0.2s;
        }
        .contact-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }
        .contact-image {
            width: 100%;
            height: auto;
            border-radius: 4px;
            margin-bottom: 10px;
        }
        .contact-name {
            font-weight: bold;
            color: #333;
            margin-bottom: 5px;
        }
        .contact-info {
            font-size: 0.9em;
            color: #666;
        }
        .no-image {
            width: 100px;
            height: 100px;
            background: #e0e0e0;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 4px;
            color: #999;
            font-size: 3em;
            margin: 0 auto 10px;
        }
    </style>
</head>
<body>
    <h1>Odoo Contacts Gallery</h1>
    <div class="gallery">
"""

    for contact in contacts:
        contact_id = contact['id']
        contact_name = contact['name']
        vat = contact.get('vat', 'N/A')
        email = contact.get('email', 'N/A')

        if contact.get('image_1920'):
            filename = f"contact_{contact_id}_{contact_name[:30]}.png"
            filename = "".join(c for c in filename if c.isalnum() or c in (' ', '_', '-', '.')).rstrip()
            img_path = image_dir.name + '/' + filename
            img_tag = f'<img src="{img_path}" alt="{contact_name}" class="contact-image">'
        else:
            img_tag = '<div class="no-image">👤</div>'

        html_content += f"""
        <div class="contact-card">
            {img_tag}
            <div class="contact-name">{contact_name}</div>
            <div class="contact-info">
                <div>RUT: {vat}</div>
                <div>Email: {email if email else 'N/A'}</div>
            </div>
        </div>
"""

    html_content += """
    </div>
</body>
</html>
"""

    output_file = output_dir / 'gallery.html'
    output_file.write_text(html_content)
    return output_file


def main():
    """Main function"""
    # Configuration
    COMPANY = 'bmya'  # Change this to your company name
    MAX_SIZE = (100, 100)
    OUTPUT_DIR = Path(__file__).parent.parent / 'output' / 'contact_images'

    print(f"Odoo Contact Image Processor")
    print(f"=" * 50)
    print(f"Company: {COMPANY}")
    print(f"Max size: {MAX_SIZE[0]}x{MAX_SIZE[1]}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"=" * 50)
    print()

    try:
        # Load configuration
        print("Loading configuration...")
        config = load_config(COMPANY)
        print(f"✓ Connected to: {config['url']}")
        print()

        # Fetch contacts
        print("Fetching contacts with images...")
        contacts = fetch_contacts_with_images(config)
        print(f"✓ Found {len(contacts)} contacts")
        print()

        # Process and save images
        print("Processing images...")
        saved, skipped = save_images(contacts, OUTPUT_DIR / 'images', MAX_SIZE)
        print()
        print(f"Results: {saved} saved, {skipped} skipped")
        print()

        # Generate HTML gallery
        print("Generating HTML gallery...")
        html_file = generate_html_gallery(contacts, OUTPUT_DIR, OUTPUT_DIR / 'images')
        print(f"✓ Gallery created: {html_file}")
        print()

        print("=" * 50)
        print("Done! Open the gallery in your browser:")
        print(f"  file://{html_file.absolute()}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
