"""
Stock Reservation Service (kniterp P1.2)
=========================================
Single authoritative location for all SRE/Bin mutation logic related to
SCIO manufacturing production flows. Called exclusively by production_wizard.py
endpoints — never inline from multiple sites.

Public API
----------
  sync_scio_sre_before_manufacture(wo_doc)
  ensure_scio_fg_sre(wo_doc, se_doc)
  release_scio_fg_sres_on_revert(wo_doc, se_doc)
  recalculate_bin_reserved_for_direct_consumption(wo_doc, se_doc, mode="complete")
"""

import frappe
from frappe.utils import flt

_logger = frappe.logger("kniterp.sre_service")


# ---------------------------------------------------------------------------
# Helper: pre/post logging wrapper for Bin mutations
# ---------------------------------------------------------------------------

def _log_bin_change(item_code, warehouse, pre_val, post_val, reason):
    _logger.info({
        "event": "bin_reserved_qty_for_production_changed",
        "item_code": item_code,
        "warehouse": warehouse,
        "before": pre_val,
        "after": post_val,
        "reason": reason,
    })


# ---------------------------------------------------------------------------
# 1. Sync SCIO SREs into WO before manufacturing (incremental RM batches)
# ---------------------------------------------------------------------------

def sync_scio_sre_before_manufacture(wo_doc):
    """
    Transfer any new SCIO SREs to the Work Order before consuming stock.

    When a second batch of RM is received against a SCIO, the SCIO creates a
    new SRE. Since the WO is already submitted, the standard transfer never
    happens automatically. This forces the sync before each manufacture entry.

    Only applies to SCIO WOs with reserve_stock enabled.
    """
    if not (wo_doc.subcontracting_inward_order and wo_doc.reserve_stock):
        return

    wo_doc._action = "update_after_submit"
    wo_doc.update_stock_reservation()
    wo_doc.reload()
    _logger.info({
        "event": "scio_sre_synced_before_manufacture",
        "work_order": wo_doc.name,
        "scio": wo_doc.subcontracting_inward_order,
    })


# ---------------------------------------------------------------------------
# 2. Ensure FG SRE exists after manufacture (SCIO WOs)
# ---------------------------------------------------------------------------

def ensure_scio_fg_sre(wo_doc, se_doc):
    """
    Create a FG Stock Reservation Entry for the produced quantity after a
    Manufacture Stock Entry is submitted, if one doesn't already exist.

    ERPNext v15/v16 doesn't auto-create FG SREs for subsequent manufacture
    batches in SCIO contexts. This ensures the produced FG is reserved against
    the SCIO for downstream delivery.
    """
    if not wo_doc.subcontracting_inward_order:
        return

    for row in se_doc.items:
        if not (row.is_finished_item and not row.is_scrap_item):
            continue

        existing_sre = frappe.db.get_value("Stock Reservation Entry", {
            "item_code": row.item_code,
            "warehouse": row.t_warehouse,
            "voucher_type": "Subcontracting Inward Order",
            "voucher_no": wo_doc.subcontracting_inward_order,
            "from_voucher_type": "Stock Entry",
            "from_voucher_no": se_doc.name,
            "from_voucher_detail_no": row.name,
            "docstatus": 1
        })

        if existing_sre:
            _logger.info({
                "event": "fg_sre_already_exists",
                "sre": existing_sre,
                "stock_entry": se_doc.name,
            })
            continue

        scio_item_qty = frappe.db.get_value(
            "Subcontracting Inward Order Item",
            wo_doc.subcontracting_inward_order_item,
            "qty"
        )
        available_qty = (
            frappe.db.get_value(
                "Bin",
                {"item_code": row.item_code, "warehouse": row.t_warehouse},
                "actual_qty"
            ) or 0
        )

        sre = frappe.new_doc("Stock Reservation Entry")
        sre.item_code = row.item_code
        sre.warehouse = row.t_warehouse
        sre.voucher_type = "Subcontracting Inward Order"
        sre.voucher_no = wo_doc.subcontracting_inward_order
        sre.voucher_detail_no = wo_doc.subcontracting_inward_order_item
        sre.available_qty = flt(available_qty)
        sre.voucher_qty = flt(scio_item_qty)
        sre.reserved_qty = flt(row.qty)
        sre.company = se_doc.company
        sre.stock_uom = row.stock_uom
        sre.from_voucher_type = "Stock Entry"
        sre.from_voucher_no = se_doc.name
        sre.from_voucher_detail_no = row.name

        sre.insert()
        sre.submit()

        _logger.info({
            "event": "fg_sre_created",
            "sre": sre.name,
            "item_code": row.item_code,
            "reserved_qty": row.qty,
            "voucher_no": wo_doc.subcontracting_inward_order,
            "stock_entry": se_doc.name,
        })


# ---------------------------------------------------------------------------
# 3. Release SCIO FG SREs on revert
# ---------------------------------------------------------------------------

