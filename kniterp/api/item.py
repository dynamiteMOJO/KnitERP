import frappe

def enforce_batch_tracking_for_fabric_yarn(doc, method=None):
    """
    Called on `before_save` doc event for Item.
    Forces has_batch_no=1 if custom_item_classification is Fabric or Yarn.
    """
    if doc.custom_item_classification in ("Fabric", "Yarn"):
        doc.has_batch_no = 1