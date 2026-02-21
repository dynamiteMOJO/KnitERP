import frappe
from kniterp.api.access_control import require_production_write_access

@frappe.whitelist()
def get_subcontract_po_items(sales_order):
    so = frappe.get_doc("Sales Order", sales_order)

    rows = []

    for row in so.items:
        if not row.fg_item:
            frappe.throw(
                f"Finished Good not selected for row {row.idx}"
            )

        rows.append({
            "so_item": row.name,
            "service_item": row.item_code,
            "service_item_name": row.item_name,
            "service_qty": row.qty,
            "fg_item": row.fg_item,
            "fg_qty": row.fg_item_qty,
            "delivery_date": row.delivery_date,
            "supplier_warehouse": "Job Work Outward - O"
        })

    return rows



@frappe.whitelist()
def make_subcontract_purchase_order(sales_order, supplier, items):
    require_production_write_access("create subcontract purchase orders")
    items = frappe.parse_json(items)

    po = frappe.new_doc("Purchase Order")
    po.supplier = supplier
    po.is_subcontracted = 1
    po.company = frappe.get_doc("Sales Order", sales_order).company
    po.schedule_date = max(i["delivery_date"] for i in items)
    po.supplier_warehouse = "Job Work Outward - O"

    po.set_missing_values()

    for row in items:
        po.append("items", {
            "item_code": row["service_item"],
            "item_name": row["service_item_name"],
            "qty": row["service_qty"],
            "fg_item": row["fg_item"],
            "fg_item_qty": row["fg_qty"],
            "schedule_date": row["delivery_date"],
            "sales_order": sales_order
        })

    po.insert()

    # Copy transaction parameters from SO Items to PO Items (per-item via JSON field)
    po_doc = frappe.get_doc("Purchase Order", po.name)
    changed = False
    for idx, row in enumerate(items):
        so_item_name = row.get("so_item")
        if not so_item_name:
            continue
        if idx < len(po_doc.items):
            so_item_doc = frappe.get_doc("Sales Order Item", so_item_name)
            params_json = so_item_doc.custom_transaction_params_json or '[]'
            if params_json and params_json != '[]':
                po_doc.items[idx].custom_transaction_params_json = params_json
                changed = True
    if changed:
        po_doc.save(ignore_permissions=True)

    return po.name
