import frappe
from frappe import _
from frappe.utils import flt, getdate, add_months, add_days, nowdate, cint
import json


@frappe.whitelist()
def get_standalone_jwo_list(filters=None):
    """Return active standalone Job Work Out POs (not linked to any Sales Order).

    A PO is standalone when is_subcontracted=1 AND none of its items have a
    sales_order_item link.

    Returns list of dicts with PO header + first FG item summary + computed status.
    """
    if isinstance(filters, str):
        import json
        filters = json.loads(filters)
    filters = filters or {}

    conditions = [
        "po.is_subcontracted = 1",
        "po.docstatus = 1",
        "po.status NOT IN ('Cancelled')",
    ]
    values = {}

    # Exclude POs that have ANY item linked to a Sales Order
    conditions.append("""
        NOT EXISTS (
            SELECT 1 FROM `tabPurchase Order Item` poi_link
            WHERE poi_link.parent = po.name
            AND poi_link.sales_order_item IS NOT NULL
            AND poi_link.sales_order_item != ''
        )
    """)

    if filters.get("supplier"):
        conditions.append("po.supplier = %(supplier)s")
        values["supplier"] = filters["supplier"]

    if filters.get("from_date"):
        conditions.append("po.transaction_date >= %(from_date)s")
        values["from_date"] = getdate(filters["from_date"])

    if filters.get("to_date"):
        conditions.append("po.transaction_date <= %(to_date)s")
        values["to_date"] = getdate(filters["to_date"])

    status_filter = filters.get("status")

    # Base query: PO header + first item summary
    rows = frappe.db.sql("""
        SELECT
            po.name,
            po.supplier,
            po.supplier_name,
            po.transaction_date,
            po.schedule_date,
            po.status AS po_status,
            po.per_received,
            po.grand_total,
            poi.fg_item,
            poi.fg_item_qty,
            poi.item_code AS service_item,
            poi.qty AS service_qty,
            poi.received_qty AS service_received_qty,
            poi.item_name AS service_item_name,
            (SELECT fi.item_name FROM `tabItem` fi WHERE fi.name = poi.fg_item) AS fg_item_name,
            (SELECT sco.name FROM `tabSubcontracting Order` sco
             WHERE sco.purchase_order = po.name AND sco.docstatus = 1 LIMIT 1) AS sco_name
        FROM `tabPurchase Order` po
        INNER JOIN `tabPurchase Order Item` poi ON poi.parent = po.name AND poi.idx = 1
        WHERE {conditions}
        ORDER BY po.transaction_date DESC, po.name DESC
    """.format(conditions=" AND ".join(conditions)), values, as_dict=1)

    result = []
    for row in rows:
        computed_status = _compute_jwo_status(row)
        if status_filter and computed_status != status_filter:
            continue
        row["computed_status"] = computed_status
        result.append(row)

    return result


