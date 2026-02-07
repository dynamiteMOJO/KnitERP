
import frappe

def clear_all_transactions():
    """
    Clears all transactional data to reset stock and accounting.
    1. Removes links manually to break circular dependencies.
    2. Deletes Ledgers.
    3. Deletes Transaction Documents.
    4. Clears Orphans.
    """
    
    # 1. Break Dependencies: Clear Ledgers first
    ledgers = [
        "Stock Ledger Entry", "GL Entry", "Repost Item Valuation", 
        "Payment Ledger Entry", "Serial No", "Batch", "Bin",
        "BOM Update Log", "Stock Entry Detail", "Stock Reservation Entry"
    ]
    print("Pre-wiping Ledgers to break dependencies...")
    for dt in ledgers:
        try:
            if frappe.db.exists("DocType", dt):
                frappe.db.delete(dt)
            elif dt == "Stock Entry Detail": # Child table often doesn't have DocType record
                frappe.db.sql("DELETE FROM `tabStock Entry Detail`")
        except Exception as e:
            print(f"Could not clear {dt}: {e}")
    frappe.db.commit()

    # 2. Break Circular Links (Job Card <-> PO <-> WO)
    print("Unlinking Job Cards and Work Orders...")
    try:
        frappe.db.sql("UPDATE `tabJob Card` SET work_order = NULL")
        frappe.db.sql("UPDATE `tabWork Order` SET sales_order = NULL")
        frappe.db.sql("UPDATE `tabPurchase Order Item` SET job_card = NULL")
        frappe.db.commit()
    except Exception as e:
        print(f"Error unlinking: {e}")

    # 3. Transaction Doctypes to Delete
    doctypes_to_delete = [
        "Stock Entry", 
        "Delivery Note", 
        "Sales Invoice", 
        "Purchase Receipt",
        "Purchase Invoice", 
        "Payment Entry", 
        "Journal Entry", 
        "Material Request",
        
        # Operations
        "Job Card", 
        "Work Order", 
        
        "Quality Inspection", 
        "Serial and Batch Bundle", 
        "Subcontracting Receipt", 
        "Subcontracting Order", 
        "Subcontracting Inward Order",
        "Stock Reservation Entry",
        
        # Orders
        "Sales Order", 
        "Purchase Order", 
        
        # "BOM", "Item Price" # User wants to keep these master data
    ]

    print("Starting Transaction Cleanup...")

    for dt in doctypes_to_delete:
        try:
            # Get Submitted Docs (docstatus=1)
            submitted_docs = frappe.get_all(dt, filters={"docstatus": 1}, pluck="name")
            if submitted_docs:
                print(f"Cancelling {len(submitted_docs)} submitted {dt}s...")
                for name in submitted_docs:
                    try:
                         # Force cancel if needed, but try standard first
                        doc = frappe.get_doc(dt, name)
                        doc.cancel()
                    except Exception as e:
                        print(f"  [FAIL] Could not cancel {dt} {name}: {e}")

            # Get Cancelled (2) or Draft (0) Docs
            remaining_docs = frappe.get_all(dt, filters={"docstatus": ["in", [0, 2]]}, pluck="name")
            if remaining_docs:
                print(f"Deleting {len(remaining_docs)} draft/cancelled {dt}s...")
                for name in remaining_docs:
                    try:
                        frappe.delete_doc(dt, name)
                    except Exception as e:
                        print(f"  [FAIL] Could not delete {dt} {name}: {e}")

        except Exception as e:
            print(f"Major Error checking {dt}: {e}")

    # 4. Post-wipe Ledgers again to be absolutely sure
    print("Post-wiping Ledgers...")
    for dt in ledgers:
        try:
            if frappe.db.exists("DocType", dt):
                frappe.db.delete(dt)
        except Exception as e:
            pass

    frappe.db.commit()

    # 5. Clean up Orphans (cases where parent was deleted via db.delete)
    print("Cleaning up Orphaned Child Records...")
    orphan_queries = [
        "DELETE FROM `tabBOM Item` WHERE parent NOT IN (SELECT name FROM tabBOM)",
        "DELETE FROM `tabBOM Operation` WHERE parent NOT IN (SELECT name FROM tabBOM)",
        "DELETE FROM `tabStock Entry Detail` WHERE parent NOT IN (SELECT name FROM `tabStock Entry`) AND parent NOT LIKE 'old-%'"
    ]
    for q in orphan_queries:
        try:
            frappe.db.sql(q)
        except Exception:
            pass

    frappe.db.commit()
    print("Cleanup Complete. Site is ready for new transactions.")

# Define an alias execution
def execute():
    clear_all_transactions()
