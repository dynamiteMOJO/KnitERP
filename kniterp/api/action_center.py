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
        'pending_purchase_receipt': get_pending_purchase_receipt_items(),
        'pending_purchase_invoice': get_pending_purchase_invoice_items(),
        'pending_delivery': get_pending_delivery_items(),
        'pending_invoice': get_pending_invoice_items()
    }
    return actions


@frappe.whitelist()
def get_fix_details(action_key):
    """
    Returns detailed data for the Fix dialog based on action_key.
    Each card type has specific columns, data, and available actions.
    """
    handlers = {
        'rm_shortage': get_rm_shortage_fix_details,
        'knitting_pending': get_knitting_pending_fix_details,
        'send_to_job_worker': get_send_to_jw_fix_details,
        'receive_from_job_worker': get_receive_from_jw_fix_details,
        'receive_rm_from_customer': get_receive_rm_from_customer_fix_details,
        'pending_purchase_receipt': get_pending_purchase_receipt_fix_details,
        'pending_purchase_invoice': get_pending_purchase_invoice_fix_details,
        'pending_delivery': get_pending_delivery_fix_details,
        'pending_invoice': get_pending_invoice_fix_details
    }
    
    handler = handlers.get(action_key)
    if not handler:
        return {'title': 'Unknown', 'columns': [], 'data': []}
    
    return handler()


def get_rm_shortage_fix_details():
    """Get detailed RM shortage breakdown for Fix dialog."""
    from kniterp.api.production_wizard import get_production_details
    
    items = get_pending_production_items()
    shortage_data = []
    
    for item in items:
        if item.work_order_status in [None, 'Draft', 'Not Started', 'Pending']:
            if not check_rm_availability(item.item_code, item.qty):
                # Get detailed BOM breakdown
                try:
                    details = get_production_details(item.sales_order_item)
                    for rm in details.get('raw_materials', []):
                        if rm.get('shortage', 0) > 0:
                            shortage_data.append({
                                'party': item.customer_name,
                                'sales_order': item.sales_order,
                                'sales_order_item': item.sales_order_item,
                                'item_to_produce': item.item_name,
                                'item_code': item.item_code,
                                'rm_item': rm['item_code'],
                                'rm_name': rm['item_name'],
                                'required_qty': flt(rm['required_qty'], 3),
                                'available_qty': flt(rm['available_qty'], 3),
                                'shortage': flt(rm['shortage'], 3),
                                '_raw_shortage': flt(rm['shortage']),
                                'uom': rm['uom'],
                                'warehouse': rm.get('warehouse'),
                                'delivery_date': item.delivery_date
                            })
                except Exception:
                    continue
    
    return {
        'title': _('Resolve Raw Material Shortage'),
        'button_label': _('Resolve'),
        'columns': [
            {'fieldname': 'select', 'label': '', 'width': 30},
            {'fieldname': 'party', 'label': _('Party')},
            {'fieldname': 'item_to_produce', 'label': _('Item to Produce')},
            {'fieldname': 'rm_name', 'label': _('Raw Material')},
            {'fieldname': 'required_qty', 'label': _('Required')},
            {'fieldname': 'available_qty', 'label': _('Available')},
            {'fieldname': 'shortage', 'label': _('Shortage')},
            {'fieldname': 'action_btn', 'label': _('Actions')}
        ],
        'data': shortage_data,
        'row_actions': [
            {'action': 'create_po', 'label': _('Create PO'), 'icon': 'fa fa-shopping-cart'},
            {'action': 'view_order', 'label': _('View'), 'icon': 'fa fa-external-link'}
        ],
        'bulk_actions': [
            {'action': 'consolidated_po', 'label': _('Create Consolidated PO'), 'icon': 'fa fa-shopping-cart'}
        ]
    }


