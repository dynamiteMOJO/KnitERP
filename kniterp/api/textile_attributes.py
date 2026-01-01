import frappe

@frappe.whitelist()
def get_textile_attributes_for(classification):
    """
    Returns Textile Attributes applicable to Fabric / Yarn
    """

    return frappe.db.sql("""
        SELECT
            ta.name,
            ta.kniterp_attribute_name,
            ta.kniterp_field_type,
            ta.kniterp_sequence
        FROM `tabTextile Attribute` ta
        INNER JOIN `tabItem Attribute Applies To` ap
            ON ap.parent = ta.name
        WHERE
            ta.kniterp_is_active = 1
            AND ap.parenttype = 'Textile Attribute'
            AND ap.parentfield = 'kniterp_applies_to'
            AND ap.item_attribute_applies_to = %s
        ORDER BY ta.kniterp_sequence ASC
    """, classification, as_dict=True)


@frappe.whitelist()
def get_attribute_values(attribute):

    return frappe.db.sql("""
        SELECT
            tav.name,
            tav.kniterp_value,
            tav.kniterp_short_code,
            tav.kniterp_sort_order
        FROM `tabTextile Attribute Value` tav
        WHERE
            tav.kniterp_attribute = %s
            AND tav.kniterp_is_active = 1
        ORDER BY tav.kniterp_sort_order ASC
    """, attribute, as_dict=True)