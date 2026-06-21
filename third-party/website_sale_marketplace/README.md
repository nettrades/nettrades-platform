# Website Sale Marketplace

## Overview

This module extends Odoo's website sale functionality to support a marketplace model where vendors can manage their own products through a portal interface. Products are subject to an approval workflow before being published on the website.

## Features

### Vendor Portal
- **Product Management**: Vendors can create, edit, and manage their products through a dedicated portal interface
- **Self-Service**: Vendors access their products via `/my/products` portal page
- **Simplified Interface**: Streamlined product form with essential fields for marketplace vendors

### Product Approval Workflow
Products go through a three-state approval process:

1. **Draft**: Initial state when vendor creates a product
2. **Pending Approval**: Vendor submits product for review
3. **Approved**: Backend user approves product for publication

**Workflow Rules:**
- Only approved products can be published on the website
- When vendors edit approved products, state automatically resets to draft
- Vendors can submit products for approval via "Send for Approval" button
- Backend users approve products via "Approve" button

### Automatic Dropshipping
- Products created by marketplace vendors automatically use dropship route
- Purchase orders are auto-created when customers order marketplace products
- POs automatically confirm when sale orders are confirmed
- Vendor pricing is calculated based on configurable markup

### Markup Configuration
Marketplace markup can be configured at two levels:
- **Category Level**: Set markup per product category
- **Vendor Level**: Set default markup for all vendor products
- Category markup takes precedence over vendor markup

### Visual Indicators
- **List View**: State badges (Draft/Pending Approval/Approved) with color coding
- **Kanban View**: Light green "Marketplace" badge on marketplace product cards
- **Form View**: Status bar showing current approval state

## Backend Features

### Marketplace Products Menu
Navigate to: **Sales > Products > Marketplace Products**

- Dedicated view for all marketplace products
- Default filter: "To Approve" (shows products pending approval)
- Additional filters: Draft, Approved
- Group by: Vendor, State, Category

### Product Management
- View and approve vendor-submitted products
- Set products back to draft if changes needed
- Publish/unpublish approved products
- Validation prevents publishing non-approved products

## Technical Details

### Models Extended

**product.template**
- `marketplace_vendor_id`: Link to vendor partner
- `marketplace_state`: Approval workflow state (draft/approval/approved)
- `description_ecommerce`: Rich HTML description for ecommerce

**sale.order**
- Auto-confirm marketplace vendor POs on order confirmation

**res.partner**
- `is_marketplace_vendor`: Flag to identify marketplace vendors
- `marketplace_markup`: Default markup percentage for vendor products

**product.category**
- `marketplace_markup`: Category-specific markup percentage

### Key Methods

**product.template**
- `action_send_for_approval()`: Transition from draft to approval
- `action_approve()`: Transition from approval to approved
- `action_set_draft()`: Reset to draft state
- `_check_marketplace_publish()`: Constraint preventing non-approved product publication
- `_setup_vendor_dropshipping()`: Configure dropship route and supplier info

**sale.order**
- `_auto_confirm_marketplace_pos()`: Auto-confirm marketplace POs after SO confirmation

### Dependencies
- website_sale
- portal
- contacts
- product
- stock_dropshipping
- html_editor

## Configuration

### Enable Marketplace Vendor
1. Navigate to Contacts
2. Open partner record
3. Enable "Is Marketplace Vendor" checkbox
4. Set "Marketplace Markup" percentage (optional)

### Configure Category Markup
1. Navigate to Sales > Configuration > Product Categories
2. Edit category
3. Set "Marketplace Markup" percentage
4. Category markup overrides vendor markup

## Usage

### For Vendors (Portal Users)
1. Login to portal
2. Navigate to "My Products" or visit `/my/products`
3. Create new product or edit existing
4. Fill in product details (name, price, category, description)
5. Click "Send for Approval" when ready
6. Wait for approval notification
7. Product appears on website once approved

### For Backend Users (Approval)
1. Navigate to Sales > Products > Marketplace Products
2. Review products in "To Approve" filter
3. Open product to review details
4. Click "Approve" to approve or "Set to Draft" to request changes
5. Approved products can be published to website

## Workflow Diagram

```
┌─────────┐  Send for     ┌──────────────────┐   Approve    ┌──────────┐
│  Draft  │─────Approval──>│ Pending Approval │────────────>│ Approved │
└─────────┘               └──────────────────┘              └──────────┘
     ^                                                             │
     │                                                             │
     └─────────────────── Vendor Edit ───────────────────────────┘
```

## License

LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl)

## Credits

**Authors:**
- ERPGAP/PROMPTEQUATION LDA

**Copyright:** 2024 ERPGAP/PROMPTEQUATION LDA