@frappe.whitelist()
def get_standalone_jwo_details(purchase_order):
    """Return full detail for a single standalone JWO Purchase Order.

    Includes: PO header, SCO details, supplied items, Stock Entry history,
    Subcontracting Receipt history, and available actions.
    """
    po = frappe.get_doc("Purchase Order", purchase_order)

    if not po.is_subcontracted or po.docstatus != 1:
        frappe.throw(_("Not a valid submitted subcontracting Purchase Order"))

    # PO Items (with FG details)
    items = []
    for item in po.items:
        fg_item_name = frappe.db.get_value("Item", item.fg_item, "item_name") if item.fg_item else ""
        # Compute received FG qty
        fg_received = 0
        if item.fg_item_qty and item.qty:
            fg_received = flt(item.received_qty * (item.fg_item_qty / item.qty), 3)
        else:
            fg_received = flt(item.received_qty, 3)
        items.append({
            "item_code": item.item_code,
            "item_name": item.item_name,
            "fg_item": item.fg_item,
            "fg_item_name": fg_item_name,
            "fg_item_qty": flt(item.fg_item_qty, 3),
            "service_qty": flt(item.qty, 3),
            "rate": flt(item.rate, 2),
            "received_qty": flt(item.received_qty, 3),
            "fg_received_qty": fg_received,
            "fg_pending_qty": flt(flt(item.fg_item_qty, 3) - fg_received, 3),
            "bom": item.bom,
        })

    # SCO details
    sco_name = frappe.db.get_value(
        "Subcontracting Order",
        {"purchase_order": purchase_order, "docstatus": 1},
        "name",
    )
    supplied_items = []
    sco_status = ""
    if sco_name:
        sco_doc = frappe.get_doc("Subcontracting Order", sco_name)
        sco_status = sco_doc.status
        for si in sco_doc.supplied_items:
            pending_qty = flt(flt(si.required_qty, 3) - flt(si.supplied_qty, 3), 3)

            # Stock availability
            reserve_wh = si.reserve_warehouse
            bin_data = frappe.db.get_value(
                "Bin",
                {"item_code": si.rm_item_code, "warehouse": reserve_wh},
                ["actual_qty", "reserved_qty"],
                as_dict=True,
            ) or {}
            actual_qty = flt(bin_data.get("actual_qty", 0), 3)
            reserved_qty = flt(bin_data.get("reserved_qty", 0), 3)
            available_qty = flt(actual_qty - reserved_qty, 3)
            shortage = flt(max(0, pending_qty - available_qty), 3)

            # BOM info (can this RM be manufactured?)
            default_bom = frappe.db.get_value("Item", si.rm_item_code, "default_bom") or ""
            has_bom = bool(default_bom)

            # Existing open POs for this RM
            existing_pos = frappe.db.sql("""
                SELECT po.name, po.status, poi.qty, poi.received_qty
                FROM `tabPurchase Order Item` poi
                INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
                WHERE poi.item_code = %s
                AND po.docstatus = 1
                AND po.status NOT IN ('Closed', 'Cancelled', 'Completed')
                AND poi.received_qty < poi.qty
                ORDER BY po.creation DESC
                LIMIT 5
            """, (si.rm_item_code,), as_dict=True)

            # Existing open WOs for this RM
            existing_wos = frappe.get_all(
                "Work Order",
                filters={
                    "production_item": si.rm_item_code,
                    "docstatus": ["!=", 2],
                    "status": ["not in", ["Completed", "Stopped", "Cancelled"]],
                },
                fields=["name", "status", "qty", "produced_qty"],
                order_by="creation desc",
                limit=5,
            )

            # Last purchase rate
            item_rates = frappe.db.get_value(
                "Item", si.rm_item_code,
                ["last_purchase_rate", "valuation_rate"],
                as_dict=True,
            ) or {}

            supplied_items.append({
                "rm_item_code": si.rm_item_code,
                "rm_item_name": frappe.db.get_value("Item", si.rm_item_code, "item_name") or si.rm_item_code,
                "required_qty": flt(si.required_qty, 3),
                "supplied_qty": flt(si.supplied_qty, 3),
                "pending_qty": pending_qty,
                "stock_uom": si.stock_uom,
                "reserve_warehouse": reserve_wh,
                "actual_qty": actual_qty,
                "available_qty": available_qty,
                "shortage": shortage,
                "has_bom": has_bom,
                "default_bom": default_bom,
                "existing_pos": existing_pos,
                "existing_wos": existing_wos,
                "last_purchase_rate": flt(item_rates.get("last_purchase_rate", 0)),
                "valuation_rate": flt(item_rates.get("valuation_rate", 0)),
            })

    # Stock Entry history (Send to Subcontractor)
    stock_entries = []
    if sco_name:
        se_list = frappe.get_all(
            "Stock Entry",
            filters={
                "subcontracting_order": sco_name,
                "purpose": "Send to Subcontractor",
                "docstatus": ["!=", 2],
            },
            fields=["name", "posting_date", "docstatus", "total_outgoing_value"],
            order_by="posting_date asc, name asc",
        )
        for se in se_list:
            se_items = frappe.get_all(
                "Stock Entry Detail",
                filters={"parent": se.name},
                fields=["item_code", "qty", "batch_no"],
            )
            stock_entries.append({
                "name": se.name,
                "posting_date": se.posting_date,
                "docstatus": se.docstatus,
                "total_value": flt(se.total_outgoing_value, 2),
                "items": se_items,
            })

    # SCR history
    receipts = []
    if sco_name:
        scr_list = frappe.get_all(
            "Subcontracting Receipt",
            filters={
                "supplier": po.supplier,
                "docstatus": ["!=", 2],
            },
            fields=["name", "posting_date", "docstatus", "total_qty"],
            order_by="posting_date asc, name asc",
        )
        # Filter to only SCRs linked to our SCO
        for scr in scr_list:
            is_linked = frappe.db.exists(
                "Subcontracting Receipt Item",
                {"parent": scr.name, "subcontracting_order": sco_name},
            )
            if not is_linked:
                continue
            scr_items = frappe.get_all(
                "Subcontracting Receipt Item",
                filters={"parent": scr.name},
                fields=["item_code", "qty", "received_qty", "is_scrap_item",
                         "serial_and_batch_bundle"],
            )
            receipts.append({
                "name": scr.name,
                "posting_date": scr.posting_date,
                "docstatus": scr.docstatus,
                "total_qty": flt(scr.total_qty, 3),
                "items": scr_items,
            })

    # Purchase Invoice history
    pi_list = frappe.get_all(
        "Purchase Invoice Item",
        filters={"purchase_order": purchase_order, "docstatus": ["!=", 2]},
        fields=["parent", "qty", "rate", "amount"],
        group_by="parent",
    )
    invoices = []
    for pi_item in pi_list:
        pi_data = frappe.db.get_value(
            "Purchase Invoice", pi_item.parent,
            ["posting_date", "status", "grand_total", "docstatus"], as_dict=1,
        )
        if pi_data:
            invoices.append({
                "name": pi_item.parent,
                "posting_date": pi_data.posting_date,
                "status": pi_data.status,
                "grand_total": flt(pi_data.grand_total, 2),
                "docstatus": pi_data.docstatus,
            })

    # Compute status and available actions
    total_rm_required = sum(s["required_qty"] for s in supplied_items)
    total_rm_supplied = sum(s["supplied_qty"] for s in supplied_items)
    total_fg_ordered = sum(i["fg_item_qty"] for i in items)
    total_fg_received = sum(i["fg_received_qty"] for i in items)
    rm_pending = any(s["pending_qty"] > 0 for s in supplied_items)
    has_submitted_se = any(se["docstatus"] == 1 for se in stock_entries)

    actions = {
        "can_send_material": bool(sco_name and rm_pending),
        "can_receive_goods": bool(sco_name and has_submitted_se and total_fg_received < total_fg_ordered),
        "can_create_invoice": bool(total_fg_received > 0),
    }

    return {
        "purchase_order": {
            "name": po.name,
            "supplier": po.supplier,
            "supplier_name": po.supplier_name,
            "transaction_date": po.transaction_date,
            "schedule_date": po.schedule_date,
            "status": po.status,
            "grand_total": flt(po.grand_total, 2),
            "per_received": flt(po.per_received, 2),
        },
        "items": items,
        "sco_name": sco_name or "",
        "sco_status": sco_status,
        "supplied_items": supplied_items,
        "stock_entries": stock_entries,
        "receipts": receipts,
        "invoices": invoices,
        "summary": {
            "total_rm_required": flt(total_rm_required, 3),
            "total_rm_supplied": flt(total_rm_supplied, 3),
            "total_fg_ordered": flt(total_fg_ordered, 3),
            "total_fg_received": flt(total_fg_received, 3),
        },
        "actions": actions,
    }


