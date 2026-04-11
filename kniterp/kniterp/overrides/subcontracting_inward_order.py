
import frappe
from frappe.utils import flt
from erpnext.subcontracting.doctype.subcontracting_inward_order.subcontracting_inward_order import SubcontractingInwardOrder

class CustomSubcontractingInwardOrder(SubcontractingInwardOrder):
    def update_status(self, status=None, update_modified=True):
        """
        Override to guard against ZeroDivisionError when no CP items or FG items exist yet
        (ERPNext does not guard total_to_be_received or total_to_be_produced against zero).
        """
        if self.status == "Closed" and self.status != status:
            from erpnext.controllers.status_updater import check_on_hold_or_closed_status
            check_on_hold_or_closed_status("Sales Order", self.sales_order)

        total_to_be_received = total_received = total_rm_returned = 0
        for rm in self.get("received_items"):
            if rm.get("is_customer_provided_item"):
                total_to_be_received += flt(rm.required_qty)
                total_received += flt(rm.received_qty)
                total_rm_returned += flt(rm.returned_qty)

        total_to_be_produced = total_produced = total_process_loss = total_delivered = total_fg_returned = 0
        for item in self.get("items"):
            total_to_be_produced += flt(item.qty)
            total_produced += flt(item.produced_qty)
            total_process_loss += flt(item.process_loss_qty)
            total_delivered += flt(item.delivered_qty)
            total_fg_returned += flt(item.returned_qty)

        per_raw_material_received = flt(total_received / total_to_be_received * 100, 2) if total_to_be_received else 0
        per_raw_material_returned = flt(total_rm_returned / total_received * 100, 2) if total_received else 0
        per_produced = flt(total_produced / total_to_be_produced * 100, 2) if total_to_be_produced else 0
        per_process_loss = flt(total_process_loss / total_produced * 100, 2) if total_produced else 0
        per_delivered = flt(total_delivered / total_to_be_produced * 100, 2) if total_to_be_produced else 0
        per_returned = flt(total_fg_returned / total_delivered * 100, 2) if total_delivered else 0

        self.db_set("per_raw_material_received", per_raw_material_received, update_modified=update_modified)
        self.db_set("per_raw_material_returned", per_raw_material_returned, update_modified=update_modified)
        self.db_set("per_produced", per_produced, update_modified=update_modified)
        self.db_set("per_process_loss", per_process_loss, update_modified=update_modified)
        self.db_set("per_delivered", per_delivered, update_modified=update_modified)
        self.db_set("per_returned", per_returned, update_modified=update_modified)

        if self.docstatus >= 1 and not status:
            if self.docstatus == 1:
                if self.status == "Draft":
                    status = "Open"
                elif self.per_returned == 100:
                    status = "Returned"
                elif self.per_delivered == 100:
                    status = "Delivered"
                elif self.per_produced == 100:
                    status = "Produced"
                elif self.per_raw_material_received > 0:
                    status = "Ongoing"
                else:
                    status = "Open"
            elif self.docstatus == 2:
                status = "Cancelled"

        if status and self.status != status:
            self.db_set("status", status, update_modified=update_modified)

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
                    ratio = flt(item.required_qty) / flt(d.qty)

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
        """Create a Delivery Note to dispatch FG back to the customer.

        Uses the Production Wizard API so the logic stays in one place.
        Returns the DN name (or as_dict for form sync when called via run_doc_method).
        """
        from kniterp.api.production_wizard import create_scio_delivery_note

        dn_name = create_scio_delivery_note(self.name)
        dn = frappe.get_doc("Delivery Note", dn_name)

        if target_doc is not None:
            return dn
        return dn.as_dict()
