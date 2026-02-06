import frappe
from frappe import _
from frappe.utils import flt, nowdate, add_days

@frappe.whitelist()
def get_action_items():
    """
    Returns a dictionary of action items categorized by type.
    Categories:
    1. rm_shortage: Sales Orders pending production where RM is insufficient.
    2. knitting_pending: Orders pending production where RM IS available.
    3. send_to_job_worker: Subcontracting Orders needing material transfer.
    4. receive_from_job_worker: Subcontracting Orders needing receipt.
    5. receive_rm_from_customer: Job Work Inward Orders pending material receipt.
    6. pending_delivery: Sales Orders ready to deliver.
    7. pending_invoice: Delivery Notes ready to invoice.
    """
    
    actions = {
        'rm_shortage': get_rm_shortage_items(),
        'knitting_pending': get_knitting_pending_items(),
        'send_to_job_worker': get_send_to_jw_items(),
        'receive_from_job_worker': get_receive_from_jw_items(),
        'receive_rm_from_customer': get_receive_rm_from_customer_items(),
        'pending_delivery': get_pending_delivery_items(),
        'pending_invoice': get_pending_invoice_items()
    }
    return actions

from kniterp.api.production_wizard import get_pending_production_items as get_wizard_items

def get_pending_production_items():
    """
    Helper to get all pending Sales Order Items that need production (Knitting).
    Returns list of dicts.
    """
    items = get_wizard_items()
    
    # Enriched items with Work Order Status
    for item in items:
        # Check for linked Work Order status
        wo_status = frappe.db.get_value('Work Order', 
            {'sales_order_item': item.sales_order_item, 'docstatus': ['!=', 2]}, 
            'status')
        item['work_order_status'] = wo_status or 'Not Started'
        
    return items

def check_rm_availability(item_code, required_qty):
    """
    Checks if RM is available for the given FG item and qty.
    Returns True if available, False otherwise.
    """
    # Get BOM
    bom = frappe.db.get_value('BOM', {'item': item_code, 'is_active': 1, 'is_default': 1}, 'name')
    if not bom:
        return False # No BOM means we can't determine, treat as shortage/issue
        
    # Get RMs from BOM
    rms = frappe.db.get_all('BOM Item', filters={'parent': bom}, fields=['item_code', 'qty', 'uom'])
    
    for rm in rms:
        needed = rm.qty * required_qty # Simple logic, ignoring scrap for high-level check
        actual = get_stock_balance(rm.item_code)
        if actual < needed:
            return False
            
    return True

def get_stock_balance(item_code):
    # Simplified stock balance check
    # In a real scenario, we might check specific warehouses
    bal = frappe.db.sql("""
        SELECT sum(actual_qty) FROM `tabBin` WHERE item_code = %s
    """, (item_code,))
    return flt(bal[0][0]) if bal and bal[0][0] else 0.0

def get_rm_shortage_items():
    shortage_items = []
    # This can be expensive, so we limit to checking top 20 urgent items or similar if dataset is huge.
    # For now, we iterate all pending.
    items = get_pending_production_items()
    
    for item in items:
        # Check if Work Order is not started (meaning we need to check RM)
        if item.work_order_status in [None, 'Draft', 'Not Started', 'Pending']:
            if not check_rm_availability(item.item_code, item.qty):
                shortage_items.append({
                    'title': f"{item.customer_name} - {item.item_name}",
                    'description': f"Qty: {item.qty}",
                    'link': 'production-wizard',
                    'route_options': {
                        'materials_status': 'Shortage',
                        'selected_item': item.sales_order_item
                    },
                    'date': item.delivery_date
                })
                
    return {
        'count': len(shortage_items),
        'items': shortage_items[:5],
        'label': 'Raw Material Shortage',
        'color': 'danger'
    }

def get_knitting_pending_items():
    ready_items = []
    items = get_pending_production_items()
    
    for item in items:
         # Need to check if work order is NOT created or Draft
         if item.work_order_status in [None, 'Draft', 'Not Started', 'Pending']:
            if check_rm_availability(item.item_code, item.qty):
                ready_items.append({
                    'title': f"{item.customer_name} - {item.item_name}",
                    'description': f"Qty: {item.qty}",
                    'link': 'production-wizard',
                    'route_options': {
                        'materials_status': 'Ready',
                        'selected_item': item.sales_order_item
                    },
                    'date': item.delivery_date
                })

    return {
        'count': len(ready_items),
        'items': ready_items[:5],
        'label': 'Ready for Knitting',
        'color': 'warning'
    }

