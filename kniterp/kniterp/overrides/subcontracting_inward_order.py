
import frappe
from frappe.utils import flt
from frappe.model.mapper import get_mapped_doc
from erpnext.subcontracting.doctype.subcontracting_inward_order.subcontracting_inward_order import SubcontractingInwardOrder

class CustomSubcontractingInwardOrder(SubcontractingInwardOrder):
    def get_production_items(self):
        """
        OVERRIDE: Removed precision rounding on ratio calculation to prevent rounding errors
        that allow over-production (e.g. 247.036 vs 246.999).
        """
        item_list = []

        for d in self.items:
            if d.produced_qty >= d.qty:
                continue

            item_details = {
                "production_item": d.item_code,
                "use_multi_level_bom": d.include_exploded_items,
                "subcontracting_inward_order": self.name,
                "bom_no": d.bom,
                "stock_uom": d.stock_uom,
                "company": self.company,
                "project": frappe.get_cached_value("Sales Order", self.sales_order, "project"),
                "source_warehouse": self.customer_warehouse,
                "subcontracting_inward_order_item": d.name,
                "reserve_stock": 1,
                "fg_warehouse": d.delivery_warehouse,
            }

            # --- MODIFIED LOGIC START ---
            qty_list = []
            for item in self.get("received_items"):
                if item.reference_name == d.name and item.is_customer_provided_item and item.required_qty:
                    # FIX: Round ratio to 9 decimal places for intermediate precision, final qty to 3
                    ratio = flt(flt(item.required_qty, 3) / flt(d.qty, 3))

                    qty = flt(
                        (flt(item.received_qty, 3) - flt(item.returned_qty, 3) - flt(item.work_order_qty, 3)) / ratio,
                        3
                    )
                    qty_list.append(qty)
            
            if qty_list:
                qty = flt(min(qty_list), 3)
            else:
                # If no RMs, fallback to remaining qty
                qty = flt(flt(d.qty, 3) - flt(d.produced_qty, 3), 3)
            
            # --- MODIFIED LOGIC END ---

            qty = flt(min(
                int(qty) if frappe.get_cached_value("UOM", d.stock_uom, "must_be_whole_number") else qty,
                flt(d.qty, 3) - flt(d.produced_qty, 3),
            ), 3)

            item_details.update({"qty": qty, "max_producible_qty": qty})
            item_list.append(item_details)

        return item_list

    @frappe.whitelist()
    def make_subcontracting_delivery(self, target_doc=None):
        if target_doc and target_doc.get("items"):
            target_doc.items = []

        stock_entry = get_mapped_doc(
            "Subcontracting Inward Order",
            self.name,
            {
                "Subcontracting Inward Order": {
                    "doctype": "Stock Entry",
                    "validation": {
                        "docstatus": ["=", 1],
                    },
                },
            },
            target_doc,
            ignore_child_tables=True,
        )

        stock_entry.purpose = "Subcontracting Delivery"
        stock_entry.set_stock_entry_type()
        stock_entry.subcontracting_inward_order = self.name
        scio_details = []

        allow_over = frappe.get_single_value("Selling Settings", "allow_delivery_of_overproduced_qty")
        for fg_item in self.items:
            # FIX: Always subtract delivered_qty!
            produced_limit = flt(fg_item.produced_qty, 3)
            if not allow_over:
                produced_limit = flt(min(flt(fg_item.qty, 3), flt(fg_item.produced_qty, 3)), 3)
            
            qty = flt(produced_limit - flt(fg_item.delivered_qty, 3), 3)

            # Only add if there is pending quantity or if negative (return?)
            # Usually only positive qty is delivered here. 
            if qty <= 0:
                continue

            scio_details.append(fg_item.name)
            items_dict = {
                fg_item.item_code: {
                    "qty": qty,
                    "from_warehouse": fg_item.delivery_warehouse,
                    "stock_uom": fg_item.stock_uom,
                    "scio_detail": fg_item.name,
                    "is_finished_item": 1,
                }
            }

            stock_entry.add_to_stock_entry_detail(items_dict)

        # Copied logic for scrap items
        if (
            frappe.get_single_value("Selling Settings", "deliver_scrap_items")
            and self.scrap_items
            and scio_details
        ):
            scrap_items = [
                scrap_item for scrap_item in self.scrap_items if scrap_item.reference_name in scio_details
            ]
            for scrap_item in scrap_items:
                qty = flt(flt(scrap_item.produced_qty, 3) - flt(scrap_item.delivered_qty, 3), 3)
                if qty > 0:
                    items_dict = {
                        scrap_item.item_code: {
                            "qty": flt(flt(scrap_item.produced_qty, 3) - flt(scrap_item.delivered_qty, 3), 3),
                            "from_warehouse": scrap_item.warehouse,
                            "stock_uom": scrap_item.stock_uom,
                            "scio_detail": scrap_item.name,
                            "is_scrap_item": 1,
                        }
                    }

                    stock_entry.add_to_stock_entry_detail(items_dict)

        if target_doc:
            return stock_entry
        else:
            return stock_entry.as_dict()
