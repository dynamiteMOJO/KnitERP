import frappe
import json

@frappe.whitelist()
def find_exact_items(classification, attributes):
    import json

    if isinstance(attributes, str):
        attributes = json.loads(attributes)

    if not attributes:
        return []

    conditions = []
    values = []

    for a in attributes:
        if a.get("numeric_value") is not None:
            conditions.append("""
                (ita.kniterp_attribute = %s AND ita.kniterp_numeric_value = %s)
            """)
            values.extend([a["attribute"], a["numeric_value"]])

        else:
            conditions.append("""
                (ita.kniterp_attribute = %s AND ita.kniterp_value = %s)
            """)
            values.extend([a["attribute"], a["value"]])

    condition_sql = " OR ".join(conditions)
    selected_count = len(attributes)

    sql = f"""
        SELECT
            i.name AS item_code,
            i.item_name,
            COUNT(DISTINCT ita.kniterp_attribute) AS match_count,
            (
                SELECT COUNT(*)
                FROM `tabItem Textile Attribute` ita2
                WHERE ita2.parent = i.name
            ) AS total_attr_count
        FROM `tabItem` i
        INNER JOIN `tabItem Textile Attribute` ita
            ON ita.parent = i.name
        WHERE
            i.custom_item_classification = %s
            AND i.disabled = 0
            AND ({condition_sql})
        GROUP BY i.name
        HAVING match_count = %s
    """

    values = [classification] + values + [selected_count]

    return frappe.db.sql(sql, values, as_dict=True)


@frappe.whitelist()
def search_textile_attribute_values(txt, classification):

    return frappe.db.sql("""
        SELECT
            tav.name,
            tav.kniterp_value,
            tav.kniterp_short_code,

            ta.name AS attribute,
            ta.kniterp_attribute_name,
            ta.kniterp_field_type,
            ta.kniterp_sequence,
            ta.kniterp_affects_naming,
            ta.kniterp_affects_code

        FROM `tabTextile Attribute Value` tav
        INNER JOIN `tabTextile Attribute` ta
            ON ta.name = tav.kniterp_attribute
        INNER JOIN `tabItem Attribute Applies To` ap
            ON ap.parent = ta.name

        WHERE
            ta.kniterp_is_active = 1
            AND tav.kniterp_is_active = 1
            AND ap.item_attribute_applies_to = %s
            AND (
                tav.kniterp_value LIKE %s
                OR tav.kniterp_short_code LIKE %s
            )

        ORDER BY ta.kniterp_sequence, tav.kniterp_sort_order
        LIMIT 20
    """, (
        classification,
        f"%{txt}%",
        f"%{txt}%"
    ), as_dict=True)