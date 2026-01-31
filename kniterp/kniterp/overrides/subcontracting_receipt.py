import frappe
from frappe.utils import flt
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


def on_submit_complete_job_cards(doc, method):
    """
    Auto-complete Job Cards linked to the Subcontracting Order when fully received.
    Also updates Work Order status if all Job Cards are complete.
    """
    # Get SCO name from the receipt items
    for item in doc.items:
        if not item.subcontracting_order:
            continue
        
        # Get job card linked to this SCO via Purchase Order
        sco = frappe.get_doc("Subcontracting Order", item.subcontracting_order)
        if not sco.purchase_order:
            continue
        
        # Find job cards linked to items in this PO
        po_items = frappe.get_all(
            "Purchase Order Item",
            filters={"parent": sco.purchase_order, "docstatus": 1},
            fields=["job_card", "fg_item_qty"]
        )
        
        for po_item in po_items:
            if not po_item.job_card:
                continue
            
            jc = frappe.get_doc("Job Card", po_item.job_card)
            
            # Skip if already submitted
            if jc.docstatus == 1:
                continue
            
            # Calculate total received qty for this SCO
            total_received = frappe.db.sql("""
                SELECT SUM(sri.received_qty)
                FROM `tabSubcontracting Receipt` scr
                JOIN `tabSubcontracting Receipt Item` sri ON sri.parent = scr.name
                WHERE sri.subcontracting_order = %s
                AND scr.docstatus = 1
            """, item.subcontracting_order)
            received_qty = flt(total_received[0][0]) if total_received and total_received[0][0] else 0
            
            # If fully received, submit the job card
            if received_qty >= flt(po_item.fg_item_qty):
                try:
                    # Add time log with received qty
                    jc.append("time_logs", {
                        "from_time": frappe.utils.now_datetime(),
                        "to_time": frappe.utils.now_datetime(),
                        "completed_qty": received_qty
                    })
                    jc.save()
                    jc.submit()
                    frappe.msgprint(f"Job Card {jc.name} has been completed", alert=True)
                    
                    # Check if all Job Cards for this Work Order are complete
                    _check_and_complete_work_order(jc.work_order)
                    
                except Exception as e:
                    frappe.log_error(f"Error completing Job Card {jc.name}: {str(e)}")
                    frappe.msgprint(f"Could not auto-complete Job Card {jc.name}: {str(e)}", indicator="orange", alert=True)


def _check_and_complete_work_order(work_order_name):
    """
    Check if all Job Cards for a Work Order are complete and update WO status.
    """
    # Commit DB first to ensure the just-submitted Job Card is visible
    frappe.db.commit()
    
    # Count pending (draft) Job Cards for this Work Order
    pending_jcs = frappe.db.count(
        "Job Card",
        filters={
            "work_order": work_order_name,
            "docstatus": 0,  # Draft = not submitted
        }
    )
    
    if pending_jcs == 0:
        # All Job Cards are submitted - update Work Order status
        wo = frappe.get_doc("Work Order", work_order_name)
        
        if wo.status != "Completed":
            try:
                # Update manufactured qty from job cards
                wo.update_work_order_qty()
                
                # Use the correct method - update_status()
                wo.update_status()
                
                frappe.msgprint(f"Work Order {work_order_name} status updated to: {wo.status}", alert=True)
            except Exception as e:
                frappe.log_error(f"Error updating Work Order {work_order_name}: {str(e)}")
                frappe.msgprint(f"Could not update Work Order status: {str(e)}", indicator="orange", alert=True)


