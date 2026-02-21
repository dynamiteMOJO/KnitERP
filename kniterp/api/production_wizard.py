"""
Production Wizard API

Unified production management API for the kniterp app.
Provides endpoints to manage the entire manufacturing process from a single interface.
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate, getdate, add_days, cint
import json
from erpnext.stock.doctype.stock_entry_type.stock_entry_type import ManufactureEntry
from erpnext.manufacturing.doctype.bom.bom import add_additional_cost
from kniterp.api.access_control import require_production_write_access


def log_manual_production_action(
    action,
    jc=None,
    se=None,
    wo=None,
    qty_before=None,
    qty_after=None,
    status_before=None,
    status_after=None,
    mode=None,
    outcome="success",
    message=None,
):
    """
    Append a structured timeline comment to the primary document(s) involved in a
    manual production action (P1.4 audit trail).

    Comment format:
      [PRODUCTION ACTION] {action}
      Actor: {user} | {timestamp}
      Job Card: {jc} | WO: {wo} | SE: {se}
      Qty: {qty_before} → {qty_after} | Status: {status_before} → {status_after}
      Mode: {mode}
      Outcome: {outcome} — {message}
    """
    import frappe.utils

    timestamp = frappe.utils.now()
    actor = frappe.session.user

    text = (
        f"[PRODUCTION ACTION] {action}\n"
        f"Actor: {actor} | {timestamp}\n"
        f"Job Card: {jc or '-'} | WO: {wo or '-'} | SE: {se or '-'}\n"
        f"Qty: {qty_before if qty_before is not None else '-'} → {qty_after if qty_after is not None else '-'} "
        f"| Status: {status_before or '-'} → {status_after or '-'}\n"
        f"Mode: {mode or '-'}\n"
        f"Outcome: {outcome} — {message or ''}"
    )

    # Add comment to Job Card (primary)
    if jc:
        try:
            jc_doc = frappe.get_doc("Job Card", jc) if isinstance(jc, str) else jc
            jc_doc.add_comment("Comment", text)
        except Exception:
            frappe.logger("kniterp").warning(f"[audit] Failed to add comment to Job Card {jc}")

    # Echo to Stock Entry when SE is involved
    if se:
        try:
            se_doc = frappe.get_doc("Stock Entry", se) if isinstance(se, str) else se
            se_doc.add_comment("Comment", text)
        except Exception:
            frappe.logger("kniterp").warning(f"[audit] Failed to add comment to Stock Entry {se}")

    # Echo to Work Order for WO-level visibility
    if wo:
        try:
            wo_doc = frappe.get_doc("Work Order", wo) if isinstance(wo, str) else wo
            wo_doc.add_comment("Comment", text)
        except Exception:
            frappe.logger("kniterp").warning(f"[audit] Failed to add comment to Work Order {wo}")



def check_rm_availability(item_code, required_qty):
    """
    Checks if RM is available for the given FG item and qty.
    Returns True if available, False otherwise.
    """
    # Get BOM
    bom_data = frappe.db.get_value('BOM', {'item': item_code, 'is_active': 1, 'is_default': 1}, ['name', 'quantity'], as_dict=1)
    if not bom_data:
        return False # No BOM means we can't determine, treat as shortage/issue
        
    bom_no = bom_data.name
    bom_qty = flt(bom_data.quantity) or 1.0

    # Get RMs from BOM
    rms = frappe.db.get_all('BOM Item', filters={'parent': bom_no}, fields=['item_code', 'qty', 'uom'])
    
    for rm in rms:
        needed = (flt(rm.qty) / bom_qty) * flt(required_qty)
        
        # Simple stock balance check
        bal = frappe.db.sql("SELECT sum(actual_qty) FROM `tabBin` WHERE item_code = %s", (rm.item_code,))
        actual = flt(bal[0][0]) if bal and bal[0][0] else 0.0
        
        if actual < needed:
            return False
            
    return True




@frappe.whitelist()
def get_unique_parties(filters=None):
    """
    Fetch unique customers who have pending production items, respecting current filters.
    """
    if filters and isinstance(filters, str):
        filters = json.loads(filters)
    
    filters = filters or {}
    
    conditions = []
    values = {"docstatus": 1}
    
    # Base conditions
    conditions.append("so.docstatus = %(docstatus)s")
    conditions.append("so.status NOT IN ('Closed', 'Completed')")
    conditions.append("(soi.qty > soi.delivered_qty OR soi.billed_amt < soi.amount)")
    
    # Apply other filters from the wizard
    if filters.get("from_date"):
        conditions.append("so.transaction_date >= %(from_date)s")
        values["from_date"] = filters.get("from_date")
    
    if filters.get("to_date"):
        conditions.append("so.transaction_date <= %(to_date)s")
        values["to_date"] = filters.get("to_date")
    
    if filters.get("urgent"):
        conditions.append("soi.delivery_date < %(today)s")
        values["today"] = nowdate()

    invoice_status = filters.get("invoice_status")
    if invoice_status in ["Pending Production", "Ready to Deliver"]:
        conditions.append("soi.qty > soi.delivered_qty")
    elif invoice_status == "Ready to Invoice":
        conditions.append("soi.qty <= soi.delivered_qty")

    if filters.get("job_work"):
        if filters.get("job_work") == "Inward":
            conditions.append("so.is_subcontracted = 1")
        elif filters.get("job_work") == "Outward":
            conditions.append("""
                EXISTS (
                    SELECT 1 FROM `tabWork Order` wo
                    INNER JOIN `tabJob Card` jc ON jc.work_order = wo.name
                    INNER JOIN `tabPurchase Order Item` poi ON poi.job_card = jc.name
                    INNER JOIN `tabSubcontracting Order` sco ON sco.purchase_order = poi.parent
                    WHERE wo.sales_order = so.name
                    AND wo.sales_order_item = soi.name
                    AND sco.docstatus = 1
                    AND sco.status NOT IN ('Closed', 'Completed', 'Cancelled')
                )
            """)
        elif filters.get("job_work") == "Standard":
             conditions.append("so.is_subcontracted = 0")
    
    where_clause = " AND ".join(conditions)

    parties = frappe.db.sql("""
        SELECT DISTINCT so.customer, so.customer_name
        FROM `tabSales Order` so
        INNER JOIN `tabSales Order Item` soi ON so.name = soi.parent
        WHERE {where_clause}
        ORDER BY so.customer_name ASC
    """.format(where_clause=where_clause), values, as_dict=True)
    
    return parties


@frappe.whitelist()
def get_pending_production_items(filters=None):
    """
    Fetch all Sales Order items pending manufacture.
    
    Returns items that have:
    - BOM defined
    - Pending qty > 0 (qty - delivered_qty - work_order_qty)
    - Sales Order is submitted and not closed
    """
    if filters and isinstance(filters, str):
        filters = json.loads(filters)
    
    filters = filters or {}
    
    conditions = []
    values = {"docstatus": 1}
    
    # Base conditions
    conditions.append("so.docstatus = %(docstatus)s")
    conditions.append("so.status NOT IN ('Closed', 'Completed')")
    conditions.append("(soi.qty > soi.delivered_qty OR soi.billed_amt < soi.amount)")
    
    # Optional filters
    if filters.get("customer"):
        conditions.append("so.customer = %(customer)s")
        values["customer"] = filters.get("customer")
    
    if filters.get("from_date"):
        conditions.append("so.transaction_date >= %(from_date)s")
        values["from_date"] = filters.get("from_date")
    
    if filters.get("to_date"):
        conditions.append("so.transaction_date <= %(to_date)s")
        values["to_date"] = filters.get("to_date")
    
    if filters.get("item_code"):
        conditions.append("soi.item_code = %(item_code)s")
        values["item_code"] = filters.get("item_code")
    
    if filters.get("urgent"):
        conditions.append("soi.delivery_date < %(today)s")
        values["today"] = nowdate()

    invoice_status = filters.get("invoice_status")
    if invoice_status in ["Pending Production", "Ready to Deliver"]:
        conditions.append("soi.qty > soi.delivered_qty")
    elif invoice_status == "Ready to Invoice":
        conditions.append("soi.qty <= soi.delivered_qty")

    if filters.get("job_work"):
        if filters.get("job_work") == "Inward":
            conditions.append("so.is_subcontracted = 1")
        elif filters.get("job_work") == "Outward":
            conditions.append("""
                EXISTS (
                    SELECT 1 FROM `tabWork Order` wo
                    INNER JOIN `tabJob Card` jc ON jc.work_order = wo.name
                    INNER JOIN `tabPurchase Order Item` poi ON poi.job_card = jc.name
                    INNER JOIN `tabSubcontracting Order` sco ON sco.purchase_order = poi.parent
                    WHERE wo.sales_order = so.name
                    AND wo.sales_order_item = soi.name
                    AND sco.docstatus = 1
                    AND sco.status NOT IN ('Closed', 'Completed', 'Cancelled')
                )
            """)
        elif filters.get("job_work") == "Standard":
             conditions.append("so.is_subcontracted = 0")
    
    where_clause = " AND ".join(conditions)
    
    items = frappe.db.sql("""
        SELECT
            soi.name as sales_order_item,
            so.name as sales_order,
            so.status as sales_order_status,
            so.customer,
            so.customer_name,
            so.transaction_date,
            soi.item_code,
            soi.item_name,
            soi.qty,
            soi.billed_amt,
            soi.amount,
            soi.delivered_qty,
            soi.work_order_qty,
            (soi.qty - soi.delivered_qty) as pending_qty,
            soi.delivery_date,
            soi.warehouse,
            soi.description,
            so.is_subcontracted,
            soi.fg_item,
            soi.fg_item_qty,
            COALESCE(soi.bom_no, (
                SELECT name FROM `tabBOM` 
                WHERE item = IF(so.is_subcontracted = 1, soi.fg_item, soi.item_code) AND is_active = 1 AND is_default = 1
                LIMIT 1
            )) as bom_no
        FROM `tabSales Order Item` soi
        INNER JOIN `tabSales Order` so ON so.name = soi.parent
        WHERE {where_clause}
        ORDER BY soi.delivery_date ASC, so.name ASC
    """.format(where_clause=where_clause), values, as_dict=True)
    
    # Get linked work orders for each item FIRST (before filtering)
    for item in items:
        # Determine production item
        item.production_item = item.fg_item if item.is_subcontracted else item.item_code
        
        # If subcontracted, recalculate pending qty based on fg_item_qty
        if item.is_subcontracted and item.fg_item_qty:
            # Pro-rate pending qty
            ratio = flt(item.fg_item_qty) / flt(item.qty) if item.qty else 1.0
            item.pending_qty = flt(item.pending_qty) * ratio
            
        # Get work order if exists
        work_order = frappe.db.get_value(
            "Work Order",
            {
                "sales_order": item.sales_order,
                "sales_order_item": item.sales_order_item,
                "docstatus": ["!=", 2]
            },
            ["name", "status", "qty", "produced_qty", "material_transferred_for_manufacturing"],
            as_dict=True
        )
        
        if work_order:
            item.work_order = work_order.name
            item.work_order_status = work_order.status
            item.work_order_qty = work_order.qty
            item.produced_qty = work_order.produced_qty
        else:
            # Fallback: Check if WO is linked via Subcontracting Inward Order (SIO)
            # SIO-created WOs might reference the SIO but not the SO directly
            if item.is_subcontracted:
                # Find SIO linking to this Sales Order Item
                sio_name = frappe.db.get_value("Subcontracting Inward Order Item", 
                    {"sales_order_item": item.sales_order_item, "docstatus": 1}, "parent")
                
                if sio_name:
                    # Find WO linked to this SIO
                    wo_sio = frappe.db.get_value("Work Order", 
                        {"subcontracting_inward_order": sio_name, "docstatus": ["!=", 2]},
                        ["name", "status", "qty", "produced_qty"], as_dict=True)
                    
                    if wo_sio:
                        item.work_order = wo_sio.name
                        item.work_order_status = wo_sio.status
                        item.work_order_qty = wo_sio.qty
                        item.produced_qty = wo_sio.produced_qty
                    else:
                        item.work_order = None
                        item.work_order_status = None
                        item.produced_qty = 0
                else:
                    item.work_order = None
                    item.work_order_status = None
                    item.produced_qty = 0
            else:
                item.work_order = None
                item.work_order_status = None
                item.produced_qty = 0
    
    # Post-query filtering for materials_status and invoice_status (Ready to Deliver)
    materials_status = filters.get("materials_status")
    
    final_items = items
    
    # Filter for Ready to Deliver (must have produced qty that hasn't been delivered yet)
    if invoice_status == "Ready to Deliver":
        ready_items = []
        for i in items:
            delivered_qty = flt(i.delivered_qty or 0)
            produced_qty = flt(i.produced_qty or 0)
            pending_to_deliver = flt(i.qty) - delivered_qty
            
            # Check if there's produced qty that hasn't been delivered
            ready_qty = 0
            if produced_qty > 0:
                ready_qty = max(0, produced_qty - delivered_qty)
            else:
                # No WO - check stock availability
                stock = frappe.db.sql("""
                    SELECT COALESCE(SUM(actual_qty), 0) 
                    FROM `tabBin` WHERE item_code = %s
                """, i.item_code)
                stock_qty = flt(stock[0][0] if stock else 0)
                ready_qty = min(stock_qty, pending_to_deliver)
            
            if ready_qty > 0:
                i.ready_to_deliver = ready_qty
                ready_items.append(i)
        
        items = ready_items
        final_items = items

    if materials_status:
        filtered_items = []
        for item in final_items:
            # We only check availability if work order is not started
            if not item.work_order or item.work_order_status in ['Draft', 'Not Started']:
                is_ready = check_rm_availability(item.production_item, item.pending_qty)
                
                if materials_status == 'Ready':
                    if is_ready:
                        filtered_items.append(item)
                elif materials_status == 'Shortage':
                    if not is_ready:
                         filtered_items.append(item)
            else:
                # If WO started, we generally consider it 'handled' for this specific filter purpose
                # or we exclude it. For now, let's include it only if 'All' (which is the default branch)
                # If specific status requested for *Production Planning*, started ones are usually ignored or separate.
                pass
        
        final_items = filtered_items
    
    return final_items



@frappe.whitelist()
def get_production_details(sales_order_item):
    """
    Get detailed breakdown of a single item's production requirements.
    
    Returns:
    - Item details
    - BOM info
    - Operations with status (in-house vs subcontracted)
    - Raw material availability
    - Linked documents (Work Order, Job Cards, POs, etc.)
    """
    # Get Sales Order Item details
    soi = frappe.db.get_value(
        "Sales Order Item",
        sales_order_item,
        ["name", "parent", "item_code", "item_name", "qty", "delivered_qty", 
         "delivery_date", "warehouse", "bom_no", "description", "fg_item", "fg_item_qty",
         "stock_uom", "billed_amt", "amount", "rate", "custom_transaction_params_json"],
        as_dict=True
    )
    
    if not soi:
        frappe.throw(_("Sales Order Item not found"))
        
    so = frappe.db.get_value("Sales Order", soi.parent, ["is_subcontracted", "company"], as_dict=True)
    is_subcontracted = so.is_subcontracted
    production_item = soi.fg_item if is_subcontracted else soi.item_code
    
    # Get BOM
    bom_no = soi.bom_no
    if not bom_no:
        bom_no = frappe.db.get_value(
            "BOM",
            {"item": production_item, "is_active": 1, "is_default": 1},
            "name"
        )
    
    bom = None
    if bom_no:
        bom = frappe.get_doc("BOM", bom_no)
    
    # Check BOM compatibility with Subcontracting Inward
    bom_scio_compatible = True
    if is_subcontracted and bom:
        has_customer_provided = False
        for item in bom.items:
            if item.is_sub_assembly_item:
                continue
            if frappe.get_cached_value("Item", item.item_code, "is_customer_provided_item"):
                has_customer_provided = True
                break
        if not has_customer_provided:
            bom_scio_compatible = False
    
    # Get Work Order if exists
    work_order = None
    work_order_doc = None
    job_cards = []
    
    wo_name = frappe.db.get_value(
        "Work Order",
        {
            "sales_order": soi.parent,
            "sales_order_item": soi.name,
            "docstatus": ["!=", 2]
        },
        "name"
    )

    if not wo_name and is_subcontracted:
        # Fallback: Check if WO is linked via Subcontracting Inward Order (SIO)
        sio_name_check = frappe.db.get_value("Subcontracting Inward Order Item", 
            {"sales_order_item": soi.name, "docstatus": 1}, "parent")
        
        if sio_name_check:
            wo_name = frappe.db.get_value("Work Order", 
                {"subcontracting_inward_order": sio_name_check, "docstatus": ["!=", 2]},
                "name")
    
    if wo_name:
        work_order_doc = frappe.get_doc("Work Order", wo_name)
        work_order = {
            "name": work_order_doc.name,
            "status": work_order_doc.status,
            "qty": work_order_doc.qty,
            "produced_qty": work_order_doc.produced_qty,
            "material_transferred_for_manufacturing": work_order_doc.material_transferred_for_manufacturing
        }
        
        # Get Job Cards
        job_cards = frappe.get_all(
            "Job Card",
            filters={"work_order": wo_name, "docstatus": ["!=", 2]},
            fields=["name", "operation", "status", "for_quantity", "total_completed_qty", 
                    "is_subcontracted", "wip_warehouse"]
        )
    
    # Check for Subcontracting Inward Order
    sio_name = None
    sio_status = None
    sio_delivered_qty = 0
    sio_qty = 0
    
    if is_subcontracted:
        sio_item = frappe.db.get_value(
            "Subcontracting Inward Order Item",
            {"sales_order_item": soi.name, "docstatus": ["!=", 2]},
            ["parent", "qty", "delivered_qty"],
            as_dict=True
        )
        if sio_item:
            sio_name = sio_item.parent
            sio_qty = flt(sio_item.qty)
            sio_delivered_qty = flt(sio_item.delivered_qty)
            sio_status = frappe.db.get_value("Subcontracting Inward Order", sio_name, "status")
            
            # Fetch SIO received items (Customer Provided Items)
            sio_received_items = frappe.get_all(
                "Subcontracting Inward Order Received Item",
                filters={"parent": sio_name, "is_customer_provided_item": 1},
                fields=["rm_item_code", "required_qty", "received_qty", "returned_qty", "warehouse"]
            )
            
            # Store in dict for easy lookup
            # Assume one entry per item code for simplicity, though could be multiple? usually one per item
            sio_received_map = {item.rm_item_code: item for item in sio_received_items}
    
    # Check for Draft Sales Invoice
    draft_sales_invoice = frappe.db.get_value(
        "Sales Invoice Item",
        {"so_detail": soi.name, "docstatus": 0},
        "parent"
    )

    pending_qty = soi.qty - soi.delivered_qty
    if is_subcontracted and soi.fg_item_qty:
         ratio = flt(soi.fg_item_qty) / flt(soi.qty) if soi.qty else 1.0
         pending_qty = flt(pending_qty) * ratio

    # --- 1. Calculate Raw Materials & Max Producible (Pre-Process) ---
    # We do this FIRST because Operations availability depends on Max Producible bottleneck
    
    raw_materials = []
    max_producible_qty = None
    bottleneck_item = None
    
    if bom:
        company = so.company
        item_rates_map = {} # Cache
        
        for item in bom.items:
            # Skip semi-finished goods - they are produced by earlier operations, not purchased
            if item.is_sub_assembly_item:
                continue
            
            required_qty = flt(flt(item.qty) * flt(pending_qty) / flt(bom.quantity), 3)
            original_required_qty = required_qty # Keep track for usage rate calculation
            
            # Get available qty from bin
            bin_data = frappe.db.get_value(
                "Bin",
                {"item_code": item.item_code, "warehouse": soi.warehouse or item.source_warehouse},
                ["actual_qty", "projected_qty", "reserved_qty"],
                as_dict=True
            ) or {}
            
            actual_qty = flt(bin_data.get("actual_qty", 0), 3)
            projected_qty = flt(bin_data.get("projected_qty", 0), 3)
            reserved_qty = flt(bin_data.get("reserved_qty", 0), 3)
            
            available_qty = actual_qty - reserved_qty
            shortage = max(0, required_qty - available_qty)
            
            # Check if material is consumed via Stock Entries
            material_consumed = False
            consumed_qty = 0
            
            # Find the job card(s) for this item
            target_jc_names = []
            if item.operation:
                # Find matching job cards by operation name
                target_jc_names = [jc.name for jc in job_cards if jc.operation == item.operation]
            elif job_cards:
                 # Default to all job cards if no specific op is defined in BOM Item
                 target_jc_names = [jc.name for jc in job_cards]

            if target_jc_names:
                # Sum up consumed qty from Stock Entries for ALL matching job cards
                placeholders = ', '.join(['%s'] * len(target_jc_names))
                query_args = tuple(target_jc_names) + (item.item_code,)
                
                actual_consumed = frappe.db.sql(f"""
                    SELECT SUM(sed.qty)
                    FROM `tabStock Entry` se
                    JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
                    WHERE se.job_card IN ({placeholders})
                    AND se.docstatus = 1
                    AND se.purpose = 'Manufacture'
                    AND sed.item_code = %s
                    AND sed.is_finished_item = 0
                """, query_args)
                
                consumed_qty = flt(actual_consumed[0][0]) if actual_consumed and actual_consumed[0][0] else 0
                
                if consumed_qty > 0:
                     material_consumed = True
                     required_qty = max(0, flt(required_qty) - flt(consumed_qty))
                     shortage = max(0, required_qty - available_qty)
            
            # Determine status
            if material_consumed and required_qty == 0:
                status = "consumed"
            elif shortage > 0:
                status = "shortage"
            else:
                 status = "available"

            # Get POs...
            po_data = frappe.db.sql("""
                SELECT 
                    po.name as po_name,
                    po.status as po_status,
                    poi.qty as ordered_qty,
                    poi.received_qty,
                    poi.warehouse,
                    poi.sales_order,
                    poi.sales_order_item
                FROM `tabPurchase Order Item` poi
                INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
                WHERE poi.item_code = %s
                AND (
                    poi.sales_order_item = %s 
                    OR ( (poi.sales_order_item IS NULL OR poi.sales_order_item = '') AND poi.sales_order = %s )
                    OR ( (poi.sales_order IS NULL OR poi.sales_order = '') )
                )
                AND po.docstatus = 1
                AND po.status NOT IN ('Closed', 'Cancelled')
                ORDER BY po.creation DESC
            """, (item.item_code, soi.name, soi.parent), as_dict=True)
            
            linked_pos = []
            total_ordered = 0
            for po in po_data:
                pending = flt(po.ordered_qty) - flt(po.received_qty)
                if pending > 0:
                    total_ordered += pending
                    linked_pos.append({
                        "po_name": po.po_name,
                        "status": po.po_status,
                        "ordered_qty": flt(po.ordered_qty),
                        "received_qty": flt(po.received_qty),
                        "pending_qty": pending
                    })
            
            # Item Rates
            if item.item_code not in item_rates_map:
                item_rates_map[item.item_code] = frappe.db.get_value("Item", item.item_code, ["last_purchase_rate", "valuation_rate"], as_dict=True) or {}
            item_rates = item_rates_map[item.item_code]
            
            # SIO Check
            is_cust_provided = 0
            sio_req = 0
            sio_rec = 0
            
            if is_subcontracted and sio_name and item.item_code in sio_received_map:
                sio_data = sio_received_map[item.item_code]
                is_cust_provided = 1
                sio_req = flt(sio_data.required_qty)
                sio_rec = flt(sio_data.received_qty)
                
                cust_wh = sio_data.warehouse
                if cust_wh:
                    bin_data_cust = frappe.db.get_value(
                        "Bin",
                        {"item_code": item.item_code, "warehouse": cust_wh},
                        ["actual_qty", "projected_qty", "reserved_qty"],
                        as_dict=True
                    ) or {}
                    
                    available_qty = flt(bin_data_cust.get("actual_qty", 0), 3) - flt(bin_data_cust.get("reserved_qty", 0), 3)
                    shortage = max(0, required_qty - available_qty)
                    
                    if sio_rec < sio_req:
                         status = "pending_receipt"
                    else:
                         if shortage <= 0: status = "available_cust"
                         elif available_qty > 0: status = "partial_cust"
                         else: status = "shortage_cust"

            # Max Producible Logic
            # Use original ratio to determine usage per unit of FG/pending_qty
            # Remove restrictive condition to allow calculation even if partially received
            qty_per_unit = original_required_qty / flt(pending_qty) if pending_qty else 0
            
            if qty_per_unit > 0:
                available = flt(available_qty)
                producible_from_rm = available / qty_per_unit
                
                if max_producible_qty is None or producible_from_rm < max_producible_qty:
                    max_producible_qty = producible_from_rm
                    bottleneck_item = item.item_code

            rm_data = {
                "item_code": item.item_code,
                "item_name": item.item_name,
                "required_qty": required_qty,
                "available_qty": available_qty,
                "shortage": shortage,
                "status": status,
                "consumed_qty": consumed_qty,
                "ordered_qty": total_ordered,
                "linked_pos": linked_pos,
                "operation_next": item.operation,
                "is_customer_provided": is_cust_provided,
                "sio_received_qty": sio_rec,
                "sio_required_qty": sio_req,
                "last_purchase_rate": flt(item.rate) if item.rate else flt(item_rates.get("last_purchase_rate", 0)),
                "valuation_rate": flt(item_rates.get("valuation_rate", 0)),
                "qty_per_unit": flt(original_required_qty / flt(pending_qty), 6) if pending_qty else 0,
                "uom": item.uom,
                "warehouse": soi.warehouse or item.source_warehouse
            }
            raw_materials.append(rm_data)

    if max_producible_qty:
        nearest_int = round(max_producible_qty)
        if abs(max_producible_qty - nearest_int) < 0.005:
            max_producible_qty = nearest_int
    max_producible_qty = flt(max_producible_qty, 3) if max_producible_qty else 0

    
    # --- 2. Build Operations & Production Flow ---
    # Now we can calculate flow knowing max_producible_qty constraints
    
    operations = []
    
    if bom:
        for idx, op in enumerate(bom.operations):
            # Calculate expected qty from BOM operation's finished_good_qty (scrap factor)
            # If operation has finished_good_qty, use ratio to calculate operation qty
            expected_qty = pending_qty
            if op.finished_good_qty:
                expected_qty = flt(flt(op.finished_good_qty) * flt(pending_qty) / flt(bom.quantity), 3)
            
            operation_data = {
                "idx": op.idx,
                "sequence_id": op.sequence_id or op.idx,
                "operation": op.operation,
                "workstation": op.workstation,
                "workstation_type": op.workstation_type,
                "time_in_mins": op.time_in_mins,
                "is_subcontracted": op.is_subcontracted or False,
                "status": "Pending",
                "completed_qty": 0,
                "for_quantity": expected_qty,  # Pre-calculated from BOM
                "job_card": None,
                "purchase_order": None,
                "subcontracting_receipt": None,
                "previous_complete": idx == 0  # First operation can always start
            }
            
            # Find corresponding job card
            for jc in job_cards:
                if jc.operation == op.operation:
                    operation_data["job_card"] = jc.name
                    operation_data["status"] = jc.status
                    operation_data["completed_qty"] = jc.total_completed_qty or 0
                    operation_data["for_quantity"] = jc.for_quantity  # Override with actual job card qty
                    operation_data["is_subcontracted"] = jc.is_subcontracted
                    
                    # If subcontracted, find ALL POs and receipt details (supports multiple SCOs per operation)
                    if jc.is_subcontracted:
                        # Fetch all PO items for this job card
                        po_items = frappe.db.sql("""
                            SELECT poi.parent as po_name, poi.fg_item_qty, poi.qty
                            FROM `tabPurchase Order Item` poi
                            INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
                            WHERE poi.job_card = %s AND po.docstatus != 2
                            ORDER BY po.creation ASC
                        """, jc.name, as_dict=True)
                        
                        total_po_qty = 0
                        total_sent_qty = 0
                        total_received_qty = 0
                        subcontracting_orders = []  # List of individual SCOs for display
                        
                        for po in po_items:
                            po_fg_qty = flt(po.fg_item_qty or po.qty)
                            total_po_qty += po_fg_qty
                            
                            # Get SCO for this PO
                            sco = frappe.db.get_value(
                                "Subcontracting Order",
                                {"purchase_order": po.po_name, "docstatus": 1},
                                "name"
                            )
                            
                            if sco:
                                # Get material sent qty from Stock Entry
                                sent_qty = frappe.db.sql("""
                                    SELECT COALESCE(SUM(sed.qty), 0)
                                    FROM `tabStock Entry` se
                                    JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
                                    WHERE se.subcontracting_order = %s
                                    AND se.purpose = 'Send to Subcontractor'
                                    AND se.docstatus = 1
                                """, sco)[0][0] or 0
                                
                                # Get received qty from Subcontracting Receipt 
                                received_qty = frappe.db.sql("""
                                    SELECT COALESCE(SUM(sri.received_qty), 0)
                                    FROM `tabSubcontracting Receipt` scr
                                    JOIN `tabSubcontracting Receipt Item` sri ON sri.parent = scr.name
                                    WHERE sri.subcontracting_order = %s
                                    AND scr.docstatus = 1
                                """, sco)[0][0] or 0
                                
                                total_sent_qty += flt(sent_qty, 3)
                                total_received_qty += flt(received_qty, 3)
                                
                                # Get supplier for display
                                supplier = frappe.db.get_value("Purchase Order", po.po_name, "supplier")
                                
                                # Get Total Required RM Qty (to decide "Send Material" visibility)
                                required_rm_qty = frappe.db.sql("""
                                    SELECT COALESCE(SUM(required_qty), 0)
                                    FROM `tabSubcontracting Order Supplied Item`
                                    WHERE parent = %s
                                """, sco)[0][0] or 0
                                
                                subcontracting_orders.append({
                                    "po_name": po.po_name,
                                    "sco_name": sco,
                                    "supplier": supplier,
                                    "qty": po_fg_qty,
                                    "required_rm_qty": flt(required_rm_qty, 3),
                                    "sent_qty": flt(sent_qty, 3),
                                    "received_qty": flt(received_qty, 3)
                                })
                        
                        if po_items:
                            operation_data["purchase_order"] = po_items[0].po_name  # First PO for backward compat
                            operation_data["po_qty"] = total_po_qty
                            operation_data["sent_qty"] = total_sent_qty
                            operation_data["received_qty"] = total_received_qty
                            operation_data["subcontracting_orders"] = subcontracting_orders
                            operation_data["remaining_to_subcontract"] = flt(jc.for_quantity) - total_po_qty
                            
                            # For subcontracted ops: Use actual Job Card status
                            # User will manually complete via "Complete Job Card" button when ready
                            # Track received qty for progress display
                            operation_data["completed_qty"] = total_received_qty
                            # status remains from jc.status (from DB) - no auto-completion
                    break
            
            operations.append(operation_data)

    # Set previous_complete flag and calculate available_to_process
    for idx, op in enumerate(operations):
        # Determine what has already been processed in THIS operation (in FG/Output terms usually)
        current_processed = flt(op.get("po_qty") if op.get("is_subcontracted") else op.get("completed_qty"), 3)
        
        if idx == 0:
            # First operation: limited by total pending qty
            prev_output = pending_qty
            op["previous_complete"] = True # First op is always ready to start
        else:
            prev_op = operations[idx - 1]
            # Previous output is what was completed/received
            if prev_op.get("is_subcontracted"):
                prev_output = flt(prev_op.get("received_qty"), 3)
                # For subcontracted: can proceed if any goods received
                op["previous_complete"] = prev_output > 0 or prev_op["status"] == "Completed"
            else:
                prev_output = flt(prev_op.get("completed_qty"), 3)
                # For in-house: can proceed if any qty is completed
                op["previous_complete"] = prev_output > 0 or prev_op["status"] == "Completed"

        # Calculate Conversion Factor (Prev Op Output -> Current Op Output/FG)
        conversion_factor = 1.0
        
        if idx == 0:
             # First operation: Check if BOM defines a different quantity for this Op compared to the SO Item
             # If so, calculate the conversion factor: SO Item Qty / Op Required Qty
             # Example: SO Item 700, Op Req 714.287 -> CF = 700 / 714.287 = 0.98...
             # Then Available Input (700 logic) / CF -> 714.287 (Op logic)
             if op.get("for_quantity") and pending_qty:
                 conversion_factor = flt(pending_qty) / flt(op["for_quantity"])
        elif idx > 0:
            # Try to use explicit finished_good_qty from attributes first (most accurate)
            # op is from bom.operations iteration, so it has attributes
            prev_bom_op = bom.operations[idx - 1]
            
            # Check if Prev Op has explicit output qty
            if getattr(prev_bom_op, "finished_good_qty", 0):
                 prev_op_output_per_bom = flt(prev_bom_op.finished_good_qty)
                 # Factor = Prev Output / BOM Qty
                 conversion_factor = prev_op_output_per_bom / flt(bom.quantity)
            else:
                # Fallback: Find items in BOM linked to THIS operation (Input for this op)
                consumed_items = [d for d in bom.items if d.operation == op["operation"]]
                if consumed_items and bom.quantity:
                    # Qty of SFG required per BOM Qty
                    qty_per_bom = flt(consumed_items[0].qty)
                    conversion_factor = qty_per_bom / flt(bom.quantity)
        
        if conversion_factor == 0:
            conversion_factor = 1.0

        # available_to_process (in Current Op terms) = (Available Input / Conversion Factor) - Processed
        val_unrounded = (prev_output / conversion_factor) - current_processed
        available_op_qty = flt(val_unrounded, 3)
        
        # Limit available_to_process by max_producible_qty for the first operation
        # This ensures we don't suggest processing more than we have RM for
        if idx == 0 and max_producible_qty is not None:
            # max_producible_qty is in FG units
            # available_op_qty is in Op units. We must convert max_producible_qty to Op units.
            max_producible_op = flt(max_producible_qty) / conversion_factor
            
            # Instead of capping, if we overproduced, available_op_qty might be negative or 0.
            # But we can still produce up to max_producible_op based on RM!
            # So for the first operation, the TRUE RM availability is exactly max_producible_op.
            # And we don't want to limit it by (pending_qty - processed) if they overproduce.
            # We just use max_producible_op directly, and let remaining_required cap it later for the default value.
            available_op_qty = max_producible_op
        
        available_op_qty = max(0, available_op_qty)

        # But we shouldn't exceed the total required for this operation
        total_required = flt(op.get("for_quantity") or pending_qty, 3)
        remaining_required = max(0, total_required - current_processed)

        # Available to process
        op["available_to_process"] = min(available_op_qty, remaining_required)
        op["available_to_process"] = flt(op["available_to_process"], 3)
        
        # Store the raw "waiting" qty specifically from flow context (in Op terms for consistency in UI)
        op["qty_ready_from_prev"] = available_op_qty
        op["conversion_factor"] = conversion_factor # Useful for UI debugging if propertie needed
    
 
    fg_projected_qty = pending_qty
    

    if work_order:
        if work_order["status"] == "Completed":
            fg_projected_qty = work_order["produced_qty"]
        elif operations:
            # If in progress, look at the last operation
            # The last operation drives the final output
            last_op = operations[-1]
            if last_op.get("job_card"):
                # If last op has a job card, its 'for_quantity' (updated by cascade) 
                # is the best projection of final output
                fg_projected_qty = last_op["for_quantity"]
            elif work_order.get("qty"):
                 # Fallback to WO qty if last op not started but WO exists
                 fg_projected_qty = work_order["qty"]


    
    return {
        "sales_order": soi.parent,
        "sales_order_item": soi.name,
        "item_code": soi.item_code,
        "fg_item": soi.fg_item,
        "fg_item_qty": soi.fg_item_qty,
        "is_subcontracted": is_subcontracted,
        "production_item": production_item,
        "item_name": soi.item_name,
        "qty": soi.qty,
        "delivered_qty": soi.delivered_qty,
        "pending_qty": soi.qty - soi.delivered_qty,
        "delivery_date": soi.delivery_date,
        "warehouse": soi.warehouse,
        "description": soi.description,
        "bom_no": bom_no,
        "bom_qty": bom.quantity if bom else 1.0,
        "work_order": work_order,
        "operations": operations,
        "raw_materials": raw_materials,
        "projected_qty": fg_projected_qty,
        "max_producible_qty": max_producible_qty,
        "bottleneck_item": bottleneck_item,
        "subcontracting_inward_order": sio_name,
        "sio_status": sio_status,
        "sio_qty": sio_qty,
        "sio_delivered_qty": sio_delivered_qty,
        "bom_scio_compatible": bom_scio_compatible,
        "uom": soi.stock_uom,
        "billed_amt": soi.billed_amt,
        "amount": soi.amount,
        "rate": soi.rate,
        "draft_sales_invoice": draft_sales_invoice,
        "notes": get_notes(soi.name),
        "transaction_parameters": json.loads(soi.custom_transaction_params_json or '[]')
    }


@frappe.whitelist()
def create_work_order(sales_order, sales_order_item):
    """
    Create Work Order for a Sales Order item.
    Returns the created Work Order name.
    """
    require_production_write_access("create work orders")

    # Get Sales Order Item
    soi = frappe.db.get_value(
        "Sales Order Item",
        sales_order_item,
        ["item_code", "qty", "delivered_qty", "warehouse", "bom_no", "description", "fg_item", "fg_item_qty"],
        as_dict=True
    )
    
    if not soi:
        frappe.throw(_("Sales Order Item not found"))
        
    so = frappe.db.get_value("Sales Order", sales_order, ["company", "project", "is_subcontracted"], as_dict=True)
    is_subcontracted = so.is_subcontracted
    production_item = soi.fg_item if is_subcontracted else soi.item_code
    
    if is_subcontracted and not production_item:
         frappe.throw(_("Finished Good Item (fg_item) is missing for this Subcontracted Order"))
    
    # Check if work order already exists
    existing_wo = frappe.db.get_value(
        "Work Order",
        {
            "sales_order": sales_order,
            "sales_order_item": sales_order_item,
            "docstatus": ["!=", 2]
        },
        "name"
    )
    
    if existing_wo:
        frappe.throw(_("Work Order {0} already exists for this item").format(existing_wo))
    
    # Get BOM
    bom_no = soi.bom_no
    if not bom_no:
        bom_no = frappe.db.get_value(
            "BOM",
            {"item": production_item, "is_active": 1, "is_default": 1},
            "name"
        )
    
    if not bom_no:
        frappe.throw(_("No active BOM found for item {0}").format(production_item))
    
    # Get Sales Order details
    # so already fetched above
    pass
    
    # Create Work Order
    wo = frappe.new_doc("Work Order")
    wo.production_item = production_item
    wo.bom_no = bom_no
    
    qty_to_produce = flt(soi.qty) - flt(soi.delivered_qty)
    if is_subcontracted and soi.fg_item_qty:
         ratio = flt(soi.fg_item_qty) / flt(soi.qty) if soi.qty else 1.0
         qty_to_produce = flt(qty_to_produce) * ratio
         
    wo.qty = qty_to_produce
    wo.sales_order = sales_order
    wo.sales_order_item = sales_order_item
    wo.company = so.company
    wo.project = so.project
    wo.fg_warehouse = soi.warehouse
    wo.description = soi.description

    if is_subcontracted:
        scio_details = frappe.db.get_value(
            "Subcontracting Inward Order", 
            {"sales_order": sales_order, "docstatus": 1}, 
            ["name", "customer_warehouse"],
            as_dict=True
        )
        if scio_details:
            scio_item_details = frappe.db.get_value(
                "Subcontracting Inward Order Item", 
                {"parent": scio_details.name, "sales_order_item": sales_order_item}, 
                ["name", "delivery_warehouse", "qty", "include_exploded_items"],
                as_dict=True
            )
            if scio_item_details:
                wo.subcontracting_inward_order = scio_details.name
                wo.subcontracting_inward_order_item = scio_item_details.name
                wo.source_warehouse = scio_details.customer_warehouse
                wo.reserve_stock = 1
                wo.use_multi_level_bom = scio_item_details.include_exploded_items
                if scio_item_details.delivery_warehouse:
                    wo.fg_warehouse = scio_item_details.delivery_warehouse

                # Calculate correct max_producible_qty if linked to SCIO (Core Logic from SubcontractingInwardOrder.get_production_items)
                scio_item_qty = scio_item_details.qty
                
                # Get received items linked to this SCIO Item
                received_items = frappe.get_all(
                    "Subcontracting Inward Order Received Item",
                    filters={
                        "parent": wo.subcontracting_inward_order,
                        "reference_name": wo.subcontracting_inward_order_item,
                        "is_customer_provided_item": 1,
                        "docstatus": 1
                    },
                    fields=["received_qty", "returned_qty", "work_order_qty", "required_qty", "rm_item_code"]
                )
                
                possible_quantities = []
                for ri in received_items:
                    if flt(ri.required_qty) > 0 and flt(scio_item_qty) > 0:
                        # Qty required per unit of FG
                        qty_per_fg = flt(ri.required_qty) / flt(scio_item_qty)
                        
                        # Available RM for production
                        available_rm = flt(ri.received_qty) - flt(ri.returned_qty) - flt(ri.work_order_qty)
                        
                        if qty_per_fg > 0:
                            max_fg = available_rm / qty_per_fg
                            possible_quantities.append(max_fg)
                
                if possible_quantities:
                    # Set max producible for informational purposes (ERPNext shows a warning, not an error)
                    # Do NOT cap wo.qty — allow full SCIO qty so the WO stays "In Process"
                    # and supports incremental production (partial RM → partial production → partial delivery)
                    wo.max_producible_qty = min(possible_quantities)
    
    
    wo.set_work_order_operations()
    wo.set_required_items()
    
    # Check if Source Warehouse is a Customer Warehouse and mark items as Customer Provided
    if wo.source_warehouse:
        is_customer_wh = frappe.get_cached_value("Warehouse", wo.source_warehouse, "customer")
        if is_customer_wh:
            for item in wo.required_items:
                if not item.source_warehouse or item.source_warehouse == wo.source_warehouse:
                    item.source_warehouse = wo.source_warehouse
                    item.is_customer_provided_item = 1
    
    # Calculate custom planned output for each operation based on BOM requirements
    # Logic: 
    # 1. Check if BOM Operation defines 'finished_good_qty' (Output of that op)
    # 2. If not, fallback to Input Qty required for Next Op (Logic from before)
    if wo.operations:
         bom_doc = frappe.get_doc("BOM", wo.bom_no)
         
         # Map operations by name or index. WO Ops are copied from BOM Ops.
         # Ideally match by operation and sequence_id
         
         for idx, op in enumerate(wo.operations):
            planned_qty = wo.qty
            
            # Find corresponding BOM Operation
            bom_op = None
            if idx < len(bom_doc.operations):
                bom_op = bom_doc.operations[idx]
                # Double check matching
                if bom_op.operation != op.operation:
                     # Fallback search
                     found = [b for b in bom_doc.operations if b.operation == op.operation]
                     if found: bom_op = found[0]
            
            if bom_op and flt(bom_op.finished_good_qty) > 0:
                 # Use explicit output qty from BOM Op
                 per_unit_qty = flt(bom_op.finished_good_qty) / flt(bom_doc.quantity)
                 planned_qty = flt(wo.qty) * per_unit_qty
            
            # Fallback: If BOM Op qty missing, check what NEXT op consumes (only if mapped)
            elif idx < len(wo.operations) - 1:
                next_op = wo.operations[idx + 1]
                
                # Find items in BOM linked to next_op.operation
                consumed_items = [
                    d for d in bom_doc.items 
                    if d.operation == next_op.operation
                ]
                
                if consumed_items:
                    # Use the quantity of the first/major item consumed by the next step
                    per_unit_qty = flt(consumed_items[0].qty) / flt(bom_doc.quantity)
                    planned_qty = flt(wo.qty) * per_unit_qty
            
            # Set the custom field
            op.custom_planned_output_qty = planned_qty

    wo.flags.ignore_mandatory = True
    wo.flags.ignore_validate = True
    wo.insert()
    
    frappe.msgprint(_("Work Order {0} created successfully").format(wo.name))
    
    return wo.name


@frappe.whitelist()
def start_work_order(work_order, operation_settings=None):
    """
    Submit Work Order to start production.
    This will create Job Cards for each operation.
    """
    require_production_write_access("start work orders")

    if operation_settings and isinstance(operation_settings, str):
        operation_settings = json.loads(operation_settings)

    wo = frappe.get_doc("Work Order", work_order)
    
    if wo.docstatus == 1:
        frappe.throw(_("Work Order is already submitted"))
    
    if wo.docstatus == 2:
        frappe.throw(_("Work Order is cancelled"))
    
    # Validate material availability before starting
    for item in wo.required_items:
        bin_data = frappe.db.get_value(
            "Bin",
            {"item_code": item.item_code, "warehouse": item.source_warehouse},
            ["actual_qty", "reserved_qty"],
            as_dict=True
        ) or {}
        
        actual_qty = flt(bin_data.get("actual_qty", 0))
        reserved_qty = flt(bin_data.get("reserved_qty", 0))
        available = actual_qty - reserved_qty
        if flt(available, 3) < flt(item.required_qty, 3):
            frappe.msgprint(
                _("Warning: Insufficient stock for {0}. Available: {1}, Required: {2}").format(
                    item.item_code, available, item.required_qty
                ),
                indicator="orange"
            )
    
    wo.submit()
    
    # Update Job Cards with correct quantities and apply settings
    # Also fetch created JCs to update for_quantity from custom_planned_output_qty
    
    # Re-fetch WO to get operations with custom_planned_output_qty
    wo.reload()
    op_qty_map = {op.operation: op.custom_planned_output_qty for op in wo.operations}

    job_cards = frappe.get_all("Job Card", filters={"work_order": wo.name, "docstatus": 0}, fields=["name", "operation"])
    
    # Create a map for settings lookup
    settings_map = {s.get("operation"): s for s in operation_settings} if operation_settings else {}
    
    for jc_item in job_cards:
        jc = frappe.get_doc("Job Card", jc_item.name)
        
        # 1. Update Quantity if custom planned output is set
        planned_qty = op_qty_map.get(jc.operation)
        if planned_qty and flt(planned_qty) > 0:
            jc.for_quantity = planned_qty
            
        # 2. Apply User Settings
        settings = settings_map.get(jc.operation)
        if settings:
            if "skip_material_transfer" in settings:
                jc.skip_material_transfer = cint(settings["skip_material_transfer"])
            
            if "wip_warehouse" in settings:
                jc.wip_warehouse = settings["wip_warehouse"]
            
            if "workstation" in settings and settings["workstation"]:
                jc.workstation = settings["workstation"]
        
        # Final validation: Ensure workstation exists before standard save
        if not jc.workstation:
            # Fallback to first available matching workstation type if BOM was empty
            filters = {}
            if jc.workstation_type:
                filters["workstation_type"] = jc.workstation_type
            
            jc.workstation = frappe.db.get_value("Workstation", filters, "name")
        
        # Bypass sequence validation when just applying initial settings
        # (we're not completing operations, just setting workstation/wip_warehouse)
        jc.flags.ignore_validate = True
        jc.save()
        jc.flags.ignore_validate = False

    frappe.msgprint(_("Work Order {0} started. Job Cards created for operations.").format(wo.name))
    
    return {
        "work_order": wo.name,
        "status": wo.status
    }


@frappe.whitelist()
def create_subcontracting_order(work_order, operation, supplier, qty=None, rate=None):
    """
    Create Subcontracting Purchase Order and Subcontracting Order for a specific operation.
    
    This creates PO, submits it. ERPNext may auto-create SCO on PO submit (based on settings).
    If not auto-created, we create it manually.
    """
    require_production_write_access("create subcontracting orders")

    wo = frappe.get_doc("Work Order", work_order)
    
    if wo.docstatus != 1:
        frappe.throw(_("Work Order must be submitted to create Subcontracting Order"))
    
    # Find the job card for this operation
    job_card = frappe.db.get_value(
        "Job Card",
        {
            "work_order": work_order,
            "operation": operation,
            "docstatus": ["!=", 2]
        },
        ["name", "for_quantity", "total_completed_qty", "is_subcontracted", "finished_good", "semi_fg_bom", "sequence_id"],
        as_dict=True
    )
    
    if not job_card:
        frappe.throw(_("No Job Card found for operation {0}").format(operation))
    
    if not job_card.is_subcontracted:
        frappe.throw(_("Operation {0} is not marked as subcontracted").format(operation))
    
    # Check operation sequence - ensure all previous operations have AT LEAST SOME output
    # (Allow partial production flow)
    previous_ops = frappe.db.sql("""
        SELECT jc.name, jc.operation, jc.status, jc.total_completed_qty, jc.is_subcontracted
        FROM `tabJob Card` jc
        WHERE jc.work_order = %s
        AND jc.docstatus != 2
        AND jc.sequence_id < %s
        ORDER BY jc.sequence_id
    """, (work_order, job_card.get("sequence_id") or 999), as_dict=True)
    
    for prev_op in previous_ops:
        is_started = False
        
        if prev_op.is_subcontracted:
             # Check if any goods received for this subcontracted job card
             # (Purchase Order Item tracks received_qty against job_card)
             received_qty = frappe.db.sql("""
                SELECT SUM(poi.received_qty)
                FROM `tabPurchase Order Item` poi
                WHERE poi.job_card = %s
                AND poi.docstatus = 1
             """, prev_op.name)[0][0] or 0
             
             if flt(received_qty) > 0 or prev_op.status == 'Completed':
                 is_started = True
        else:
             # In-house: check completed qty
             if flt(prev_op.total_completed_qty) > 0 or prev_op.status == 'Completed':
                 is_started = True
        
        if not is_started:
            frappe.throw(_("Cannot start this operation. Previous operation '{0}' has no completed quantity.").format(prev_op.operation))
    
    # Calculate already ordered qty for this job card (allows multiple SCOs per operation)
    already_ordered_qty = frappe.db.sql("""
        SELECT COALESCE(SUM(poi.fg_item_qty), 0)
        FROM `tabPurchase Order Item` poi
        INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
        WHERE poi.job_card = %s
        AND po.docstatus != 2
    """, job_card.name)[0][0] or 0
    
    remaining_to_subcontract = flt(job_card.for_quantity) - flt(already_ordered_qty)
    
    if remaining_to_subcontract <= 0:
        frappe.throw(_("All quantity ({0}) has already been subcontracted for this operation. Existing POs cover the full Job Card quantity.").format(job_card.for_quantity))
    
    # Get subcontracting BOM details - use the finished_good from job card
    from erpnext.subcontracting.doctype.subcontracting_bom.subcontracting_bom import (
        get_subcontracting_boms_for_finished_goods
    )
    
    fg_item = job_card.finished_good or wo.production_item
    sc_bom = get_subcontracting_boms_for_finished_goods(fg_item)
    
    if not sc_bom:
        frappe.throw(_("No Subcontracting BOM found for item {0}").format(fg_item))
    
    # Use provided qty or remaining qty
    order_qty = remaining_to_subcontract
    if qty:
        order_qty = flt(qty)
    
    order_qty = flt(order_qty, 3)
    
    # Get company abbreviation for supplier warehouse
    company_abbr = frappe.get_cached_value("Company", wo.company, "abbr")
    supplier_warehouse = f"Job Work Outward - {company_abbr}"
    
    # Create supplier warehouse if it doesn't exist (shouldn't happen normally)
    if not frappe.db.exists("Warehouse", supplier_warehouse):
        # Try to find any subcontracting warehouse
        supplier_warehouse = frappe.db.get_value(
            "Warehouse", 
            {"company": wo.company, "warehouse_name": ("like", "%Job Work%")},
        "name"
    ) or wo.wip_warehouse
    
    # Create Purchase Order
    po = frappe.new_doc("Purchase Order")
    po.supplier = supplier
    po.company = wo.company
    po.is_subcontracted = 1
    po.schedule_date = nowdate()
    po.supplier_warehouse = supplier_warehouse
    
    service_item_qty = flt(sc_bom.service_item_qty) or 1.0
    fg_item_qty = flt(sc_bom.finished_good_qty) or 1.0
    
    po.append("items", {
        "item_code": sc_bom.service_item,
        "fg_item": fg_item,
        "uom": sc_bom.service_item_uom,
        "stock_uom": sc_bom.service_item_uom,
        "conversion_factor": sc_bom.conversion_factor or 1,
        "item_name": sc_bom.service_item,
        "qty": flt(order_qty * service_item_qty / fg_item_qty, 3),
        "fg_item_qty": order_qty,
        "job_card": job_card.name,
        "bom": job_card.semi_fg_bom or sc_bom.finished_good_bom,
        "rate": flt(rate) if rate else 0,
        "warehouse": wo.fg_warehouse
    })
    
    po.set_missing_values()
    
    # Force rate if provided, as set_missing_values might fetch from Price List
    if rate and flt(rate) > 0:
        for item in po.items:
            item.rate = flt(rate)
            item.price_list_rate = flt(rate)
            
    po.flags.ignore_mandatory = True
    po.insert()

    # Copy transaction parameters from linked Sales Order Item to PO item (per-item via JSON field)
    so_item_name = wo.sales_order_item
    if so_item_name and po.items:
        so_item_doc = frappe.get_doc("Sales Order Item", so_item_name)
        params_json = so_item_doc.custom_transaction_params_json or '[]'
        if params_json and params_json != '[]':
            po_doc = frappe.get_doc("Purchase Order", po.name)
            po_doc.items[0].custom_transaction_params_json = params_json
            po_doc.save(ignore_permissions=True)
            po = po_doc

    po.submit()
    
    # Check if SCO was auto-created by ERPNext (based on Buying Settings)
    # ERPNext's auto_create_subcontracting_order may have created one on PO submit
    sco_name = frappe.db.get_value(
        "Subcontracting Order",
        {"purchase_order": po.name, "docstatus": ["!=", 2]},
        "name"
    )
    
    if not sco_name:
        # SCO was not auto-created, create it manually
        from erpnext.buying.doctype.purchase_order.purchase_order import (
            make_subcontracting_order
        )
        
        sco = make_subcontracting_order(po.name)
        sco.flags.ignore_mandatory = True
        sco.insert()
        sco.submit()
        sco_name = sco.name
    else:
        # SCO was auto-created, just submit if it's draft
        sco_doc = frappe.get_doc("Subcontracting Order", sco_name)
        if sco_doc.docstatus == 0:
            sco_doc.submit()
    
    return {
        "purchase_order": po.name,
        "subcontracting_order": sco_name,
        "supplier_warehouse": supplier_warehouse
    }



def custom_get_operating_cost_per_unit(work_order=None, bom_no=None):
    from erpnext.stock.doctype.stock_entry.stock_entry import (
        get_consumed_operating_cost,
    )
    from erpnext.manufacturing.doctype.bom.bom import get_op_cost_from_sub_assemblies
    
    operating_cost_per_unit = 0
    if work_order:
        if (
            bom_no
            and frappe.db.get_single_value(
                "Manufacturing Settings", "set_op_cost_and_scrap_from_sub_assemblies"
            )
            and frappe.get_cached_value("Work Order", work_order.name, "use_multi_level_bom")
        ):
            return get_op_cost_from_sub_assemblies(bom_no)

        if not bom_no:
            bom_no = work_order.bom_no

        for d in work_order.get("operations"):
            if flt(d.completed_qty):
                # FIX: Check for division by zero (wip_qty)
                wip_qty = flt(d.completed_qty) - flt(work_order.produced_qty)
                if wip_qty > 0:
                    operating_cost_per_unit += flt(
                        d.actual_operating_cost - get_consumed_operating_cost(work_order.name, bom_no)
                    ) / wip_qty
            elif work_order.qty:
                operating_cost_per_unit += flt(d.planned_operating_cost) / flt(work_order.qty)

    # Get operating cost from BOM if not found in work_order.
    if not operating_cost_per_unit and bom_no:
        bom = frappe.db.get_value("BOM", bom_no, ["operating_cost", "quantity"], as_dict=1)
        if bom and bom.quantity:
            operating_cost_per_unit = flt(bom.operating_cost) / flt(bom.quantity)

    return operating_cost_per_unit

def custom_add_operations_cost(stock_entry, work_order=None, expense_account=None, job_card=None):
    from erpnext.stock.doctype.stock_entry.stock_entry import get_consumed_operating_cost
    from erpnext.manufacturing.doctype.bom.bom import add_operating_cost_component_wise

    operating_cost_per_unit = custom_get_operating_cost_per_unit(work_order, stock_entry.bom_no)

    if operating_cost_per_unit:
        cost_added = add_operating_cost_component_wise(
            stock_entry,
            work_order,
            get_consumed_operating_cost(work_order.name, stock_entry.bom_no),
            expense_account,
            job_card=job_card,
        )

        if not cost_added and not job_card:
            stock_entry.append(
                "additional_costs",
                {
                    "expense_account": expense_account,
                    "description": _("Operating Cost as per Work Order / BOM"),
                    "amount": operating_cost_per_unit * flt(stock_entry.fg_completed_qty),
                    "has_operating_cost": 1,
                },
            )

    if work_order and work_order.additional_operating_cost and work_order.qty:
        additional_operating_cost_per_unit = flt(work_order.additional_operating_cost) / flt(work_order.qty)

        if additional_operating_cost_per_unit:
            stock_entry.append(
                "additional_costs",
                {
                    "expense_account": expense_account,
                    "description": "Additional Operating Cost",
                    "amount": additional_operating_cost_per_unit * flt(stock_entry.fg_completed_qty),
                },
            )

def custom_add_additional_cost(stock_entry, work_order, job_card=None):
    from erpnext.manufacturing.doctype.bom.bom import add_non_stock_items_cost

    # Add non stock items cost in the additional cost
    stock_entry.additional_costs = []
    company_account = frappe.db.get_value(
        "Company",
        work_order.company,
        ["default_expense_account", "default_operating_cost_account"],
        as_dict=1,
    )

    expense_account = (
        company_account.default_operating_cost_account or company_account.default_expense_account
    )
    add_non_stock_items_cost(stock_entry, work_order, expense_account, job_card=job_card)
    custom_add_operations_cost(stock_entry, work_order, expense_account, job_card=job_card)


@frappe.whitelist()
def complete_operation(work_order, operation, qty, workstation=None, employee=None, attendance_date=None, shift=None):
    """
    Mark an in-house operation as complete by updating the Job Card.
    """
    require_production_write_access("complete operations")

    qty = flt(qty)
    
    # Find the job card
    job_card_name = frappe.db.get_value(
        "Job Card",
        {
            "work_order": work_order,
            "operation": operation,
            "docstatus": ["!=", 2]
        },
        "name"
    )
    
    if not job_card_name:
        frappe.throw(_("No Job Card found for operation {0}").format(operation))
    
    job_card = frappe.get_doc("Job Card", job_card_name)
    
    if job_card.is_subcontracted:
        frappe.throw(_("Operation {0} is subcontracted. Use receive_subcontracted_goods instead.").format(operation))
    
    # Update Job Card settings if provided
    if workstation:
        job_card.workstation = workstation
    
    # Add time log - this updates manufactured qty without submitting job card
    job_card.append("time_logs", {
        "from_time": frappe.utils.now_datetime(),
        "to_time": frappe.utils.now_datetime(),
        "completed_qty": qty,
        "employee": employee,
        "workstation": workstation
    })
    
    job_card.save()
    
    if "knitting" in operation.lower() and employee and attendance_date and shift:
        ma = frappe.new_doc("Machine Attendance")
        ma.employee = employee
        ma.date = attendance_date
        ma.shift = shift
        ma.machine = workstation or job_card.workstation
        ma.production_qty_kg = qty
        ma.company = job_card.company
        
        # Link machine attendance to the time log we just created for easy revert
        if job_card.time_logs:
            ma.job_card_time_log = job_card.time_logs[-1].name
            
        ma.flags.ignore_permissions = True
        ma.insert()

    # FIX: ERPNext auto-calculates process_loss_qty as (for_qty - completed_qty) on save.
    # For partial updates, this incorrectly marks the remainder as loss.
    # We must reset it to 0.
    if job_card.process_loss_qty > 0:
        job_card.db_set("process_loss_qty", 0)
        job_card.process_loss_qty = 0
    
    # ALWAYS synchronize the Work Order (Operation Qty) with the Job Card (Completed Qty)
    # This is critical before creating a Stock Entry, otherwise 'add_additional_cost'
    # fails with ZeroDivisionError (WO Produced Qty == WO Op Qty)
    job_card.update_work_order()
    
    # Create Stock Entry for the manufactured quantity (if applicable)
    # This ensures 'manufactured_qty' and RM 'consumed_qty' are updated on the Job Card
    stock_entry_name = None
    if job_card.finished_good:
        try:
            # Determine BOM to use
            bom_no = job_card.semi_fg_bom or frappe.db.get_value("Work Order", job_card.work_order, "bom_no")
            
            # Prepare arguments for ManufactureEntry
            # We use the specific quantity reported in this operation
            ste_args = {
                "for_quantity": qty, 
                "job_card": job_card.name,
                "skip_material_transfer": job_card.skip_material_transfer,
                "backflush_from_wip_warehouse": job_card.backflush_from_wip_warehouse,
                "work_order": job_card.work_order,
                "purpose": "Manufacture",
                "production_item": job_card.finished_good,
                "company": job_card.company,
                "wip_warehouse": job_card.wip_warehouse,
                "fg_warehouse": job_card.target_warehouse or job_card.wip_warehouse, # Fallback if not set (though validation might fail)
                "bom_no": bom_no,
                "project": job_card.project or frappe.db.get_value("Work Order", job_card.work_order, "project"),
            }
            
            # Handle missing target warehouse by fetching from WO if needed
            if not ste_args["fg_warehouse"]:
                ste_args["fg_warehouse"] = frappe.db.get_value("Work Order", job_card.work_order, "fg_warehouse")
            
            ste = ManufactureEntry(ste_args)
            ste.make_stock_entry()
            
            # FIX: Scale Raw Material consumption pro-rata based on produced quantity
            # By default, ManufactureEntry might consume full remaining qty (if based on transfer)
            # We want strict pro-rata consumption: (Req Qty / Total JC Qty) * Manufactured Qty
            if flt(job_card.for_quantity) > 0:
                ratio = flt(qty) / flt(job_card.for_quantity)
                for row in ste.stock_entry.items:
                    if not row.is_finished_item and row.job_card_item:
                        jc_required = frappe.db.get_value("Job Card Item", row.job_card_item, "required_qty")
                        row.qty = flt(flt(jc_required) * ratio, 3)
                        
                        # Fix: Auto-adjust consumption if close to available stock (avoid negative stock error)
                        if row.s_warehouse:
                            bin_qty = flt(frappe.db.get_value("Bin", 
                                {"item_code": row.item_code, "warehouse": row.s_warehouse}, 
                                "actual_qty"))
                            
                            # If we are trying to consume slightly more than available (within 0.005 tolerance)
                            if row.qty > bin_qty and (row.qty - bin_qty) < 0.005:
                                row.qty = bin_qty
            
            # Configure Stock Entry
            ste.stock_entry.flags.ignore_mandatory = True
            
            # FIX: Prevent ERPNext from overwriting fg_completed_qty with Job Card for_quantity
            # ManufactureEntry does not pass work_order to stock_entry, which triggers set_job_card_data
            ste.stock_entry.work_order = job_card.work_order
            
            # Add additional costs (operating costs)
            wo_doc = frappe.get_doc("Work Order", job_card.work_order)
            
            # Sync SCIO SREs to WO before consuming stock (service layer — P1.2)
            from kniterp.api.stock_reservation_service import (
                sync_scio_sre_before_manufacture,
                ensure_scio_fg_sre,
                recalculate_bin_reserved_for_direct_consumption,
            )
            sync_scio_sre_before_manufacture(wo_doc)
            
            # FIX: Ensure Work Order Operation 'completed_qty' is updated in memory
            # Standard update_work_order might not reflect Draft Job Card quantities in DB immediately/correctly
            # causing ZeroDivisionError in add_additional_cost
            if job_card.operation_id:
                for op in wo_doc.operations:
                    if op.name == job_card.operation_id:
                        # If the OP qty hasn't advanced beyond Produced Qty, manual bump it
                        # We use max() to ensure we count the current qty at minimum
                        current_wip = flt(op.completed_qty) - flt(wo_doc.produced_qty)
                        if current_wip <= 0:
                             op.completed_qty = flt(wo_doc.produced_qty) + flt(qty)
                        break
            
            # Use custom safer method instead of standard add_additional_cost
            custom_add_additional_cost(ste.stock_entry, wo_doc, job_card)
            
            # Handle scrap items
            ste.stock_entry.set_scrap_items()
            for row in ste.stock_entry.items:
                if row.is_scrap_item and not row.t_warehouse:
                    row.t_warehouse = ste_args["fg_warehouse"]
            
            # Submit the Stock Entry
            ste.stock_entry.submit()
            stock_entry_name = ste.stock_entry.name
            
            # Create FG SRE for SCIO WOs (service layer — P1.2)
            ensure_scio_fg_sre(wo_doc, ste.stock_entry)
            
            # Recalculate Bin reserved_qty_for_production for direct consumption (service layer — P1.2)
            wo_doc.reload()
            recalculate_bin_reserved_for_direct_consumption(wo_doc, ste.stock_entry, mode="complete")
            
            frappe.msgprint(_("Stock Entry {0} created for {1} {2}").format(
                frappe.utils.get_link_to_form("Stock Entry", stock_entry_name), 
                qty, 
                job_card.finished_good
            ))
            
            
        except Exception as e:
            # If Stock Entry fails (e.g. negative stock), we MUST rollback the time log 
            # so the user can fix the stock issue first.
            frappe.log_error(f"Failed to create Stock Entry for Job Card {job_card.name}: {str(e)}")
            
            # Clear previous messages to avoid duplicate error display in UI
            frappe.clear_messages()
            
            # Check for common stock errors to give better message
            if "Negative Stock Error" in str(e) or "Insufficient stock" in str(e):
                 frappe.throw(_("Cannot update manufactured quantity: Raw Material stock is not available.<br><br>{0}").format(str(e)))
            else:
                 frappe.throw(_("Failed to create Stock Entry: {0}").format(str(e)))


    # Defensive re-sync: ensure total_completed_qty matches the actual sum of time logs.
    # Stock Entry submission hooks may load separate Job Card instances whose writes
    # can leave total_completed_qty stale in the original instance.
    actual_total = flt(frappe.db.sql("""
        SELECT COALESCE(SUM(completed_qty), 0)
        FROM `tabJob Card Time Log`
        WHERE parent = %s
    """, job_card.name)[0][0])
    
    if flt(job_card.total_completed_qty) != actual_total:
        job_card.db_set("total_completed_qty", flt(actual_total, job_card.precision("total_completed_qty")))
        job_card.total_completed_qty = actual_total

    return {
        "job_card": job_card.name,
        "status": job_card.status,
        "total_completed_qty": job_card.total_completed_qty,
        "stock_entry": stock_entry_name
    }


@frappe.whitelist()
def complete_job_card(job_card, additional_qty=0, process_loss_qty=0, 
                      wip_warehouse=None, skip_material_transfer=None, source_warehouses=None):
    require_production_write_access("complete job cards")
    return _complete_job_card_inhouse(
        job_card=job_card,
        additional_qty=additional_qty,
        process_loss_qty=process_loss_qty,
        wip_warehouse=wip_warehouse,
        skip_material_transfer=skip_material_transfer,
        source_warehouses=source_warehouses,
    )


def _complete_job_card_inhouse(job_card, additional_qty=0, process_loss_qty=0, 
                               wip_warehouse=None, skip_material_transfer=None, source_warehouses=None):
    """
    Complete a Job Card - validate, submit it and create stock entry.
    
    Args:
        job_card: Job Card name
        additional_qty: Any additional qty to add before completing
        process_loss_qty: Process loss quantity
        wip_warehouse: WIP Warehouse (if provided, will update Job Card)
        skip_material_transfer: Skip Material Transfer flag (if provided, will update Job Card)
        source_warehouses: Dict of {item_code: source_warehouse} for raw materials
    """
    jc = frappe.get_doc("Job Card", job_card)
    
    if jc.docstatus == 1:
        frappe.throw(_("Job Card {0} is already submitted").format(job_card))
    
    if jc.docstatus == 2:
        frappe.throw(_("Job Card {0} is cancelled").format(job_card))
    
    # Apply user-provided values BEFORE validation
    if skip_material_transfer is not None:
        jc.skip_material_transfer = cint(skip_material_transfer)
    
    if wip_warehouse:
        jc.wip_warehouse = wip_warehouse
    
    # Parse source_warehouses if provided as JSON string
    if source_warehouses:
        if isinstance(source_warehouses, str):
            import json
            source_warehouses = json.loads(source_warehouses)
        
        for item in jc.items:
            if item.item_code in source_warehouses:
                item.source_warehouse = source_warehouses[item.item_code]
    
    # Save the changes
    jc.save()
    
    additional_qty = flt(additional_qty)
    process_loss_qty = flt(process_loss_qty)
    
    # Add additional qty if specified
    if additional_qty > 0:
        jc.append("time_logs", {
            "from_time": frappe.utils.now_datetime(),
            "to_time": frappe.utils.now_datetime(),
            "completed_qty": additional_qty
        })
        jc.save()
    
    # Set process loss qty
    if process_loss_qty > 0:
        jc.process_loss_qty = process_loss_qty
        jc.save()
    
    # Validate required fields BEFORE submitting
    # Check Work Order settings for material transfer
    work_order = frappe.get_doc("Work Order", jc.work_order)
    
    # skip_wip_transfer means: consume raw materials directly from source_wh (no WIP transfer needed)
    # Check BOTH Work Order's skip_transfer AND Job Card's skip_material_transfer
    skip_wip_transfer = work_order.skip_transfer or jc.skip_material_transfer or False
    
    # Source warehouse is ALWAYS required for raw material items
    # Also check stock availability to prevent negative inventory
    if jc.items:
        for item in jc.items:
            if not item.source_warehouse:
                frappe.throw(_("Row {0}: Source Warehouse is required for item {1}. Please update the Job Card.").format(
                    item.idx, item.item_code
                ))
            
    jc.submit()
    
    # Force update Work Order status as standard ERPNext might not trigger it on simple submit
    # if there are no pending operations
    wo = frappe.get_doc("Work Order", jc.work_order)
    wo.update_status()

    # Audit trail (P1.4)
    log_manual_production_action(
        action="complete_job_card_inhouse",
        jc=jc.name,
        wo=jc.work_order,
        qty_before=flt(jc.total_completed_qty) - flt(additional_qty),
        qty_after=flt(jc.total_completed_qty),
        status_before="Draft",
        status_after="Submitted",
        mode="inhouse",
        outcome="success",
        message=f"Job Card manually completed. process_loss_qty={process_loss_qty}",
    )

    return {
        "success": True,
        "job_card": jc.name,
        "message": _("Job Card {0} completed successfully").format(jc.name),
        "mode": "inhouse",
        "received_qty": None,
    }

@frappe.whitelist()
def get_production_logs(job_card):
    """
    Get production logs (Stock Entries) for a job card.
    Enriched with Employee and Machine data from Job Card Time Logs.
    """
    job_card_doc = frappe.get_doc("Job Card", job_card)
    
    logs = frappe.get_all(
        "Stock Entry",
        filters={"job_card": job_card, "purpose": "Manufacture", "docstatus": 1},
        fields=["name", "posting_date", "posting_time", "fg_completed_qty", "creation"],
        order_by="creation desc"
    )
    
    # Enrich logs with Employee and Machine info
    # We try to match Stock Entry to Time Log based on creation time proximity and quantity
    # Note: This is a "best effort" match since there's no hard ID link
    
    # Create a copy of time logs to consume during matching
    time_logs = [tl for tl in job_card_doc.time_logs]
    
    for log in logs:
        log["workstation"] = job_card_doc.workstation # Default to current JC workstation
        log["employee"] = ""
        log["employee_name"] = ""
        
        # Find matching time log
        match_index = -1
        for i, tl in enumerate(time_logs):
             if flt(tl.completed_qty) == flt(log.fg_completed_qty):
                 match_index = i
                 break 
        
        if match_index != -1:
            tl = time_logs.pop(match_index)
            log["employee"] = tl.employee
            if tl.employee:
                log["employee_name"] = frappe.get_cached_value("Employee", tl.employee, "employee_name")
            
            # Check if custom workstation field exists on time log
            if hasattr(tl, "workstation") and tl.workstation:
                log["workstation"] = tl.workstation 
            # (TimeLog doctype usually doesn't have workstation)

    return logs

@frappe.whitelist()
def revert_production_entry(stock_entry):
    """
    Revert a production entry:
    1. Cancel the Stock Entry.
    2. Remove the corresponding Time Log from Job Card.
    """
    require_production_write_access("revert production entries")

    try:
        se = frappe.get_doc("Stock Entry", stock_entry)
        if se.docstatus != 1:
            frappe.throw(_("Stock Entry {0} is not submitted").format(stock_entry))
            
        job_card_name = se.job_card
        qty = se.fg_completed_qty
        
        # Release SCIO FG SREs before cancelling SE (service layer — P1.2)
        wo_doc = None
        if se.work_order:
            wo_doc = frappe.get_doc("Work Order", se.work_order)
            from kniterp.api.stock_reservation_service import (
                release_scio_fg_sres_on_revert,
                recalculate_bin_reserved_for_direct_consumption,
            )
            release_scio_fg_sres_on_revert(wo_doc, se)
        
        # 1. Cancel Stock Entry
        se.cancel()
        
        # Recalculate Bin reserved_qty_for_production after cancel (service layer — P1.2)
        if wo_doc:
            recalculate_bin_reserved_for_direct_consumption(wo_doc, se, mode="revert")
        
        # 2. Update Job Card
        if job_card_name:
            jc = frappe.get_doc("Job Card", job_card_name)
            
            # Find a matching time log to remove
            # We look for the latest log with the same completed_qty
            log_to_remove = None
            for i, log in enumerate(reversed(jc.time_logs)):
                if flt(log.completed_qty) == flt(qty):
                    # Found a match (checking from end means we get the latest)
                    log_to_remove = len(jc.time_logs) - 1 - i
                    break
            
            if log_to_remove is not None:
                # Cancel linked Machine Attendance if it exists
                log_row = jc.time_logs[log_to_remove]
                ma_name = frappe.db.get_value("Machine Attendance", {"job_card_time_log": log_row.name}, "name")
                if ma_name:
                    ma = frappe.get_doc("Machine Attendance", ma_name)
                    ma.flags.ignore_permissions = True
                    # Just delete it to keep it truly reverted
                    ma.delete()

                # Remove the time log row via direct DB delete (can't use jc.save()
                # on submitted JC — it triggers validate_job_card which throws 
                # when total_completed_qty != for_quantity after removing a log)
                frappe.delete_doc("Job Card Time Log", log_row.name, ignore_permissions=True)
                del jc.time_logs[log_to_remove]
                
                # Recalculate total_completed_qty and total_time_in_mins from remaining time logs
                new_total_completed = sum(flt(tl.completed_qty) for tl in jc.time_logs)
                new_total_time = sum(flt(tl.time_in_mins) for tl in jc.time_logs)
                jc.db_set({
                    "total_completed_qty": flt(new_total_completed, jc.precision("total_completed_qty")),
                    "total_time_in_mins": flt(new_total_time),
                })
                
                # Recalculate manufactured_qty from submitted stock entries and update status
                jc.set_manufactured_qty()
                jc.update_work_order()
                
                # Audit trail (P1.4)
                log_manual_production_action(
                    action="revert_production_entry",
                    jc=job_card_name,
                    se=stock_entry,
                    wo=se.work_order,
                    qty_before=flt(qty),
                    qty_after=flt(new_total_completed),
                    status_before="Submitted",
                    status_after="Cancelled",
                    mode="inhouse",
                    outcome="success",
                    message=f"Stock Entry cancelled and Time Log removed.",
                )

                frappe.msgprint(_("Reverted production entry. Stock Entry {0} cancelled and Time Log removed.").format(stock_entry))
            else:
                 frappe.msgprint(_("Stock Entry {0} cancelled. However, could not find an exact matching Time Log of {1} units to remove. Please update Job Card manually if needed.").format(stock_entry, qty))
                 
    except Exception as e:
        frappe.log_error(f"Failed to revert production entry {stock_entry}: {str(e)}")
        frappe.throw(_("Failed to revert entry: {0}").format(str(e)))

@frappe.whitelist()
def update_production_entry(stock_entry, qty, employee, workstation):
    """
    Update a production entry (Revert + New Entry).
    """
    require_production_write_access("update production entries")

    try:
        # 1. Get details before reverting
        se = frappe.get_doc("Stock Entry", stock_entry)
        job_card_name = se.job_card
        work_order_name = se.work_order
        
        if not job_card_name:
             frappe.throw(_("Cannot update Stock Entry {0} as it is not linked to a Job Card").format(stock_entry))

        jc = frappe.get_doc("Job Card", job_card_name)
        operation = jc.operation
        
        # 2. Revert the existing entry
        revert_production_entry(stock_entry)
        
        # 3. Create new entry with updated values
        # We reuse complete_operation logic which handles everything (Stock Entry + Time Log)
        complete_operation(
            work_order=work_order_name,
            operation=operation,
            qty=qty,
            workstation=workstation,
            employee=employee
        )

        # Audit trail (P1.4)
        log_manual_production_action(
            action="update_production_entry",
            jc=job_card_name,
            se=stock_entry,
            wo=work_order_name,
            qty_before=flt(se.fg_completed_qty),
            qty_after=flt(qty),
            status_before="Submitted",
            status_after="Cancelled+Recreated",
            mode="inhouse",
            outcome="success",
            message=f"Stock Entry replaced. New qty={qty}, workstation={workstation}, employee={employee}.",
        )

        frappe.msgprint(_("Production entry updated successfully."))
        
    except Exception as e:
        frappe.log_error(f"Failed to update production entry {stock_entry}: {str(e)}")
        frappe.throw(_("Failed to update entry: {0}").format(str(e)))


    



@frappe.whitelist()
def receive_subcontracted_goods(purchase_order, qty=None, rate=None, supplier_delivery_note=None, items=None, subcontracting_order=None):
    """
    Create Subcontracting Receipt to receive goods from subcontractor.
    Auto-updates Job Card and Work Order status.
    """
    require_production_write_access("receive subcontracted goods")

    po = frappe.get_doc("Purchase Order", purchase_order)
    
    if po.docstatus != 1:
        frappe.throw(_("Purchase Order must be submitted"))
    
    if not po.is_subcontracted:
        frappe.throw(_("Purchase Order is not a subcontracting order"))
    
    # Create Subcontracting Order first if not exists
    sco = None
    if subcontracting_order:
        sco = subcontracting_order
    else:
        sco = frappe.db.get_value(
            "Subcontracting Order",
            {"purchase_order": purchase_order, "docstatus": 1},
            "name"
        )
    
    if not sco:
        # Create SCO from PO - import from purchase_order module
        from erpnext.buying.doctype.purchase_order.purchase_order import (
            make_subcontracting_order
        )
        sco_doc = make_subcontracting_order(purchase_order)
        sco_doc.insert()
        sco_doc.submit()
        sco = sco_doc.name
    
    # Create Subcontracting Receipt
    from erpnext.subcontracting.doctype.subcontracting_order.subcontracting_order import (
        make_subcontracting_receipt
    )
    
    scr = make_subcontracting_receipt(sco)
    
    # Update Receipt Details if provided
    if supplier_delivery_note:
        scr.supplier_delivery_note = supplier_delivery_note
        
    for item in scr.items:
        if qty and flt(qty) > 0:
            item.qty = flt(qty, 3)
            # Re-calculate amount ? (Standard save might handle it, but setting rate explicitly helps)
        if rate and flt(rate) > 0:
            item.rate = flt(rate, 2)
            
    scr.insert()
    scr.submit()
    
    # Check for linked Purchase Receipt (Draft) and submit it
    # Sometimes a Purchase Receipt is created for Service Items or other logic
    linked_pr = frappe.db.get_value("Purchase Receipt", {"purchase_order": purchase_order, "docstatus": 0}, "name")
    if linked_pr:
        pr_doc = frappe.get_doc("Purchase Receipt", linked_pr)
        pr_doc.submit()
        frappe.msgprint(_("Linked Purchase Receipt {0} submitted").format(pr_doc.name))
    
    frappe.msgprint(_("Subcontracting Receipt {0} created and submitted").format(scr.name))
    
    return scr.name


@frappe.whitelist()
def create_purchase_orders_for_shortage(items, supplier, schedule_date=None, warehouse=None, submit=True):
    """
    Create Purchase Order for multiple shortage items.
    
    Args:
        items: JSON array of {item_code, qty, rate, warehouse}
        supplier: Supplier name
        schedule_date: Required by date (optional, default: today + 7 days)
        warehouse: Target warehouse (optional, uses item's warehouse if not provided)
        submit: If True, submit the PO (default: True)
    """
    require_production_write_access("create purchase orders for shortages")

    if isinstance(items, str):
        items = json.loads(items)
    
    if not items:
        frappe.throw(_("No items provided"))
    
    if not supplier:
        frappe.throw(_("Supplier is required"))
    
    # Get company from first item's warehouse or provided warehouse
    target_wh = warehouse or items[0].get("warehouse")
    company = frappe.db.get_value("Warehouse", target_wh, "company")
    
    # Use provided date or default to 7 days from now
    req_date = schedule_date or add_days(nowdate(), 7)
    
    po = frappe.new_doc("Purchase Order")
    po.supplier = supplier
    po.company = company
    po.schedule_date = req_date
    
    for item in items:
        item_doc = frappe.get_cached_doc("Item", item.get("item_code"))
        item_warehouse = warehouse or item.get("warehouse")
        
        row_data = {
            "item_code": item.get("item_code"),
            "item_name": item_doc.item_name,
            "qty": flt(item.get("qty")),
            "uom": item_doc.stock_uom,
            "stock_uom": item_doc.stock_uom,
            "warehouse": item_warehouse,
            "schedule_date": req_date
        }

        # Link to Sales Order if provided
        if item.get("sales_order"):
            row_data["sales_order"] = item.get("sales_order")
        
        # Link to Sales Order Item if provided
        if item.get("sales_order_item"):
            row_data["sales_order_item"] = item.get("sales_order_item")
        
        # Set rate if provided
        if item.get("rate"):
            row_data["rate"] = flt(item.get("rate"))
        
        po.append("items", row_data)
    
    po.set_missing_values()
    po.insert()
    
    # Submit the PO if requested
    if cint(submit):
        po.submit()
    
    status_text = "submitted" if cint(submit) else "created as draft"
    frappe.msgprint(_(
        "Purchase Order <a href='/app/purchase-order/{0}'>{0}</a> {1} for {2} items"
    ).format(po.name, status_text, len(items)))
    
    return {
        "name": po.name,
        "status": po.status,
        "docstatus": po.docstatus,
        "supplier": po.supplier,
        "total": po.grand_total,
        "items_count": len(items)
    }


@frappe.whitelist()
def transfer_materials_to_subcontractor(subcontracting_order):
    """
    Create Stock Entry to transfer materials to subcontractor warehouse.
    """
    require_production_write_access("transfer materials to subcontractor")

    sco = frappe.get_doc("Subcontracting Order", subcontracting_order)
    
    if sco.docstatus != 1:
        frappe.throw(_("Subcontracting Order must be submitted"))
    
    # Create Stock Entry for material transfer
    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = "Send to Subcontractor"
    se.company = sco.company
    se.subcontracting_order = sco.name
    
    for item in sco.supplied_items:
        if flt(item.supplied_qty) >= flt(item.required_qty):
            continue  # Already supplied
        
        pending = flt(item.required_qty) - flt(item.supplied_qty)
        
        se.append("items", {
            "item_code": item.rm_item_code,
            "qty": pending,
            "s_warehouse": item.reserve_warehouse,
            "t_warehouse": sco.supplier_warehouse,
            "subcontracting_order": sco.name
        })
    
    if not se.items:
        frappe.throw(_("All materials already transferred"))
    
    se.set_stock_entry_type()
    se.insert()
    
    frappe.msgprint(_("Stock Entry {0} created for material transfer").format(se.name))
    
    return se.name


@frappe.whitelist()
def get_supplier_list():
    """
    Get list of active suppliers for dropdown.
    """
    suppliers = frappe.get_all(
        "Supplier",
        filters={"disabled": 0},
        fields=["name", "supplier_name", "supplier_group"],
        order_by="supplier_name"
    )
    
    return suppliers


@frappe.whitelist()
def get_status_summary():
    """
    Get dashboard summary of all pending production.
    """
    # Pending items (no work order)
    pending_items = frappe.db.sql("""
        SELECT COUNT(*) 
        FROM `tabSales Order Item` soi
        INNER JOIN `tabSales Order` so ON so.name = soi.parent
        WHERE so.docstatus = 1 
        AND so.status NOT IN ('Closed', 'Completed')
        AND (soi.qty > soi.delivered_qty OR soi.billed_amt < soi.amount)
    """)[0][0]
    
    # Work orders by status
    wo_status = frappe.db.sql("""
        SELECT status, COUNT(*) as count
        FROM `tabWork Order`
        WHERE docstatus = 1 AND status NOT IN ('Completed', 'Stopped', 'Closed')
        GROUP BY status
    """, as_dict=True)
    
    # Subcontracting orders pending receipt
    pending_receipts = frappe.db.count("Subcontracting Order", {
        "docstatus": 1,
        "status": ["in", ["Pending", "Partial"]]
    })
    
    # Material shortages
    # This is a simplified check - in production you'd want a more sophisticated query
    
    return {
        "pending_items": pending_items,
        "work_order_status": {s.status: s.count for s in wo_status},
        "pending_receipts": pending_receipts
    }


@frappe.whitelist()
def create_delivery_note(sales_order, items=None):
    """
    Create Delivery Note for completed items.
    Uses actual produced/received qty instead of Sales Order pending qty.
    Checks for existing draft DN before creating new one.
    """
    require_production_write_access("create delivery notes")

    # 1. Check for existing draft Delivery Note for this Sales Order
    existing_draft = frappe.db.get_value(
        "Delivery Note Item",
        {"against_sales_order": sales_order, "docstatus": 0},
        "parent"
    )
    
    if existing_draft:
        frappe.msgprint(_("Opening existing Draft Delivery Note {0}").format(existing_draft))
        return existing_draft
    
    from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
    
    dn = make_delivery_note(sales_order)
    
    # Track items to keep (those with ready qty > 0)
    items_to_keep = []
    
    # Update quantities based on actual production/subcontracting
    for item in dn.items:
        if not item.so_detail:
            items_to_keep.append(item)
            continue
        
        # Get SO Item details
        soi = frappe.db.get_value(
            "Sales Order Item", item.so_detail,
            ["delivered_qty", "qty"], as_dict=True
        )
        delivered_qty = flt(soi.delivered_qty) if soi else 0
        remaining_so_qty = flt(soi.qty) - delivered_qty if soi else 0
        
        if remaining_so_qty <= 0:
            continue  # Already fully delivered
        
        # Calculate ready qty from production sources
        ready_qty = 0
        
        # Check Work Order produced qty
        wo_produced = frappe.db.get_value(
            "Work Order",
            {"sales_order": sales_order, "sales_order_item": item.so_detail, "docstatus": 1},
            "produced_qty"
        ) or 0
        
        # Check Subcontracting Receipts received qty
        # Path: SCR -> SRI -> SCO (via subcontracting_order) -> PO (via purchase_order) -> POI
        sc_received = frappe.db.sql("""
            SELECT COALESCE(SUM(sri.received_qty), 0)
            FROM `tabSubcontracting Receipt Item` sri
            INNER JOIN `tabSubcontracting Receipt` scr ON scr.name = sri.parent
            INNER JOIN `tabSubcontracting Order` sco ON sco.name = sri.subcontracting_order
            INNER JOIN `tabPurchase Order` po ON po.name = sco.purchase_order
            INNER JOIN `tabPurchase Order Item` poi ON poi.parent = po.name
            WHERE poi.sales_order = %s
            AND poi.sales_order_item = %s
            AND scr.docstatus = 1
        """, (sales_order, item.so_detail))[0][0] or 0
        
        # Use the maximum of produced or received (usually one or the other applies)
        ready_qty = max(flt(wo_produced), flt(sc_received))
        available_to_deliver = flt(ready_qty) - delivered_qty
        
        if available_to_deliver > 0:
            # Allow over-delivery if produced quantity is greater than remaining SO quantity
            # We use the actual available to deliver (Produced - Delivered) even if it exceeds Planned SO Qty
            item.qty = available_to_deliver
            items_to_keep.append(item)
            
            if flt(wo_produced) > 0:
                frappe.msgprint(
                    _("Item {0}: Delivery qty set to {1} based on production").format(
                        item.item_code, item.qty
                    ),
                    alert=True
                )
            elif flt(sc_received) > 0:
                frappe.msgprint(
                    _("Item {0}: Delivery qty set to {1} based on subcontracting receipt").format(
                        item.item_code, item.qty
                    ),
                    alert=True
                )
    
    dn.items = items_to_keep
    
    if not dn.items:
        frappe.throw(_("No items ready for delivery. Produce or receive goods first."))

    dn.insert()
    
    frappe.msgprint(_("Delivery Note {0} created").format(dn.name))
    
    return dn.name


@frappe.whitelist()
def get_consolidated_shortages(filters=None):
    """
    Get aggregated raw material shortages for multiple Sales Orders based on filters.
    Returns a dictionary grouped by Item Code with breakdown by Sales Order.
    """
    if isinstance(filters, str):
        filters = json.loads(filters)
    filters = filters or {}
    
    # Reuse get_pending_production_items logic to find relevant SO items
    # We can pass the filters directly as they share structure (customer, from_date, to_date)
    # We might need to add 'item_group' support to get_pending_production_items or filter here
    
    pending_items = get_pending_production_items(filters)
    
    consolidated_shortages = {}
    
    for item in pending_items:
        # Get details for this item (BOM, raw materials)
        # This calls get_production_details which does the heavy lifting of BOM traversal and Stock checks
        try:
            details = get_production_details(item.sales_order_item)
            
            for rm in details.get("raw_materials", []):
                # We only care about shortages
                if rm.get("shortage", 0) > 0:
                    item_code = rm["item_code"]
                    
                    if item_code not in consolidated_shortages:
                        consolidated_shortages[item_code] = {
                            "item_code": item_code,
                            "item_name": rm["item_name"],
                            "description": rm.get("description"),
                            "uom": rm["uom"],
                            "total_required": 0.0,
                            "total_shortage": 0.0,
                            "breakdown": []
                        }
                    
                    # Add to consolidated record
                    shortage_qty = flt(rm["shortage"])
                    consolidated_shortages[item_code]["total_required"] += flt(rm["required_qty"])
                    consolidated_shortages[item_code]["total_shortage"] += shortage_qty
                    
                    consolidated_shortages[item_code]["breakdown"].append({
                        "sales_order": item.sales_order,
                        "sales_order_item": item.sales_order_item,
                        "required_qty": flt(rm["required_qty"]),
                        "shortage": shortage_qty,
                        "warehouse": rm.get("warehouse")
                    })
                    
        except Exception as e:
            frappe.log_error(f"Error calculating shortage for {item.sales_order_item}: {str(e)}")
            continue

    # Filter by Item Group if specified
    if filters.get("item_group"):
        item_group = filters.get("item_group")
        filtered_shortages = {}
        for code, data in consolidated_shortages.items():
            db_group = frappe.get_cached_value("Item", code, "item_group")
            if db_group == item_group:
                filtered_shortages[code] = data
        return filtered_shortages

    return consolidated_shortages


@frappe.whitelist()
def create_sales_invoice(sales_order):
    """
    Create Sales Invoice for a Sales Order.
    Prioritizes billing against Delivery Notes to support over-delivery and split deliveries.
    """
    require_production_write_access("create sales invoices")

    # Check for existing draft Sales Invoice for this Sales Order
    existing_draft = frappe.db.get_value(
        "Sales Invoice Item",
        {"sales_order": sales_order, "docstatus": 0},
        "parent"
    )
    
    if existing_draft:
        frappe.msgprint(_("Opening existing Draft Sales Invoice {0}").format(existing_draft))
        return existing_draft

    from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
    
    si = make_sales_invoice(sales_order)
    
    # We will rebuild items to ensure proper DN linking
    final_items = []
    
    # Fetch all Submitted Delivery Notes linked to this SO
    # Grouped by SO Detail to easily match with SI items
    dn_items = frappe.db.sql("""
        SELECT 
            dni.name as dn_detail, dni.parent as delivery_note, dni.item_code, dni.item_name, 
            dni.qty, dni.stock_uom, dni.uom, dni.conversion_factor, dni.rate, dni.amount,
            dni.so_detail, dni.description
        FROM `tabDelivery Note Item` dni
        INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
        WHERE dni.against_sales_order = %s AND dn.docstatus = 1
        ORDER BY dn.creation ASC
    """, sales_order, as_dict=True)
    
    dn_map = {} # so_detail -> list of dn_items
    for dni in dn_items:
        if dni.so_detail:
            if dni.so_detail not in dn_map:
                dn_map[dni.so_detail] = []
            dn_map[dni.so_detail].append(dni)

    for item in si.items:
        if item.so_detail and item.so_detail in dn_map:
            # This item has Delivery Notes.
            # Create invoice lines based on UNBILLED DN items instead of the aggregate SO item
            
            linked_dns = dn_map[item.so_detail]
            item_fully_billed = True
            
            for dni in linked_dns:
                 # Check billed qty for this specific DN Detail
                billed_qty = frappe.db.sql("""
                    SELECT SUM(qty)
                    FROM `tabSales Invoice Item`
                    WHERE dn_detail = %s
                    AND docstatus = 1
                """, dni.dn_detail)[0][0] or 0.0
                
                pending_qty = flt(dni.qty) - flt(billed_qty)
                
                if pending_qty > 0:
                    item_fully_billed = False
                    
                    # Create new item row based on DN Item
                    # We copy properties from the generated 'item' (from make_sales_invoice) to preserve defaults
                    # but override with DN specific values
                    new_item = frappe.copy_doc(item)
                    new_item.qty = pending_qty
                    new_item.dn_detail = dni.dn_detail
                    new_item.delivery_note = dni.delivery_note
                    new_item.rate = dni.rate # Trust DN rate? Or maintain SO rate? Usually DN rate comes from SO.
                    new_item.amount = flt(pending_qty) * flt(new_item.rate)
                    
                    # Update description if needed?
                    
                    final_items.append(new_item)
            
            if item_fully_billed:
                # If all DNs are billed, we don't add anything for this SO item
                # (unless there's non-stock billing needed, but we assume stock items Bill by Delivery)
                pass

        else:
            # No DNs found (Service item, or no delivery yet)
            # Use original logic: Check Delivered Qty vs Billed Qty (aggregate)
            if item.so_detail:
                so_item = frappe.db.get_value(
                    "Sales Order Item",
                    item.so_detail,
                    ["delivered_qty", "qty"],
                    as_dict=True
                )
                
                if so_item:
                    billed_qty = frappe.db.sql("""
                        SELECT SUM(qty)
                        FROM `tabSales Invoice Item`
                        WHERE so_detail = %s
                        AND docstatus = 1
                    """, item.so_detail)[0][0] or 0.0
                    
                    pending_delivery_billing = flt(so_item.delivered_qty) - flt(billed_qty)
                    
                    if pending_delivery_billing > 0:
                        item.qty = pending_delivery_billing
                        final_items.append(item)
            else:
                 # No SO Detail (Ad-hoc item?) - keep it
                 final_items.append(item)
            
    si.items = final_items
    
    # Remove items with 0 qty just in case
    si.items = [d for d in si.items if d.qty > 0]
    
    if not si.items:
        frappe.throw(_("No items to invoice (Deliveries are fully billed or nothing delivered)"))

    si.set_missing_values()
    si.insert()
    
    frappe.msgprint(_("Sales Invoice {0} created").format(si.name))
    
    return si.name


@frappe.whitelist()
def create_scio_sales_invoice(sales_order_item):
    """
    Create a partial Sales Invoice for a subcontracted (SCIO) Sales Order item.
    
    Invoiceable qty is calculated based on the service-to-FG ratio:
    - SIO delivered_qty tracks how much FG has been delivered
    - Service qty = FG delivered * (service_qty / fg_item_qty)
    - Already billed qty is subtracted to get the invoiceable amount
    """
    require_production_write_access("create SCIO sales invoices")

    # Get SOI details
    soi = frappe.db.get_value(
        "Sales Order Item",
        sales_order_item,
        ["name", "parent", "item_code", "item_name", "qty", "rate", "amount",
         "fg_item", "fg_item_qty", "billed_amt", "uom", "stock_uom",
         "delivery_date", "warehouse", "description", "conversion_factor"],
        as_dict=True
    )
    
    if not soi:
        frappe.throw(_("Sales Order Item not found"))
    
    so = frappe.get_doc("Sales Order", soi.parent)
    
    if not so.is_subcontracted:
        frappe.throw(_("This function is only for Subcontracted Sales Orders"))
    
    # Check for existing draft
    existing_draft = frappe.db.get_value(
        "Sales Invoice Item",
        {"so_detail": soi.name, "docstatus": 0},
        "parent"
    )
    if existing_draft:
        frappe.msgprint(_("Opening existing Draft Sales Invoice {0}").format(existing_draft))
        return existing_draft
    
    # Get SIO delivered qty (FG qty delivered)
    sio_item = frappe.db.get_value(
        "Subcontracting Inward Order Item",
        {"sales_order_item": soi.name, "docstatus": 1},
        ["qty", "delivered_qty"],
        as_dict=True
    )
    
    if not sio_item or flt(sio_item.delivered_qty) <= 0:
        frappe.throw(_("No FG qty has been delivered via Subcontracting Inward Order yet"))
    
    fg_delivered = flt(sio_item.delivered_qty)
    
    # Calculate service-to-FG ratio
    fg_item_qty = flt(soi.fg_item_qty)
    service_qty = flt(soi.qty)
    
    if fg_item_qty <= 0:
        frappe.throw(_("FG Item Qty is not set on the Sales Order Item"))
    
    ratio = service_qty / fg_item_qty  # e.g. 500 / 493.998 = 1.01215
    
    # Service qty corresponding to delivered FG
    service_qty_for_delivered = flt(fg_delivered * ratio, 3)
    
    # Already billed qty
    already_billed_qty = flt(frappe.db.sql("""
        SELECT COALESCE(SUM(qty), 0)
        FROM `tabSales Invoice Item`
        WHERE so_detail = %s AND docstatus = 1
    """, soi.name)[0][0])
    
    invoiceable_qty = flt(service_qty_for_delivered - already_billed_qty, 3)
    
    if invoiceable_qty <= 0:
        frappe.throw(_("No invoiceable qty remaining. Delivered FG: {0}, Already billed: {1}").format(
            fg_delivered, already_billed_qty
        ))
    
    # Create Sales Invoice
    si = frappe.new_doc("Sales Invoice")
    si.customer = so.customer
    si.company = so.company
    si.currency = so.currency
    si.selling_price_list = so.selling_price_list
    si.conversion_rate = so.conversion_rate
    si.update_stock = 0
    
    si.append("items", {
        "item_code": soi.item_code,
        "item_name": soi.item_name,
        "description": soi.description,
        "qty": invoiceable_qty,
        "rate": soi.rate,
        "uom": soi.uom or soi.stock_uom,
        "stock_uom": soi.stock_uom,
        "conversion_factor": soi.conversion_factor or 1,
        "sales_order": soi.parent,
        "so_detail": soi.name,
        "warehouse": soi.warehouse,
    })
    
    si.set_missing_values()
    si.insert()
    
    frappe.msgprint(_("Sales Invoice {0} created for {1} qty (FG delivered: {2})").format(
        si.name, invoiceable_qty, fg_delivered
    ))
    
    return si.name

@frappe.whitelist()
def create_subcontracting_inward_order(sales_order, sales_order_item):
    """
    Create Subcontracting Inward Order for a Sales Order item.
    """
    require_production_write_access("create subcontracting inward orders")

    soi = frappe.db.get_value(
        "Sales Order Item",
        sales_order_item,
        ["item_code", "item_name", "qty", "uom", "rate", "delivered_qty", "warehouse", "bom_no", "fg_item", "fg_item_qty"],
        as_dict=True
    )
    
    if not soi:
        frappe.throw(_("Sales Order Item not found"))
    
    so = frappe.get_doc("Sales Order", sales_order)
    
    if not so.is_subcontracted:
        frappe.throw(_("Sales Order is not marked as Subcontracted"))
    
    # Identify Production Item
    production_item = soi.fg_item or soi.item_code
    
    # Identify BOM
    bom_no = soi.bom_no
    if not bom_no:
        bom_no = frappe.db.get_value(
            "BOM",
            {"item": production_item, "is_active": 1, "is_default": 1},
            "name"
        )
    
    if not bom_no:
        frappe.throw(_("No valid BOM found for item {0}").format(production_item))

    # Find Customer Warehouse (required for SIO)
    customer_warehouse = None
    company_abbr = frappe.get_cached_value('Company', so.company, 'abbr')
    
    # Strategy 1: Find any warehouse explicitly linked to this customer
    customer_warehouse = frappe.db.get_value(
        "Warehouse", 
        {"customer": so.customer, "company": so.company, "is_group": 0}, 
        "name"
    )
    
    # Strategy 2: Create new warehouse following standard: JW-IN - {Customer} - {Abbr}
    if not customer_warehouse:
        # Standard Parent: Customer Owned - Job Work - {Abbr}
        parent_wh_name = f"Customer Owned - Job Work - {company_abbr}"
        parent_wh = frappe.db.exists("Warehouse", parent_wh_name)
        
        if not parent_wh:
             # Fallback: Try fuzzy search for parent
             parent_wh = frappe.db.get_value(
                "Warehouse",
                {"name": ["like", "%Customer%Job%Work%"], "is_group": 1, "company": so.company},
                "name"
            )
             
        if not parent_wh:
             frappe.throw(_("Could not find parent warehouse 'Customer Owned - Job Work - {0}'. Please create it first.").format(company_abbr))
        
        # Create standard warehouse
        new_wh_name = f"JW-IN - {so.customer_name} - {company_abbr}"
        
        # Check if warehouse with this name exists but without customer link (edge case)
        existing_wh_doc = frappe.db.exists("Warehouse", new_wh_name)
        if existing_wh_doc:
             # Update it? Or use it?
             # If it exists, let's update the customer link if missing
             wh_doc = frappe.get_doc("Warehouse", new_wh_name)
             if not wh_doc.customer:
                 wh_doc.customer = so.customer
                 wh_doc.save(ignore_permissions=True)
             customer_warehouse = new_wh_name
        else:
             new_wh = frappe.new_doc("Warehouse")
             new_wh.warehouse_name = f"JW-IN - {so.customer_name} - {company_abbr}"
             new_wh.parent_warehouse = parent_wh
             new_wh.is_group = 0
             new_wh.company = so.company
             new_wh.customer = so.customer # CRITICAL: Set the customer field
             new_wh.insert(ignore_permissions=True)
             customer_warehouse = new_wh.name
             frappe.msgprint(_("Created new warehouse {0} for customer raw materials").format(customer_warehouse))

    if not customer_warehouse:
        frappe.throw(_("No Customer Warehouse found and could not auto-create one. Please create a warehouse for Customer {0} manually.").format(so.customer_name))
        
    # Determine Delivery Warehouse: Customer Job Work Completed - {Abbr}
    delivery_wh_name = f"Customer Job Work Completed - {company_abbr}"
    if not frappe.db.exists("Warehouse", delivery_wh_name):
         # Try finding it broadly
         delivery_wh_name = frappe.db.get_value(
            "Warehouse",
            {"name": ["like", "%Customer%Job%Work%Completed%"], "company": so.company},
            "name"
        )
    
    if not delivery_wh_name:
         frappe.throw(_("Could not find Delivery Warehouse 'Customer Job Work Completed - {0}'.").format(company_abbr))

    sio = frappe.new_doc("Subcontracting Inward Order")
    sio.sales_order = sales_order
    sio.customer = so.customer
    sio.customer_name = so.customer_name
    sio.company = so.company
    sio.transaction_date = nowdate()
    sio.customer_warehouse = customer_warehouse
    sio.set_delivery_warehouse = delivery_wh_name # Set default for items
    sio.status = "Draft"
    sio.from_production_wizard = 1 
    
    # Add Service Item
    service_item = sio.append("service_items", {})
    service_item.sales_order_item = sales_order_item # Required for populate
    service_item.item_code = soi.item_code # Service Item
    service_item.item_name = soi.item_name
    service_item.qty = flt(soi.qty)
    service_item.uom = soi.uom
    service_item.rate = soi.rate
    service_item.amount = flt(soi.qty) * flt(soi.rate)
    service_item.fg_item = soi.fg_item
    service_item.fg_item_qty = flt(soi.fg_item_qty)
    
    # Ensure Sales Order context is set
    sio.sales_order = sales_order

    # Populate Items table using standard logic (Subcontracting BOM lookup)
    sio.populate_items_table()
    
    if not sio.items:
        frappe.throw(_("No items populated for Subcontracting Inward Order. Please check if a Subcontracting BOM is active for Service Item {0} and Finished Good {1}.").format(soi.item_code, soi.fg_item)) 
    
    # Ensure delivery warehouse is set on items (in case populate didn't set it from set_delivery_warehouse)
    for item in sio.items:
        if not item.delivery_warehouse:
            item.delivery_warehouse = delivery_wh_name

    sio.insert(ignore_permissions=True)
    
    return sio.name
@frappe.whitelist()
def get_notes(sales_order_item):
    """
    Fetch all notes for a specific sales order item.
    """
    notes = frappe.db.get_all(
        "Production Wizard Note",
        filters={"sales_order_item": sales_order_item},
        fields=["name", "note", "owner", "creation", "item_code"],
        order_by="creation desc"
    )

    for note in notes:
        user = frappe.get_doc("User", note.owner)
        note.user_fullname = user.full_name
        note.user_image = user.user_image

    return notes

@frappe.whitelist()
def get_transaction_parameters(sales_order_item):
    """
    Fetch all transaction parameters for a specific sales order item.
    Returns list of {name, parameter, value}.
    """
    return frappe.get_all(
        "SO Transaction Parameter",
        filters={"sales_order_item": sales_order_item},
        fields=["name", "parameter", "value"],
        order_by="creation asc"
    )

@frappe.whitelist()
def save_transaction_parameters(sales_order, sales_order_item, item_code, params):
    """
    Bulk save transaction parameters for a sales order item.
    Deletes existing params and recreates from the provided list.
    
    Args:
        sales_order: Sales Order name
        sales_order_item: Sales Order Item row name
        item_code: Item Code (for reference)
        params: list of {parameter, value}
    """
    import json
    if isinstance(params, str):
        params = json.loads(params)
    
    # Delete existing params for this SO Item
    existing = frappe.get_all(
        "SO Transaction Parameter",
        filters={"sales_order_item": sales_order_item},
        pluck="name"
    )
    for name in existing:
        frappe.delete_doc("SO Transaction Parameter", name, ignore_permissions=True)
    
    # Create new params
    count = 0
    for p in params:
        if p.get("parameter") and p.get("value"):
            doc = frappe.get_doc({
                "doctype": "SO Transaction Parameter",
                "sales_order": sales_order,
                "sales_order_item": sales_order_item,
                "item_code": item_code,
                "parameter": p["parameter"],
                "value": p["value"]
            })
            doc.insert(ignore_permissions=True)
            count += 1
    
    frappe.db.commit()
    return {"count": count}

@frappe.whitelist()
def get_po_transaction_parameters(purchase_order_item):
    """
    Fetch all transaction parameters for a specific purchase order item.
    """
    return frappe.get_all(
        "PO Transaction Parameter",
        filters={"purchase_order_item": purchase_order_item},
        fields=["name", "parameter", "value"],
        order_by="creation asc"
    )

@frappe.whitelist()
def save_po_transaction_parameters(purchase_order, purchase_order_item, item_code, params):
    """
    Bulk save transaction parameters for a purchase order item.
    """
    import json
    if isinstance(params, str):
        params = json.loads(params)
    
    existing = frappe.get_all(
        "PO Transaction Parameter",
        filters={"purchase_order_item": purchase_order_item},
        pluck="name"
    )
    for name in existing:
        frappe.delete_doc("PO Transaction Parameter", name, ignore_permissions=True)
    
    count = 0
    for p in params:
        if p.get("parameter") and p.get("value"):
            doc = frappe.get_doc({
                "doctype": "PO Transaction Parameter",
                "purchase_order": purchase_order,
                "purchase_order_item": purchase_order_item,
                "item_code": item_code,
                "parameter": p["parameter"],
                "value": p["value"]
            })
            doc.insert(ignore_permissions=True)
            count += 1
    
    frappe.db.commit()
    return {"count": count}

@frappe.whitelist()
def add_production_note(sales_order_item, note):
    """
    Add a new note to the production wizard item.
    """
    require_production_write_access("add production notes")

    if not note:
        frappe.throw(_("Note content is required"))

    soi = frappe.db.get_value("Sales Order Item", sales_order_item, ["parent", "item_code"], as_dict=True)
    if not soi:
        frappe.throw(_("Sales Order Item not found"))

    doc = frappe.get_doc({
        "doctype": "Production Wizard Note",
        "sales_order": soi.parent,
        "sales_order_item": sales_order_item,
        "item_code": soi.item_code,
        "note": note
    })
    doc.insert()
    return doc

@frappe.whitelist()
def delete_production_note(note_name):
    """
    Delete a production wizard note.
    Only the creator or System Manager can delete.
    """
    require_production_write_access("delete production notes")

    if not frappe.db.exists("Production Wizard Note", note_name):
        frappe.throw(_("Note not found"))

    note = frappe.get_doc("Production Wizard Note", note_name)
    
    if note.owner != frappe.session.user and "System Manager" not in frappe.get_roles():
        frappe.throw(_("You are not authorized to delete this note"))

    note.delete()
    return "deleted"

def _validate_so_item_bom_mutation_allowed(sales_order_item, bom_no):
    """
    Guard helper for update_so_item_bom (P1.3).

    Rejects BOM mutation when:
      - WO already exists (any non-cancelled state) — BOM is already consumed for planning/operations.
      - SCIO Item already exists — subcontracting is in flight with this BOM.
      - BOM is inactive or not submitted.
      - BOM's item doesn't match the SO Item's production context.
    """
    soi = frappe.db.get_value(
        "Sales Order Item",
        sales_order_item,
        ["item_code", "fg_item", "parent", "bom_no"],
        as_dict=True
    )
    if not soi:
        frappe.throw(_("Sales Order Item {0} not found").format(sales_order_item))

    so = frappe.db.get_value("Sales Order", soi.parent, "is_subcontracted")
    production_item = soi.fg_item if so else soi.item_code

    # --- Lifecycle guard: Work Order ---
    blocking_wo = frappe.db.get_value(
        "Work Order",
        {"sales_order_item": sales_order_item, "docstatus": ["!=", 2]},
        "name"
    )
    if blocking_wo:
        frappe.throw(
            _("Cannot change BOM: Work Order <b>{0}</b> already exists for this Sales Order Item. "
              "Cancel and close the Work Order before modifying the BOM.").format(blocking_wo)
        )

    # --- Lifecycle guard: Subcontracting Inward Order ---
    blocking_scio_item = frappe.db.get_value(
        "Subcontracting Inward Order Item",
        {"sales_order_item": sales_order_item, "docstatus": ["!=", 2]},
        "parent"
    )
    if blocking_scio_item:
        frappe.throw(
            _("Cannot change BOM: Subcontracting Inward Order <b>{0}</b> already exists for this "
              "Sales Order Item. Cancel the order before modifying the BOM.").format(blocking_scio_item)
        )

    # --- BOM validity ---
    bom = frappe.db.get_value(
        "BOM",
        bom_no,
        ["name", "item", "is_active", "docstatus"],
        as_dict=True
    )
    if not bom:
        frappe.throw(_("BOM {0} not found.").format(bom_no))
    if bom.docstatus != 1:
        frappe.throw(_("BOM {0} is not submitted (current status: {1}).").format(bom_no, bom.docstatus))
    if not bom.is_active:
        frappe.throw(_("BOM {0} is inactive. Only active BOMs can be assigned.").format(bom_no))
    if bom.item != production_item:
        frappe.throw(
            _("BOM {0} is for item <b>{1}</b>, but this Sales Order Item requires a BOM for <b>{2}</b>.").format(
                bom_no, bom.item, production_item
            )
        )

    return soi.bom_no  # return old BOM for audit/response


@frappe.whitelist()
def update_so_item_bom(sales_order_item, bom_no):
    """
    Update the BOM number for a specific Sales Order Item.
    Guarded: rejects if WO or SCIO exists, or BOM is invalid/inactive.
    """
    require_production_write_access("update sales order item BOM")

    old_bom = _validate_so_item_bom_mutation_allowed(sales_order_item, bom_no)
    frappe.db.set_value("Sales Order Item", sales_order_item, "bom_no", bom_no)
    return {
        "message": "BOM Updated",
        "old_bom": old_bom,
        "new_bom": bom_no,
    }


@frappe.whitelist()
def get_batch_production_summary(sales_order_item):
    """
    Get comprehensive summary of production batches for a Sales Order Item.
    
    Returns:
    - Work Order info
    - Manufacturing batches (Stock Entries)
    - Subcontracting batches (by PO/SCO)
    - Delivery batches (Delivery Notes)
    """
    soi = frappe.db.get_value(
        "Sales Order Item", sales_order_item,
        ["parent", "item_code", "qty", "delivered_qty", "stock_uom"],
        as_dict=True
    )
    
    if not soi:
        frappe.throw(_("Sales Order Item not found"))
    
    # Get Work Order
    wo = frappe.db.get_value(
        "Work Order",
        {"sales_order_item": sales_order_item, "docstatus": ["!=", 2]},
        ["name", "qty", "produced_qty", "status"],
        as_dict=True
    )
    
    result = {
        "sales_order": soi.parent,
        "sales_order_item": sales_order_item,
        "item_code": soi.item_code,
        "uom": soi.stock_uom,
        "total_ordered_qty": soi.qty,
        "total_delivered_qty": soi.delivered_qty,
        "work_order": wo.name if wo else None,
        "work_order_status": wo.status if wo else None,
        "work_order_qty": wo.qty if wo else 0,
        "total_produced_qty": wo.produced_qty if wo else 0,
        "manufacturing_batches": [],
        "subcontracting_batches": [],
        "delivery_batches": []
    }
    
    if wo:
        # Get Manufacturing Batches (Stock Entries for Manufacture)
        mfg_entries = frappe.db.sql("""
            SELECT 
                se.name, se.posting_date, se.fg_completed_qty,
                tl.employee, tl.workstation
            FROM `tabStock Entry` se
            LEFT JOIN `tabJob Card Time Log` tl ON tl.parent = se.job_card AND tl.idx = 1
            WHERE se.work_order = %s
            AND se.docstatus = 1
            AND se.purpose = 'Manufacture'
            ORDER BY se.creation ASC
        """, wo.name, as_dict=True)
        
        for idx, se in enumerate(mfg_entries):
            result["manufacturing_batches"].append({
                "batch_no": idx + 1,
                "stock_entry": se.name,
                "date": se.posting_date,
                "qty": se.fg_completed_qty,
                "employee": se.employee,
                "workstation": se.workstation
            })
        
        # Get Subcontracting Batches (grouped by PO)
        sco_data = frappe.db.sql("""
            SELECT 
                poi.parent as po_name,
                po.supplier,
                poi.fg_item_qty as ordered_qty,
                sco.name as sco_name,
                po.creation as order_date
            FROM `tabPurchase Order Item` poi
            INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
            INNER JOIN `tabJob Card` jc ON jc.name = poi.job_card
            LEFT JOIN `tabSubcontracting Order` sco ON sco.purchase_order = po.name AND sco.docstatus = 1
            WHERE jc.work_order = %s
            AND po.docstatus != 2
            ORDER BY po.creation ASC
        """, wo.name, as_dict=True)
        
        for idx, sco in enumerate(sco_data):
            # Get sent and received qty for this SCO
            sent_qty = 0
            received_qty = 0
            
            if sco.sco_name:
                sent = frappe.db.sql("""
                    SELECT COALESCE(SUM(sed.qty), 0)
                    FROM `tabStock Entry` se
                    JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
                    WHERE se.subcontracting_order = %s
                    AND se.purpose = 'Send to Subcontractor'
                    AND se.docstatus = 1
                """, sco.sco_name)
                sent_qty = flt(sent[0][0]) if sent else 0
                
                recd = frappe.db.sql("""
                    SELECT COALESCE(SUM(sri.received_qty), 0)
                    FROM `tabSubcontracting Receipt` scr
                    JOIN `tabSubcontracting Receipt Item` sri ON sri.parent = scr.name
                    WHERE sri.subcontracting_order = %s
                    AND scr.docstatus = 1
                """, sco.sco_name)
                received_qty = flt(recd[0][0]) if recd else 0
            
            result["subcontracting_batches"].append({
                "batch_no": idx + 1,
                "po_name": sco.po_name,
                "sco_name": sco.sco_name,
                "supplier": sco.supplier,
                "ordered_qty": sco.ordered_qty,
                "sent_qty": sent_qty,
                "received_qty": received_qty,
                "order_date": sco.order_date
            })
    
    # Get Delivery Batches
    dn_data = frappe.db.sql("""
        SELECT 
            dni.parent as dn_name,
            dn.posting_date,
            dni.qty as delivered_qty
        FROM `tabDelivery Note Item` dni
        INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
        WHERE dni.so_detail = %s
        AND dn.docstatus = 1
        ORDER BY dn.creation ASC
    """, sales_order_item, as_dict=True)
    
    for idx, dn in enumerate(dn_data):
        result["delivery_batches"].append({
            "batch_no": idx + 1,
            "dn_name": dn.dn_name,
            "date": dn.posting_date,
            "qty": dn.delivered_qty
        })
    
    return result


@frappe.whitelist()
def complete_subcontracted_job_card(job_card):
    require_production_write_access("complete subcontracted job cards")
    return _complete_job_card_subcontracted(job_card)


def _complete_job_card_subcontracted(job_card):
    """
    Manually complete a subcontracted Job Card from the Production Wizard.
    This is used when the user decides no more subcontracting orders will be created.
    """
    jc = frappe.get_doc("Job Card", job_card)
    
    if jc.docstatus == 1:
        # Already submitted — just force status; audit this high-risk path explicitly.
        prev_status = jc.status
        jc.db_set("status", "Completed")

        # Audit trail (P1.4 — submitted-doc force path)
        log_manual_production_action(
            action="complete_subcontracted_job_card_force_status",
            jc=jc.name,
            wo=jc.work_order,
            qty_after=flt(jc.manufactured_qty),
            status_before=prev_status,
            status_after="Completed",
            mode="subcontracted",
            outcome="success",
            message="Status forced on already-submitted Job Card (no re-submission).",
        )

        return {
            "success": True,
            "job_card": jc.name,
            "message": _("Job Card {0} marked as Completed").format(job_card),
            "mode": "subcontracted",
            "received_qty": flt(jc.manufactured_qty),
        }
    
    if jc.docstatus == 2:
        frappe.throw(_("Cannot complete a cancelled Job Card"))
    
    # For draft job cards (likely subcontracted), we need to submit them
    try:
        if jc.is_subcontracted:
            # Get total received qty for this job card
            total_received = frappe.db.sql("""
                SELECT SUM(sri.qty) 
                FROM `tabSubcontracting Receipt Item` sri
                JOIN `tabSubcontracting Receipt` scr ON scr.name = sri.parent
                WHERE sri.job_card = %s AND scr.docstatus = 1
            """, job_card)
            received_qty = flt(total_received[0][0]) if total_received and total_received[0][0] else 0
            
            if received_qty <= 0:
                frappe.throw(_("Cannot complete Job Card with no received quantity"))
        
            # Add time log with total received qty
            jc.append("time_logs", {
                "from_time": frappe.utils.now_datetime(),
                "to_time": frappe.utils.now_datetime(),
                "completed_qty": received_qty
            })
        else:
            # For internal job cards, use the already logged manufactured quantity
            received_qty = jc.total_completed_qty

        jc.save()
        jc.submit()
        
        # Update Work Order status
        if jc.work_order:
            wo = frappe.get_doc("Work Order", jc.work_order)
            wo.update_work_order_qty()
            wo.update_status()

        # Audit trail (P1.4)
        log_manual_production_action(
            action="complete_subcontracted_job_card",
            jc=jc.name,
            wo=jc.work_order,
            qty_after=received_qty,
            status_before="Draft",
            status_after="Submitted",
            mode="subcontracted",
            outcome="success",
            message=f"Subcontracted Job Card manually completed. received_qty={received_qty}",
        )

        return {
            "success": True,
            "job_card": jc.name,
            "message": _("Job Card {0} completed with {1} qty").format(job_card, received_qty),
            "mode": "subcontracted",
            "received_qty": received_qty,
        }
    except Exception as e:
        frappe.log_error(f"Error completing Job Card {job_card}: {str(e)}")
        frappe.throw(str(e))


@frappe.whitelist()
def get_order_activity_log(sales_order_item):
    """
    Get a comprehensive, chronological activity log for a Sales Order Item.

    Aggregates events from all linked documents:
    - Sales Order
    - Work Order (creation, status changes)
    - Job Cards (operations, audit comments)
    - Stock Entries (manufacture, material transfer, reversals)
    - Purchase Orders (subcontracting)
    - Subcontracting Orders & Receipts
    - Delivery Notes
    - Sales Invoices
    - Production Wizard Notes
    """
    soi = frappe.db.get_value(
        "Sales Order Item", sales_order_item,
        ["name", "parent", "item_code", "item_name", "qty"],
        as_dict=True
    )

    if not soi:
        frappe.throw(_("Sales Order Item not found"))

    events = []

    def _add(timestamp, event_type, icon, color, title, description="",
             actor="", linked_doctype="", linked_name=""):
        actor_name = ""
        if actor:
            actor_name = frappe.get_cached_value("User", actor, "full_name") or actor
        events.append({
            "timestamp": str(timestamp),
            "event_type": event_type,
            "icon": icon,
            "color": color,
            "title": title,
            "description": description,
            "actor": actor,
            "actor_name": actor_name,
            "linked_doctype": linked_doctype,
            "linked_name": linked_name,
        })

    # ── 1. Sales Order ──
    so_creation = frappe.db.get_value(
        "Sales Order", soi.parent, ["creation", "owner"], as_dict=True
    )
    if so_creation:
        _add(
            so_creation.creation, "order", "fa-file-text-o", "#1976d2",
            f"Sales Order {soi.parent} created",
            f"Item {soi.item_code} — Qty {soi.qty}",
            so_creation.owner, "Sales Order", soi.parent
        )

    # ── 2. Work Order ──
    wo = frappe.db.get_value(
        "Work Order",
        {"sales_order_item": sales_order_item, "docstatus": ["!=", 2]},
        ["name", "status", "qty", "produced_qty", "creation", "owner", "modified"],
        as_dict=True
    )

    wo_name = wo.name if wo else None

    if wo:
        _add(
            wo.creation, "work_order", "fa-cogs", "#7b1fa2",
            f"Work Order {wo.name} created",
            f"Qty: {wo.qty} | Status: {wo.status}",
            wo.owner, "Work Order", wo.name
        )

        # Work Order comments (includes status changes, audit logs)
        wo_comments = frappe.get_all(
            "Comment",
            filters={"reference_doctype": "Work Order", "reference_name": wo.name,
                      "comment_type": "Comment"},
            fields=["content", "creation", "owner"],
            order_by="creation asc"
        )
        for c in wo_comments:
            is_audit = "[PRODUCTION ACTION]" in (c.content or "")
            _add(
                c.creation,
                "audit" if is_audit else "comment",
                "fa-shield" if is_audit else "fa-comment",
                "#e65100" if is_audit else "#546e7a",
                "Production Audit Log" if is_audit else "Comment on Work Order",
                c.content or "",
                c.owner, "Work Order", wo.name
            )

    # ── 3. Job Cards ──
    job_cards = []
    if wo_name:
        job_cards = frappe.get_all(
            "Job Card",
            filters={"work_order": wo_name, "docstatus": ["!=", 2]},
            fields=["name", "operation", "status", "for_quantity", "total_completed_qty",
                     "is_subcontracted", "creation", "owner", "modified"],
            order_by="creation asc"
        )

    for jc in job_cards:
        _add(
            jc.creation, "job_card", "fa-wrench", "#00897b",
            f"Job Card {jc.name} created — {jc.operation}",
            f"Qty: {jc.for_quantity} | {'Subcontracted' if jc.is_subcontracted else 'In-house'}",
            jc.owner, "Job Card", jc.name
        )

        # Job Card comments (audit logs from log_manual_production_action)
        jc_comments = frappe.get_all(
            "Comment",
            filters={"reference_doctype": "Job Card", "reference_name": jc.name,
                      "comment_type": "Comment"},
            fields=["content", "creation", "owner"],
            order_by="creation asc"
        )
        for c in jc_comments:
            is_audit = "[PRODUCTION ACTION]" in (c.content or "")
            _add(
                c.creation,
                "audit" if is_audit else "comment",
                "fa-shield" if is_audit else "fa-comment",
                "#e65100" if is_audit else "#546e7a",
                f"{'Production Audit' if is_audit else 'Comment'} — {jc.operation}",
                c.content or "",
                c.owner, "Job Card", jc.name
            )

    # ── 4. Stock Entries (Manufacture, Material Transfer, Reversals) ──
    if wo_name:
        stock_entries = frappe.get_all(
            "Stock Entry",
            filters={"work_order": wo_name, "docstatus": ["!=", 2]},
            fields=["name", "purpose", "fg_completed_qty", "posting_date",
                     "creation", "owner", "docstatus"],
            order_by="creation asc"
        )

        purpose_config = {
            "Manufacture": ("fa-industry", "#388e3c", "Manufactured"),
            "Material Transfer for Manufacture": ("fa-exchange", "#1565c0", "Material Transfer"),
            "Send to Subcontractor": ("fa-truck", "#6a1b9a", "Sent to Subcontractor"),
        }

        for se in stock_entries:
            cfg = purpose_config.get(se.purpose, ("fa-cube", "#757575", se.purpose))
            qty_txt = f" — {se.fg_completed_qty} qty" if se.fg_completed_qty else ""
            status_txt = " (Draft)" if se.docstatus == 0 else ""
            _add(
                se.creation, "stock_entry", cfg[0], cfg[1],
                f"{cfg[2]}{qty_txt}{status_txt}",
                f"Stock Entry {se.name} | {se.purpose}",
                se.owner, "Stock Entry", se.name
            )

    # ── 5. Purchase Orders (Subcontracting POs) ──
    if wo_name:
        po_data = frappe.db.sql("""
            SELECT DISTINCT
                poi.parent as po_name, po.supplier, po.supplier_name,
                po.creation, po.owner, po.docstatus
            FROM `tabPurchase Order Item` poi
            INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
            INNER JOIN `tabJob Card` jc ON jc.name = poi.job_card
            WHERE jc.work_order = %s
            AND po.docstatus != 2
            ORDER BY po.creation ASC
        """, wo_name, as_dict=True)

        for po in po_data:
            _add(
                po.creation, "subcontracting", "fa-shopping-cart", "#ad1457",
                f"Purchase Order {po.po_name} — {po.supplier_name or po.supplier}",
                "Subcontracting PO",
                po.owner, "Purchase Order", po.po_name
            )

    # ── 6. Subcontracting Orders ──
    if wo_name:
        sco_data = frappe.db.sql("""
            SELECT DISTINCT
                sco.name, sco.supplier, sco.supplier_name,
                sco.creation, sco.owner
            FROM `tabSubcontracting Order` sco
            INNER JOIN `tabPurchase Order` po ON po.name = sco.purchase_order
            INNER JOIN `tabPurchase Order Item` poi ON poi.parent = po.name
            INNER JOIN `tabJob Card` jc ON jc.name = poi.job_card
            WHERE jc.work_order = %s
            AND sco.docstatus = 1
            ORDER BY sco.creation ASC
        """, wo_name, as_dict=True)

        for sco in sco_data:
            _add(
                sco.creation, "subcontracting", "fa-share-square-o", "#6a1b9a",
                f"Subcontracting Order {sco.name}",
                f"Supplier: {sco.supplier_name or sco.supplier}",
                sco.owner, "Subcontracting Order", sco.name
            )

    # ── 7. Subcontracting Receipts ──
    if wo_name:
        scr_data = frappe.db.sql("""
            SELECT DISTINCT
                scr.name, scr.supplier, scr.supplier_name,
                scr.creation, scr.owner
            FROM `tabSubcontracting Receipt` scr
            INNER JOIN `tabSubcontracting Receipt Item` sri ON sri.parent = scr.name
            INNER JOIN `tabSubcontracting Order` sco ON sco.name = sri.subcontracting_order
            INNER JOIN `tabPurchase Order` po ON po.name = sco.purchase_order
            INNER JOIN `tabPurchase Order Item` poi ON poi.parent = po.name
            INNER JOIN `tabJob Card` jc ON jc.name = poi.job_card
            WHERE jc.work_order = %s
            AND scr.docstatus = 1
            ORDER BY scr.creation ASC
        """, wo_name, as_dict=True)

        for scr in scr_data:
            _add(
                scr.creation, "subcontracting", "fa-check-square-o", "#2e7d32",
                f"Subcontracting Receipt {scr.name}",
                f"Received from {scr.supplier_name or scr.supplier}",
                scr.owner, "Subcontracting Receipt", scr.name
            )

    # ── 8. Subcontracting Inward Order (SCIO) ──
    sio_item = frappe.db.get_value(
        "Subcontracting Inward Order Item",
        {"sales_order_item": sales_order_item, "docstatus": ["!=", 2]},
        ["parent", "qty", "delivered_qty"],
        as_dict=True
    )
    if sio_item:
        sio = frappe.db.get_value(
            "Subcontracting Inward Order", sio_item.parent,
            ["name", "status", "creation", "owner"],
            as_dict=True
        )
        if sio:
            _add(
                sio.creation, "subcontracting", "fa-share-square-o", "#6a1b9a",
                f"Subcontracting Inward Order {sio.name}",
                f"Status: {sio.status} | Qty: {sio_item.qty} | Delivered: {sio_item.delivered_qty}",
                sio.owner, "Subcontracting Inward Order", sio.name
            )

    # ── 9. Delivery Notes ──
    dn_data = frappe.db.sql("""
        SELECT
            dni.parent as dn_name, dn.posting_date, dni.qty,
            dn.creation, dn.owner
        FROM `tabDelivery Note Item` dni
        INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
        WHERE dni.so_detail = %s
        AND dn.docstatus != 2
        ORDER BY dn.creation ASC
    """, sales_order_item, as_dict=True)

    for dn in dn_data:
        _add(
            dn.creation, "delivery", "fa-truck", "#2e7d32",
            f"Delivery Note {dn.dn_name} — {dn.qty} qty",
            f"Posting Date: {dn.posting_date}",
            dn.owner, "Delivery Note", dn.dn_name
        )

    # ── 10. Sales Invoices ──
    si_data = frappe.db.sql("""
        SELECT
            sii.parent as si_name, si.posting_date, sii.qty, sii.amount,
            si.creation, si.owner, si.docstatus
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE sii.so_detail = %s
        AND si.docstatus != 2
        ORDER BY si.creation ASC
    """, sales_order_item, as_dict=True)

    for si in si_data:
        status_txt = " (Draft)" if si.docstatus == 0 else ""
        _add(
            si.creation, "invoice", "fa-file-text", "#f57f17",
            f"Sales Invoice {si.si_name}{status_txt}",
            f"Qty: {si.qty} | Amount: {si.amount}",
            si.owner, "Sales Invoice", si.si_name
        )

    # ── 11. Production Wizard Notes ──
    notes = frappe.get_all(
        "Production Wizard Note",
        filters={"sales_order_item": sales_order_item},
        fields=["name", "note", "owner", "creation"],
        order_by="creation asc"
    )
    for n in notes:
        _add(
            n.creation, "note", "fa-sticky-note", "#5d4037",
            "Production Note",
            n.note,
            n.owner, "Production Wizard Note", n.name
        )

    # Sort all events newest-first
    events.sort(key=lambda e: e["timestamp"], reverse=True)

    return {
        "sales_order": soi.parent,
        "sales_order_item": sales_order_item,
        "item_code": soi.item_code,
        "item_name": soi.item_name,
        "total_events": len(events),
        "events": events
    }
