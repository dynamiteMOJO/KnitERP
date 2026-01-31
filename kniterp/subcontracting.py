import frappe

def update_work_order_from_job_card(jc, completed_qty):
    if not jc.work_order:
        return

    wo = frappe.get_doc("Work Order", jc.work_order)

    # 1. Update completed_qty directly in DB
    for op in wo.operations:
        if op.operation == jc.operation:
            frappe.db.set_value(
                "Work Order Operation",
                op.name,
                "completed_qty",
                completed_qty
            )

    # 2. Let ERPNext recalculate statuses SAFELY
    wo = frappe.get_doc("Work Order", wo.name)
    wo.update_operation_status()

    # 3. Persist operation status changes safely
    for op in wo.operations:
        frappe.db.set_value(
            "Work Order Operation",
            op.name,
            "status",
            op.status
        )

    frappe.logger().info({
        "work_order_updated": wo.name,
        "operation": jc.operation,
        "completed_qty": completed_qty
    })

def complete_job_card_from_po_item(purchase_order, pr_item):

    po_items = frappe.get_all(
        "Purchase Order Item",
        filters={
            "parent": purchase_order,
            "job_card": ["is", "set"]
        },
        fields=["job_card"]
    )

    for poi in po_items:
        jc = frappe.get_doc("Job Card", poi.job_card)

        # if jc.docstatus != 1 or jc.status == "Completed":
        #     continue

        # ✅ only complete job card
        jc.db_set("status", "Completed", update_modified=False)

        frappe.logger().info({
            "job_card_completed": jc.name,
            "source": "purchase_receipt",
            "purchase_order": purchase_order
        })

        update_work_order_from_job_card(
            jc,
            completed_qty=pr_item.qty
        )

def on_pr_submit_complete_job_cards(pr, method):
    if not pr.is_subcontracted:
        return

    for pr_item in pr.items:
        if not pr_item.purchase_order:
            continue

        complete_job_card_from_po_item(
            purchase_order=pr_item.purchase_order,
            pr_item=pr_item
        )