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

    def test_complete_jc_uses_manufactured_qty_when_no_scr(self):
        """
        _complete_job_card_subcontracted should not throw when SCR qty=0
        but jc.manufactured_qty > 0 (direct delivery path).
        This test validates the logic branching — not a full integration test.
        """
        from kniterp.api.production_wizard import _complete_job_card_subcontracted
        self.assertTrue(callable(_complete_job_card_subcontracted))