def get_knitting_pending_fix_details():
    """Get items ready for production for Fix dialog."""
    items = get_pending_production_items()
    ready_data = []
    
    for item in items:
        if item.work_order_status in [None, 'Draft', 'Not Started', 'Pending']:
            if check_rm_availability(item.item_code, item.qty):
                bom = frappe.db.get_value('BOM', {'item': item.item_code, 'is_active': 1, 'is_default': 1}, 'name')
                ready_data.append({
                    'party': item.customer_name,
                    'sales_order': item.sales_order,
                    'sales_order_item': item.sales_order_item,
                    'item_name': item.item_name,
                    'item_code': item.item_code,
                    'qty': flt(item.qty, 3),
                    'bom_no': bom or '-',
                    'delivery_date': item.delivery_date
                })
    
    return {
        'title': _('Start Production'),
        'button_label': _('Produce'),
        'columns': [
            {'fieldname': 'select', 'label': '', 'width': 30},
            {'fieldname': 'party', 'label': _('Party')},
            {'fieldname': 'item_name', 'label': _('Item')},
            {'fieldname': 'qty', 'label': _('Qty')},
            {'fieldname': 'bom_no', 'label': _('BOM')},
            {'fieldname': 'delivery_date', 'label': _('Delivery Date')},
            {'fieldname': 'action_btn', 'label': _('Actions')}
        ],
        'data': ready_data,
        'row_actions': [
            {'action': 'create_wo', 'label': _('Create WO'), 'icon': 'fa fa-cogs'},
            {'action': 'view_order', 'label': _('View'), 'icon': 'fa fa-external-link'}
        ],
        'bulk_actions': [
            {'action': 'bulk_create_wo', 'label': _('Create Work Orders'), 'icon': 'fa fa-cogs'}
        ]
    }