@frappe.whitelist()
def get_standalone_jwo_suppliers():
    """Return list of suppliers who have active standalone JWOs."""
    suppliers = frappe.db.sql("""
        SELECT DISTINCT po.supplier, po.supplier_name
        FROM `tabPurchase Order` po
        WHERE po.is_subcontracted = 1
        AND po.docstatus = 1
        AND po.status NOT IN ('Cancelled', 'Closed', 'Completed')
        AND NOT EXISTS (
            SELECT 1 FROM `tabPurchase Order Item` poi_link
            WHERE poi_link.parent = po.name
            AND poi_link.sales_order_item IS NOT NULL
            AND poi_link.sales_order_item != ''
        )
        ORDER BY po.supplier_name
    """, as_dict=1)

    return suppliers


@frappe.whitelist()
def create_rm_purchase_order(subcontracting_order, items, supplier, schedule_date=None, warehouse=None, submit=True):
    """Create a Purchase Order for RM items needed by a subcontracting order."""
    if isinstance(items, str):
        items = json.loads(items)

    if not items:
        frappe.throw(_("No items provided"))
    if not supplier:
        frappe.throw(_("Supplier is required"))

    sco = frappe.get_doc("Subcontracting Order", subcontracting_order)
    company = sco.company
    req_date = schedule_date or add_days(nowdate(), 7)

    po = frappe.new_doc("Purchase Order")
    po.supplier = supplier
    po.company = company
    po.schedule_date = req_date

    for item in items:
        item_doc = frappe.get_cached_doc("Item", item.get("item_code"))
        row_data = {
            "item_code": item.get("item_code"),
            "item_name": item_doc.item_name,
            "qty": flt(item.get("qty"), 3),
            "uom": item_doc.stock_uom,
            "stock_uom": item_doc.stock_uom,
            "warehouse": warehouse or item.get("warehouse") or sco.supplier_warehouse,
            "schedule_date": req_date,
        }
        if item.get("rate"):
            row_data["rate"] = flt(item.get("rate"))
        po.append("items", row_data)

    po.set_missing_values()
    po.insert()

    if cint(submit):
        po.submit()

    status_text = "submitted" if cint(submit) else "created as draft"
    frappe.msgprint(_(
        "Purchase Order <a href='/app/purchase-order/{0}'>{0}</a> {1}"
    ).format(po.name, status_text))

    return {
        "name": po.name,
        "status": po.status,
        "docstatus": po.docstatus,
    }


