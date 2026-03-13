import frappe

def after_migrate():
    setup_custom_fields()
    setup_property_setters()
    setup_service_items()
    setup_salary_components()
    hide_unwanted_workspaces()


def setup_custom_fields():
    custom_fields = [
        {
            "dt": "Salary Slip",
            "fieldname": "custom_per_day_salary",
            "label": "Per Day Salary",
            "fieldtype": "Currency",
            "insert_after": "earnings_and_deductions_tab",
            "read_only": 1,
            "bold": 1,
        },
    ]

    for cf in custom_fields:
        if not frappe.db.exists("Custom Field", {"dt": cf["dt"], "fieldname": cf["fieldname"]}):
            doc = frappe.new_doc("Custom Field")
            doc.update(cf)
            doc.insert(ignore_permissions=True)

    frappe.db.commit()


def setup_property_setters():
    """Create Property Setters for doctype layout customizations."""
    property_setters = [
        {
            "doctype": "Salary Slip",
            "fieldname": "column_break_k1jz",
            "property": "fieldtype",
            "value": "Section Break",
            "property_type": "Select",
        },
    ]

    for ps in property_setters:
        if not frappe.db.exists("Property Setter", {
            "doc_type": ps["doctype"],
            "field_name": ps["fieldname"],
            "property": ps["property"],
            "module": "Kniterp",
        }):
            doc = frappe.new_doc("Property Setter")
            doc.doctype_or_field = "DocField"
            doc.doc_type = ps["doctype"]
            doc.field_name = ps["fieldname"]
            doc.property = ps["property"]
            doc.value = ps["value"]
            doc.property_type = ps["property_type"]
            doc.module = "Kniterp"
            doc.is_system_generated = 0
            doc.insert(ignore_permissions=True)

    frappe.db.commit()

def setup_service_items():
    service_items = [
        {"item_code": "Knitting Jobwork", "item_name": "Knitting Jobwork", "item_group": "Services", "stock_uom": "Kg", "gst_hsn_code": "998821"},
        {"item_code": "Dyeing Jobwork", "item_name": "Dyeing Jobwork", "item_group": "Services", "stock_uom": "Kg", "gst_hsn_code": "998821"},
        {"item_code": "Yarn Processing", "item_name": "Yarn Processing", "item_group": "Services", "stock_uom": "Kg", "gst_hsn_code": "998821"},
    ]

    for item_data in service_items:
        if not frappe.db.exists("Item", item_data["item_code"]):
            item = frappe.new_doc("Item")
            item.update(item_data)
            item.is_stock_item = 0
            item.insert(ignore_permissions=True)

    frappe.db.commit()


def setup_salary_components():
    components = [
        {"salary_component": "Sunday Pay", "type": "Earning"},
        {"salary_component": "Dual Shift Pay", "type": "Earning"},
        {"salary_component": "Machine Extra Pay", "type": "Earning"},
        {"salary_component": "Conveyance Allowance", "type": "Earning"},
        {"salary_component": "Tea Allowance", "type": "Earning"},
        {"salary_component": "Rejected Holiday Deduction", "type": "Deduction"},
    ]

    for comp_data in components:
        if not frappe.db.exists("Salary Component", comp_data["salary_component"]):
            comp = frappe.new_doc("Salary Component")
            comp.update(comp_data)
            comp.insert(ignore_permissions=True)

    frappe.db.commit()


def hide_unwanted_workspaces():
    modules_to_hide = [
        "Subscription", "Share Management", "Budget", "Home", "CRM", "Selling", 
        "Buying", "Stock", "Assets", "Projects", "Support", "Quality", 
        "Manufacturing", "Recruitment", "Tenure", "Shift & Attendance", 
        "Performance", "Expenses", "Payroll", "Frappe HR", "Subcontracting", 
        "ERPNext", "Data", "Printing", "Automation", "Email", "Website", 
        "Users", "Integrations", "Build"
    ]

    # 1. Hide the Workspaces themselves and assign to Administrator
    frappe.db.set_value("Workspace", {"name": ("in", modules_to_hide)}, "is_hidden", 1)
    frappe.db.set_value("Workspace", {"name": ("in", modules_to_hide)}, "public", 0)
    
    # Add Administrator role to Workspace
    for workspace_name in modules_to_hide:
        if frappe.db.exists("Workspace", workspace_name):
            workspace_doc = frappe.get_doc("Workspace", workspace_name)
            # Check if Administrator role already exists to avoid duplicates
            has_admin_role = any(row.role == "Administrator" for row in workspace_doc.roles)
            if not has_admin_role:
                workspace_doc.append("roles", {"role": "Administrator"})
                workspace_doc.save(ignore_permissions=True)

    # 2. Update Workspace Sidebars (Uncheck Standard, set for_user = Administrator)
    frappe.db.set_value("Workspace Sidebar", {"name": ("in", modules_to_hide)}, {
        "standard": 0,
        "for_user": "Administrator"
    })

    # 3. Hide the Desktop Icons and add Administrator role
    frappe.db.set_value("Desktop Icon", {"name": ("in", modules_to_hide)}, {
        "hidden": 1,
        "standard": 0
    })
    
    for icon_name in modules_to_hide:
        if frappe.db.exists("Desktop Icon", icon_name):
            icon_doc = frappe.get_doc("Desktop Icon", icon_name)
            has_admin_role = any(row.role == "Administrator" for row in icon_doc.roles)
            if not has_admin_role:
                icon_doc.append("roles", {"role": "Administrator"})
                icon_doc.save(ignore_permissions=True)

    # 4. Push all non-KnitERP Desktop Icons & Workspaces to the bottom
    frappe.db.sql("""
        UPDATE `tabDesktop Icon`
        SET idx = idx + 100
        WHERE app != 'kniterp' AND idx < 100
    """)
    frappe.db.sql("""
        UPDATE `tabWorkspace`
        SET sequence_id = sequence_id + 100
        WHERE module != 'Kniterp' AND sequence_id < 100
    """)

    frappe.db.commit()
