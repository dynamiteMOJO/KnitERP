import frappe


def get_bootinfo(bootinfo):
	if frappe.db.exists("DocType", "KnitERP Settings"):
		bootinfo.kniterp_settings = frappe.get_cached_doc("KnitERP Settings").as_dict()
