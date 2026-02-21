import logging
import os
import frappe
from frappe.utils import flt

logger = logging.getLogger("kniterp_sfg_debug")


def setup_logger():
    try:
        log_dir = os.path.join(os.getcwd(), "logs")
        if not os.path.exists(log_dir):
            log_dir = "/workspace/development/frappe-bench/logs"

        log_file = os.path.join(log_dir, "kniterp_sfg_debug.txt")

        handler = logging.FileHandler(log_file)
        handler.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)

        if not logger.handlers:
            logger.addHandler(handler)

        logger.setLevel(logging.DEBUG)
    except Exception:
        pass


setup_logger()


from erpnext.manufacturing.doctype.work_order.work_order import WorkOrder
from frappe import _
from frappe.utils import get_link_to_form


class CustomWorkOrder(WorkOrder):
    def validate_subcontracting_inward_order(self):
        if scio := self.subcontracting_inward_order:
            if self.source_warehouse != (
                rm_receipt_warehouse := frappe.get_cached_value(
                    "Subcontracting Inward Order",
                    scio,
                    "customer_warehouse",
                )
            ):
                frappe.throw(
                    _(
                        "Source Warehouse {0} must be same as Customer Warehouse {1} in the Subcontracting Inward Order."
                    ).format(
                        get_link_to_form("Warehouse", self.source_warehouse),
                        get_link_to_form("Warehouse", rm_receipt_warehouse),
                    )
                )

            if self.fg_warehouse != (
                delivery_warehouse := frappe.get_cached_value(
                    "Subcontracting Inward Order Item",
                    self.subcontracting_inward_order_item,
                    "delivery_warehouse",
                )
            ):
                frappe.throw(
                    _(
                        "Target Warehouse {0} must be same as Delivery Warehouse {1} in the Subcontracting Inward Order Item."
                    ).format(
                        get_link_to_form("Warehouse", self.fg_warehouse),
                        get_link_to_form(
                            "Warehouse",
                            delivery_warehouse,
                        ),
                    )
                )

            possible_customer_provided_items = frappe.get_all(
                "Subcontracting Inward Order Received Item",
                {
                    "reference_name": self.subcontracting_inward_order_item,
                    "is_customer_provided_item": 1,
                    "docstatus": 1,
                },
                ["rm_item_code", "received_qty", "returned_qty", "work_order_qty"],
            )
            item_codes = []
            for item in self.required_items:
                if item.is_customer_provided_item:
                    if item.source_warehouse != self.source_warehouse:
                        frappe.throw(
                            _(
                                "Row #{0}: Source Warehouse {1} for item {2} must be same as Source Warehouse {3} in the Work Order."
                            ).format(
                                item.idx,
                                get_link_to_form("Warehouse", item.source_warehouse),
                                get_link_to_form("Item", item.item_code),
                                get_link_to_form("Warehouse", self.source_warehouse),
                            )
                        )
                    elif item.item_code in item_codes:
                        frappe.throw(
                            _("Row #{0}: Customer Provided Item {1} cannot be added multiple times.").format(
                                item.idx,
                                get_link_to_form("Item", item.item_code),
                            )
                        )
                    else:
                        row = next(
                            (i for i in possible_customer_provided_items if i.rm_item_code == item.item_code),
                            None,
                        )
                        if row:
                            # kniterp FIX: Use flt(..., 3) or higher precision rounding to avoid tiny floating point errors
                            # from preventing WO submission when quantities match but have tiny diffs at 8+ decimals.
                            available_qty = flt(flt(row.received_qty, 3) - flt(row.returned_qty, 3) - flt(row.work_order_qty, 3), 3)
                            if flt(item.required_qty, 3) > flt(available_qty, 3):
                                frappe.msgprint(
                                    _(
                                        "Row #{0}: Customer Provided Item {1} has insufficient quantity in the Subcontracting Inward Order. Available quantity is {2}."
                                    ).format(
                                        item.idx,
                                        get_link_to_form("Item", item.item_code),
                                        frappe.bold(available_qty),
                                    ),
                                    indicator="orange",
                                    alert=True
                                )
                            item_codes.append(item.item_code)
                        else:
                            frappe.throw(
                                _(
                                    "Row #{0}: Customer Provided Item {1} does not exist in the Required Items table linked to the Subcontracting Inward Order."
                                ).format(
                                    item.idx,
                                    get_link_to_form("Item", item.item_code),
                                )
                            )
                elif frappe.get_cached_value("Warehouse", item.source_warehouse, "customer"):
                    frappe.throw(
                        _(
                            "Row #{0}: Source Warehouse {1} for item {2} cannot be a customer warehouse."
                        ).format(
                            item.idx,
                            get_link_to_form("Warehouse", item.source_warehouse),
                            get_link_to_form("Item", item.item_code),
                        )
                    )


def set_planned_qty_on_work_order(doc, method=None):
    """
    Compute and store planned_qty on Work Order Operation
    for Track Semi Finished Goods (ERPNext v16)
    """

    try:
        if not doc.track_semi_finished_goods or not doc.bom_no:
            return

        bom = frappe.get_doc("BOM", doc.bom_no)

        if not bom.quantity:
            logger.warning(
                f"[WO {doc.name}] BOM qty is zero, skipping planned_qty calculation"
            )
            return

        # Map BOM operations by operation name
        bom_ops = {
            op.operation: op for op in bom.operations
        }

        logger.info(
            f"[WO {doc.name}] Calculating planned_qty for operations "
            f"(WO qty={doc.qty}, BOM qty={bom.quantity})"
        )

        for wo_op in doc.operations:
            bom_op = bom_ops.get(wo_op.operation)

            if not bom_op:
                logger.warning(
                    f"[WO {doc.name}] Operation '{wo_op.operation}' "
                    f"not found in BOM, using WO qty"
                )
                frappe.db.set_value(
                    "Work Order Operation",
                    wo_op.name,
                    "planned_qty",
                    flt(doc.qty, 3)
                )
                continue

            # Final FG operation
            if bom_op.is_final_finished_good:
                wo_op.planned_qty = flt(doc.qty, 3)
                logger.info(
                    f"[WO {doc.name}] Operation '{wo_op.operation}' "
                    f"is final FG → planned_qty={doc.qty}"
                )
                continue

            
            planned_qty = flt(
                flt(doc.qty, 3)
                * flt(bom_op.finished_good_qty, 3)
                / flt(bom.quantity, 3),
                3
            )


            wo_op.planned_qty = flt(planned_qty, 3)

            # frappe.db.set_value(
            #     "Work Order Operation",
            #     wo_op.name,
            #     "planned_qty",
            #     planned_qty
            # )

            logger.info(
                f"[WO {doc.name}] Operation '{wo_op.operation}' "
                f"planned_qty={wo_op.planned_qty} (fg_qty={bom_op.finished_good_qty})"
            )

    except Exception:
        logger.error(frappe.get_traceback())
        frappe.log_error(
            frappe.get_traceback(),
            "KNITERP SFG – Work Order planned_qty failed"
        )
