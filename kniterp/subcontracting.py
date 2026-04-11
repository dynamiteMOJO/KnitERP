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
    """
    _update_job_card_transferred_hook(se)

def on_se_cancel_update_job_card_transferred(se, method):
    """
    Recalculate Job Card's transferred_qty when Stock Entry (Send to Subcontractor) is cancelled.
    """
    _update_job_card_transferred_hook(se)

def _update_job_card_transferred_hook(se):
    """
    Common logic to identify Job Cards from Stock Entry and trigger update.
    """
    if se.purpose != "Send to Subcontractor":
        return
    
    if not se.subcontracting_order:
        return
    
    # Find Job Cards linked to this SCO
    # Link: SCO Item -> PO Item -> Job Card
    job_cards = frappe.db.sql("""
        SELECT DISTINCT poi.job_card
        FROM `tabSubcontracting Order Item` scoi
        JOIN `tabPurchase Order Item` poi ON poi.name = scoi.purchase_order_item
        WHERE scoi.parent = %s
        AND poi.job_card IS NOT NULL
    """, se.subcontracting_order, as_dict=True)
    
    for row in job_cards:
        if row.job_card:
            update_job_card_transferred_qty(row.job_card)

def update_job_card_transferred_qty(job_card_name):
    """
    Recalculate and update transferred_qty for a Job Card based on ALL relevant stock entries.
    Identifies proper SCOs linked to this Job Card to sum up quantities.
    """
    jc = frappe.get_doc("Job Card", job_card_name)
    
    # Subquery to find relevant SCOs (Those containing items linked to this Job Card)
    relevant_sco_subquery = """
        SELECT scoi.parent
        FROM `tabSubcontracting Order Item` scoi
        JOIN `tabPurchase Order Item` poi ON poi.name = scoi.purchase_order_item
        WHERE poi.job_card = %s
    """
    
    total_header_sent = 0.0
    has_change = False
    
    # Update Item Level Transferred Qty
    for item in jc.items:
        # Sum quantity from all SEs linked to relevant SCOs for this Item Code
        item_sent = frappe.db.sql(f"""
            SELECT SUM(sed.qty)
            FROM `tabStock Entry Detail` sed
            JOIN `tabStock Entry` se ON se.name = sed.parent
            WHERE se.docstatus = 1
            AND se.purpose = 'Send to Subcontractor'
            AND se.subcontracting_order IN ({relevant_sco_subquery})
            AND sed.item_code = %s
        """, (jc.name, item.item_code))
        
        qty = flt(item_sent[0][0]) if item_sent and item_sent[0][0] else 0.0
        
        if flt(item.transferred_qty) != qty:
             frappe.db.set_value("Job Card Item", item.name, "transferred_qty", qty)
             item.transferred_qty = qty
             has_change = True
        
        total_header_sent += qty

    # Update Header Transferred Qty
    if flt(jc.transferred_qty) != total_header_sent:
        jc.db_set("transferred_qty", total_header_sent, update_modified=False)
        has_change = True
        
    # Update Status based on progress
    current_status = jc.status
    new_status = current_status
    
    if total_header_sent >= jc.for_quantity and current_status not in ["Completed", "Submitted"]:
         new_status = "Material Transferred"
    elif total_header_sent > 0 and current_status not in ["Completed", "Submitted", "Material Transferred"]:
         new_status = "Work In Progress"
    elif total_header_sent == 0 and current_status not in ["Completed", "Submitted"]:
         new_status = "Open"
    
    if new_status != current_status:
        jc.db_set("status", new_status, update_modified=False)

    frappe.logger().info({
        "job_card_transferred_update": jc.name,
        "sent_qty": total_header_sent,
        "for_quantity": jc.for_quantity
    })


def on_dn_submit_update_scio_delivered(doc, method):
    _update_scio_delivered_qty(doc, is_cancel=False)


def on_dn_cancel_update_scio_delivered(doc, method):
    _update_scio_delivered_qty(doc, is_cancel=True)
    on_dn_cancel_clear_scio_sre(doc, method)


def _update_scio_delivered_qty(doc, is_cancel=False):
    scio_name = doc.get("custom_subcontracting_inward_order")
    if not scio_name:
        return

    for item in doc.items:
        scio_detail = item.get("custom_scio_detail")
        if not scio_detail:
            continue

        current_qty = flt(frappe.db.get_value(
            "Subcontracting Inward Order Item", scio_detail, "delivered_qty"
        ))
        delta = flt(item.stock_qty or item.qty)
        new_qty = current_qty - delta if is_cancel else current_qty + delta

        frappe.db.set_value(
            "Subcontracting Inward Order Item",
            scio_detail,
            "delivered_qty",
            max(new_qty, 0),
        )

    scio = frappe.get_doc("Subcontracting Inward Order", scio_name)
    scio.update_status()


def on_dn_before_submit_clear_scio_sre(doc, method):
    """
    Consume SCIO SREs before Delivery Note is submitted by incrementing delivered_qty.
    Mirrors how stock_controller.py handles Subcontracting Delivery Stock Entries.
    """
    _update_scio_sres(doc, is_cancel=False)

def on_dn_cancel_clear_scio_sre(doc, method):
    """
    Revert the consumed SCIO SREs when the Delivery Note is cancelled.
    """
    _update_scio_sres(doc, is_cancel=True)

def _update_scio_sres(doc, is_cancel=False):
    scio_name = doc.get("custom_subcontracting_inward_order")
    if not scio_name:
        return

    for item in doc.items:
        if not item.get("custom_scio_detail"):
            continue

        qty = flt(item.stock_qty or item.qty)
        if qty <= 0:
            continue

        blocking_sres = frappe.get_all(
            "Stock Reservation Entry",
            filters={
                "voucher_type": "Subcontracting Inward Order",
                "voucher_no": scio_name,
                "item_code": item.item_code,
                "warehouse": item.warehouse,
                "docstatus": 1,
            },
            order_by="creation desc"
        )

        for sre in blocking_sres:
            if qty <= 0:
                break

            sre_doc = frappe.get_doc("Stock Reservation Entry", sre.name)
            working_qty = 0

            if sre_doc.reservation_based_on == "Serial and Batch":
                sbb = frappe.get_doc("Serial and Batch Bundle", item.serial_and_batch_bundle)
                if sre_doc.has_serial_no:
                    serial_nos = [d.serial_no for d in sbb.entries if d.qty < 0] # outward
                    for entry in sre_doc.sb_entries:
                        if entry.serial_no in serial_nos:
                            if is_cancel:
                                entry.delivered_qty = 0
                            else:
                                entry.delivered_qty = 1
                            entry.db_update()
                            working_qty += 1
                            serial_nos.remove(entry.serial_no)
                else:
                    batch_qty = {d.batch_no: -1 * d.qty for d in sbb.entries if d.qty < 0}
                    for entry in sre_doc.sb_entries:
                        if entry.batch_no in batch_qty:
                            if is_cancel:
                                delivered_qty = min(entry.delivered_qty, batch_qty[entry.batch_no])
                                entry.delivered_qty -= delivered_qty
                                working_qty += delivered_qty
                            else:
                                delivered_qty = min(
                                    (entry.qty - entry.delivered_qty),
                                    batch_qty[entry.batch_no],
                                )
                                entry.delivered_qty += delivered_qty
                                working_qty += delivered_qty
                            
                            entry.db_update()
                            batch_qty[entry.batch_no] -= delivered_qty

            else:
                if is_cancel:
                    working_qty = min(sre_doc.delivered_qty, qty)
                else:
                    working_qty = min(sre_doc.reserved_qty - sre_doc.delivered_qty, qty)

            if working_qty > 0:
                if is_cancel:
                    sre_doc.db_set("delivered_qty", sre_doc.delivered_qty - working_qty)
                else:
                    sre_doc.db_set("delivered_qty", sre_doc.delivered_qty + working_qty)
                
                sre_doc.update_reserved_qty_in_voucher()
                sre_doc.update_status()
                sre_doc.update_reserved_stock_in_bin()

            qty -= working_qty