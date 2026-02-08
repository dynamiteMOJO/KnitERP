import frappe
from erpnext.stock.doctype.item.item import Item
from frappe.utils import strip

class CustomItem(Item):

    def autoname(self):        
        if self.custom_item_classification in ("Fabric", "Yarn"):
            self.process_textile_attributes()
            self.build_textile_code()

            # item_code IS the name
            self.item_code = strip(self.item_code)
            self.name = self.item_code
            
            if self.is_customer_provided_item:
                if not self.item_code.endswith(" - CP"):
                    self.item_code = strip(f"{self.item_code} - CP")
                    self.name = self.item_code
        else:
            super().autoname()

    def validate(self):        
        if self.custom_item_classification in ("Fabric", "Yarn"):
            self.process_textile_attributes()
            self.build_textile_name()
        
        if self.custom_item_classification == "Fabric":
            self.is_sub_contracted_item = 1

        if self.item_group == "Services":
            self.is_stock_item = 0

        super().validate()
        

    def process_textile_attributes(self):
        if self.custom_item_classification not in ("Fabric", "Yarn"):
            return

        seen_attributes = set()

        for row in self.custom_textile_attributes:
            if not row.kniterp_attribute:
                continue

            # Duplicate check
            if row.kniterp_attribute in seen_attributes:
                frappe.throw(f"Duplicate attribute: {row.kniterp_attribute}")
            seen_attributes.add(row.kniterp_attribute)

            attr = frappe.get_doc("Textile Attribute", row.kniterp_attribute)

            # Copy config
            row.kniterp_sequence = attr.kniterp_sequence
            row.kniterp_affects_naming = attr.kniterp_affects_naming
            row.kniterp_affects_code = attr.kniterp_affects_code
            row.kniterp_searchable = attr.kniterp_searchable
            row.kniterp_is_active = attr.kniterp_is_active

            # Value enforcement
            if attr.kniterp_field_type == "Select":
                if not row.kniterp_value:
                    frappe.throw(f"Value required for {attr.attribute_name}")
                row.kniterp_numeric_value = None
                row.kniterp_display_value = row.kniterp_value

            elif attr.kniterp_field_type in ("Int", "Float"):
                if row.kniterp_numeric_value is None:
                    frappe.throw(f"Numeric value required for {attr.attribute_name}")
                row.kniterp_value = None
                row.kniterp_display_value = str(row.kniterp_numeric_value)


    def build_textile_name(self):
        if self.custom_item_classification not in ("Fabric", "Yarn"):
            return

        parts = []

        # Sort attributes by sequence
        attrs = sorted(
            self.custom_textile_attributes,
            key=lambda x: x.kniterp_sequence or 0
        )

        for row in attrs:
            if not row.kniterp_affects_naming:
                continue

            if row.kniterp_display_value:
                parts.append(row.kniterp_display_value)

        self.item_name = " ".join(parts)

    def build_textile_code(self):
        if self.custom_item_classification not in ("Fabric", "Yarn"):
            return

        parts = []

        prefix = "FB" if self.custom_item_classification == "Fabric" else "YR"
        attrs = sorted(
            self.custom_textile_attributes,
            key=lambda x: x.kniterp_sequence or 0
        )

        for row in attrs:
            if not row.kniterp_affects_code:
                continue

            if row.kniterp_value:
                parts.append(row.kniterp_short_code)
            elif row.kniterp_numeric_value is not None:
                parts.append(str(int(row.kniterp_numeric_value)))

        self.item_code = f"{prefix}-" + "-".join(parts)


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
        base_code = self.item_code.replace(" - CP", "").strip()
        cp_code = f"{base_code} - CP"

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
        base_code = self.item_code.replace(" - CP", "").strip()
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
            "item_name": self.item_name, # Name usually matches code for these or follows naming rule
            "item_group": self.item_group,
            "stock_uom": self.stock_uom,
            "gst_hsn_code": self.gst_hsn_code,
            "include_item_in_manufacturing": 1,
            
            # Allow this item to have alternatives
            "allow_alternative_item": 1,
            
            # CP vs Base logic
            "is_customer_provided_item": 1 if is_cp else 0,
            "is_purchase_item": 0 if is_cp else 1,
            "is_sales_item": 0, # Usually neither are sales items? Or maybe Base is. 
                                # Original code set 0 for Base created from CP.
                                # Let's stick to: CP is never sales, Base *could* be but let's default to 0 for auto-creation safe-side.
            
            "default_material_request_type": "Customer Provided" if is_cp else "Purchase",
            
            "is_stock_item": self.is_stock_item,
            "custom_item_classification": self.custom_item_classification,
            "end_of_life": self.end_of_life,
        })
        
        # Copy textile attributes
        for row in self.custom_textile_attributes:
            item_doc.append("custom_textile_attributes", {
                "kniterp_attribute": row.kniterp_attribute,
                "kniterp_value": row.kniterp_value,
                "kniterp_numeric_value": row.kniterp_numeric_value,
                "kniterp_display_value": row.kniterp_display_value,
                "kniterp_affects_naming": row.kniterp_affects_naming,
                "kniterp_affects_code": row.kniterp_affects_code,
                "kniterp_searchable": row.kniterp_searchable,
                "kniterp_sequence": row.kniterp_sequence,
                "kniterp_is_active": row.kniterp_is_active,
                "kniterp_short_code": row.kniterp_short_code,
                "kniterp_field_type": row.kniterp_field_type,
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