def get_send_to_jw_fix_details():
    """Get pending material transfers to job workers."""
    pos = frappe.db.sql("""
        SELECT 
            po.name, po.supplier, po.supplier_name, po.transaction_date
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
    
    data = []
    for po in pos:
        # Get pending materials
        materials = frappe.db.sql("""
            SELECT item_code, item_name, required_qty, supplied_qty
            FROM `tabPurchase Order Item Supplied`
            WHERE parent = %s AND (required_qty - supplied_qty) > 0
        """, po.name, as_dict=1)
        
        so_item = frappe.db.get_value('Purchase Order Item', {'parent': po.name}, 'sales_order_item')
        
        for mat in materials:
            data.append({
                'supplier': po.supplier_name,
                'po_name': po.name,
                'item_code': mat.item_code,
                'item_name': mat.item_name,
                'required_qty': flt(mat.required_qty, 3),
                'sent_qty': flt(mat.supplied_qty, 3),
                'pending_qty': flt(mat.required_qty - mat.supplied_qty, 3),
                'sales_order_item': so_item
            })
    
    return {
        'title': _('Send Materials to Job Worker'),
        'button_label': _('Send'),
        'columns': [
            {'fieldname': 'select', 'label': '', 'width': 30},
            {'fieldname': 'supplier', 'label': _('Supplier')},
            {'fieldname': 'po_name', 'label': _('PO')},
            {'fieldname': 'item_name', 'label': _('Material')},
            {'fieldname': 'pending_qty', 'label': _('Qty to Send')},
            {'fieldname': 'action_btn', 'label': _('Actions')}
        ],
        'data': data,
        'row_actions': [
            {'action': 'send_material', 'label': _('Send'), 'icon': 'fa fa-truck'},
            {'action': 'view_po', 'label': _('View PO'), 'icon': 'fa fa-external-link'}
        ],
        'bulk_actions': []
    }


def get_receive_from_jw_fix_details():
    """Get pending FG receipts from job workers."""
    pos = frappe.db.sql("""
        SELECT 
            po.name, po.supplier, po.supplier_name
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
        items = frappe.db.sql("""
            SELECT item_code, item_name, fg_item, qty, received_qty
            FROM `tabPurchase Order Item`
            WHERE parent = %s AND (qty - received_qty) > 0
        """, po.name, as_dict=1)
        
        so_item = frappe.db.get_value('Purchase Order Item', {'parent': po.name}, 'sales_order_item')
        
        for item in items:
            data.append({
                'supplier': po.supplier_name,
                'po_name': po.name,
                'fg_item': item.fg_item or item.item_code,
                'item_name': item.item_name,
                'ordered_qty': flt(item.qty, 3),
                'received_qty': flt(item.received_qty, 3),
                'pending_qty': flt(item.qty - item.received_qty, 3),
                'sales_order_item': so_item
            })
    
    return {
        'title': _('Receive FG from Job Worker'),
        'button_label': _('Receive'),
        'columns': [
            {'fieldname': 'select', 'label': '', 'width': 30},
            {'fieldname': 'supplier', 'label': _('Supplier')},
            {'fieldname': 'po_name', 'label': _('PO')},
            {'fieldname': 'fg_item', 'label': _('FG Item')},
            {'fieldname': 'pending_qty', 'label': _('Qty to Receive')},
            {'fieldname': 'action_btn', 'label': _('Actions')}
        ],
        'data': data,
        'row_actions': [
            {'action': 'receive_goods', 'label': _('Receive'), 'icon': 'fa fa-download'},
            {'action': 'view_po', 'label': _('View PO'), 'icon': 'fa fa-external-link'}
        ],
        'bulk_actions': []
    }


def get_receive_rm_from_customer_fix_details():
    """Get pending RM receipts from customers."""
    try:
        orders = frappe.db.get_all('Subcontracting Inward Order', 
            filters={'docstatus': 1, 'status': ['not in', ['Completed', 'Closed', 'Cancelled']]},
            fields=['name', 'customer', 'customer_name', 'transaction_date'])
    except Exception:
        return {'title': _('Receive RM from Customer'), 'button_label': _('Receive'), 'columns': [], 'data': []}
    
    data = []
    for o in orders:
        try:
            items = frappe.db.get_all('Subcontracting Inward Order Item',
                filters={'parent': o.name},
                fields=['item_code', 'item_name', 'qty', 'received_qty', 'sales_order_item'])
        except Exception:
            continue
            
        for item in items:
            pending = flt(item.qty) - flt(item.received_qty)
            if pending > 0:
                data.append({
                    'customer': o.customer_name,
                    'order_name': o.name,
                    'item_code': item.item_code,
                    'item_name': item.item_name,
                    'pending_qty': flt(pending, 3),
                    'sales_order_item': item.sales_order_item
                })
    
    return {
        'title': _('Receive RM from Customer'),
        'button_label': _('Receive'),
        'columns': [
            {'fieldname': 'select', 'label': '', 'width': 30},
            {'fieldname': 'customer', 'label': _('Customer')},
            {'fieldname': 'order_name', 'label': _('Order')},
            {'fieldname': 'item_name', 'label': _('Material')},
            {'fieldname': 'pending_qty', 'label': _('Qty to Receive')},
            {'fieldname': 'action_btn', 'label': _('Actions')}
        ],
        'data': data,
        'row_actions': [
            {'action': 'receive_rm', 'label': _('Receive'), 'icon': 'fa fa-download'},
            {'action': 'view_order', 'label': _('View'), 'icon': 'fa fa-external-link'}
        ],
        'bulk_actions': []
    }


def get_pending_delivery_fix_details():
    """Get items that are manufactured and ready for delivery."""
    orders = frappe.db.get_all('Sales Order',
        filters={
            'docstatus': 1, 
            'status': ['in', ['To Deliver and Bill', 'To Deliver']],
            'per_delivered': ['<', 100]
        },
        fields=['name', 'customer', 'customer_name', 'delivery_date'],
        order_by='delivery_date asc'
    )
    
    data = []
    for o in orders:
        items = frappe.db.sql("""
            SELECT name, item_code, item_name, qty, delivered_qty
            FROM `tabSales Order Item`
            WHERE parent = %s AND qty > delivered_qty
        """, o.name, as_dict=1)
        
        for item in items:
            total_qty = flt(item.qty, 3)
            delivered_qty = flt(item.delivered_qty, 3)
            pending_to_deliver = flt(total_qty - delivered_qty, 3)
            
            # Get manufacturing status from Work Orders
            wo_data = frappe.db.sql("""
                SELECT 
                    COALESCE(SUM(qty), 0) as total_wo_qty,
                    COALESCE(SUM(produced_qty), 0) as produced_qty
                FROM `tabWork Order`
                WHERE sales_order = %s 
                    AND sales_order_item = %s
                    AND docstatus = 1
            """, (o.name, item.name), as_dict=1)
            
            total_to_manufacture = flt(wo_data[0].total_wo_qty if wo_data else 0, 3)
            manufactured_qty = flt(wo_data[0].produced_qty if wo_data else 0, 3)
            pending_to_manufacture = flt(total_to_manufacture - manufactured_qty, 3)
            
            # Ready to deliver = manufactured qty - already delivered qty
            # If no WO exists, item might be available in stock directly
            if total_to_manufacture == 0:
                # No work order - check stock availability
                stock_qty = get_available_stock(item.item_code)
                ready_to_deliver = min(stock_qty, pending_to_deliver)
            else:
                ready_to_deliver = max(0, flt(manufactured_qty - delivered_qty, 3))
            
            # Only show if there's something ready to deliver
            if ready_to_deliver > 0:
                data.append({
                    'customer': o.customer_name,
                    'sales_order': o.name,
                    'sales_order_item': item.name,
                    'item_name': item.item_name,
                    'item_code': item.item_code,
                    'total_qty': total_qty,
                    'total_to_manufacture': total_to_manufacture,
                    'manufactured_qty': manufactured_qty,
                    'pending_manufacture': pending_to_manufacture,
                    'delivered_qty': delivered_qty,
                    'ready_to_deliver': ready_to_deliver,
                    'delivery_date': o.delivery_date
                })
    
    return {
        'title': _('Create Delivery Notes'),
        'button_label': _('Deliver'),
        'columns': [
            {'fieldname': 'select', 'label': '', 'width': 30},
            {'fieldname': 'customer', 'label': _('Customer')},
            {'fieldname': 'sales_order', 'label': _('SO')},
            {'fieldname': 'item_name', 'label': _('Item')},
            {'fieldname': 'total_qty', 'label': _('Total Qty')},
            {'fieldname': 'pending_manufacture', 'label': _('Pending Mfg')},
            {'fieldname': 'ready_to_deliver', 'label': _('Ready to Deliver')},
            {'fieldname': 'delivery_date', 'label': _('Due Date')},
            {'fieldname': 'action_btn', 'label': _('Actions')}
        ],
        'data': data,
        'row_actions': [
            {'action': 'create_dn', 'label': _('Create DN'), 'icon': 'fa fa-truck'},
            {'action': 'view_order', 'label': _('View'), 'icon': 'fa fa-external-link'}
        ],
        'bulk_actions': [
            {'action': 'bulk_create_dn', 'label': _('Create Delivery Notes'), 'icon': 'fa fa-truck'}
        ]
    }


def get_available_stock(item_code):
    """Get available stock qty for an item across all warehouses."""
    stock = frappe.db.sql("""
        SELECT COALESCE(SUM(actual_qty), 0) as qty
        FROM `tabBin`
        WHERE item_code = %s
    """, item_code)
    return flt(stock[0][0] if stock else 0, 3)


def get_pending_invoice_fix_details():
    """Get DNs ready for invoicing."""
    dns = frappe.db.get_all('Delivery Note',
        filters={
            'docstatus': 1,
            'per_billed': ['<', 100],
            'status': ['!=', 'Closed']
        },
        fields=['name', 'customer', 'customer_name', 'posting_date', 'grand_total'],
        order_by='posting_date asc'
    )
    
    data = []
    for d in dns:
        so_item = frappe.db.sql("""
            SELECT so_detail FROM `tabDelivery Note Item`
            WHERE parent = %s AND so_detail IS NOT NULL
            LIMIT 1
        """, d.name)
        
        data.append({
            'customer': d.customer_name,
            'dn_name': d.name,
            'posting_date': d.posting_date,
            'amount': flt(d.grand_total, 2),
            'sales_order_item': so_item[0][0] if so_item else None
        })
    
    return {
        'title': _('Create Sales Invoices'),
        'button_label': _('Invoice'),
        'columns': [
            {'fieldname': 'select', 'label': '', 'width': 30},
            {'fieldname': 'customer', 'label': _('Customer')},
            {'fieldname': 'dn_name', 'label': _('Delivery Note')},
            {'fieldname': 'posting_date', 'label': _('Date')},
            {'fieldname': 'amount', 'label': _('Amount')},
            {'fieldname': 'action_btn', 'label': _('Actions')}
        ],
        'data': data,
        'row_actions': [
            {'action': 'create_invoice', 'label': _('Create Invoice'), 'icon': 'fa fa-file-text'},
            {'action': 'view_dn', 'label': _('View DN'), 'icon': 'fa fa-external-link'}
        ],
        'bulk_actions': [
            {'action': 'bulk_create_invoice', 'label': _('Create Invoices'), 'icon': 'fa fa-file-text'}
        ]
    }

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
    bom_data = frappe.db.get_value('BOM', {'item': item_code, 'is_active': 1, 'is_default': 1}, ['name', 'quantity'], as_dict=1)
    if not bom_data:
        return False # No BOM means we can't determine, treat as shortage/issue
        
    bom_no = bom_data.name
    bom_qty = flt(bom_data.quantity) or 1.0

    # Get RMs from BOM
    rms = frappe.db.get_all('BOM Item', filters={'parent': bom_no}, fields=['item_code', 'qty', 'uom'])
    
    for rm in rms:
        needed = (flt(rm.qty) / bom_qty) * flt(required_qty)
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
            qty_to_check = item.pending_qty if 'pending_qty' in item else item.qty
            if not check_rm_availability(item.item_code, qty_to_check):
                shortage_items.append({
                    'title': f"{item.customer_name} - {item.item_name}",
                    'description': f"Qty: {qty_to_check}",
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
            qty_to_check = item.pending_qty if 'pending_qty' in item else item.qty
            if check_rm_availability(item.item_code, qty_to_check):
                ready_items.append({
                    'title': f"{item.customer_name} - {item.item_name}",
                    'description': f"Qty: {qty_to_check}",
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
    
    data = []
    for po in pos:
        # Check for linked Sales Order Item in PO Items
        so_item = frappe.db.get_value('Purchase Order Item', {'parent': po.name}, 'sales_order_item')
        
        item_data = {
            'title': f"{po.supplier_name}",
            'description': f"PO: {po.name}",
        }
        
        if so_item:
            item_data['link'] = 'production-wizard'
            item_data['route_options'] = {
                'selected_item': so_item
            }
        else:
            item_data['link'] = 'Form/Purchase Order/' + po.name
            
        data.append(item_data)

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
        # Check for linked Sales Order Item in PO Items
        so_item = frappe.db.get_value('Purchase Order Item', {'parent': po.name}, 'sales_order_item')
        
        item_data = {
            'title': f"{po.supplier_name}",
            'description': f"PO: {po.name}",
        }
        
        if so_item:
            item_data['link'] = 'production-wizard'
            item_data['route_options'] = {
                'selected_item': so_item
            }
        else:
            item_data['link'] = 'Form/Purchase Order/' + po.name
            
        data.append(item_data)

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
        # Find linked Sales Order Item
        so_item = frappe.db.get_value('Subcontracting Inward Order Item', {'parent': o.name}, 'sales_order_item')
        
        item_data = {
            'title': f"{o.customer_name}",
            'description': f"Order: {o.name}",
        }
        
        if so_item:
            item_data['link'] = 'production-wizard'
            item_data['route_options'] = {
                'selected_item': so_item
            }
        else:
            item_data['link'] = 'Form/Subcontracting Inward Order/' + o.name

        data.append(item_data)
        
    return {
        'count': len(data),
        'items': data[:5],
        'label': 'Receive RM from Customer',
        'color': 'warning'
    }

def get_pending_delivery_items():
    # Sales Orders where items are manufactured (Work Order completed) and ready to deliver
    
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
        # Get SO Items pending delivery
        items = frappe.db.sql("""
            SELECT name, item_code, item_name, qty, delivered_qty
            FROM `tabSales Order Item`
            WHERE parent = %s AND qty > delivered_qty
        """, (o.name,), as_dict=1)
        
        for item in items:
            delivered_qty = flt(item.delivered_qty)
            pending_to_deliver = flt(item.qty) - delivered_qty
            
            # Check manufactured qty from Work Orders
            wo_data = frappe.db.sql("""
                SELECT COALESCE(SUM(produced_qty), 0) as produced
                FROM `tabWork Order`
                WHERE sales_order = %s 
                    AND sales_order_item = %s
                    AND docstatus = 1
            """, (o.name, item.name))
            
            manufactured_qty = flt(wo_data[0][0] if wo_data else 0)
            
            # Ready to deliver = manufactured - already delivered
            if manufactured_qty == 0:
                # No WO - check stock
                stock_qty = get_available_stock(item.item_code)
                ready_qty = min(stock_qty, pending_to_deliver)
            else:
                ready_qty = max(0, manufactured_qty - delivered_qty)
            
            # Only add if ready to deliver
            if ready_qty > 0:
                item_data = {
                    'title': f"{o.customer_name} - {item.item_name}",
                    'description': f"Ready: {ready_qty}",
                    'date': o.delivery_date,
                    'link': 'production-wizard',
                    'route_options': {
                        'invoice_status': 'Ready to Deliver',
                        'selected_item': item.name
                    }
                }
                data.append(item_data)
        
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
        # Find linked SO Item via DN Item
        # We need an SO item that corresponds to this DN.
        # DN Item -> so_detail (link to Sales Order Item)
        so_item = frappe.db.sql("""
            SELECT so_detail FROM `tabDelivery Note Item`
            WHERE parent = %s AND so_detail IS NOT NULL
            LIMIT 1
        """, (d.name,))
        
        item_name = so_item[0][0] if so_item else None
        
        item_data = {
            'title': f"{d.customer_name}",
            'description': f"DN: {d.name}",
        }
        
        if item_name:
            item_data['link'] = 'production-wizard'
            item_data['route_options'] = {
                'invoice_status': 'Ready to Invoice',
                'selected_item': item_name
            }
        else:
             item_data['link'] = 'Form/Delivery Note/' + d.name

        data.append(item_data)
        
    return {
        'count': len(data),
        'items': data[:5],
        'label': 'Pending Sales Invoices',
        'color': 'success'
    }


def get_pending_purchase_receipt_items():
    """Get pending Purchase Receipts for ordered items (excluding subcontracted POs)."""
    pos = frappe.db.sql("""
        SELECT 
            po.name, po.supplier_name, po.transaction_date
        FROM
            `tabPurchase Order` po
        WHERE
            po.docstatus = 1
            AND po.is_subcontracted = 0
            AND po.status NOT IN ('Closed', 'Completed', 'Cancelled')
            AND po.per_received < 100
        ORDER BY po.transaction_date ASC
        LIMIT 5
    """, as_dict=1)
    
    data = []
    for po in pos:
        data.append({
            'title': f"{po.supplier_name}",
            'description': f"PO: {po.name}",
            'date': po.transaction_date,
            'link': 'Form/Purchase Order/' + po.name
        })
        
    # Get total count
    count_result = frappe.db.sql("""
        SELECT COUNT(*) as count
        FROM `tabPurchase Order`
        WHERE docstatus = 1
            AND is_subcontracted = 0
            AND status NOT IN ('Closed', 'Completed', 'Cancelled')
            AND per_received < 100
    """)
    
    return {
        'count': count_result[0][0] if count_result else 0,
        'items': data,
        'label': 'Pending Purchase Receipt',
        'color': 'warning'
    }


def get_pending_purchase_receipt_fix_details():
    """Get detailed pending purchase receipt data for Fix dialog."""
    pos = frappe.db.sql("""
        SELECT 
            po.name, po.supplier, po.supplier_name, po.transaction_date
        FROM
            `tabPurchase Order` po
        WHERE
            po.docstatus = 1
            AND po.is_subcontracted = 0
            AND po.status NOT IN ('Closed', 'Completed', 'Cancelled')
            AND po.per_received < 100
        ORDER BY po.transaction_date ASC
    """, as_dict=1)
    
    data = []
    for po in pos:
        items = frappe.db.sql("""
            SELECT item_code, item_name, qty, received_qty, stock_uom
            FROM `tabPurchase Order Item`
            WHERE parent = %s AND (qty - received_qty) > 0
        """, po.name, as_dict=1)
        
        for item in items:
            data.append({
                'supplier': po.supplier_name,
                'po_name': po.name,
                'item_code': item.item_code,
                'item_name': item.item_name,
                'ordered_qty': flt(item.qty, 3),
                'received_qty': flt(item.received_qty, 3),
                'pending_qty': flt(item.qty - item.received_qty, 3),
                'uom': item.stock_uom,
                'po_date': po.transaction_date
            })
    
    return {
        'title': _('Receive Ordered Items'),
        'button_label': _('Receive'),
        'columns': [
            {'fieldname': 'select', 'label': '', 'width': 30},
            {'fieldname': 'supplier', 'label': _('Supplier')},
            {'fieldname': 'po_name', 'label': _('PO')},
            {'fieldname': 'item_name', 'label': _('Item')},
            {'fieldname': 'ordered_qty', 'label': _('Ordered')},
            {'fieldname': 'received_qty', 'label': _('Received')},
            {'fieldname': 'pending_qty', 'label': _('Pending')},
            {'fieldname': 'po_date', 'label': _('PO Date')},
            {'fieldname': 'action_btn', 'label': _('Actions')}
        ],
        'data': data,
        'row_actions': [
            {'action': 'create_pr', 'label': _('Create PR'), 'icon': 'fa fa-download'},
            {'action': 'view_po', 'label': _('View PO'), 'icon': 'fa fa-external-link'}
        ],
        'bulk_actions': []
    }


def get_pending_purchase_invoice_items():
    """Get pending Purchase Invoices for ordered items (both regular and subcontracted POs)."""
    # Get regular POs
    regular_pos = frappe.db.sql("""
        SELECT 
            po.name, po.supplier_name, po.transaction_date, 'Regular' as po_type
        FROM
            `tabPurchase Order` po
        WHERE
            po.docstatus = 1
            AND po.is_subcontracted = 0
            AND po.status NOT IN ('Closed', 'Cancelled')
            AND po.per_billed < 100
        ORDER BY po.transaction_date ASC
        LIMIT 3
    """, as_dict=1)
    
    # Get subcontracted POs
    subcontracted_pos = frappe.db.sql("""
        SELECT 
            po.name, po.supplier_name, po.transaction_date, 'Subcontracted' as po_type
        FROM
            `tabPurchase Order` po
        WHERE
            po.docstatus = 1
            AND po.is_subcontracted = 1
            AND po.status NOT IN ('Closed', 'Cancelled')
            AND po.per_billed < 100
        ORDER BY po.transaction_date ASC
        LIMIT 2
    """, as_dict=1)
    
    data = []
    for po in regular_pos + subcontracted_pos:
        data.append({
            'title': f"{po.supplier_name} ({po.po_type})",
            'description': f"PO: {po.name}",
            'date': po.transaction_date,
            'link': 'Form/Purchase Order/' + po.name
        })
        
    # Get total counts
    regular_count_result = frappe.db.sql("""
        SELECT COUNT(*) as count
        FROM `tabPurchase Order`
        WHERE docstatus = 1
            AND is_subcontracted = 0
            AND status NOT IN ('Closed', 'Cancelled')
            AND per_billed < 100
    """)
    regular_count = regular_count_result[0][0] if regular_count_result else 0
    
    subcontracted_count_result = frappe.db.sql("""
        SELECT COUNT(*) as count
        FROM `tabPurchase Order`
        WHERE docstatus = 1
            AND is_subcontracted = 1
            AND status NOT IN ('Closed', 'Cancelled')
            AND per_billed < 100
    """)
    subcontracted_count = subcontracted_count_result[0][0] if subcontracted_count_result else 0
    
    return {
        'count': regular_count + subcontracted_count,
        'items': data[:5],
        'label': 'Pending Purchase Invoice',
        'color': 'warning'
    }


def get_pending_purchase_invoice_fix_details():
    """Get detailed pending purchase invoice data for Fix dialog."""
    # Get regular POs
    regular_pos = frappe.db.sql("""
        SELECT 
            po.name, po.supplier, po.supplier_name, po.transaction_date, 
            po.grand_total, po.per_billed, 'Regular' as po_type
        FROM
            `tabPurchase Order` po
        WHERE
            po.docstatus = 1
            AND po.is_subcontracted = 0
            AND po.status NOT IN ('Closed', 'Cancelled')
            AND po.per_billed < 100
        ORDER BY po.transaction_date ASC
    """, as_dict=1)
    
    # Get subcontracted POs
    subcontracted_pos = frappe.db.sql("""
        SELECT 
            po.name, po.supplier, po.supplier_name, po.transaction_date, 
            po.grand_total, po.per_billed, 'Subcontracted' as po_type
        FROM
            `tabPurchase Order` po
        WHERE
            po.docstatus = 1
            AND po.is_subcontracted = 1
            AND po.status NOT IN ('Closed', 'Cancelled')
            AND po.per_billed < 100
        ORDER BY po.transaction_date ASC
    """, as_dict=1)
    
    data = []
    for po in regular_pos + subcontracted_pos:
        pending_amount = flt(po.grand_total) * (100 - flt(po.per_billed)) / 100
        data.append({
            'supplier': po.supplier_name,
            'po_name': po.name,
            'po_type': po.po_type,
            'po_date': po.transaction_date,
            'total_amount': flt(po.grand_total, 2),
            'billed_percent': flt(po.per_billed, 2),
            'pending_amount': flt(pending_amount, 2)
        })
    
    return {
        'title': _('Create Purchase Invoices'),
        'button_label': _('Invoice'),
        'columns': [
            {'fieldname': 'select', 'label': '', 'width': 30},
            {'fieldname': 'supplier', 'label': _('Supplier')},
            {'fieldname': 'po_name', 'label': _('PO')},
            {'fieldname': 'po_type', 'label': _('Type')},
            {'fieldname': 'po_date', 'label': _('PO Date')},
            {'fieldname': 'total_amount', 'label': _('Total Amount')},
            {'fieldname': 'billed_percent', 'label': _('Billed %')},
            {'fieldname': 'pending_amount', 'label': _('Pending Amount')},
            {'fieldname': 'action_btn', 'label': _('Actions')}
        ],
        'data': data,
        'row_actions': [
            {'action': 'create_pi', 'label': _('Create Invoice'), 'icon': 'fa fa-file-text'},
            {'action': 'view_po', 'label': _('View PO'), 'icon': 'fa fa-external-link'}
        ],
        'bulk_actions': []
    }

