"""
Custom override for Job Card to fix the make_subcontracting_po method.

This fixes the issue where source.finished_good is None but should use source.production_item instead.
"""

import frappe
from frappe.model.mapper import get_mapped_doc
from erpnext.subcontracting.doctype.subcontracting_bom.subcontracting_bom import (
    get_subcontracting_boms_for_finished_goods,
)
from frappe.utils import flt


@frappe.whitelist()
def make_subcontracting_po(source_name, target_doc=None):
    """
    Fixed version of make_subcontracting_po that uses production_item instead of finished_good.
    """

    def set_missing_values(source, target):
        # Use production_item instead of finished_good
        fg_item = source.production_item or source.finished_good

        if not fg_item:
            frappe.throw(
                frappe._("Neither finished_good nor production_item is set in the Job Card {0}").format(
                    source.name
                )
            )

        _item_details = get_subcontracting_boms_for_finished_goods(fg_item)

        pending_qty = source.for_quantity - source.manufactured_qty
        service_item_qty = flt(_item_details.service_item_qty) or 1.0
        fg_item_qty = flt(_item_details.finished_good_qty) or 1.0

        target.is_subcontracted = 1
        target.supplier_warehouse = source.wip_warehouse
        target.append(
            "items",
            {
                "item_code": _item_details.service_item,
                "fg_item": fg_item,
                "uom": _item_details.service_item_uom,
                "stock_uom": _item_details.service_item_uom,
                "conversion_factor": _item_details.conversion_factor or 1,
                "item_name": _item_details.service_item,
                "qty": pending_qty * service_item_qty / fg_item_qty,
                "fg_item_qty": pending_qty,
                "job_card": source.name,
                "bom": source.semi_fg_bom,
                "warehouse": source.target_warehouse,
            },
        )

    doclist = get_mapped_doc(
        "Job Card",
        source_name,
        {
            "Job Card": {
                "doctype": "Purchase Order",
            },
        },
        target_doc,
        set_missing_values,
    )

    return doclist
