"""
Production Wizard API

Unified production management API for the kniterp app.
Provides endpoints to manage the entire manufacturing process from a single interface.
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate, getdate, add_days, cint
import json


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
    conditions.append("soi.qty > soi.delivered_qty")
    
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
    
    where_clause = " AND ".join(conditions)
    
    items = frappe.db.sql("""
        SELECT
            soi.name as sales_order_item,
            so.name as sales_order,
            so.customer,
            so.customer_name,
            so.transaction_date,
            soi.item_code,
            soi.item_name,
            soi.qty,
            soi.delivered_qty,
            soi.work_order_qty,
            (soi.qty - soi.delivered_qty) as pending_qty,
            soi.delivery_date,
            soi.warehouse,
            soi.description,
            COALESCE(soi.bom_no, (
                SELECT name FROM `tabBOM` 
                WHERE item = soi.item_code AND is_active = 1 AND is_default = 1
                LIMIT 1
            )) as bom_no
        FROM `tabSales Order Item` soi
        INNER JOIN `tabSales Order` so ON so.name = soi.parent
        WHERE {where_clause}
        ORDER BY soi.delivery_date ASC, so.name ASC
    """.format(where_clause=where_clause), values, as_dict=True)
    
    # Get linked work orders for each item
    for item in items:
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
            item.work_order = None
            item.work_order_status = None
            item.produced_qty = 0
    
    return items


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
         "delivery_date", "warehouse", "bom_no", "description"],
        as_dict=True
    )
    
    if not soi:
        frappe.throw(_("Sales Order Item not found"))
    
    # Get BOM
    bom_no = soi.bom_no
    if not bom_no:
        bom_no = frappe.db.get_value(
            "BOM",
            {"item": soi.item_code, "is_active": 1, "is_default": 1},
            "name"
        )
    
    bom = None
    if bom_no:
        bom = frappe.get_doc("BOM", bom_no)
    
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
    
    # Build operations list from BOM
    operations = []
    pending_qty = soi.qty - soi.delivered_qty
    
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
                    
                    # If subcontracted, find PO and receipt details
                    if jc.is_subcontracted:
                        po = frappe.db.get_value(
                            "Purchase Order Item",
                            {"job_card": jc.name, "docstatus": ["!=", 2]},
                            ["parent", "qty", "fg_item_qty"],
                            as_dict=True
                        )
                        if po:
                            operation_data["purchase_order"] = po.parent
                            operation_data["po_qty"] = po.fg_item_qty or po.qty
                            
                            # Get SCO for this PO
                            sco = frappe.db.get_value(
                                "Subcontracting Order",
                                {"purchase_order": po.parent, "docstatus": 1},
                                "name"
                            )
                            
                            # Get material sent qty from Stock Entry
                            sent_qty = frappe.db.sql("""
                                SELECT SUM(sed.qty) 
                                FROM `tabStock Entry` se
                                JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
                                WHERE se.subcontracting_order = %s
                                AND se.purpose = 'Send to Subcontractor'
                                AND se.docstatus = 1
                            """, sco) if sco else [[0]]
                            operation_data["sent_qty"] = flt(sent_qty[0][0], 3) if sent_qty and sent_qty[0][0] else 0
                            
                            # Get received qty from Subcontracting Receipt 
                            received_qty = frappe.db.sql("""
                                SELECT SUM(sri.received_qty)
                                FROM `tabSubcontracting Receipt` scr
                                JOIN `tabSubcontracting Receipt Item` sri ON sri.parent = scr.name
                                WHERE sri.subcontracting_order = %s
                                AND scr.docstatus = 1
                            """, sco) if sco else [[0]]
                            operation_data["received_qty"] = flt(received_qty[0][0], 3) if received_qty and received_qty[0][0] else 0
                            
                            # If fully received, mark operation as completed
                            if operation_data["received_qty"] >= operation_data["po_qty"]:
                                operation_data["status"] = "Completed"
                                operation_data["completed_qty"] = operation_data["received_qty"]
                    break
            
            operations.append(operation_data)
        
        # Set previous_complete flag for each operation based on sequence
        # For subcontracted ops, also check if received_qty >= po_qty
        for idx, op in enumerate(operations):
            if idx > 0:
                prev_op = operations[idx - 1]
                if prev_op.get("is_subcontracted"):
                    # For subcontracted, complete when fully received
                    op["previous_complete"] = prev_op.get("received_qty", 0) >= prev_op.get("po_qty", 0) or prev_op["status"] == "Completed"
                else:
                    op["previous_complete"] = prev_op["status"] == "Completed"
    

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

    # ... get raw materials ...

    # Filter to only show purchasable items (not semi-finished goods produced by earlier operations)
    raw_materials = []
    
    if bom:
        company = frappe.db.get_value("Sales Order", soi.parent, "company")
        
        for item in bom.items:
            # Skip semi-finished goods - they are produced by earlier operations, not purchased
            if item.is_sub_assembly_item:
                continue
            
            
            required_qty = flt(flt(item.qty) * flt(soi.qty - soi.delivered_qty) / flt(bom.quantity), 3)
            
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
            
            # Check if material is consumed by checking if the operation using this item is completed
            material_consumed = False
            consumed_qty = 0
            target_operation = item.operation
            
            if not target_operation and operations and len(operations) > 0:
                # No specific operation - raw materials typically consumed by FIRST operation
                target_operation = operations[0].get("operation")
            
            if target_operation:
                # Find if operation for this item is complete
                for op in operations:
                    if op.get("operation") == target_operation:
                        # Material is consumed if job card is submitted (completed)
                        if op.get("status") == "Completed":
                            material_consumed = True
                            
                            # Get actual consumed qty from Stock Entry (Manufacture)
                            if op.get("job_card") and work_order:
                                # Sum up consumed qty from Stock Entries linked to this Job Card
                                # Filter for raw materials (is_finished_item=0)
                                actual_consumed = frappe.db.sql("""
                                    SELECT SUM(sed.qty)
                                    FROM `tabStock Entry` se
                                    JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
                                    WHERE se.job_card = %s
                                    AND se.docstatus = 1
                                    AND se.purpose = 'Manufacture'
                                    AND sed.item_code = %s
                                    AND sed.is_finished_item = 0
                                """, (op.get("job_card"), item.item_code))
                                
                                consumed_qty = flt(actual_consumed[0][0]) if actual_consumed and actual_consumed[0][0] else required_qty
                            else:
                                consumed_qty = required_qty
                        break
            
            # Determine status
            if material_consumed:
                status = "consumed"
            elif shortage <= 0:
                status = "available"
            elif available_qty > 0:
                status = "low"
            else:
                status = "shortage"
            
            # Get ordered qty from pending Purchase Orders (for this item, any warehouse)
            po_data = frappe.db.sql("""
                SELECT 
                    po.name as po_name,
                    po.status as po_status,
                    poi.qty as ordered_qty,
                    poi.received_qty,
                    poi.warehouse
                FROM `tabPurchase Order Item` poi
                INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
                WHERE poi.item_code = %s
                AND po.docstatus = 1
                AND po.status NOT IN ('Closed', 'Cancelled')
                ORDER BY po.creation DESC
            """, (item.item_code,), as_dict=True)
            
            # Calculate totals and build PO list
            linked_pos = []
            total_ordered = 0
            total_received = 0
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
                total_received += flt(po.received_qty)
            
            raw_materials.append({
                "item_code": item.item_code,
                "item_name": item.item_name,
                "required_qty": required_qty,
                "available_qty": available_qty,
                "actual_qty": actual_qty,
                "projected_qty": projected_qty,
                "reserved_qty": reserved_qty,
                "warehouse": soi.warehouse or item.source_warehouse,
                "uom": item.uom,
                "shortage": shortage,
                "status": status,
                "consumed_qty": consumed_qty,
                "ordered_qty": total_ordered,
                "linked_pos": linked_pos,
                "operation": item.operation,
                "operation_row_id": item.operation_row_id
            })
    
    return {
        "sales_order": soi.parent,
        "sales_order_item": soi.name,
        "item_code": soi.item_code,
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
        "projected_qty": fg_projected_qty
    }


@frappe.whitelist()
def create_work_order(sales_order, sales_order_item):
    """
    Create Work Order for a Sales Order item.
    Returns the created Work Order name.
    """
    # Get Sales Order Item
    soi = frappe.db.get_value(
        "Sales Order Item",
        sales_order_item,
        ["item_code", "qty", "delivered_qty", "warehouse", "bom_no", "description"],
        as_dict=True
    )
    
    if not soi:
        frappe.throw(_("Sales Order Item not found"))
    
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
            {"item": soi.item_code, "is_active": 1, "is_default": 1},
            "name"
        )
    
    if not bom_no:
        frappe.throw(_("No active BOM found for item {0}").format(soi.item_code))
    
    # Get Sales Order details
    so = frappe.db.get_value(
        "Sales Order",
        sales_order,
        ["company", "project"],
        as_dict=True
    )
    
    # Create Work Order
    wo = frappe.new_doc("Work Order")
    wo.production_item = soi.item_code
    wo.bom_no = bom_no
    wo.qty = flt(soi.qty) - flt(soi.delivered_qty)
    wo.sales_order = sales_order
    wo.sales_order_item = sales_order_item
    wo.company = so.company
    wo.project = so.project
    wo.fg_warehouse = soi.warehouse
    wo.description = soi.description
    
    wo.set_work_order_operations()
    wo.flags.ignore_mandatory = True
    wo.insert()
    wo.save()
    
    frappe.msgprint(_("Work Order {0} created successfully").format(wo.name))
    
    return wo.name


@frappe.whitelist()
def start_work_order(work_order):
    """
    Submit Work Order to start production.
    This will create Job Cards for each operation.
    """
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
        if available < item.required_qty:
            frappe.msgprint(
                _("Warning: Insufficient stock for {0}. Available: {1}, Required: {2}").format(
                    item.item_code, available, item.required_qty
                ),
                indicator="orange"
            )
    
    wo.submit()
    
    frappe.msgprint(_("Work Order {0} started. Job Cards created for operations.").format(wo.name))
    
    return {
        "work_order": wo.name,
        "status": wo.status
    }


@frappe.whitelist()
def create_subcontracting_order(work_order, operation, supplier, qty=None):
    """
    Create Subcontracting Purchase Order and Subcontracting Order for a specific operation.
    
    This creates PO, submits it. ERPNext may auto-create SCO on PO submit (based on settings).
    If not auto-created, we create it manually.
    """
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
    
    # Check operation sequence - ensure all previous operations are completed
    previous_ops_incomplete = frappe.db.sql("""
        SELECT jc.name, jc.operation, jc.status
        FROM `tabJob Card` jc
        WHERE jc.work_order = %s
        AND jc.docstatus != 2
        AND jc.sequence_id < %s
        AND jc.status != 'Completed'
    """, (work_order, job_card.sequence_id or 999), as_dict=True)
    
    if previous_ops_incomplete:
        incomplete_ops = ", ".join([op.operation for op in previous_ops_incomplete])
        frappe.throw(_("Cannot start this operation. Previous operations not completed: {0}").format(incomplete_ops))
    
    # Check if PO already exists
    existing_po = frappe.db.get_value(
        "Purchase Order Item",
        {"job_card": job_card.name, "docstatus": ["!=", 2]},
        "parent"
    )
    
    if existing_po:
        frappe.throw(_("Purchase Order {0} already exists for this operation").format(existing_po))
    
    # Get subcontracting BOM details - use the finished_good from job card
    from erpnext.subcontracting.doctype.subcontracting_bom.subcontracting_bom import (
        get_subcontracting_boms_for_finished_goods
    )
    
    fg_item = job_card.finished_good or wo.production_item
    sc_bom = get_subcontracting_boms_for_finished_goods(fg_item)
    
    if not sc_bom:
        frappe.throw(_("No Subcontracting BOM found for item {0}").format(fg_item))
    
    pending_qty = flt(job_card.for_quantity) - flt(job_card.total_completed_qty)
    if qty:
        pending_qty = min(flt(qty), pending_qty)
    
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
        "qty": pending_qty * service_item_qty / fg_item_qty,
        "fg_item_qty": pending_qty,
        "job_card": job_card.name,
        "bom": job_card.semi_fg_bom or sc_bom.finished_good_bom,
        "warehouse": wo.fg_warehouse
    })
    
    po.set_missing_values()
    po.flags.ignore_mandatory = True
    po.insert()
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


@frappe.whitelist()
def complete_operation(work_order, operation, qty):
    """
    Mark an in-house operation as complete by updating the Job Card.
    """
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
    
    # Add time log - this updates manufactured qty without submitting job card
    job_card.append("time_logs", {
        "from_time": frappe.utils.now_datetime(),
        "to_time": frappe.utils.now_datetime(),
        "completed_qty": qty
    })
    
    job_card.save()
    
    return {
        "job_card": job_card.name,
        "status": job_card.status,
        "total_completed_qty": job_card.total_completed_qty
    }


@frappe.whitelist()
def complete_job_card(job_card, additional_qty=0, process_loss_qty=0, 
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
            
            # Check stock availability - PREVENT negative inventory
            available_qty = frappe.db.get_value(
                "Bin",
                {"item_code": item.item_code, "warehouse": item.source_warehouse},
                "actual_qty"
            ) or 0
            
            if flt(available_qty) < flt(item.required_qty):
                frappe.throw(
                    _("Row {0}: Insufficient stock for {1}. Required: {2}, Available: {3} in {4}. Please ensure stock is available before completing the Job Card.").format(
                        item.idx, 
                        item.item_code, 
                        frappe.format(item.required_qty, {"fieldtype": "Float"}),
                        frappe.format(available_qty, {"fieldtype": "Float"}),
                        item.source_warehouse
                    )
                )
    
    # WIP warehouse is required ONLY if skip_material_transfer is NOT enabled (on either WO or JC)
    if not skip_wip_transfer and not jc.wip_warehouse:
        frappe.throw(_("WIP Warehouse is required. Please update the Job Card or enable 'Skip Material Transfer' on Job Card or Work Order."))
    
    # For semi-finished goods, validate target warehouse
    if jc.finished_good and not work_order.fg_warehouse:
        frappe.throw(_("Finished Goods Warehouse is not set on Work Order {0}").format(jc.work_order))
    
    # Now submit the job card
    try:
        jc.submit()
    except Exception as e:
        frappe.throw(_("Failed to submit Job Card: {0}").format(str(e)))
    
    # Create stock entry for semi-finished goods if applicable
    # Stock entry is ALWAYS required to manufacture finished goods - never skip
    stock_entry_name = None
    if jc.finished_good:
        try:
            se_result = jc.make_stock_entry_for_semi_fg_item(auto_submit=True)
            if se_result:
                stock_entry_name = se_result.get("name")
        except Exception as e:
            # Stock entry failed - notify user but don't throw (JC is already submitted)
            frappe.log_error(f"Error creating stock entry for Job Card {job_card}: {str(e)}")
            frappe.msgprint(_("Note: Job Card was submitted successfully. However, Stock Entry creation failed: {0}. Please create Stock Entry manually.").format(str(e)), indicator="orange")
    
    return stock_entry_name or jc.name


@frappe.whitelist()
def receive_subcontracted_goods(purchase_order, items=None):
    """
    Create Subcontracting Receipt to receive goods from subcontractor.
    Auto-updates Job Card and Work Order status.
    """
    po = frappe.get_doc("Purchase Order", purchase_order)
    
    if po.docstatus != 1:
        frappe.throw(_("Purchase Order must be submitted"))
    
    if not po.is_subcontracted:
        frappe.throw(_("Purchase Order is not a subcontracting order"))
    
    # Create Subcontracting Order first if not exists
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
    scr.insert()
    
    frappe.msgprint(_("Subcontracting Receipt {0} created").format(scr.name))
    
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
    pending_items = frappe.db.count("Sales Order Item", {
        "docstatus": 1,
        "qty": [">", "delivered_qty"]
    })
    
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
    If linked to a Work Order, use the produced_qty instead of Sales Order pending qty
    to handle over-production scenarios.
    """
    from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
    
    dn = make_delivery_note(sales_order)
    
    # Update quantities based on actual production
    for item in dn.items:
        if not item.so_detail:
            continue
            
        # Check for linked Work Order
        wo_data = frappe.db.get_value(
            "Work Order",
            {
                "sales_order": sales_order,
                "sales_order_item": item.so_detail,
                "docstatus": 1
            },
            ["name", "produced_qty"],
            as_dict=True
        )
        
        if wo_data and wo_data.produced_qty > 0:
            # Get already delivered qty for this SO item
            delivered_qty = frappe.db.get_value("Sales Order Item", item.so_detail, "delivered_qty") or 0.0
            
            # Calculate what we can deliver now
            # If we produced 320 and delivered 0, we can deliver 320
            # If we produced 320 and delivered 100, we can deliver 220
            available_to_deliver = flt(wo_data.produced_qty) - flt(delivered_qty)
            
            if available_to_deliver > item.qty:
                item.qty = available_to_deliver
                frappe.msgprint(
                    _("Updated delivery qty for item {0} to {1} based on actual production").format(
                        item.item_code, available_to_deliver
                    ),
                    alert=True
                )

    dn.insert()
    
    frappe.msgprint(_("Delivery Note {0} created").format(dn.name))
    
    return dn.name
