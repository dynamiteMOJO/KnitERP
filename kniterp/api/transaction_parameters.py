import frappe
import json

def sync_so_params(doc, method):
    """
    Sync parameters from the Sales Order Item's JSON field 
    to the SO Transaction Parameter standalone doctype for reporting.
    Runs on_update and on_update_after_submit of Sales Order.
    """
    for item in doc.items:
        # Delete existing standalone records for this item
        existing = frappe.get_all(
            "SO Transaction Parameter",
            filters={"sales_order_item": item.name},
            pluck="name"
        )
        for name in existing:
            frappe.delete_doc("SO Transaction Parameter", name, ignore_permissions=True)
            
        # Parse JSON and insert new standalone records
        params = json.loads(item.custom_transaction_params_json or '[]')
        for p in params:
            if p.get("parameter") and p.get("value"):
                frappe.get_doc({
                    "doctype": "SO Transaction Parameter",
                    "sales_order": doc.name,
                    "sales_order_item": item.name,
                    "item_code": item.item_code,
                    "parameter": p.get("parameter"),
                    "value": p.get("value")
                }).insert(ignore_permissions=True)

def sync_po_params(doc, method):
    """
    Sync parameters from the Purchase Order Item's JSON field 
    to the PO Transaction Parameter standalone doctype for reporting.
    Runs on_update and on_update_after_submit of Purchase Order.
    """
    for item in doc.items:
        # Delete existing standalone records for this item
        existing = frappe.get_all(
            "PO Transaction Parameter",
            filters={"purchase_order_item": item.name},
            pluck="name"
        )
        for name in existing:
            frappe.delete_doc("PO Transaction Parameter", name, ignore_permissions=True)
            
        # Parse JSON and insert new standalone records
        params = json.loads(item.custom_transaction_params_json or '[]')
        for p in params:
            if p.get("parameter") and p.get("value"):
                frappe.get_doc({
                    "doctype": "PO Transaction Parameter",
                    "purchase_order": doc.name,
                    "purchase_order_item": item.name,
                    "item_code": item.item_code,
                    "parameter": p.get("parameter"),
                    "value": p.get("value")
                }).insert(ignore_permissions=True)
