import frappe

def after_migrate():
    setup_custom_fields()
    setup_property_setters()
    setup_service_items()
    setup_salary_components()
    setup_virtual_goods_warehouse()
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
        {
            "dt": "Purchase Order Item",
            "fieldname": "custom_jw_description",
            "label": "Job Work Description",
            "fieldtype": "Small Text",
            "insert_after": "custom_transaction_params_json",
            "hidden": 1,
            "print_hide": 1,
        },
    ]

    for cf in custom_fields:
        if not frappe.db.exists("Custom Field", {"dt": cf["dt"], "fieldname": cf["fieldname"]}):
            doc = frappe.new_doc("Custom Field")
            doc.update(cf)
            # insert_after may reference a field that doesn't exist on a fresh install;
            # ignore_links prevents a LinkValidationError in that case.
            doc.insert(ignore_permissions=True, ignore_links=True)

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
        # The target field is auto-generated and may not exist on other installations.
        field_exists = frappe.db.exists(
            "DocField",
            {"parent": ps["doctype"], "fieldname": ps["fieldname"]},
        )
        if not field_exists:
            continue

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

def _ensure_prerequisites():
    # Ensure a root Item Group exists that can act as parent.
    # ERPNext stores root group's parent_item_group as NULL (not ""), so filter
    # by name directly to avoid a false-negative that triggers a duplicate insert.
    if frappe.db.exists("Item Group", "All Item Groups"):
        root_group = "All Item Groups"
    else:
        root_group = frappe.db.get_value(
            "Item Group", {"is_group": 1, "parent_item_group": ("is", "not set")}, "name"
        )
        if not root_group:
            ig = frappe.new_doc("Item Group")
            ig.item_group_name = "All Item Groups"
            ig.is_group = 1
            ig.insert(ignore_permissions=True)
            root_group = ig.name

    if not frappe.db.exists("Item Group", "Services"):
        ig = frappe.new_doc("Item Group")
        ig.item_group_name = "Services"
        ig.parent_item_group = root_group
        ig.insert(ignore_permissions=True)

    if not frappe.db.exists("UOM", "Kg"):
        uom = frappe.new_doc("UOM")
        uom.uom_name = "Kg"
        uom.insert(ignore_permissions=True)

    frappe.db.commit()


def setup_service_items():
    _ensure_prerequisites()
    service_items = [
        {"item_code": "Knitting Jobwork", "item_name": "Knitting Jobwork", "item_group": "Services", "stock_uom": "Kg", "gst_hsn_code": "998821"},
        {"item_code": "Dyeing Jobwork", "item_name": "Dyeing Jobwork", "item_group": "Services", "stock_uom": "Kg", "gst_hsn_code": "998821"},
        {"item_code": "Yarn Processing", "item_name": "Yarn Processing", "item_group": "Services", "stock_uom": "Kg", "gst_hsn_code": "998821"},
        {"item_code": "Knitting Jobwork outward", "item_name": "Knitting Jobwork outward", "item_group": "Services", "stock_uom": "Kg", "gst_hsn_code": "998821"},
        {"item_code": "Knitting Jobwork inward", "item_name": "Knitting Jobwork inward", "item_group": "Services", "stock_uom": "Kg", "gst_hsn_code": "998821"},
        {"item_code": "Knitting+Dyeing Jobwork", "item_name": "Knitting+Dyeing Jobwork", "item_group": "Services", "stock_uom": "Kg", "gst_hsn_code": "998821"},
        {"item_code": "Yarn processing Jobwork", "item_name": "Yarn processing Jobwork", "item_group": "Services", "stock_uom": "Kg", "gst_hsn_code": "998821"},
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
        {"salary_component": "Sunday Pay", "salary_component_abbr": "SP", "type": "Earning"},
        {"salary_component": "Dual Shift Pay", "salary_component_abbr": "DSP", "type": "Earning"},
        {"salary_component": "Machine Extra Pay", "salary_component_abbr": "MEP", "type": "Earning"},
        {"salary_component": "Conveyance Allowance", "salary_component_abbr": "CA", "type": "Earning"},
        {"salary_component": "Tea Allowance", "salary_component_abbr": "TA", "type": "Earning"},
        {"salary_component": "Rejected Holiday Deduction", "salary_component_abbr": "RHD", "type": "Deduction"},
    ]

    for comp_data in components:
        if not frappe.db.exists("Salary Component", comp_data["salary_component"]):
            comp = frappe.new_doc("Salary Component")
            comp.update(comp_data)
            comp.insert(ignore_permissions=True)

    frappe.db.commit()


def setup_virtual_goods_warehouse():
    """Create Virtual Goods warehouse for direct delivery flows if not already configured."""
    settings = frappe.get_single("KnitERP Settings")
    if settings.virtual_goods_warehouse:
        return

    company = frappe.db.get_single_value("Global Defaults", "default_company")
    if not company:
        return

    abbr = frappe.db.get_value("Company", company, "abbr")
    wh_name = f"Virtual Goods - {abbr}"

    if not frappe.db.exists("Warehouse", wh_name):
        parent_wh = frappe.db.get_value("Warehouse", {"company": company, "is_group": 1, "parent_warehouse": ""}, "name")
        wh = frappe.new_doc("Warehouse")
        wh.warehouse_name = "Virtual Goods"
        wh.company = company
        wh.parent_warehouse = parent_wh
        wh.insert(ignore_permissions=True)
        wh_name = wh.name

    settings.virtual_goods_warehouse = wh_name
    settings.save(ignore_permissions=True)
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
                workspace_doc.save(ignore_permissions=True, ignore_links=True)

    # 2. Update Workspace Sidebars — doctype may not exist in all versions
    try:
        frappe.db.set_value("Workspace Sidebar", {"name": ("in", modules_to_hide)}, {
            "standard": 0,
            "for_user": "Administrator"
        })
    except Exception:
        pass

    # 3. Hide the Desktop Icons — doctype may not exist in all framework versions
    try:
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
                    icon_doc.save(ignore_permissions=True, ignore_links=True)
    except Exception:
        pass

    # 4. Push all non-KnitERP Desktop Icons & Workspaces to the bottom
    try:
        frappe.db.sql("""
            UPDATE `tabDesktop Icon`
            SET idx = idx + 100
            WHERE app != 'kniterp' AND idx < 100
        """)
    except Exception:
        pass

    frappe.db.sql("""
        UPDATE `tabWorkspace`
        SET sequence_id = sequence_id + 100
        WHERE module != 'Kniterp' AND sequence_id < 100
    """)

    frappe.db.commit()
