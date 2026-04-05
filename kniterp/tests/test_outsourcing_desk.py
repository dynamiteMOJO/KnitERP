from unittest.mock import MagicMock, patch, call
import frappe
from frappe.tests.utils import FrappeTestCase
from kniterp.api import outsourcing_desk


def _make_fake_po(item_code="ITEM-001", qty=100, received_qty=0, rate=50.0,
                  uom="Kg", stock_uom="Kg", warehouse="Stores - TC"):
    po_item = MagicMock()
    po_item.item_code = item_code
    po_item.item_name = item_code + " Name"
    po_item.qty = qty
    po_item.received_qty = received_qty
    po_item.rate = rate
    po_item.uom = uom
    po_item.stock_uom = stock_uom
    po_item.warehouse = warehouse
    po_item.name = "PO-ITEM-001"

    po = MagicMock()
    po.docstatus = 1
    po.supplier = "SUP-001"
    po.company = "Test Company"
    po.buying_price_list = "Standard Buying"
    po.name = "PO-0001"
    po.items = [po_item]
    return po, po_item


class TestCreateRmPurchaseReceipt(FrappeTestCase):

    @patch("kniterp.api.outsourcing_desk.frappe.get_doc")
    @patch("kniterp.api.outsourcing_desk.frappe.new_doc")
    def test_draft_created_without_received_batches(self, mock_new_doc, mock_get_doc):
        """No received_batches → PR inserted but not submitted, no SABB created."""
        po, _ = _make_fake_po()
        mock_get_doc.return_value = po

        pr = MagicMock()
        pr.items = []
        pr.name = "PR-0001"
        pr.docstatus = 0
        pr.company = "Test Company"

        def new_doc_side_effect(doctype):
            if doctype == "Purchase Receipt":
                return pr
            return MagicMock()

        mock_new_doc.side_effect = new_doc_side_effect

        result = outsourcing_desk.create_rm_purchase_receipt("PO-0001")

        pr.insert.assert_called_once()
        pr.submit.assert_not_called()
        self.assertEqual(result["docstatus"], 0)

    @patch("kniterp.api.outsourcing_desk.frappe.get_cached_value")
    @patch("kniterp.api.outsourcing_desk.frappe.db.set_value")
    @patch("kniterp.api.outsourcing_desk.frappe.get_doc")
    @patch("kniterp.api.outsourcing_desk.frappe.new_doc")
    def test_submit_with_received_batches_creates_sabb(
        self, mock_new_doc, mock_get_doc, mock_db_set, mock_cached_val
    ):
        """received_batches + submit=1 → SABB created, linked to PR item, PR submitted."""
        po, po_item = _make_fake_po()
        mock_get_doc.return_value = po
        mock_cached_val.return_value = 1  # has_batch_no = 1

        pr_item = MagicMock()
        pr_item.item_code = "ITEM-001"
        pr_item.warehouse = "Stores - TC"
        pr_item.serial_and_batch_bundle = None
        pr_item.name = "PRI-001"

        pr = MagicMock()
        pr.items = [pr_item]
        pr.name = "PR-0001"
        pr.docstatus = 1
        pr.company = "Test Company"

        sabb = MagicMock()
        sabb.name = "SABB-001"
        sabb.entries = []

        def sabb_append(table, row):
            sabb.entries.append(row)

        sabb.append = sabb_append

        def new_doc_side_effect(doctype):
            if doctype == "Purchase Receipt":
                return pr
            if doctype == "Serial and Batch Bundle":
                return sabb
            return MagicMock()

        mock_new_doc.side_effect = new_doc_side_effect

        received_batches = [{"batch_no": "LOT-A", "qty": 50}, {"batch_no": "LOT-B", "qty": 50}]

        with patch("kniterp.api.outsourcing_desk.ensure_batch_exists") as mock_ensure:
            result = outsourcing_desk.create_rm_purchase_receipt(
                "PO-0001",
                received_batches=received_batches,
                submit=1,
            )

        # SABB inserted
        sabb.insert.assert_called_once()
        # Two batches in SABB entries
        self.assertEqual(len(sabb.entries), 2)
        self.assertEqual(sabb.entries[0]["batch_no"], "LOT-A")
        self.assertEqual(sabb.entries[1]["batch_no"], "LOT-B")
        # PR item linked to SABB
        self.assertEqual(pr_item.serial_and_batch_bundle, sabb.name)
        self.assertEqual(pr_item.use_serial_batch_fields, 0)
        # ensure_batch_exists called for each batch
        self.assertEqual(mock_ensure.call_count, 2)
        # SABB patched with voucher refs
        mock_db_set.assert_called_with(
            "Serial and Batch Bundle",
            sabb.name,
            {"voucher_no": pr.name, "voucher_detail_no": pr_item.name, "is_cancelled": 0},
        )
        # PR submitted
        pr.submit.assert_called_once()
        self.assertEqual(result["docstatus"], 1)

    @patch("kniterp.api.outsourcing_desk.frappe.get_cached_value")
    @patch("kniterp.api.outsourcing_desk.frappe.get_doc")
    @patch("kniterp.api.outsourcing_desk.frappe.new_doc")
    def test_non_batch_item_skips_sabb(self, mock_new_doc, mock_get_doc, mock_cached_val):
        """Item with has_batch_no=0 — SABB not created even if received_batches passed."""
        po, _ = _make_fake_po()
        mock_get_doc.return_value = po
        mock_cached_val.return_value = 0  # has_batch_no = 0

        pr_item = MagicMock()
        pr_item.item_code = "ITEM-001"
        pr_item.warehouse = "Stores - TC"
        pr_item.serial_and_batch_bundle = None
        pr_item.name = "PRI-001"

        pr = MagicMock()
        pr.items = [pr_item]
        pr.name = "PR-0001"
        pr.docstatus = 0
        pr.company = "Test Company"

        def new_doc_side_effect(doctype):
            if doctype == "Purchase Receipt":
                return pr
            return MagicMock()

        mock_new_doc.side_effect = new_doc_side_effect

        outsourcing_desk.create_rm_purchase_receipt(
            "PO-0001",
            received_batches=[{"batch_no": "LOT-A", "qty": 100}],
            submit=0,
        )

        # Serial and Batch Bundle never instantiated
        for c in mock_new_doc.call_args_list:
            self.assertNotEqual(c.args[0], "Serial and Batch Bundle")
