# Copyright (c) 2026, Kartik and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import add_days
import json
from kniterp.api.access_control import require_production_write_access

@frappe.whitelist()
def generate_attendance(date, company, entries):
    require_production_write_access("generate machine attendance")

    if isinstance(entries, str):
        entries = json.loads(entries)

    if not date:
        frappe.throw("Date is mandatory")

    created = 0
    
    for row in entries:
        created += create_row(date, company, row, "morning")
        created += create_row(date, company, row, "night")

    frappe.msgprint(f"{created} Machine Attendance records created")


def create_row(date, company, row, shift):
    employee = row.get(f"{shift.lower()}_employee")
    qty = row.get(f"{shift.lower()}_production_kg")
    machine = row.get("machine")
    
    if not employee or not qty:
        return 0

    doc = frappe.get_doc({
        "doctype": "Machine Attendance",
        "date": date,
        "company": company,
        "machine": machine,
        "employee": employee,
        "shift": shift,
        "production_qty_kg": qty
    })
    doc.insert(ignore_permissions=True)
    return 1

class MachineAttendanceTool(Document):
    
	def onload(self):
		if not self.entries:
			self.load_machines_with_last_employees()

	def validate_date(self):
		if not self.date:
			frappe.throw("Date is mandatory")


	def load_machines_with_last_employees(self):
		self.entries = []

		machines = frappe.get_all("Workstation", pluck="name")
		

		for machine in machines:
			morning_emp = self.get_last_employee(machine, self.date, "Morning")
			night_emp = self.get_last_employee(machine, self.date, "Night")

			self.append("entries", {
				"machine": machine,
				"morning_employee": morning_emp,
				"night_employee": night_emp
			})

	def get_last_employee(self, machine, date, shift):
		res = frappe.db.sql("""
			SELECT employee
			FROM `tabMachine Attendance`
			WHERE machine = %s
			AND shift = %s
			AND date < %s
			ORDER BY date DESC
			LIMIT 1
		""", (machine, shift, date))
		return res[0][0] if res else None
