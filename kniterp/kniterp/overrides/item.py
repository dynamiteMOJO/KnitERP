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
        # Create purchase item only for CP item
        if self.is_customer_provided_item:
            self.create_purchase_item()

    def create_purchase_item(self):
        base_code = self.item_code.replace(" - CP", "").strip()

        # Safety: don’t duplicate
        if frappe.db.exists("Item", base_code):
            return

        purchase_item = frappe.get_doc({
            "doctype": "Item",
            "item_code": base_code,
            "item_name": self.item_name,
            "item_group": self.item_group,
            "stock_uom": self.stock_uom,
            "gst_hsn_code": self.gst_hsn_code,
            "include_item_in_manufacturing": self.include_item_in_manufacturing,
            "is_sales_item": self.is_sales_item,

            # very important
            "is_customer_provided_item": 0,
            "is_stock_item": self.is_stock_item,
            "default_material_request_type": "Purchase",

            # buying enabled
            "is_purchase_item": 1,
            "is_sales_item": 0,

            # copy anything else you need
            "custom_item_classification": self.custom_item_classification,
            "end_of_life": self.end_of_life,
        })

        # ----------------------------
        # COPY TEXTILE ATTRIBUTES
        # ----------------------------
        for row in self.custom_textile_attributes:
            purchase_item.append("custom_textile_attributes", {
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

        purchase_item.insert(ignore_permissions=True)