# Copyright (c) 2026, Kartik and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

MIN_QTY = 30

class MachineAttendance(Document):

    def validate(self):
        self.validate_duplicate()
        self.validate_operator()
        self.validate_production_qty_kg()

    def validate_duplicate(self):
        exists = frappe.db.exists(
            "Machine Attendance",
            {
                "employee": self.employee,
                "date": self.date,
                "machine": self.machine,
                "shift": self.shift,
                "name": ["!=", self.name]
            }
        )
        
        if exists:
            frappe.throw("Same machine already marked for this day")

    def validate_operator(self):
        designation = frappe.db.get_value("Employee", self.employee, "designation")
        if designation != "Operator":
            frappe.throw("Machine Attendance allowed only for Operators")

    def validate_production_qty_kg(self):
        if self.production_qty_kg is None:
            frappe.throw("Production quantity is required")

        if self.production_qty_kg < 0:
            frappe.throw("Production quantity cannot be negative")
