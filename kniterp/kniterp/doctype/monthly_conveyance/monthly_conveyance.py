# Copyright (c) 2026, Kartik and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class MonthlyConveyance(Document):

    def validate(self):
        self.rate_per_km = 3
        self.amount = self.total_km * self.rate_per_km
