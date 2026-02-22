import frappe

def after_migrate():
    hide_unwanted_workspaces()

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
    frappe.db.set_value("Desktop Icon", {"name": ("in", modules_to_hide)}, "hidden", 1)
    
    for icon_name in modules_to_hide:
        if frappe.db.exists("Desktop Icon", icon_name):
            icon_doc = frappe.get_doc("Desktop Icon", icon_name)
            has_admin_role = any(row.role == "Administrator" for row in icon_doc.roles)
            if not has_admin_role:
                icon_doc.append("roles", {"role": "Administrator"})
                icon_doc.save(ignore_permissions=True)

    frappe.db.commit()
