# Copyright (c) 2026, Kartik and contributors
# For license information, please see license.txt

import frappe
import json
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


@frappe.whitelist()
def get_present_operators(doctype, txt, searchfield, start, page_len, filters):
    if isinstance(filters, str):
        filters = json.loads(filters)

    date = filters.get("date")
    shift = filters.get("shift")

    present_employees = None
    if date:
        att_filters = {"attendance_date": date, "status": "Present", "docstatus": 1}
        if shift:
            att_filters["shift"] = shift
        present_employees = frappe.get_all("Attendance", filters=att_filters, pluck="employee")
        if not present_employees:
            return []

    conditions = ["e.designation = %(designation)s", "e.status = %(emp_status)s"]
    params = {
        "designation": "Operator",
        "emp_status": "Active",
        "txt": f"%{txt}%",
        "start": int(start),
        "page_len": int(page_len),
    }

    if present_employees:
        escaped = [frappe.db.escape(e) for e in present_employees]
        conditions.append(f"e.name IN ({', '.join(escaped)})")

    if txt:
        conditions.append("(e.name LIKE %(txt)s OR e.employee_name LIKE %(txt)s)")

    where_clause = " AND ".join(conditions)

    return frappe.db.sql(f"""
        SELECT e.name, e.employee_name
        FROM `tabEmployee` e
        WHERE {where_clause}
        LIMIT %(start)s, %(page_len)s
    """, params)

