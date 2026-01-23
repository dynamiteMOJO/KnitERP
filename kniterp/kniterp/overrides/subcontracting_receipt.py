import frappe
from erpnext.subcontracting.doctype.subcontracting_receipt.subcontracting_receipt import (
    SubcontractingReceipt
)

_original_validate = SubcontractingReceipt.validate


def patched_validate(self):
    # TEMP FIX: ERPNext bug (v16)
    if not getattr(self, "customer_warehouse", None):
        frappe.logger("kniterp").warning(
            f"[SCR PATCH] Injecting customer_warehouse from supplier_warehouse for {self.name}"
        )
        self.customer_warehouse = self.supplier_warehouse

    return _original_validate(self)


SubcontractingReceipt.validate = patched_validate
