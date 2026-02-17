import frappe
from pypika import functions as fn
from erpnext.stock.doctype.stock_reservation_entry import stock_reservation_entry

# Patch for ERPNext failing to deduct consumed_qty in dashboard calculations
# This runtime patch fixes the "Reserved Stock" display issue.

def get_sre_reserved_qty_for_items_and_warehouses(
	item_code_list: list, warehouse_list: list | None = None
) -> dict:
	"""Returns a dict like {("item_code", "warehouse"): "reserved_qty", ... }."""

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
			& (sre.delivered_qty < sre.reserved_qty)
			& (sre.status.notin(["Closed", "Delivered"]))
		)
		.groupby(sre.item_code, sre.warehouse)
	)

	if warehouse_list:
		query = query.where(sre.warehouse.isin(warehouse_list))

	data = query.run(as_dict=True)

	return {(d["item_code"], d["warehouse"]): d["reserved_qty"] for d in data} if data else {}


def get_sre_reserved_qty_details_for_voucher(voucher_type: str, voucher_no: str) -> dict:
	"""Returns a dict like {"voucher_detail_no": "reserved_qty", ... }."""

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
			& (sre.delivered_qty < sre.reserved_qty)
			& (sre.status.notin(["Closed", "Delivered"]))
		)
		.groupby(sre.voucher_detail_no)
	).run(as_dict=True)

	return {d.voucher_detail_no: d.reserved_qty for d in data} if data else {}

# Apply patches
stock_reservation_entry.get_sre_reserved_qty_for_items_and_warehouses = get_sre_reserved_qty_for_items_and_warehouses
stock_reservation_entry.get_sre_reserved_qty_details_for_voucher = get_sre_reserved_qty_details_for_voucher