@frappe.whitelist(methods=["POST"])
def create_rm_purchase_receipt(purchase_order, items=None, received_batches=None, submit=False, supplier_delivery_note=None):
    """Create Purchase Receipt from an existing PO for RM items.

    Args:
        purchase_order: PO name (str)
        items: JSON list of {item_code, qty} — filters/overrides pending qty per item
        received_batches: JSON list of {batch_no, qty} — creates Serial and Batch Bundle per batch item
        submit: if truthy, submit the PR after creation
    """
    po = frappe.get_doc("Purchase Order", purchase_order)
    if po.docstatus != 1:
        frappe.throw(_("Purchase Order must be submitted"))

    if isinstance(items, str):
        items = json.loads(items)
    if isinstance(received_batches, str):
        received_batches = json.loads(received_batches)
    submit = cint(submit)

    pr = frappe.new_doc("Purchase Receipt")
    pr.supplier = po.supplier
    pr.company = po.company
    pr.buying_price_list = po.buying_price_list

    items_appended = 0
    for po_item in po.items:
        pending = flt(po_item.qty - po_item.received_qty, 3)
        if pending <= 0:
            continue

        if items:
            match = next((i for i in items if i.get("item_code") == po_item.item_code), None)
            if not match:
                continue
            pending = min(pending, flt(match.get("qty", pending), 3))

        pr.append("items", {
            "item_code": po_item.item_code,
            "item_name": po_item.item_name,
            "qty": pending,
            "rate": po_item.rate,
            "uom": po_item.uom,
            "stock_uom": po_item.stock_uom,
            "warehouse": po_item.warehouse,
            "purchase_order": po.name,
            "purchase_order_item": po_item.name,
        })
        items_appended += 1

    if not items_appended:
        frappe.throw(_("No pending items to receive"))

    pr.set_missing_values()
    if supplier_delivery_note:
        pr.supplier_delivery_note = supplier_delivery_note
    pr.insert()

    created_batches = []
    try:
        if received_batches:
            batch_tracked_items = [i for i in pr.items if frappe.get_cached_value("Item", i.item_code, "has_batch_no")]
            if len(batch_tracked_items) > 1:
                frappe.throw(_("Batch assignment for multi-item Purchase Receipts is not supported via this dialog. Please use the standard form."))

            for pr_item in pr.items:
                has_batch = frappe.get_cached_value("Item", pr_item.item_code, "has_batch_no")
                if not has_batch:
                    continue

                sabb = frappe.new_doc("Serial and Batch Bundle")
                sabb.item_code = pr_item.item_code
                sabb.warehouse = pr_item.warehouse
                sabb.type_of_transaction = "Inward"
                sabb.voucher_type = "Purchase Receipt"
                sabb.has_batch_no = 1
                sabb.company = pr.company

                for batch in received_batches:
                    batch_no = batch.get("batch_no")
                    qty = flt(batch.get("qty"), 3)
                    if not frappe.db.exists("Batch", batch_no):
                        batch_doc = frappe.new_doc("Batch")
                        batch_doc.batch_id = batch_no
                        batch_doc.item = pr_item.item_code
                        batch_doc.source_type = "Supplier"
                        batch_doc.flags.ignore_permissions = True
                        batch_doc.insert(ignore_permissions=True)
                        created_batches.append(batch_no)
                    sabb.append("entries", {
                        "batch_no": batch_no,
                        "qty": qty,
                        "warehouse": pr_item.warehouse,
                    })

                sabb.insert(ignore_permissions=True)
                pr_item.serial_and_batch_bundle = sabb.name
                pr_item.use_serial_batch_fields = 0

            pr.save()

            for pr_item in pr.items:
                if pr_item.serial_and_batch_bundle:
                    frappe.db.set_value(
                        "Serial and Batch Bundle",
                        pr_item.serial_and_batch_bundle,
                        {
                            "voucher_no": pr.name,
                            "voucher_detail_no": pr_item.name,
                            "is_cancelled": 0,
                        },
                    )

        if submit:
            pr.submit()

    except Exception:
        for batch_name in created_batches:
            try:
                frappe.delete_doc("Batch", batch_name, ignore_permissions=True, force=1)
            except Exception:
                pass
        frappe.log_error(frappe.get_traceback(), "create_rm_purchase_receipt failed")
        raise

    return {"name": pr.name, "docstatus": pr.docstatus}


