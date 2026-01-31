import frappe
from frappe import _
from frappe.utils import nowdate, getdate, flt
from erpnext.accounts.utils import get_fiscal_year

@frappe.whitelist()
def get_dashboard_metrics():
    """
    Fetch all metrics for the Home dashboard.
    """
    metrics = {}
    
    # Fiscal Year Dates
    today = nowdate()
    # frappe won't directly give the start date of the fiscal year easily without passing a specific year or date
    # but we can get it from the 'Fiscal Year' doctype or using erpnext helper
    
    try:
        fy_details = get_fiscal_year(today)
        fy_start_date = fy_details[1]
        fy_end_date = fy_details[2]
    except Exception:
        # Fallback to start of current year if hrms/erpnext helper fails
        fy_start_date = f"{getdate(today).year}-01-01"
        fy_end_date = f"{getdate(today).year}-12-31"

    # 1. Sales Metrics
    metrics['sales'] = {
        'active_orders': frappe.db.count('Sales Order', {
            'docstatus': 1,
            'is_subcontracted': 0,
            'status': ['not in', ['Closed', 'Completed', 'Cancelled']]
        }),
        'orders_this_fy': frappe.db.count('Sales Order', {
            'docstatus': 1,
            'is_subcontracted': 0,
            'status': ['!=', 'Cancelled'],
            'transaction_date': ['between', [fy_start_date, fy_end_date]]
        }),
        'urgent_count': frappe.db.count('Sales Order', {
            'docstatus': 1,
            'is_subcontracted': 0,
            'status': ['not in', ['Closed', 'Completed', 'Cancelled']],
            'delivery_date': ['<', today]
        })
    }

    # 2. Purchase Metrics
    metrics['purchase'] = {
        'pending_orders': frappe.db.count('Purchase Order', {
            'docstatus': 1,
            'is_subcontracted': 0,
            'status': ['not in', ['Closed', 'Completed', 'Cancelled']]
        }),
        'orders_this_fy': frappe.db.count('Purchase Order', {
            'docstatus': 1,
            'is_subcontracted': 0,
            'status': ['!=', 'Cancelled'],
            'transaction_date': ['between', [fy_start_date, fy_end_date]]
        }),
        'urgent_count': frappe.db.count('Purchase Order', {
            'docstatus': 1,
            'is_subcontracted': 0,
            'status': ['not in', ['Closed', 'Completed', 'Cancelled']],
            'schedule_date': ['<', today]
        })
    }

    # 3. Job Work Metrics
    metrics['job_work'] = {
        'inward_active': frappe.db.count('Subcontracting Inward Order', {
            'docstatus': 1,
            'status': ['not in', ['Closed', 'Completed', 'Cancelled']]
        }),
        'outward_active': frappe.db.count('Subcontracting Order', {
            'docstatus': 1,
            'status': ['not in', ['Closed', 'Completed', 'Cancelled']]
        })
    }

    # 4. Item Metrics
    metrics['items'] = {
        'stock_items': frappe.db.count('Item', {'is_stock_item': 1, 'disabled': 0}),
        'service_items': frappe.db.count('Item', {'is_stock_item': 0, 'disabled': 0})
    }

    # 5. BOM Metrics
    metrics['bom'] = {
        'active_boms': frappe.db.count('BOM', {'is_active': 1, 'docstatus': 1}),
        'active_jw_boms': frappe.db.count('Subcontracting BOM', {'is_active': 1, 'docstatus': 1})
    }

    # 6. Employee Metrics
    metrics['employees'] = {
        'present_today': frappe.db.count('Attendance', {
            'attendance_date': today,
            'status': ['in', ['Present', 'Half Day']],
            'docstatus': 1
        }),
        'absent_today': frappe.db.count('Attendance', {
            'attendance_date': today,
            'status': 'Absent',
            'docstatus': 1
        })
    }

    # User Info
    user = frappe.session.user
    first_name = frappe.db.get_value('User', user, 'first_name') or 'User'
    full_name = frappe.db.get_value('User', user, 'full_name') or first_name

    metrics['user'] = {
        'full_name': full_name,
        'first_name': first_name
    }

    return metrics
