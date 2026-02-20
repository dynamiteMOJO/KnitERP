"""
Custom override for Job Card to fix the make_subcontracting_po method.

This fixes the issue where source.finished_good is None but should use source.production_item instead.
"""

import logging
import frappe
from frappe.model.mapper import get_mapped_doc
from erpnext.subcontracting.doctype.subcontracting_bom.subcontracting_bom import (
    get_subcontracting_boms_for_finished_goods,
)
from frappe.utils import flt
from frappe.query_builder.functions import Sum
import os
from kniterp.api.access_control import require_production_write_access

from erpnext.manufacturing.doctype.job_card.job_card import JobCard

logger = logging.getLogger("kniterp_sfg_debug")

# Configure file handler for the logger
def setup_logger():
    """Setup file handler for kniterp_sfg_debug logger"""
    try:
        # Get the logs directory - this is relative to where Frappe is running
        log_dir = os.path.join(os.getcwd(), "logs")
        if not os.path.exists(log_dir):
            log_dir = "/workspace/development/frappe-bench/logs"
        
        log_file = os.path.join(log_dir, "kniterp_sfg_debug.txt")
        
        # Create file handler
        handler = logging.FileHandler(log_file)
        handler.setLevel(logging.DEBUG)
        
        # Create formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        # Add handler to logger
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    except Exception as e:
        pass  # Silently fail if logger setup fails

# Setup logger on module import
setup_logger()


@frappe.whitelist()
def make_subcontracting_po(source_name, target_doc=None):
    """
    Fixed version of make_subcontracting_po that uses production_item instead of finished_good.
    """
    require_production_write_access("create subcontracting purchase orders from job cards")

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



def set_job_card_qty_from_planned_qty(doc, method=None):
    """
    Set Job Card for_quantity from Work Order Operation.planned_qty
    """

    try:
        if not doc.work_order or not doc.operation:
            return

        wo_op = frappe.db.get_value(
            "Work Order Operation",
            {
                "parent": doc.work_order,
                "operation": doc.operation
            },
            ["name", "planned_qty"],
            as_dict=True
        )

        if not wo_op:
            logger.warning(
                f"[JC {doc.name}] No Work Order Operation found "
                f"(WO={doc.work_order}, OP={doc.operation})"
            )
            return

        if not wo_op.planned_qty:
            logger.warning(
                f"[JC {doc.name}] planned_qty missing for operation "
                f"{doc.operation} → keeping default qty={doc.for_quantity}"
            )
            return

        precision = frappe.get_precision(
            "Job Card", "for_quantity"
        ) or 3

        doc.for_quantity = flt(wo_op.planned_qty, precision)

        logger.info(
            f"[JC {doc.name}] Set for_quantity={doc.for_quantity} "
            f"from WO Operation planned_qty"
        )

    except Exception:
        logger.error(frappe.get_traceback())
        frappe.log_error(
            frappe.get_traceback(),
            "KNITERP SFG – Job Card planned_qty wiring failed"
        )


