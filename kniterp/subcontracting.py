import frappe
from frappe.utils import flt

def update_work_order_from_job_card(jc, completed_qty):
    if not jc.work_order:
        return

    wo = frappe.get_doc("Work Order", jc.work_order)

    # 1. Update completed_qty directly in DB
    for op in wo.operations:
        if op.operation == jc.operation:
            frappe.db.set_value(
                "Work Order Operation",
                op.name,
                "completed_qty",
                completed_qty
            )

    # 2. Let ERPNext recalculate statuses SAFELY
    wo = frappe.get_doc("Work Order", wo.name)
    wo.update_operation_status()

    # 3. Persist operation status changes safely
    for op in wo.operations:
        frappe.db.set_value(
            "Work Order Operation",
            op.name,
            "status",
            op.status
        )

    frappe.logger().info({
        "work_order_updated": wo.name,
        "operation": jc.operation,
        "completed_qty": completed_qty
    })

def complete_job_card_from_po_item(purchase_order, pr_item):
    """
    Update Job Card status when Subcontracting Receipt is submitted.
    NOTE: Does NOT auto-complete - user must manually complete via Production Wizard.
    """
    po_items = frappe.get_all(
        "Purchase Order Item",
        filters={
            "parent": purchase_order,
            "job_card": ["is", "set"]
        },
        fields=["job_card"]
    )

    for poi in po_items:
        jc = frappe.get_doc("Job Card", poi.job_card)

        # Get total received qty across ALL Subcontracting Receipts for this job card
        total_received = frappe.db.sql("""
            SELECT SUM(sri.qty) 
            FROM `tabSubcontracting Receipt Item` sri
            JOIN `tabSubcontracting Receipt` scr ON scr.name = sri.parent
            WHERE sri.job_card = %s AND scr.docstatus = 1
        """, jc.name)
        received_qty = flt(total_received[0][0]) if total_received and total_received[0][0] else 0
        
        # Never auto-complete - user will close manually via Production Wizard button
        # Only set to Work In Progress if not already submitted/completed
        if jc.status not in ["Completed", "Submitted"]:
            jc.db_set("status", "Work In Progress", update_modified=False)
        
        # Update manufactured_qty to track progress
        jc.db_set("manufactured_qty", received_qty, update_modified=False)
        
        frappe.logger().info({
            "job_card_updated": jc.name,
            "source": "subcontracting_receipt",
            "received_qty": received_qty,
            "for_quantity": jc.for_quantity,
            "auto_complete": False
        })

        update_work_order_from_job_card(
            jc,
            completed_qty=received_qty
        )

def on_pr_submit_complete_job_cards(pr, method):
    if not pr.is_subcontracted:
        return

    for pr_item in pr.items:
        if not pr_item.purchase_order:
            continue

        complete_job_card_from_po_item(
            purchase_order=pr_item.purchase_order,
            pr_item=pr_item
        )


def on_se_submit_update_job_card_transferred(se, method):
    """
    Update Job Card's transferred_qty when Stock Entry (Send to Subcontractor) is submitted.
    This is called via doc_events hook on Stock Entry submission.
    """
    if se.purpose != "Send to Subcontractor":
        return
    
    if not se.subcontracting_order:
        return
    
    # Get the Purchase Order linked to this SCO
    po_name = frappe.db.get_value("Subcontracting Order", se.subcontracting_order, "purchase_order")
    if not po_name:
        return
    
    # Get Job Cards linked to this PO
    po_items = frappe.get_all(
        "Purchase Order Item",
        filters={"parent": po_name, "job_card": ["is", "set"]},
        fields=["job_card", "item_code"]
    )
    
    for poi in po_items:
        jc = frappe.get_doc("Job Card", poi.job_card)
        
        # Get total SENT qty to subcontractor for this job card across ALL Stock Entries
        total_sent = frappe.db.sql("""
            SELECT SUM(sed.qty)
            FROM `tabStock Entry Detail` sed
            JOIN `tabStock Entry` se ON se.name = sed.parent
            JOIN `tabSubcontracting Order` sco ON sco.name = se.subcontracting_order
            JOIN `tabPurchase Order Item` poi ON poi.parent = sco.purchase_order AND poi.job_card = %s
            WHERE se.docstatus = 1
            AND se.purpose = 'Send to Subcontractor'
        """, jc.name)
        sent_qty = flt(total_sent[0][0]) if total_sent and total_sent[0][0] else 0
        
        # Update Job Card transferred_qty
        jc.db_set("transferred_qty", sent_qty, update_modified=False)
        
        # Also update items table if it exists
        for item in jc.items:
            # Calculate how much of this item was sent
            item_sent = frappe.db.sql("""
                SELECT SUM(sed.qty)
                FROM `tabStock Entry Detail` sed
                JOIN `tabStock Entry` se ON se.name = sed.parent
                WHERE se.docstatus = 1
                AND se.purpose = 'Send to Subcontractor'
                AND se.subcontracting_order = %s
                AND sed.item_code = %s
            """, (se.subcontracting_order, item.item_code))
            item_sent_qty = flt(item_sent[0][0]) if item_sent and item_sent[0][0] else 0
            
            frappe.db.set_value("Job Card Item", item.name, "transferred_qty", item_sent_qty)
        
        # Update status to Material Transferred if all RM sent
        if sent_qty >= jc.for_quantity and jc.status not in ["Completed", "Submitted"]:
            jc.db_set("status", "Material Transferred", update_modified=False)
        elif sent_qty > 0 and jc.status not in ["Completed", "Submitted", "Material Transferred"]:
            jc.db_set("status", "Work In Progress", update_modified=False)
        
        frappe.logger().info({
            "job_card_transferred_update": jc.name,
            "source": "stock_entry_send_to_subcontractor",
            "sent_qty": sent_qty,
            "for_quantity": jc.for_quantity
        })