def release_scio_fg_sres_on_revert(wo_doc, se_doc):
    """
    Cancel FG SREs linked to a Manufacture Stock Entry before cancelling it.

    Frappe's link validation blocks cancelling the SE while linked SREs exist,
    so they must be cleared first. Also reduces any stale blocking SREs for the
    SCIO item/warehouse so the stock removal can proceed.
    """
    if not wo_doc.subcontracting_inward_order:
        return

    # Step 1: cancel SREs that directly reference this SE as from_voucher
    linked_sres = frappe.get_all(
        "Stock Reservation Entry",
        filters={
            "from_voucher_type": "Stock Entry",
            "from_voucher_no": se_doc.name,
            "docstatus": 1,
        },
        pluck="name"
    )
    for sre_name in linked_sres:
        sre_doc = frappe.get_doc("Stock Reservation Entry", sre_name)
        sre_doc.cancel()
        _logger.info({
            "event": "fg_sre_cancelled",
            "sre": sre_name,
            "stock_entry": se_doc.name,
        })

    # Step 2: reduce any blocking SCIO-level SREs that are partially/fully reserved
    # (handles case where the direct SRE is already Delivered but stale SREs block SE cancel)
    qty_to_free = flt(se_doc.fg_completed_qty)
    fg_row = next(
        (r for r in se_doc.items if r.is_finished_item and not r.is_scrap_item), None
    )

    if not fg_row or qty_to_free <= 0:
        return

    blocking_sres = frappe.get_all(
        "Stock Reservation Entry",
        filters={
            "voucher_type": "Subcontracting Inward Order",
            "voucher_no": wo_doc.subcontracting_inward_order,
            "item_code": fg_row.item_code,
            "warehouse": fg_row.t_warehouse,
            "docstatus": 1,
            "status": ["in", ["Reserved", "Partially Delivered", "Partially Reserved"]],
        },
        fields=["name", "reserved_qty", "delivered_qty"],
        order_by="creation desc"
    )

    for s in blocking_sres:
        if qty_to_free <= 0:
            break

        current_reserved = flt(s.reserved_qty)
        current_delivered = flt(s.delivered_qty)
        net_reserved = current_reserved - current_delivered

        if net_reserved <= 0:
            continue

        reduce_by = min(net_reserved, qty_to_free)
        sre_doc = frappe.get_doc("Stock Reservation Entry", s.name)

        if current_delivered <= 0 and reduce_by >= current_reserved:
            sre_doc.cancel()
            _logger.info({
                "event": "blocking_sre_fully_cancelled",
                "sre": s.name,
                "reduced_by": reduce_by,
            })
        else:
            new_reserved = flt(current_reserved - reduce_by)
            sre_doc.db_set("reserved_qty", new_reserved)
            sre_doc.update_status()
            sre_doc.update_reserved_stock_in_bin()
            _logger.info({
                "event": "blocking_sre_reduced",
                "sre": s.name,
                "old_reserved": current_reserved,
                "new_reserved": new_reserved,
                "reduced_by": reduce_by,
            })

        qty_to_free -= reduce_by


# ---------------------------------------------------------------------------
# 4. Recalculate Bin reserved_qty_for_production (consumed-qty compensation)
# ---------------------------------------------------------------------------

def recalculate_bin_reserved_for_direct_consumption(wo_doc, se_doc, mode="complete"):
    """
    Recalculate Bin.reserved_qty_for_production for SCIO WOs with direct consumption
    (skip_transfer == 0 but JC skip_material_transfer == 1).

    ERPNext's standard recalc (update_reserved_qty_for_production) uses
    required_qty - transferred_qty, which doesn't account for consumed_qty in
    direct-consumption scenarios. We compensate manually until upstream fixes it.

    mode: "complete" — subtract consumed_qty after manufacture
          "revert"   — recalc only (cancel already reversed the SE)
    """
    if not (wo_doc.skip_transfer == 0 and wo_doc.subcontracting_inward_order):
        return

    from erpnext.stock.utils import get_bin

    for row in se_doc.items:
        if row.is_finished_item or row.is_scrap_item or not row.s_warehouse:
            continue

        stock_bin = get_bin(row.item_code, row.s_warehouse)
        pre_val = flt(stock_bin.reserved_qty_for_production)
        stock_bin.update_reserved_qty_for_production()

        if mode == "complete":
            # Standard recalc still uses required−transferred; subtract the consumed portion
            # that the standard formula missed for this WO item.
            wo_item = next(
                (d for d in wo_doc.required_items
                 if d.item_code == row.item_code and d.source_warehouse == row.s_warehouse),
                None
            )
            if wo_item and flt(wo_item.consumed_qty) > 0:
                adjusted = max(0, flt(stock_bin.reserved_qty_for_production) - flt(wo_item.consumed_qty))
                if adjusted != flt(stock_bin.reserved_qty_for_production):
                    stock_bin.db_set("reserved_qty_for_production", adjusted, update_modified=False)
                    stock_bin.reserved_qty_for_production = adjusted
                    stock_bin.set_projected_qty()
                    stock_bin.db_set("projected_qty", stock_bin.projected_qty, update_modified=False)

        post_val = flt(stock_bin.reserved_qty_for_production)
        if pre_val != post_val:
            _log_bin_change(
                row.item_code, row.s_warehouse, pre_val, post_val,
                f"direct_consumption_{mode}"
            )
