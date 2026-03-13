import frappe
from frappe.model.document import Document


class KnitERPSettings(Document):
	@staticmethod
	def get_settings():
		return frappe.get_cached_doc("KnitERP Settings")
