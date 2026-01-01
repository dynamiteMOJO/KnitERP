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