@frappe.whitelist()
def create_rm_work_order(item_code, qty, bom_no=None, fg_warehouse=None):
    """Create a standalone Work Order (no Sales Order link) for manufacturing RM."""
    item_doc = frappe.get_cached_doc("Item", item_code)

    if not bom_no:
        bom_no = item_doc.default_bom
    if not bom_no:
        bom_no = frappe.db.get_value(
            "BOM",
            {"item": item_code, "is_active": 1, "is_default": 1},
            "name",
        )
    if not bom_no:
        frappe.throw(_("No active BOM found for item {0}").format(item_code))

    company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
    if not fg_warehouse:
        fg_warehouse = frappe.boot.kniterp_settings.get("default_fg_warehouse") if hasattr(frappe.boot, "kniterp_settings") else None
        if not fg_warehouse:
            fg_warehouse = frappe.db.get_value(
                "Warehouse",
                {"company": company, "is_group": 0, "warehouse_name": ["like", "%Stores%"]},
                "name",
            ) or frappe.db.get_single_value("Manufacturing Settings", "default_fg_warehouse")

    wo = frappe.new_doc("Work Order")
    wo.production_item = item_code
    wo.bom_no = bom_no
    wo.qty = flt(qty, 3)
    wo.company = company
    wo.fg_warehouse = fg_warehouse
    wo.description = item_doc.description or item_doc.item_name

    wo.get_items_and_operations_from_bom()
    wo.insert()

    frappe.msgprint(_(
        "Work Order <a href='/app/work-order/{0}'>{0}</a> created for {1} ({2})"
    ).format(wo.name, item_code, flt(qty, 3)))

    return {
        "name": wo.name,
        "status": wo.status,
        "production_item": wo.production_item,
    }


def _compute_jwo_status(row):
    """Derive a human-friendly status from PO data."""
    po_status = row.get("po_status", "")
    per_received = flt(row.get("per_received", 0))

    if po_status in ("Completed", "Closed"):
        return "Completed"

    if per_received >= 100:
        return "Completed"

    if per_received > 0:
        return "Partially Received"

    # Check if material has been sent
    sco_name = row.get("sco_name")
    if sco_name:
        has_sent = frappe.db.exists("Stock Entry", {
            "subcontracting_order": sco_name,
            "purpose": "Send to Subcontractor",
            "docstatus": 1,
        })
        if has_sent:
            return "Material Sent"

    return "Pending Material"
