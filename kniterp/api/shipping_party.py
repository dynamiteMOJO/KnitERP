import frappe
from frappe import _


def validate_shipping_party(doc, method):
    """before_validate hook for Sales Order, Delivery Note, Sales Invoice.

    When custom_shipping_party is set, ensures:
    - custom_shipping_party_name is populated from the Customer record
    - shipping_address_name is auto-filled if empty (uses shipping party's default address)
    - shipping_address_name belongs to the shipping party (validated via Dynamic Link)
    """
    if not doc.get("custom_shipping_party"):
        doc.custom_shipping_party_name = ""
        return

    ship_to = doc.custom_shipping_party

    doc.custom_shipping_party_name = (
        frappe.db.get_value("Customer", ship_to, "customer_name") or ship_to
    )

    if not doc.get("shipping_address_name"):
        default_addr = _get_default_address("Customer", ship_to)
        if default_addr:
            doc.shipping_address_name = default_addr

    if doc.get("shipping_address_name") and not _address_belongs_to(
        "Customer", ship_to, doc.shipping_address_name
    ):
        frappe.throw(
            _("Shipping Address {0} does not belong to Shipping Party {1}. "
              "Please select an address linked to {1}.").format(
                frappe.bold(doc.shipping_address_name),
                frappe.bold(ship_to),
            )
        )


def validate_deliver_to_customer(doc, method):
    """before_validate hook for Purchase Order, Subcontracting Order.

    When custom_deliver_to_customer is set, ensures:
    - custom_deliver_to_customer_name is populated from the Customer record
    - custom_deliver_to_address is auto-filled if empty
    - custom_deliver_to_address belongs to the delivery customer
    """
    if not doc.get("custom_deliver_to_customer"):
        doc.custom_deliver_to_customer_name = ""
        return

    deliver_to = doc.custom_deliver_to_customer

    doc.custom_deliver_to_customer_name = (
        frappe.db.get_value("Customer", deliver_to, "customer_name") or deliver_to
    )

    if not doc.get("custom_deliver_to_address"):
        default_addr = _get_default_address("Customer", deliver_to)
        if default_addr:
            doc.custom_deliver_to_address = default_addr

    if doc.get("custom_deliver_to_address") and not _address_belongs_to(
        "Customer", deliver_to, doc.custom_deliver_to_address
    ):
        frappe.throw(
            _("Delivery Address {0} does not belong to Delivery Party {1}. "
              "Please select an address linked to {1}.").format(
                frappe.bold(doc.custom_deliver_to_address),
                frappe.bold(deliver_to),
            )
        )


def _get_default_address(party_type, party_name):
    """Return the primary shipping address for a party, falling back to primary billing address."""
    linked = frappe.db.sql(
        """
        SELECT parent FROM `tabDynamic Link`
        WHERE link_doctype = %s AND link_name = %s AND parenttype = 'Address'
        """,
        (party_type, party_name),
        pluck=True,
    )
    if not linked:
        return None

    return frappe.db.get_value(
        "Address",
        filters={"name": ("in", linked), "disabled": 0},
        fieldname="name",
        order_by="is_shipping_address desc, is_primary_address desc, creation asc",
    )


def _address_belongs_to(party_type, party_name, address_name):
    """Return True if address_name is linked to the given party via Dynamic Link."""
    return bool(
        frappe.db.exists(
            "Dynamic Link",
            {
                "parenttype": "Address",
                "parent": address_name,
                "link_doctype": party_type,
                "link_name": party_name,
            },
        )
    )
