import frappe
from frappe.tests.utils import FrappeTestCase


class TestDirectDelivery(FrappeTestCase):
    def test_create_direct_purchase_invoice_missing_po(self):
        from kniterp.api.production_wizard import create_direct_purchase_invoice
        with self.assertRaises(frappe.exceptions.DoesNotExistError):
            create_direct_purchase_invoice("NONEXISTENT-PO", [{"batch_no": "B1", "qty": 10}])

    def test_create_direct_sales_invoice_no_job_card(self):
        from kniterp.api.production_wizard import create_direct_sales_invoice
        with self.assertRaises(frappe.exceptions.ValidationError):
            create_direct_sales_invoice("NONEXISTENT-JC")
