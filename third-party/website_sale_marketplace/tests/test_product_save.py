# -*- coding: utf-8 -*-
# Copyright 2024 ERPGAP/PROMPTEQUATION LDA
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestProductSave(TransactionCase):
    """Test that portal users can save products"""

    def setUp(self):
        super().setUp()

        # Create a marketplace vendor partner
        self.vendor_partner = self.env['res.partner'].create({
            'name': 'Test Vendor Save',
            'is_marketplace_vendor': True,
            'email': 'vendorsave@test.com',
            'marketplace_markup': 0.20,  # 20% markup
        })

        # Create portal user for the vendor
        # In Odoo 19, we need to use the share parameter to create portal users
        self.portal_user = self.env['res.users'].sudo().with_context(no_reset_password=True).create({
            'name': 'Portal Vendor Save User',
            'login': 'portal_vendor_save',
            'password': 'portal_vendor_save',
            'email': 'portal_vendor_save@test.com',
            'partner_id': self.vendor_partner.id,
            'share': True,  # This makes the user a portal user in Odoo 19
        })

        # Get UOM
        self.uom_unit = self.env.ref('uom.product_uom_unit')

    def test_portal_user_can_create_product(self):
        """
        Test that portal users can create products.
        """
        # Create product as portal user
        product = self.env['product.template'].with_user(self.portal_user).create({
            'name': 'Test Product Create',
            'list_price': 100.0,
            'uom_id': self.uom_unit.id,
            'uom_po_id': self.uom_unit.id,
        })

        self.assertTrue(product, "Product should be created")
        self.assertEqual(product.name, 'Test Product Create')
        self.assertEqual(product.marketplace_vendor_id, self.vendor_partner,
                        "Vendor should be auto-assigned")
        self.assertEqual(product.list_price, 100.0)

        # Check that cost was calculated correctly (100 / 1.20 = 83.33)
        expected_cost = round(100.0 / 1.20, 2)
        self.assertAlmostEqual(product.standard_price, expected_cost, places=2,
                              msg="Cost should be calculated based on markup")

    def test_portal_user_can_edit_product(self):
        """
        Test that portal users can edit/save their products.
        This is the main fix - ensuring write() works for portal users.
        """
        # Create product as portal user
        product = self.env['product.template'].with_user(self.portal_user).create({
            'name': 'Test Product Edit',
            'list_price': 100.0,
            'uom_id': self.uom_unit.id,
            'uom_po_id': self.uom_unit.id,
        })

        # Now try to edit the product as portal user
        product.with_user(self.portal_user).write({
            'name': 'Test Product Edited',
            'list_price': 150.0,
        })

        # Verify changes were saved
        self.assertEqual(product.name, 'Test Product Edited',
                        "Product name should be updated")
        self.assertEqual(product.list_price, 150.0,
                        "Product price should be updated")

        # Check that cost was recalculated (150 / 1.20 = 125.0)
        expected_cost = round(150.0 / 1.20, 2)
        self.assertAlmostEqual(product.standard_price, expected_cost, places=2,
                              msg="Cost should be recalculated after price change")

    def test_portal_user_can_edit_description(self):
        """
        Test that portal users can edit product descriptions.
        """
        # Create product as portal user
        product = self.env['product.template'].with_user(self.portal_user).create({
            'name': 'Test Product Description',
            'list_price': 100.0,
            'uom_id': self.uom_unit.id,
            'uom_po_id': self.uom_unit.id,
        })

        # Edit description
        product.with_user(self.portal_user).write({
            'description_sale': 'This is a test description',
            'description_ecommerce': '<p>This is an ecommerce description</p>',
        })

        # Verify changes were saved
        self.assertEqual(product.description_sale, 'This is a test description')
        self.assertEqual(product.description_ecommerce, '<p>This is an ecommerce description</p>')

    def test_marketplace_state_reset_on_edit(self):
        """
        Test that marketplace state resets to draft when vendor edits approved product.
        """
        # Create and approve product
        product = self.env['product.template'].with_user(self.portal_user).create({
            'name': 'Test Product State',
            'list_price': 100.0,
            'uom_id': self.uom_unit.id,
            'uom_po_id': self.uom_unit.id,
        })

        # Approve the product (as admin)
        product.sudo().write({'marketplace_state': 'approved'})
        self.assertEqual(product.marketplace_state, 'approved')

        # Edit as portal user - should reset to draft
        product.with_user(self.portal_user).write({
            'list_price': 120.0,
        })

        self.assertEqual(product.marketplace_state, 'draft',
                        "State should reset to draft when vendor edits approved product")
