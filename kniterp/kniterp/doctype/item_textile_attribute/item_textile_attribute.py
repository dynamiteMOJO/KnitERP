# Copyright (c) 2025, Kartik and contributors
# For license information, please see license.txt

# import frappe
import frappe
from frappe.model.document import Document


class ItemTextileAttribute(Document):
	def validate(self):
		self.populate_from_textile_attribute()
		self.validate_value_fields()
		self.build_display_value()

	def populate_from_textile_attribute(self):
		if not self.kniterp_attribute:
			return

		attr = frappe.get_doc("Textile Attribute", self.kniterp_attribute)

		# Copy config flags
		self.kniterp_sequence = attr.kniterp_sequence
		self.kniterp_affects_naming = attr.kniterp_affects_naming
		self.kniterp_affects_code = attr.kniterp_affects_code
		self.kniterp_searchable = attr.kniterp_searchable
		self.kniterp_is_active = attr.kniterp_is_active


	def validate_value_fields(self):
		attr = frappe.get_doc("Textile Attribute", self.kniterp_attribute)

		if attr.kniterp_field_type == "Select":
			if not self.kniterp_value:
				frappe.throw(f"Value is required for attribute {attr.attribute_name}")
			self.kniterp_numeric_value = None

		elif attr.kniterp_field_type in ("Int", "Float", "Data"):
			if self.kniterp_numeric_value is None:
				frappe.throw(f"Numeric Value is required for attribute {attr.attribute_name}")
			self.kniterp_value = None

	def build_display_value(self):
		attr = frappe.get_doc("Textile Attribute", self.kniterp_attribute)

		if attr.kniterp_field_type == "Select" and self.kniterp_value:
			self.kniterp_display_value = self.kniterp_value

		elif attr.kniterp_field_type in ("Int", "Float", "Data") and self.kniterp_numeric_value is not None:
			self.kniterp_display_value = self.kniterp_numeric_value
