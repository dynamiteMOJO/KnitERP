import frappe
from erpnext.subcontracting.doctype.subcontracting_inward_order.subcontracting_inward_order_dashboard import get_data as get_standard_data

def get_data(data=None):
    if not data:
        data = get_standard_data()
    
    # Add Delivery Note to Transactions group
    for transaction in data.get("transactions", []):
        if transaction.get("label") == "Transactions":
            if "Delivery Note" not in transaction.get("items", []):
                transaction["items"].append("Delivery Note")
            break
            
    # Handle custom fieldname linkage
    non_standard = data.get("non_standard_fieldnames", {})
    non_standard["Delivery Note"] = "custom_subcontracting_inward_order"
    data["non_standard_fieldnames"] = non_standard
    
    return data