def get_send_to_jw_items():
    # Subcontracting Orders where Status is not completed and material not fully sent
    # Logic: Subcontracting Order (Purchase Order with is_subcontracted=1)
    # We check 'supplied_items' in PO to see if sent < required
    
    # Using SQL for performance on joined checking
    # Finding POs where (supplied_qty < required_qty) AND docstatus=1 AND status != Completed
    
    # Note: This is an approximation. Precise logic matches standard Subcontracting finding.
    pos = frappe.db.sql("""
        SELECT 
            po.name, po.supplier_name, po.transaction_date
        FROM
            `tabPurchase Order` po
        WHERE
            po.is_subcontracted = 1
            AND po.docstatus = 1
            AND po.status NOT IN ('Closed', 'Completed', 'Cancelled')
            AND EXISTS (
                SELECT 1 FROM `tabPurchase Order Item Supplied` pois
                WHERE pois.parent = po.name 
                AND (pois.required_qty - pois.supplied_qty) > 0
            ) 
        ORDER BY po.transaction_date ASC
    """, as_dict=1)
    
    # Refined logic: the subquery above is a bit loose, let's trust the PO status or implement better check
    # For now, let's assumes if status is NOT 'Materials Transferred' (or similiar), it needs action.
    # Actually, let's just list active Subcontract POs and let user check. 
    # Or, check distinct POs that have pending transfers.
    
    data = []
    for po in pos:
        # Check transfer status helper
        # For simplicity, we assume if it's active subcontract PO, we might need to send material.
        # Ideally we check 'to_send'
        data.append({
            'title': f"{po.supplier_name}",
            'description': f"PO: {po.name}",
            'link': 'Form/Purchase Order/' + po.name
        })

    return {
        'count': len(data),
        'items': data[:5],
        'label': 'Send Material to Job Worker',
        'color': 'warning'
    }

def get_receive_from_jw_items():
    # Subcontracting Orders where material is sent (partially or full) but FG not received
    # PO Status might be 'Materials Transferred' or 'Partially Received'
    
    pos = frappe.db.sql("""
        SELECT 
            po.name, po.supplier_name
        FROM
            `tabPurchase Order` po
        WHERE
            po.is_subcontracted = 1
            AND po.docstatus = 1
            AND po.status IN ('Materials Transferred', 'Partially Received')
            AND po.per_received < 100
        ORDER BY po.transaction_date ASC
    """, as_dict=1)
    
    data = []
    for po in pos:
        data.append({
            'title': f"{po.supplier_name}",
            'description': f"PO: {po.name}",
            'link': 'Form/Purchase Order/' + po.name
        })

    return {
        'count': len(data),
        'items': data[:5],
        'label': 'Receive FG from Job Worker',
        'color': 'warning'
    }

def get_receive_rm_from_customer_items():
    # Subcontracting Inward Order (Job Work Inward)
    # These are orders where we are the Job Worker.
    # We need to receive RM from Customer.
    
    # Try to find the doctype for this. The user mentioned 'Subcontracting Inward Order' in step 23 logic
    orders = frappe.db.get_all('Subcontracting Inward Order', 
        filters={'docstatus': 1, 'status': ['not in', ['Completed', 'Closed', 'Cancelled']]},
        fields=['name', 'customer_name', 'transaction_date'])
        
    data = []
    for o in orders:
        data.append({
            'title': f"{o.customer_name}",
            'description': f"Order: {o.name}",
            'link': 'Form/Subcontracting Inward Order/' + o.name
        })
        
    return {
        'count': len(data),
        'items': data[:5],
        'label': 'Receive RM from Customer',
        'color': 'warning'
    }

def get_pending_delivery_items():
    # Sales Orders where Work Order is completed (or stock is reserved) but Delivery Note not made.
    # Simple check: SO status is 'To Deliver_and_Bill' or 'To Deliver'
    
    orders = frappe.db.get_all('Sales Order',
        filters={
            'docstatus': 1, 
            'status': ['in', ['To Deliver and Bill', 'To Deliver']],
            'per_delivered': ['<', 100]
        },
        fields=['name', 'customer_name', 'delivery_date'],
        order_by='delivery_date asc'
    )
    
    data = []
    for o in orders:
        data.append({
            'title': f"{o.customer_name}",
            'description': f"SO: {o.name}",
            'link': 'Form/Sales Order/' + o.name # Or create DN link
        })
        
    return {
        'count': len(data),
        'items': data[:5],
        'label': 'Pending Delivery to Customer',
        'color': 'success'
    }

def get_pending_invoice_items():
    # Delivery Notes submitted but not billed
    
    dns = frappe.db.get_all('Delivery Note',
        filters={
            'docstatus': 1,
            'per_billed': ['<', 100],
            'status': ['!=', 'Closed']
        },
        fields=['name', 'customer_name', 'posting_date'],
        order_by='posting_date asc'
    )
    
    data = []
    for d in dns:
        data.append({
            'title': f"{d.customer_name}",
            'description': f"DN: {d.name}",
            'link': 'Form/Delivery Note/' + d.name
        })
        
    return {
        'count': len(data),
        'items': data[:5],
        'label': 'Pending Sales Invoices',
        'color': 'success'
    }
