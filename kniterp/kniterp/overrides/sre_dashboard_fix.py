"""
SRE Dashboard Compatibility Patch (kniterp P1.1b)
==================================================
WHY THIS EXISTS:
  ERPNext's stock_reservation_entry helpers (get_sre_reserved_qty_for_items_and_warehouses
  and get_sre_reserved_qty_details_for_voucher) compute net reserved qty by subtracting
  only delivered_qty. They do NOT subtract consumed_qty, which overstates reserved stock
  in the item dashboard, SO reservation checks, and planning views after partial consumption.

GUARD:
  At import time we inspect the upstream source. If it already contains consumed_qty logic,
  we skip the patch entirely and log an info message so the patch can be removed safely.
  Otherwise we apply the patch and log a single warning explaining the reason.

SAFE TO REMOVE WHEN:
  The upstream ERPNext functions include consumed_qty in their aggregate queries.
  At that point remove this file and the import in __init__.py.
"""
import inspect

import frappe
from pypika import functions as fn
from erpnext.stock.doctype.stock_reservation_entry import stock_reservation_entry

_logger = frappe.logger("kniterp")


# ---------------------------------------------------------------------------
# Patched helpers (consumed-qty aware)
# ---------------------------------------------------------------------------

def _get_sre_reserved_qty_for_items_and_warehouses(
    item_code_list: list, warehouse_list: list | None = None
) -> dict:
    """Returns a dict like {("item_code", "warehouse"): reserved_qty, ...}.

    Net reserved = reserved_qty - delivered_qty - consumed_qty
    Only includes entries that still have unfulfilled reservation.
    """
    if not item_code_list:
        return {}

    sre = frappe.qb.DocType("Stock Reservation Entry")
    query = (
        frappe.qb.from_(sre)
        .select(
            sre.item_code,
            sre.warehouse,
            fn.Sum(sre.reserved_qty - sre.delivered_qty - sre.consumed_qty).as_("reserved_qty"),
        )
        .where(
            (sre.docstatus == 1)
            & sre.item_code.isin(item_code_list)
            # Only rows with a genuine outstanding reservation
            & ((sre.delivered_qty + sre.consumed_qty) < sre.reserved_qty)
            & (sre.status.notin(["Closed", "Delivered"]))
        )
        .groupby(sre.item_code, sre.warehouse)
    )

    if warehouse_list:
        query = query.where(sre.warehouse.isin(warehouse_list))

    data = query.run(as_dict=True)
    return {(d["item_code"], d["warehouse"]): d["reserved_qty"] for d in data} if data else {}


def _get_sre_reserved_qty_details_for_voucher(voucher_type: str, voucher_no: str) -> dict:
    """Returns a dict like {"voucher_detail_no": reserved_qty, ...}.

    Net reserved = reserved_qty - delivered_qty - consumed_qty
    Only includes entries that still have unfulfilled reservation.
    """
    sre = frappe.qb.DocType("Stock Reservation Entry")
    data = (
        frappe.qb.from_(sre)
        .select(
            sre.voucher_detail_no,
            (fn.Sum(sre.reserved_qty) - fn.Sum(sre.delivered_qty) - fn.Sum(sre.consumed_qty)).as_("reserved_qty"),
        )
        .where(
            (sre.docstatus == 1)
            & (sre.voucher_type == voucher_type)
            & (sre.voucher_no == voucher_no)
            # Only rows with a genuine outstanding reservation
            & ((sre.delivered_qty + sre.consumed_qty) < sre.reserved_qty)
            & (sre.status.notin(["Closed", "Delivered"]))
        )
        .groupby(sre.voucher_detail_no)
    ).run(as_dict=True)

    return {d.voucher_detail_no: d.reserved_qty for d in data} if data else {}


# ---------------------------------------------------------------------------
# Version / signature guard — apply patch only when upstream lacks it
# ---------------------------------------------------------------------------

def _upstream_is_consumed_aware() -> bool:
    """Return True if upstream already accounts for consumed_qty in these helpers."""
    try:
        src_items = inspect.getsource(
            stock_reservation_entry.get_sre_reserved_qty_for_items_and_warehouses
        )
        src_voucher = inspect.getsource(
            stock_reservation_entry.get_sre_reserved_qty_details_for_voucher
        )
        return "consumed_qty" in src_items and "consumed_qty" in src_voucher
    except Exception:
        # If we can't inspect, be conservative and apply the patch
        return False


if _upstream_is_consumed_aware():
    _logger.info(
        "[kniterp SRE patch] Upstream get_sre_reserved_qty_* already includes consumed_qty. "
        "Patch skipped. You can safely remove sre_dashboard_fix.py."
    )
else:
    _logger.warning(
        "[kniterp SRE patch] Applying consumed_qty compensation patch (ERPNext v16). "
        "Upstream functions at stock_reservation_entry.py do not subtract consumed_qty, "
        "which overstates reserved stock after partial consumption. "
        "Remove this patch once upstream is fixed."
    )
    stock_reservation_entry.get_sre_reserved_qty_for_items_and_warehouses = (
        _get_sre_reserved_qty_for_items_and_warehouses
    )
    stock_reservation_entry.get_sre_reserved_qty_details_for_voucher = (
        _get_sre_reserved_qty_details_for_voucher
    )
