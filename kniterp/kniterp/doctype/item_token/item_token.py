# Copyright (c) 2026, Kniterp and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ItemToken(Document):
    def validate(self):
        # Ensure short_code is uppercase
        if self.short_code:
            self.short_code = self.short_code.strip().upper()
