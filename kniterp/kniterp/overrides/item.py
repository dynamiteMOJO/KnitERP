import frappe
from erpnext.stock.doctype.item.item import Item
from frappe.utils import strip


def _get_cp_suffix():
    from kniterp.kniterp.doctype.kniterp_settings.kniterp_settings import KnitERPSettings
    return KnitERPSettings.get_settings().cp_item_suffix or " - CP"


class CustomItem(Item):

    def autoname(self):
        if self.custom_item_classification in ("Fabric", "Yarn"):
            # item_code IS the name (set by Composer)
            self.item_code = strip(self.item_code)
            self.name = self.item_code

            cp_suffix = _get_cp_suffix()
            if self.is_customer_provided_item:
                if not self.item_code.endswith(cp_suffix):
                    self.item_code = strip(f"{self.item_code}{cp_suffix}")
                    self.name = self.item_code
        else:
            super().autoname()

    def validate(self):        
        if self.custom_item_classification == "Fabric":
            self.is_sub_contracted_item = 1

        if self.item_group == "Services":
            self.is_stock_item = 0

        super().validate()
        

    def after_insert(self):
        # Handle Yarn dual creation logic
        if self.custom_item_classification == "Yarn":
            self.ensure_dual_yarn_versions()
        # Fallback for other CP items (legacy support if needed, or remove if Yarn is the only use case)
        elif self.is_customer_provided_item:
             # Retain original behavior for non-Yarn items if desired, 
             # currently the requirement specified Yarn specifically.
             self.create_purchase_item()

    def ensure_dual_yarn_versions(self):
        """
        Ensures both Base and CP versions exist for Yarn items.
        Links them as Item Alternatives.
        """
        cp_suffix = _get_cp_suffix()
        base_code = self.item_code.replace(cp_suffix, "").strip()
        cp_code = f"{base_code}{cp_suffix}"

        # Fix ValidationError: Enable substitution on the current item
        if not self.allow_alternative_item:
            frappe.db.set_value("Item", self.name, "allow_alternative_item", 1)
            self.allow_alternative_item = 1 # Update instance for subsequent logic

        if self.is_customer_provided_item:
             # Current is CP, create Base if missing
             if not frappe.db.exists("Item", base_code):
                 self.create_base_item(base_code)
        else:
             # Current is Base, create CP if missing
             if not frappe.db.exists("Item", cp_code):
                 self.create_cp_item(cp_code)
        
        # Link as Item Alternative
        self.create_item_alternative(base_code, cp_code)

    def create_base_item(self, item_code):
        # Create a purchasable Base item from the current CP item
        self.create_variant_item(item_code, is_cp=False)

    def create_cp_item(self, item_code):
        # Create a Customer Provided item from the current Base item
        self.create_variant_item(item_code, is_cp=True)

    def create_purchase_item(self):
        # Legacy method kept for non-Yarn items if they use this flow
        cp_suffix = _get_cp_suffix()
        base_code = self.item_code.replace(cp_suffix, "").strip()
        if frappe.db.exists("Item", base_code):
            return
        
        self.create_variant_item(base_code, is_cp=False)

    def create_variant_item(self, new_item_code, is_cp):
        """
        Generic method to create a variant (Base or CP) of the current item.
        """
        item_doc = frappe.get_doc({
            "doctype": "Item",
            "item_code": new_item_code,
            "item_name": self.item_name,
            "item_group": self.item_group,
            "stock_uom": self.stock_uom,
            "gst_hsn_code": self.gst_hsn_code,
            "include_item_in_manufacturing": 1,
            
            # Allow this item to have alternatives
            "allow_alternative_item": 1,
            
            # CP vs Base logic
            "is_customer_provided_item": 1 if is_cp else 0,
            "is_purchase_item": 0 if is_cp else 1,
            "is_sub_contracted_item": 1 if is_cp else 0,
            "is_sales_item": 0,
            
            "default_material_request_type": "Customer Provided" if is_cp else "Purchase",
            
            "is_stock_item": self.is_stock_item,
            "custom_item_classification": self.custom_item_classification,
            "end_of_life": self.end_of_life,
        })
            
        item_doc.insert(ignore_permissions=True)

    def create_item_alternative(self, item_code, alternative_item_code):
        if not frappe.db.exists("Item Alternative", {"item_code": item_code, "alternative_item_code": alternative_item_code}):
            alt = frappe.get_doc({
                "doctype": "Item Alternative",
                "item_code": item_code,
                "alternative_item_code": alternative_item_code,
                "two_way": 1
            })
            alt.insert(ignore_permissions=True)