class CustomJobCard(JobCard):

    def set_items_from_work_order(self):
        if not self.work_order or not self.operation:
            return

        wo = frappe.get_doc("Work Order", self.work_order)

        # clear correctly
        self.set("items", [])

        for row in wo.required_items:
            if row.operation != self.operation:
                continue

            self.append("items", {
                "item_code": row.item_code,
                "source_warehouse": row.source_warehouse,
                "required_qty": row.required_qty,
                "uom": row.stock_uom
            })

        frappe.logger().info({
            "job_card": self.name,
            "operation": self.operation,
            "items_added": len(self.items)
        })

    def set_status(self, update_status=False):
        """
        Override ERPNext's set_status to prevent auto-completion based on quantity.
        
        This maintains all standard status logic EXCEPT the auto-completion when
        manufactured_qty >= for_quantity. Users must manually complete via Production Wizard.
        """
        # Use ERPNext's standard status mapping
        self.status = {0: "Open", 1: "Submitted", 2: "Cancelled"}[self.docstatus or 0]
        
        # Standard ERPNext logic for finished_good operations
        if self.finished_good and self.docstatus == 1:
            # REMOVED: Auto-completion logic (if self.manufactured_qty >= self.for_quantity)
            # Only set to Work In Progress if there's any progress
            if self.transferred_qty > 0 or self.skip_material_transfer:
                self.status = "Work In Progress"
        
        # Standard ERPNext logic for draft with time logs
        if self.docstatus == 0 and self.time_logs:
            self.status = "Work In Progress"
        
        # Standard ERPNext logic for non-SFG operations
        if not self.track_semi_finished_goods and self.docstatus < 2:
            if flt(self.for_quantity) <= flt(self.transferred_qty):
                self.status = "Material Transferred"
            
            if self.time_logs:
                self.status = "Work In Progress"
            
            # REMOVED: Auto-completion logic for total_completed_qty
            # Users must manually complete via Production Wizard
        
        # Standard ERPNext logic for paused jobs
        if self.is_paused:
            self.status = "On Hold"
        
        # Write to database if requested
        if update_status:
            self.db_set("status", self.status)
        
        # Update workstation status
        if self.workstation:
            self.update_workstation_status()

    def set_manufactured_qty(self):
        """
        Override ERPNext's standard set_manufactured_qty to use our custom set_status.
        
        This calculates manufactured_qty correctly and updates the status in the database,
        but won't auto-complete because our set_status() override removes that logic.
        """
        table_name = "Stock Entry"
        if self.is_subcontracted:
            table_name = "Subcontracting Receipt Item"

        table = frappe.qb.DocType(table_name)
        query = frappe.qb.from_(table).where((table.job_card == self.name) & (table.docstatus == 1))

        if self.is_subcontracted:
            query = query.select(Sum(table.qty))
        else:
            query = query.select(Sum(table.fg_completed_qty))
            query = query.where(table.purpose == "Manufacture")

        qty = query.run()[0][0] or 0.0
        self.manufactured_qty = flt(qty)
        self.db_set("manufactured_qty", self.manufactured_qty)

        self.update_semi_finished_good_details()
        
        # Call our custom set_status which doesn't auto-complete
        # Use update_status=True so database stays in sync (needed for cancellations)
        self.set_status(update_status=True)
        
        frappe.logger().info({
            "job_card": self.name,
            "is_subcontracted": self.is_subcontracted,
            "manufactured_qty": self.manufactured_qty,
            "for_quantity": self.for_quantity,
            "status": self.status,
            "auto_complete_prevented": True
        })



    def is_final_fg_operation(self):
        if not self.work_order or not self.operation:
            return False

        wo = frappe.get_doc("Work Order", self.work_order)

        for op in wo.operations:
            if op.operation == self.operation and op.bom == wo.bom_no:
                return True

        return False

    def validate(self):
        super().validate()

        if self.is_subcontracted and self.is_final_fg_operation():
            if not self.items:
                self.set_items_from_work_order()

    def validate_time_logs(self):
        if self.is_subcontracted:
            frappe.logger().info({
                "job_card": self.name,
                "skip_time_logs": True
            })
            return

        super().validate_time_logs()

    def validate_transfer_qty(self):
        # ✅ Subcontracted operations do NOT require WIP transfer
        if self.is_subcontracted:
            frappe.logger().info({
                "job_card": self.name,
                "skip_transfer_validation": True
            })
            return

        super().validate_transfer_qty()

    def validate_job_card(self):
        # ✅ Subcontracted job cards do NOT require time logs
        if self.is_subcontracted:
            frappe.logger().info({
                "job_card": self.name,
                "skip_validate_job_card": True
            })
            return

        super().validate_job_card()

    @frappe.whitelist()
    def make_stock_entry_for_semi_fg_item(self, auto_submit=False):
        """
        Override to use total_completed_qty (from time logs) instead of for_quantity.
        This allows overproduction quantities entered via the Production Wizard
        to be correctly reflected in the manufactured Stock Entry.
        
        Also scales raw material consumption proportionally to the actual manufactured qty.
        """
        require_production_write_access("create semi-finished stock entries")

        from erpnext.stock.doctype.stock_entry_type.stock_entry_type import ManufactureEntry
        from erpnext.manufacturing.doctype.bom.bom import add_additional_cost

        # Calculate qty to manufacture based on time logs (overproduction support)
        actual_qty_to_manufacture = flt(max(
            flt(self.total_completed_qty), 
            flt(self.for_quantity)
        ) - flt(self.manufactured_qty), 3)
        
        if actual_qty_to_manufacture <= 0:
            frappe.msgprint(
                frappe._("No quantity to manufacture. Already manufactured: {0}").format(
                    self.manufactured_qty
                )
            )
            return None

        logger.info(
            f"[JC {self.name}] make_stock_entry_for_semi_fg_item: "
            f"for_quantity={self.for_quantity}, total_completed_qty={self.total_completed_qty}, "
            f"manufactured_qty={self.manufactured_qty}, qty_to_manufacture={actual_qty_to_manufacture}"
        )

        ste = ManufactureEntry(
            {
                "for_quantity": actual_qty_to_manufacture,
                "job_card": self.name,
                "skip_material_transfer": self.skip_material_transfer,
                "backflush_from_wip_warehouse": self.backflush_from_wip_warehouse,
                "work_order": self.work_order,
                "purpose": "Manufacture",
                "production_item": self.finished_good,
                "company": self.company,
                "wip_warehouse": self.wip_warehouse,
                "fg_warehouse": self.target_warehouse,
                "bom_no": self.semi_fg_bom,
                "project": frappe.db.get_value("Work Order", self.work_order, "project"),
            }
        )

        ste.make_stock_entry()
        ste.stock_entry.flags.ignore_mandatory = True
        
        # FIX: Recalculate raw material quantities based on actual manufactured qty
        # Standard ManufactureEntry might legally return lower quantities if based on Job Card items
        # We need to scale them up proportionally if overpricing occurred
        if self.semi_fg_bom:
            bom_doc = frappe.get_cached_doc("BOM", self.semi_fg_bom)
            bom_qty = flt(bom_doc.quantity) or 1.0
            
            # Ratio: How much we are making vs BOM batch size
            # If BOM is for 100kg and we make 320kg, ratio is 3.2
            ratio = actual_qty_to_manufacture / bom_qty
            
            for item in ste.stock_entry.items:
                # Skip the finished good itself and scrap items
                if item.is_finished_item or item.is_scrap_item:
                    continue
                    
                # Find this item in BOM to get standard qty
                bom_item_qty = 0
                for bi in bom_doc.items:
                    if bi.item_code == item.item_code:
                        bom_item_qty = flt(bi.qty)
                        break
                
                if bom_item_qty > 0:
                    new_qty = flt(bom_item_qty * ratio, 3)
                    if abs(flt(item.qty) - new_qty) > 0.001:
                        logger.info(
                            f"[JC {self.name}] Updating RM {item.item_code} qty: {item.qty} -> {new_qty} (Ratio: {ratio})"
                        )
                        item.qty = new_qty

        wo_doc = frappe.get_doc("Work Order", self.work_order)
        add_additional_cost(ste.stock_entry, wo_doc, self)

        ste.stock_entry.set_scrap_items()
        for row in ste.stock_entry.items:
            if row.is_scrap_item and not row.t_warehouse:
                row.t_warehouse = self.target_warehouse

        if auto_submit:
            ste.stock_entry.submit()
        else:
            ste.stock_entry.save()

        frappe.msgprint(
            frappe._("Stock Entry {0} has been created for {1} qty").format(
                frappe.utils.get_link_to_form("Stock Entry", ste.stock_entry.name),
                actual_qty_to_manufacture
            )
        )

        return ste.stock_entry.as_dict()

    def on_submit(self):
        super().on_submit()
        
        # Cascade over-production to subsequent operations
        if self.total_completed_qty > self.for_quantity and self.work_order:
            self.update_subsequent_operations()

    def update_subsequent_operations(self):
        """
        If this operation produced more than planned, update the planned qty 
        of subsequent operations in the same Work Order proportionally.
        """
        try:
            # 1. Calculate Ratio
            # Example: Planned 316.2, Produced 320. Ratio = 1.012
            if not self.for_quantity or self.for_quantity == 0:
                return
                
            ratio = flt(self.total_completed_qty) / flt(self.for_quantity)
            if ratio <= 1.0:
                return

            # 2. Get current operation's sequence/index
            # We need to find operations that come AFTER this one
            wo = frappe.get_doc("Work Order", self.work_order)
            
            current_op_idx = -1
            for i, op in enumerate(wo.operations):
                if op.operation == self.operation:
                    current_op_idx = i
                    break
            
            if current_op_idx == -1 or current_op_idx == len(wo.operations) - 1:
                # Operation not found or it's the last operation
                return

            # 3. Find subsequent operations
            subsequent_ops = []
            for i in range(current_op_idx + 1, len(wo.operations)):
                subsequent_ops.append(wo.operations[i].operation)
            
            if not subsequent_ops:
                return

            logger.info(
                f"[JC {self.name}] Over-production detected (Ratio: {ratio}). "
                f"Updating subsequent ops: {subsequent_ops}"
            )

            # 4. Find and Update Open Job Cards for these operations
            job_cards = frappe.get_all(
                "Job Card",
                filters={
                    "work_order": self.work_order,
                    "operation": ["in", subsequent_ops],
                    "docstatus": 0  # Only update Draft/Open job cards
                },
                fields=["name", "operation", "for_quantity"]
            )
            
            for jc in job_cards:
                new_qty = flt(jc.for_quantity) * ratio
                
                frappe.db.set_value("Job Card", jc.name, "for_quantity", new_qty)
                
                # Add a comment to the Job Card
                msg = _("Planned quantity updated from {0} to {1} based on over-production in previous operation {2}").format(
                    flt(jc.for_quantity, 2), flt(new_qty, 2), self.operation
                )
                frappe.get_doc("Job Card", jc.name).add_comment("Info", msg)
                
                logger.info(f"[JC {self.name}] Updated {jc.name} ({jc.operation}): {jc.for_quantity} -> {new_qty}")
                
            frappe.msgprint(
                _("Updated planned quantities for {0} subsequent Job Cards due to over-production.").format(len(job_cards)),
                alert=True
            )

        except Exception as e:
            logger.error(f"Error updating subsequent operations: {str(e)}")
            # Don't block submission if this optional update fails
