import frappe
import json

@frappe.whitelist()
def find_exact_items(classification, attributes):
    """
    Find items where ALL attributes match exactly.
    attributes = JSON list:
    [
      {"attribute": "GSM", "numeric_value": 180},
      {"attribute": "Fabric Structure", "value": "Single Jersey"}
    ]
    """

    if isinstance(attributes, str):
        attributes = json.loads(attributes)

    if not attributes:
        return []

    attr_count = len(attributes)

    # Build dynamic conditions
    conditions = []
    values = []

    for a in attributes:
        if "numeric_value" in a and a["numeric_value"] is not None:
            conditions.append("""
                (ita.kniterp_attribute = %s AND ita.kniterp_numeric_value = %s)
            """)
            values.extend([a["attribute"], a["numeric_value"]])

        elif "value" in a and a["value"]:
            conditions.append("""
                (ita.kniterp_attribute = %s AND ita.kniterp_value = %s)
            """)
            values.extend([a["attribute"], a["value"]])

    condition_sql = " OR ".join(conditions)

    sql = f"""
        SELECT
            i.name AS item_code,
            i.item_name,
            COUNT(ita.name) AS match_count
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

    values = [classification] + values + [attr_count]

    return frappe.db.sql(sql, values, as_dict=True)