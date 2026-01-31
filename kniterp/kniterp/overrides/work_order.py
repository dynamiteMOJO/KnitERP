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
                    flt(doc.qty)
                )
                continue

            # Final FG operation
            if bom_op.is_final_finished_good:
                wo_op.planned_qty = flt(doc.qty)
                logger.info(
                    f"[WO {doc.name}] Operation '{wo_op.operation}' "
                    f"is final FG → planned_qty={doc.qty}"
                )
                continue

            
            planned_qty = (
                flt(doc.qty)
                * flt(bom_op.finished_good_qty)
                / flt(bom.quantity)
            )


            wo_op.planned_qty = flt(planned_qty)

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