def on_se_cancel_update_job_card_transferred(se, method):
    """
    Recalculate Job Card's transferred_qty when Stock Entry (Send to Subcontractor) is cancelled.
    """
    if se.purpose != "Send to Subcontractor":
        return
    
    if not se.subcontracting_order:
        return
    
    # Get the Purchase Order linked to this SCO
    po_name = frappe.db.get_value("Subcontracting Order", se.subcontracting_order, "purchase_order")
    if not po_name:
        return
    
    # Get Job Cards linked to this PO
    po_items = frappe.get_all(
        "Purchase Order Item",
        filters={"parent": po_name, "job_card": ["is", "set"]},
        fields=["job_card", "item_code"]
    )
    
    for poi in po_items:
        jc = frappe.get_doc("Job Card", poi.job_card)
        
        # Recalculate total SENT qty excluding the cancelled entry (docstatus=1 only)
        total_sent = frappe.db.sql("""
            SELECT SUM(sed.qty)
            FROM `tabStock Entry Detail` sed
            JOIN `tabStock Entry` se ON se.name = sed.parent
            JOIN `tabSubcontracting Order` sco ON sco.name = se.subcontracting_order
            JOIN `tabPurchase Order Item` poi ON poi.parent = sco.purchase_order AND poi.job_card = %s
            WHERE se.docstatus = 1
            AND se.purpose = 'Send to Subcontractor'
        """, jc.name)
        sent_qty = flt(total_sent[0][0]) if total_sent and total_sent[0][0] else 0
        
        # Update Job Card transferred_qty
        jc.db_set("transferred_qty", sent_qty, update_modified=False)
        
        # Also update items table if it exists
        for item in jc.items:
            # Recalculate how much of this item was sent (excluding cancelled)
            item_sent = frappe.db.sql("""
                SELECT SUM(sed.qty)
                FROM `tabStock Entry Detail` sed
                JOIN `tabStock Entry` se ON se.name = sed.parent
                WHERE se.docstatus = 1
                AND se.purpose = 'Send to Subcontractor'
                AND se.subcontracting_order IN (
                    SELECT sco.name FROM `tabSubcontracting Order` sco
                    JOIN `tabPurchase Order Item` poi ON poi.parent = sco.purchase_order
                    WHERE poi.job_card = %s
                )
                AND sed.item_code = %s
            """, (jc.name, item.item_code))
            item_sent_qty = flt(item_sent[0][0]) if item_sent and item_sent[0][0] else 0
            
            frappe.db.set_value("Job Card Item", item.name, "transferred_qty", item_sent_qty)
        
        # Update status based on remaining sent qty
        if sent_qty == 0 and jc.status not in ["Completed", "Submitted"]:
            jc.db_set("status", "Open", update_modified=False)
        elif sent_qty >= jc.for_quantity and jc.status not in ["Completed", "Submitted"]:
            jc.db_set("status", "Material Transferred", update_modified=False)
        elif sent_qty > 0 and jc.status not in ["Completed", "Submitted", "Material Transferred"]:
            jc.db_set("status", "Work In Progress", update_modified=False)
        
        frappe.logger().info({
            "job_card_transferred_reverted": jc.name,
            "source": "stock_entry_cancel",
            "remaining_sent_qty": sent_qty,
            "for_quantity": jc.for_quantity
        })