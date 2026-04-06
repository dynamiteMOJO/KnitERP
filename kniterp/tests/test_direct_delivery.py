import frappe
import unittest


class TestDirectDelivery(unittest.TestCase):
    def test_create_direct_purchase_invoice_missing_po(self):
        from kniterp.api.production_wizard import create_direct_purchase_invoice
        with self.assertRaises(frappe.exceptions.DoesNotExistError):
            create_direct_purchase_invoice("NONEXISTENT-PO", [{"batch_no": "B1", "qty": 10}])
