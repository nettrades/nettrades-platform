# -*- coding: utf-8 -*-
# =============================================================================
# Section: D – Payment Stripe (OCA)
# Purpose:  The ask_someone module requires Stripe for escrow payments.
#           Odoo 19 CE does not include payment_stripe; the OCA module
#           provides this functionality.
#
# Installation: Download the OCA "payment_stripe" module from the Odoo
#               Community Association Apps Store or GitHub and place its
#               contents here.  This manifest is a placeholder; replace with
#               the actual OCA module files.
# =============================================================================
{
    'name': 'Payment Stripe (OCA)',
    'version': '1.0',
    'category': 'Accounting/Payment',
    'summary': 'Stripe payment acquirer for Odoo CE (OCA)',
    'depends': ['payment'],
    'data': [],
    'installable': True,
    'application': False,
}