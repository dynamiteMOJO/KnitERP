import frappe
from frappe.model.document import Document

class ItemTokenAlias(Document):
    def before_save(self):
        # Always store alias in lowercase
        if self.alias:
            self.alias = self.alias.strip().lower()
