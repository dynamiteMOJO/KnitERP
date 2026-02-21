import frappe

def create_report():
    report_name = "Subcontracted Batch Traceability"
    if not frappe.db.exists("Report", report_name):
        doc = frappe.new_doc("Report")
        doc.report_name = report_name
        doc.ref_doctype = "Batch"
        doc.report_type = "Script Report"
        doc.is_standard = "Yes"
        doc.module = "Kniterp"
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        print(f"Created standard report '{report_name}'")
    else:
        print(f"Report '{report_name}' already exists.")
