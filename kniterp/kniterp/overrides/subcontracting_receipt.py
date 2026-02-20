import frappe
from frappe.utils import flt


def before_validate_set_customer_warehouse(doc, method=None):
    """
    doc_events handler: Subcontracting Receipt → before_validate

    ERPNext's subcontracting controller reads customer_warehouse for customer-provided
    RM routing (subcontracting_controller.py ~line 624), but the SCR doctype does not
    natively carry that field in all paths. This handler injects it from supplier_warehouse
    when missing, ensuring downstream validation/stock logic has the correct warehouse.

    Registered via hooks.py doc_events. Not a monkey patch.
    """
    if not getattr(doc, "customer_warehouse", None):
        frappe.logger("kniterp").warning(
            f"[SCR] customer_warehouse missing on {doc.name!r} — "
            f"injecting from supplier_warehouse ({doc.supplier_warehouse!r})"
        )
        doc.customer_warehouse = doc.supplier_warehouse


def on_submit_complete_job_cards(doc, method):
    """
    Update Job Cards linked to the Subcontracting Order when goods are received.
    Also updates Work Order status if all Job Cards are complete.
    
    NOTE: ERPNext's standard subcontracting does NOT update Job Card consumed_qty.
    This is a custom extension because we link Job Cards to subcontracting for manufacturing.
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
            
            # Calculate total received qty for this JOB CARD across ALL SCRs/POs
            total_received = frappe.db.sql("""
                SELECT SUM(sri.qty)
                FROM `tabSubcontracting Receipt` scr
                JOIN `tabSubcontracting Receipt Item` sri ON sri.parent = scr.name
                WHERE sri.job_card = %s
                AND scr.docstatus = 1
            """, jc.name)
            received_qty = flt(total_received[0][0]) if total_received and total_received[0][0] else 0
            
            # Update manufactured_qty to track progress
            jc.db_set("manufactured_qty", received_qty, update_modified=False)
            
            # Update consumed_qty in Job Card items table
            # This is custom - ERPNext only tracks consumption in SCO, not Job Card
            _update_job_card_consumed_qty(jc, item.subcontracting_order, received_qty)
            
            # Set status to Work In Progress if not already completed/submitted
            if jc.status not in ["Completed", "Submitted"]:
                jc.db_set("status", "Work In Progress", update_modified=False)
            
            frappe.logger().info({
                "job_card_updated": jc.name,
                "source": "subcontracting_receipt",
                "received_qty": received_qty,
                "for_quantity": jc.for_quantity,
                "auto_complete_disabled": True
            })


def _update_job_card_consumed_qty(jc, subcontracting_order, received_qty):
    """
    Update consumed_qty in Job Card items (RM) table based on SCR supplied_items.
    
    In subcontracting, the supplier consumes the RM we sent them to produce FG.
    So when we receive FG, we consider the corresponding RM as consumed.
    
    ERPNext's standard subcontracting tracks this in Subcontracting Order supplied_items,
    but NOT in Job Card items. This is a custom extension.
    """
    if not jc.items:
        return
    
    # Get all consumed items from SCRs linked to this job card
    # SCR.supplied_items tracks the raw materials consumed
    consumed_data = frappe.db.sql("""
        SELECT 
            scr_si.rm_item_code,
            SUM(scr_si.consumed_qty) as total_consumed
        FROM `tabSubcontracting Receipt Supplied Item` scr_si
        JOIN `tabSubcontracting Receipt` scr ON scr.name = scr_si.parent
        JOIN `tabSubcontracting Receipt Item` sri ON sri.parent = scr.name AND sri.job_card = %s
        WHERE scr.docstatus = 1
        GROUP BY scr_si.rm_item_code
    """, jc.name, as_dict=True)
    
    consumed_map = {row.rm_item_code: flt(row.total_consumed) for row in consumed_data}
    
    # Update each Job Card Item
    for jc_item in jc.items:
        consumed = consumed_map.get(jc_item.item_code, 0)
        frappe.db.set_value("Job Card Item", jc_item.name, "consumed_qty", consumed)
    
    frappe.logger().info({
        "job_card_consumed_updated": jc.name,
        "consumed_map": consumed_map
    })


