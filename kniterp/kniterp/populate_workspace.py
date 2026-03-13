import frappe
import json
import uuid


def populate_kniterp_workspace():
    ws = frappe.get_doc("Workspace", "KnitERP")

    # Clear existing child tables
    ws.shortcuts = []
    ws.links = []

    # ── Shortcuts: KnitERP Pages ──
    page_shortcuts = [
        {"label": "Production Wizard", "type": "Page", "link_to": "production-wizard", "color": "#F97316", "icon": "tool"},
        {"label": "Transaction Desk", "type": "Page", "link_to": "transaction-desk", "color": "#3B82F6", "icon": "file"},
        {"label": "Action Center", "type": "Page", "link_to": "action-center", "color": "#EF4444", "icon": "alert"},
        {"label": "BOM Designer", "type": "Page", "link_to": "bom_designer", "color": "#8B5CF6", "icon": "branch"},
        {"label": "Home Dashboard", "type": "Page", "link_to": "kniterp-home", "color": "#10B981", "icon": "dashboard"},
    ]

    # ── Shortcuts: Frequently used DocTypes ──
    doctype_shortcuts = [
        {"label": "Sales Order", "type": "DocType", "link_to": "Sales Order", "color": "#316CE6", "doc_view": "List",
         "stats_filter": json.dumps({"docstatus": 1, "status": ["not in", ["Closed", "Completed", "Cancelled"]]})},
        {"label": "Purchase Order", "type": "DocType", "link_to": "Purchase Order", "color": "#8E54E9", "doc_view": "List",
         "stats_filter": json.dumps({"docstatus": 1, "status": ["not in", ["Closed", "Completed", "Cancelled"]]})},
        {"label": "Work Order", "type": "DocType", "link_to": "Work Order", "color": "#F97316", "doc_view": "List",
         "stats_filter": json.dumps({"docstatus": 1, "status": ["not in", ["Closed", "Completed", "Cancelled", "Stopped"]]})},
        {"label": "Job Card", "type": "DocType", "link_to": "Job Card", "color": "#EF4444", "doc_view": "List",
         "stats_filter": json.dumps({"docstatus": 0, "status": ["in", ["Open", "Work In Progress"]]})},
        {"label": "Stock Entry", "type": "DocType", "link_to": "Stock Entry", "color": "#10B981", "doc_view": "List"},
        {"label": "Item", "type": "DocType", "link_to": "Item", "color": "#4CAF50", "doc_view": "List"},
        {"label": "BOM", "type": "DocType", "link_to": "BOM", "color": "#3F51B5", "doc_view": "List",
         "stats_filter": json.dumps({"is_active": 1, "docstatus": 1})},
    ]

    all_shortcuts = page_shortcuts + doctype_shortcuts
    for idx, s in enumerate(all_shortcuts, start=1):
        row = {
            "label": s["label"],
            "type": s["type"],
            "link_to": s["link_to"],
            "color": s.get("color", ""),
            "icon": s.get("icon", ""),
            "idx": idx,
        }
        if s.get("doc_view"):
            row["doc_view"] = s["doc_view"]
        if s.get("stats_filter"):
            row["stats_filter"] = s["stats_filter"]
        if s.get("format"):
            row["format"] = s["format"]
        ws.append("shortcuts", row)

    # ── Link Cards ──
    link_cards = [
        {
            "card_label": "Reports",
            "card_icon": "chart",
            "links": [
                {"label": "Subcontracted Batch Traceability", "link_type": "Report", "link_to": "Subcontracted Batch Traceability", "is_query_report": 1},
                {"label": "Monthly Salary Register", "link_type": "Report", "link_to": "Monthly Salary Register", "is_query_report": 1},
                {"label": "Stock Balance", "link_type": "Report", "link_to": "Stock Balance", "is_query_report": 1},
                {"label": "BOM Stock Report", "link_type": "Report", "link_to": "BOM Stock Report", "is_query_report": 1},
                {"label": "Production Planning Report", "link_type": "Report", "link_to": "Production Planning Report", "is_query_report": 1},
            ],
        },
        {
            "card_label": "Payroll & HR",
            "card_icon": "users",
            "links": [
                {"label": "Employee", "link_type": "DocType", "link_to": "Employee"},
                {"label": "Attendance", "link_type": "DocType", "link_to": "Attendance"},
                {"label": "Salary Slip", "link_type": "DocType", "link_to": "Salary Slip"},
                {"label": "Monthly Conveyance", "link_type": "DocType", "link_to": "Monthly Conveyance"},
                {"label": "Machine Attendance Tool", "link_type": "DocType", "link_to": "Machine Attendance Tool"},
            ],
        },
        {
            "card_label": "Setup",
            "card_icon": "setting-gear",
            "links": [
                {"label": "KnitERP Settings", "link_type": "DocType", "link_to": "KnitERP Settings"},
                {"label": "Transaction Parameter", "link_type": "DocType", "link_to": "Transaction Parameter"},
                {"label": "Item Token", "link_type": "DocType", "link_to": "Item Token"},
                {"label": "Item Token Alias", "link_type": "DocType", "link_to": "Item Token Alias"},
            ],
        },
    ]

    link_idx = 1
    for card in link_cards:
        ws.append("links", {
            "type": "Card Break",
            "label": card["card_label"],
            "icon": card.get("card_icon", ""),
            "link_count": len(card["links"]),
            "idx": link_idx,
        })
        link_idx += 1

        for link in card["links"]:
            ws.append("links", {
                "type": "Link",
                "label": link["label"],
                "link_type": link["link_type"],
                "link_to": link["link_to"],
                "is_query_report": link.get("is_query_report", 0),
                "idx": link_idx,
            })
            link_idx += 1

    # ── Content JSON (block layout) ──
    def uid():
        return uuid.uuid4().hex[:12]

    content = []

    # Header: KnitERP Quick Access
    content.append({
        "id": uid(), "type": "header", "data": {
            "text": "<span class='h4'><b>Quick Access</b></span>", "col": 12
        }
    })

    # Page shortcut blocks (col=4 → 3 per row, then 2 on next)
    for s in page_shortcuts:
        content.append({
            "id": uid(), "type": "shortcut", "data": {
                "shortcut_name": s["label"], "col": 4
            }
        })

    # Spacer
    content.append({"id": uid(), "type": "spacer", "data": {"col": 12}})

    # Header: Documents
    content.append({
        "id": uid(), "type": "header", "data": {
            "text": "<span class='h4'><b>Documents</b></span>", "col": 12
        }
    })

    # DocType shortcut blocks (col=3 → 4 per row)
    for s in doctype_shortcuts:
        content.append({
            "id": uid(), "type": "shortcut", "data": {
                "shortcut_name": s["label"], "col": 3
            }
        })

    # Spacer
    content.append({"id": uid(), "type": "spacer", "data": {"col": 12}})

    # Header: Reports & Tools
    content.append({
        "id": uid(), "type": "header", "data": {
            "text": "<span class='h4'><b>Reports & Tools</b></span>", "col": 12
        }
    })

    # Link cards
    for card in link_cards:
        content.append({
            "id": uid(), "type": "card", "data": {
                "card_name": card["card_label"], "col": 4
            }
        })

    ws.content = json.dumps(content)

    ws.flags.ignore_validate = True
    ws.save(ignore_permissions=True)
    frappe.db.commit()

    print(f"✅ KnitERP workspace populated with {len(all_shortcuts)} shortcuts and {len(link_cards)} link cards")
