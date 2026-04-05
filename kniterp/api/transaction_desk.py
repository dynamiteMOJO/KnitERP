import frappe
from frappe import _
from frappe.utils import cint


# ──────────────────────────────────────────────────────────────
# Type classification helpers
# ──────────────────────────────────────────────────────────────

TRANSPORT_FIELDS = ('transporter', 'transporter_name', 'gst_transporter_id',
                    'vehicle_no', 'lr_no', 'lr_date', 'distance')

SALES_TYPES = ("sales-order", "sales-invoice", "delivery-note", "credit-note", "job-work-in")
PURCHASE_TYPES = ("purchase-order", "purchase-invoice", "purchase-receipt", "debit-note", "job-work-out")
ITEM_TYPES = SALES_TYPES + PURCHASE_TYPES + ("stock-entry",)
PAYMENT_TYPES = ("payment-receive", "payment-pay")
JOURNAL_TYPES = ("journal-entry", "contra-entry")
NO_WAREHOUSE_TYPES = PAYMENT_TYPES + JOURNAL_TYPES


# ──────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_item_details(item_code: str, voucher_type: str = "") -> dict:
    """Fetch item name, UOM, description, and price for transaction desk."""
    item = frappe.get_cached_doc("Item", item_code)
    result = {
        "item_name": item.item_name or "",
        "stock_uom": item.stock_uom or "",
        "description": (item.description or "").strip(),
    }

    # Get price based on voucher type (selling for sales-side, buying for purchase-side)
    is_buying = voucher_type in PURCHASE_TYPES
    price_filters = {"item_code": item_code}
    if is_buying:
        price_filters["buying"] = 1
    else:
        price_filters["selling"] = 1

    price = frappe.db.get_value("Item Price", price_filters, "price_list_rate")
    result["price_list_rate"] = frappe.utils.flt(price) if price else 0

    return result


@frappe.whitelist()
def get_defaults(voucher_type: str) -> dict:
    """Return smart defaults for the current user and company."""
    company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
    if not company:
        companies = frappe.get_all("Company", limit=1, pluck="name")
        company = companies[0] if companies else None

    if not company:
        frappe.throw(_("No company found. Please set up a company first."))

    company_doc = frappe.get_cached_doc("Company", company)

    defaults = {
        "company": company,
        "currency": company_doc.default_currency,
        "cost_center": company_doc.cost_center,
        "posting_date": frappe.utils.today(),
    }

    # Warehouse defaults
    default_wh = frappe.db.get_single_value("Stock Settings", "default_warehouse") or ""
    if voucher_type in SALES_TYPES:
        defaults["warehouse"] = default_wh
    elif voucher_type in PURCHASE_TYPES:
        defaults["warehouse"] = default_wh
    elif voucher_type == "stock-entry":
        defaults["warehouse"] = default_wh

    # Tax templates
    if voucher_type in SALES_TYPES:
        templates = frappe.get_all(
            "Sales Taxes and Charges Template",
            filters={"company": company},
            fields=["name", "is_default"],
            order_by="is_default desc",
        )
        defaults["tax_templates"] = templates
        defaults["default_tax_template"] = get_default_tax_template(voucher_type, company) or ""
    elif voucher_type in PURCHASE_TYPES:
        templates = frappe.get_all(
            "Purchase Taxes and Charges Template",
            filters={"company": company},
            fields=["name", "is_default"],
            order_by="is_default desc",
        )
        defaults["tax_templates"] = templates
        defaults["default_tax_template"] = get_default_tax_template(voucher_type, company) or ""

    # Payment-specific defaults
    if voucher_type in PAYMENT_TYPES:
        defaults["modes_of_payment"] = frappe.get_all("Mode of Payment", pluck="name")
        defaults["default_receivable_account"] = company_doc.default_receivable_account or ""
        defaults["default_payable_account"] = company_doc.default_payable_account or ""
        defaults["default_bank_account"] = _get_default_bank_account(company)
        defaults["default_cash_account"] = _get_default_cash_account(company)

    # Journal Entry defaults
    if voucher_type in JOURNAL_TYPES:
        defaults["accounts"] = frappe.get_all(
            "Account",
            filters={"company": company, "is_group": 0},
            fields=["name", "account_type", "account_currency"],
            order_by="name",
            limit=200,
        )

    # Warehouses for item table
    if voucher_type not in NO_WAREHOUSE_TYPES:
        defaults["warehouses"] = frappe.get_all(
            "Warehouse",
            filters={"company": company, "is_group": 0},
            pluck="name",
            order_by="name",
        )

    return defaults


@frappe.whitelist()
def create_transaction(voucher_type: str, data, submit: bool = False) -> dict:
    """Create an ERPNext document from simplified payload. Optionally submit."""
    if isinstance(data, str):
        import json
        data = json.loads(data)
    if isinstance(submit, str):
        submit = submit.lower() in ("true", "1", "yes")

    creators = {
        "sales-order": _create_sales_order,
        "purchase-order": _create_purchase_order,
        "payment-receive": _create_payment_entry_receive,
        "payment-pay": _create_payment_entry_pay,
        "journal-entry": _create_journal_entry,
        "sales-invoice": _create_sales_invoice,
        "purchase-invoice": _create_purchase_invoice,
        "delivery-note": _create_delivery_note,
        "purchase-receipt": _create_purchase_receipt,
        "debit-note": _create_debit_note,
        "credit-note": _create_credit_note,
        "stock-entry": _create_stock_entry,
        "job-work-in": _create_job_work_in,
        "job-work-out": _create_job_work_out,
    }

    creator = creators.get(voucher_type)
    if not creator:
        frappe.throw(_("Unknown voucher type: {0}").format(voucher_type))

    # Job work creators return a dict result directly (multi-doc)
    if voucher_type in ("job-work-in", "job-work-out"):
        result = creator(data, submit)
        frappe.db.commit()
        return result

    doc = creator(data)
    doc.insert()

    result = {
        "name": doc.name,
        "doctype": doc.doctype,
        "docstatus": doc.docstatus,
    }

    if submit:
        doc.submit()
        result["docstatus"] = 1

    # Include totals where applicable
    if hasattr(doc, "grand_total"):
        result["grand_total"] = doc.grand_total
    elif hasattr(doc, "total_debit"):
        result["total_debit"] = doc.total_debit
    elif hasattr(doc, "paid_amount"):
        result["paid_amount"] = doc.paid_amount

    frappe.db.commit()
    return result


@frappe.whitelist()
def get_tax_details(voucher_type: str, template_name: str) -> list:
    """Return the tax rows for a given template so the form can display them."""
    if not template_name:
        return []

    if voucher_type in SALES_TYPES:
        parent_doctype = "Sales Taxes and Charges Template"
        child_doctype = "Sales Taxes and Charges"
    elif voucher_type in PURCHASE_TYPES:
        parent_doctype = "Purchase Taxes and Charges Template"
        child_doctype = "Purchase Taxes and Charges"
    else:
        return []

    return frappe.get_all(
        child_doctype,
        filters={"parent": template_name, "parenttype": parent_doctype},
        fields=["charge_type", "account_head", "description", "rate", "tax_amount", "total", "idx", "row_id"],
        order_by="idx",
    )


@frappe.whitelist()
def get_default_tax_template(voucher_type, company):
    """Get the default tax template for a company using India Compliance's GST logic."""
    if not company:
        return ""

    is_sales = voucher_type in SALES_TYPES
    is_purchase = voucher_type in PURCHASE_TYPES

    if not is_sales and not is_purchase:
        return ""

    # Get company GSTIN
    company_gstin = _get_company_gstin(company)
    if not company_gstin:
        return ""

    doctype = "Sales Order" if is_sales else "Purchase Order"

    try:
        from india_compliance.gst_india.overrides.transaction import get_gst_details
        result = get_gst_details(
            {"company_gstin": company_gstin},
            doctype,
            company,
            update_place_of_supply=True,
        )
        return result.get("taxes_and_charges", "") if result else ""
    except Exception:
        return ""


@frappe.whitelist()
def get_party_tax_template(voucher_type, party, company=None):
    """Fetch tax template for a customer/supplier using India Compliance's GST logic."""
    if not party or not company:
        return ""

    is_sales = voucher_type in SALES_TYPES
    is_purchase = voucher_type in PURCHASE_TYPES

    if not is_sales and not is_purchase:
        return ""

    company_gstin = _get_company_gstin(company)
    if not company_gstin:
        return ""

    party_type = "Customer" if is_sales else "Supplier"
    doctype = "Sales Order" if is_sales else "Purchase Order"

    party_details = {
        "company_gstin": company_gstin,
        party_type.lower(): party,
    }

    try:
        from india_compliance.gst_india.overrides.transaction import get_gst_details
        result = get_gst_details(
            party_details,
            doctype,
            company,
            update_place_of_supply=True,
        )
        return result.get("taxes_and_charges", "") if result else ""
    except Exception:
        return ""


@frappe.whitelist()
def get_recent_transactions(voucher_type: str = None, limit: int = 10) -> list:
    """Return recent transactions visible to the current user."""
    limit = min(int(limit), 50)

    type_map = {
        "sales-order": "Sales Order",
        "purchase-order": "Purchase Order",
        "payment-receive": "Payment Entry",
        "payment-pay": "Payment Entry",
        "journal-entry": "Journal Entry",
        "sales-invoice": "Sales Invoice",
        "purchase-invoice": "Purchase Invoice",
        "delivery-note": "Delivery Note",
        "purchase-receipt": "Purchase Receipt",
        "debit-note": "Sales Invoice",   # is_return
        "credit-note": "Sales Invoice",  # is_return
        "stock-entry": "Stock Entry",
        "job-work-in": "Subcontracting Inward Order",
        "job-work-out": "Subcontracting Order",
    }

    if voucher_type and voucher_type in type_map:
        doctype = type_map[voucher_type]
        filters = {}

        if voucher_type == "payment-receive":
            filters["payment_type"] = "Receive"
        elif voucher_type == "payment-pay":
            filters["payment_type"] = "Pay"
        elif voucher_type == "debit-note":
            doctype = "Purchase Invoice"
            filters["is_return"] = 1
        elif voucher_type == "credit-note":
            doctype = "Sales Invoice"
            filters["is_return"] = 1

        fields = ["name", "creation", "docstatus"]

        # Add type-specific display fields
        if doctype == "Sales Order":
            fields += ["customer_name", "grand_total", "status"]
        elif doctype == "Purchase Order":
            fields += ["supplier_name", "grand_total", "status"]
        elif doctype == "Payment Entry":
            fields += ["party_name", "paid_amount", "status"]
        elif doctype == "Journal Entry":
            fields += ["total_debit", "voucher_type"]
        elif doctype == "Sales Invoice":
            fields += ["customer_name", "grand_total", "status"]
        elif doctype == "Purchase Invoice":
            fields += ["supplier_name", "grand_total", "status"]
        elif doctype == "Delivery Note":
            fields += ["customer_name", "grand_total", "status"]
        elif doctype == "Purchase Receipt":
            fields += ["supplier_name", "grand_total", "status"]
        elif doctype == "Stock Entry":
            fields += ["purpose", "total_amount", "stock_entry_type"]
        elif doctype == "Subcontracting Inward Order":
            fields += ["customer", "status"]
        elif doctype == "Subcontracting Order":
            fields += ["supplier_name", "total", "status"]

        return frappe.get_all(
            doctype,
            filters=filters,
            fields=fields,
            order_by="creation desc",
            limit=limit,
        )

    return []


@frappe.whitelist()
def get_invoice_items_for_return(doctype: str, invoice_name: str) -> dict:
    """Fetch items from an original Sales/Purchase Invoice for return (CN/DN) creation."""
    if doctype not in ("Sales Invoice", "Purchase Invoice"):
        frappe.throw(_("Invalid doctype for return"))

    frappe.has_permission(doctype, "read", invoice_name, throw=True)

    doc = frappe.get_doc(doctype, invoice_name)
    if doc.docstatus != 1:
        frappe.throw(_("Only submitted invoices can be used for returns"))

    items = []
    for item in doc.items:
        items.append({
            "item_code": item.item_code,
            "item_name": item.item_name or "",
            "qty": item.qty,
            "rate": item.rate,
            "uom": item.uom or "",
            "description": (item.description or "").strip(),
            "warehouse": item.warehouse or "",
            "reference_row": item.name,
        })

    result = {
        "tax_template": doc.taxes_and_charges or "",
        "items": items,
    }

    if doctype == "Sales Invoice":
        result.update({
            "party": doc.customer or "",
            "customer_address": doc.customer_address or "",
            "custom_shipping_party": doc.get("custom_shipping_party") or "",
            "shipping_address_name": doc.shipping_address_name or "",
            "po_no": doc.po_no or "",
            "po_date": str(doc.po_date) if doc.po_date else "",
        })
    else:
        result.update({
            "party": doc.supplier or "",
            "supplier_address": doc.supplier_address or "",
            "shipping_address": doc.shipping_address or "",
            "billing_address": doc.billing_address or "",
            "bill_no": doc.bill_no or "",
            "bill_date": str(doc.bill_date) if doc.bill_date else "",
        })

    # Return tax-related flags for auto-population
    result["is_reverse_charge"] = cint(doc.get("is_reverse_charge"))
    result["apply_tds"] = cint(doc.get("apply_tds"))

    return result


@frappe.whitelist()
def get_cart_items_for_voucher(items_json: str, voucher_type: str) -> list:
    """Map BOM cart items to Transaction Desk row data for the selected voucher type.

    For job-work-out/in: resolves active Subcontracting BOMs to derive service items and quantities.
    For sales-order: returns items with BOM references for Production Wizard.
    For purchase-order: returns basic item details.
    """
    from erpnext.subcontracting.doctype.subcontracting_bom.subcontracting_bom import (
        get_subcontracting_boms_for_finished_goods,
    )

    items = frappe.parse_json(items_json) if isinstance(items_json, str) else items_json
    result = []

    for item in items:
        item_code = item.get("item_code")
        qty = frappe.utils.flt(item.get("qty", 1))
        bom_no = item.get("bom_no", "")
        item_name = item.get("item_name") or frappe.db.get_value("Item", item_code, "item_name") or item_code
        uom = frappe.db.get_value("Item", item_code, "stock_uom") or "Kg"

        if voucher_type in ("job-work-out", "job-work-in"):
            sc_boms = get_subcontracting_boms_for_finished_goods([item_code])
            sc_bom = sc_boms.get(item_code) if sc_boms else None
            if not sc_bom:
                frappe.throw(
                    _("No active Subcontracting BOM found for {0}. Please go back to BOM Designer and ensure a Job Work Out stage is configured.").format(item_code)
                )
            service_item_qty = frappe.utils.flt(sc_bom.get("service_item_qty", 1))
            finished_good_qty = frappe.utils.flt(sc_bom.get("finished_good_qty", 1)) or 1
            gross_qty = qty * service_item_qty / finished_good_qty

            result.append({
                "voucher_type": voucher_type,
                "service_item": sc_bom.get("service_item"),
                "fg_item": item_code,
                "fg_item_name": item_name,
                "fg_item_qty": qty,
                "gross_qty": frappe.utils.flt(gross_qty, 3),
                "bom": sc_bom.get("finished_good_bom") or bom_no,
            })

        elif voucher_type == "sales-order":
            result.append({
                "voucher_type": voucher_type,
                "item_code": item_code,
                "item_name": item_name,
                "qty": qty,
                "uom": uom,
                "bom_no": bom_no,
            })

        else:  # purchase-order and others
            result.append({
                "voucher_type": voucher_type,
                "item_code": item_code,
                "item_name": item_name,
                "qty": qty,
                "uom": uom,
            })

    return result


@frappe.whitelist()
def get_subcontracting_bom_details(service_item: str = "", fg_item: str = "") -> dict:
    """Look up Subcontracting BOM details for auto-fill in JW IN/OUT forms.

    If fg_item is given: return BOM details (service_item, uom, ratios, bom).
    If service_item only: return the single matching FG item (if unambiguous).
    Returns {} when no BOM found rather than throwing (frontend uses this for conditional fill).
    """
    from erpnext.subcontracting.doctype.subcontracting_bom.subcontracting_bom import (
        get_subcontracting_boms_for_finished_goods,
    )

    if fg_item:
        boms = get_subcontracting_boms_for_finished_goods([fg_item])
        sc_bom = boms.get(fg_item) if boms else None
        if not sc_bom:
            return {}
        return {
            "service_item": sc_bom.get("service_item"),
            "fg_item": fg_item,
            "fg_item_name": frappe.db.get_value("Item", fg_item, "item_name") or fg_item,
            "service_item_uom": sc_bom.get("service_item_uom") or "Kg",
            "conversion_factor": frappe.utils.flt(sc_bom.get("conversion_factor") or 1),
            "finished_good_bom": sc_bom.get("finished_good_bom"),
            "finished_good_qty": frappe.utils.flt(sc_bom.get("finished_good_qty") or 1),
            "service_item_qty": frappe.utils.flt(sc_bom.get("service_item_qty") or 1),
        }

    if service_item:
        # Find active Subcontracting BOMs where this item is the service item
        sc_bom_rows = frappe.get_all(
            "Subcontracting BOM",
            filters={"service_item": service_item, "is_active": 1},
            fields=["name", "service_item", "finished_good", "service_item_uom",
                    "finished_good_bom", "finished_good_qty", "service_item_qty", "conversion_factor"],
            limit=2,
        )
        if not sc_bom_rows:
            return {}
        # Only auto-fill when there is exactly one matching FG item
        if len(sc_bom_rows) > 1:
            return {"multiple": True}
        sc_bom = sc_bom_rows[0]
        fg = sc_bom.finished_good
        return {
            "service_item": service_item,
            "fg_item": fg,
            "fg_item_name": frappe.db.get_value("Item", fg, "item_name") or fg if fg else "",
            "service_item_uom": sc_bom.service_item_uom or "Kg",
            "conversion_factor": frappe.utils.flt(sc_bom.conversion_factor or 1),
            "finished_good_bom": sc_bom.finished_good_bom,
            "finished_good_qty": frappe.utils.flt(sc_bom.finished_good_qty or 1),
            "service_item_qty": frappe.utils.flt(sc_bom.service_item_qty or 1),
        }

    return {}


@frappe.whitelist()
def search_fg_items_for_service(doctype, txt, searchfield=None, start=0, page_length=20,
                                filters=None, as_dict=False, **kwargs):
    """Search FG items eligible for a given service item via active Subcontracting BOMs.

    Used as get_query for the FG Item link control in Job Work rows.
    """
    import json
    from kniterp.api.item_search import smart_search

    if isinstance(filters, str):
        filters = json.loads(filters)
    filters = filters or {}

    service_item = filters.pop("service_item", "")

    if service_item:
        fg_items = frappe.get_all(
            "Subcontracting BOM",
            filters={"service_item": service_item, "is_active": 1},
            pluck="finished_good",
        )
        if not fg_items:
            return []
        filters["name"] = ["in", fg_items]

    return smart_search(
        doctype=doctype, txt=txt, searchfield=searchfield,
        start=start, page_length=page_length,
        filters=filters, as_dict=as_dict, **kwargs
    )


# ──────────────────────────────────────────────────────────────
# Internal creators — Existing types
# ──────────────────────────────────────────────────────────────

def _create_sales_order(data: dict):
    import json as _json
    items = []
    for row in data.get("items", []):
        item_row = {
            "item_code": row["item_code"],
            "qty": row.get("qty", 1),
            "rate": row.get("rate", 0),
            "delivery_date": data.get("delivery_date") or frappe.utils.add_days(frappe.utils.today(), 7),
            "warehouse": row.get("warehouse") or data.get("warehouse") or "",
        }
        if row.get("uom"):
            item_row["uom"] = row["uom"]
        if row.get("description"):
            item_row["description"] = row["description"]
        if row.get("transaction_params"):
            item_row["custom_transaction_params_json"] = _json.dumps(row["transaction_params"])
        if row.get("custom_knitting_charges"):
            item_row["custom_knitting_charges"] = frappe.utils.flt(row["custom_knitting_charges"])
        if row.get("bom_no"):
            item_row["bom_no"] = row["bom_no"]
        items.append(item_row)

    if not items:
        frappe.throw(_("At least one item is required."))

    doc = frappe.get_doc({
        "doctype": "Sales Order",
        "customer": data["customer"],
        "customer_address": data.get("customer_address"),
        "custom_shipping_party": data.get("custom_shipping_party") or "",
        "shipping_address_name": data.get("shipping_address_name"),
        "transaction_date": data.get("posting_date") or frappe.utils.today(),
        "delivery_date": data.get("delivery_date") or frappe.utils.add_days(frappe.utils.today(), 7),
        "company": data.get("company"),
        "currency": data.get("currency"),
        "po_no": data.get("po_no") or "",
        "po_date": data.get("po_date") or "",
        "items": items,
        "taxes_and_charges": data.get("tax_template") or "",
    })

    if data.get("tax_template"):
        doc.taxes_and_charges = data["tax_template"]
        doc.set_taxes()
        doc.run_method("set_missing_values")
        doc.run_method("calculate_taxes_and_totals")

    return doc


def _create_purchase_order(data: dict):
    import json as _json
    items = []
    for row in data.get("items", []):
        item_row = {
            "item_code": row["item_code"],
            "qty": row.get("qty", 1),
            "rate": row.get("rate", 0),
            "schedule_date": data.get("required_date") or frappe.utils.add_days(frappe.utils.today(), 14),
            "warehouse": row.get("warehouse") or data.get("warehouse") or "",
        }
        if row.get("uom"):
            item_row["uom"] = row["uom"]
        if row.get("description"):
            item_row["description"] = row["description"]
        if row.get("transaction_params"):
            item_row["custom_transaction_params_json"] = _json.dumps(row["transaction_params"])
        items.append(item_row)

    if not items:
        frappe.throw(_("At least one item is required."))

    doc = frappe.get_doc({
        "doctype": "Purchase Order",
        "supplier": data["supplier"],
        "supplier_address": data.get("supplier_address"),
        "billing_address": data.get("billing_address"),
        "custom_deliver_to_customer": data.get("custom_deliver_to_customer") or "",
        "custom_deliver_to_address": data.get("custom_deliver_to_address") or "",
        "shipping_address": data.get("shipping_address"),
        "transaction_date": data.get("posting_date") or frappe.utils.today(),
        "schedule_date": data.get("required_date") or frappe.utils.add_days(frappe.utils.today(), 14),
        "company": data.get("company"),
        "currency": data.get("currency"),
        "items": items,
        "taxes_and_charges": data.get("tax_template") or "",
    })

    if data.get("tax_template"):
        doc.taxes_and_charges = data["tax_template"]
        doc.set_taxes()
        doc.run_method("set_missing_values")
        doc.run_method("calculate_taxes_and_totals")

    return doc


def _create_payment_entry_receive(data: dict):
    return _create_payment_entry(data, "Receive")


def _create_payment_entry_pay(data: dict):
    return _create_payment_entry(data, "Pay")


def _create_payment_entry(data: dict, payment_type: str):
    company = data.get("company")
    party_type = "Customer" if payment_type == "Receive" else "Supplier"
    party = data.get("customer") if payment_type == "Receive" else data.get("supplier")
    amount = frappe.utils.flt(data.get("amount"))

    if not party:
        frappe.throw(_("{0} is required.").format(party_type))
    if not amount:
        frappe.throw(_("Amount is required."))

    mode_of_payment = data.get("mode_of_payment") or ""

    if payment_type == "Receive":
        paid_to = _get_account_for_mode_of_payment(mode_of_payment, company) or data.get("paid_to") or _get_default_bank_account(company)
        paid_from = ""
    else:
        paid_from = _get_account_for_mode_of_payment(mode_of_payment, company) or data.get("paid_from") or _get_default_bank_account(company)
        paid_to = ""

    pe_data = {
        "doctype": "Payment Entry",
        "payment_type": payment_type,
        "party_type": party_type,
        "party": party,
        "company": company,
        "posting_date": data.get("posting_date") or frappe.utils.today(),
        "mode_of_payment": mode_of_payment,
        "paid_amount": amount,
        "received_amount": amount,
        "reference_no": data.get("reference_no") or "",
        "reference_date": data.get("reference_date") or "",
    }

    if payment_type == "Receive" and paid_to:
        pe_data["paid_to"] = paid_to
    elif payment_type == "Pay" and paid_from:
        pe_data["paid_from"] = paid_from

    doc = frappe.get_doc(pe_data)
    return doc


def _create_journal_entry(data: dict):
    accounts = []
    for row in data.get("accounts", []):
        accounts.append({
            "account": row["account"],
            "debit_in_account_currency": frappe.utils.flt(row.get("debit", 0)),
            "credit_in_account_currency": frappe.utils.flt(row.get("credit", 0)),
        })

    if len(accounts) < 2:
        frappe.throw(_("At least two account rows are required."))

    entry_type = data.get("entry_type", "Journal Entry")
    doc = frappe.get_doc({
        "doctype": "Journal Entry",
        "voucher_type": entry_type,
        "company": data.get("company"),
        "posting_date": data.get("posting_date") or frappe.utils.today(),
        "cheque_no": data.get("cheque_no") or "",
        "cheque_date": data.get("cheque_date") or "",
        "user_remark": data.get("user_remark") or "",
        "accounts": accounts,
    })

    return doc


# ──────────────────────────────────────────────────────────────
# Internal creators — New types
# ──────────────────────────────────────────────────────────────

def _create_sales_invoice(data: dict):
    """Create a Sales Invoice."""
    import json as _json
    items = []
    for row in data.get("items", []):
        item_row = {
            "item_code": row["item_code"],
            "qty": row.get("qty", 1),
            "rate": row.get("rate", 0),
            "warehouse": row.get("warehouse") or data.get("warehouse") or "",
        }
        if row.get("uom"):
            item_row["uom"] = row["uom"]
        if row.get("description"):
            item_row["description"] = row["description"]
        if row.get("transaction_params"):
            item_row["custom_transaction_params_json"] = _json.dumps(row["transaction_params"])
        if row.get("custom_no_of_pkgs"):
            item_row["custom_no_of_pkgs"] = cint(row["custom_no_of_pkgs"])
        if row.get("custom_kind_of_pkgs"):
            item_row["custom_kind_of_pkgs"] = row["custom_kind_of_pkgs"]
        if row.get("custom_kind_of_pkgs_other"):
            item_row["custom_kind_of_pkgs_other"] = row["custom_kind_of_pkgs_other"]
        items.append(item_row)

    if not items:
        frappe.throw(_("At least one item is required."))

    doc = frappe.get_doc({
        "doctype": "Sales Invoice",
        "customer": data["customer"],
        "customer_address": data.get("customer_address"),
        "custom_shipping_party": data.get("custom_shipping_party") or "",
        "shipping_address_name": data.get("shipping_address_name"),
        "posting_date": data.get("posting_date") or frappe.utils.today(),
        "due_date": data.get("due_date") or frappe.utils.add_days(frappe.utils.today(), 30),
        "company": data.get("company"),
        "currency": data.get("currency"),
        "po_no": data.get("po_no") or "",
        "po_date": data.get("po_date") or "",
        "items": items,
        "taxes_and_charges": data.get("tax_template") or "",
    })

    if data.get("tax_template"):
        doc.taxes_and_charges = data["tax_template"]
        doc.set_taxes()
        doc.run_method("set_missing_values")
        doc.run_method("calculate_taxes_and_totals")

    return doc


def _create_purchase_invoice(data: dict):
    """Create a Purchase Invoice."""
    import json as _json
    items = []
    for row in data.get("items", []):
        item_row = {
            "item_code": row["item_code"],
            "qty": row.get("qty", 1),
            "rate": row.get("rate", 0),
            "warehouse": row.get("warehouse") or data.get("warehouse") or "",
        }
        if row.get("uom"):
            item_row["uom"] = row["uom"]
        if row.get("description"):
            item_row["description"] = row["description"]
        if row.get("transaction_params"):
            item_row["custom_transaction_params_json"] = _json.dumps(row["transaction_params"])
        if row.get("custom_no_of_pkgs"):
            item_row["custom_no_of_pkgs"] = cint(row["custom_no_of_pkgs"])
        if row.get("custom_kind_of_pkgs"):
            item_row["custom_kind_of_pkgs"] = row["custom_kind_of_pkgs"]
        if row.get("custom_kind_of_pkgs_other"):
            item_row["custom_kind_of_pkgs_other"] = row["custom_kind_of_pkgs_other"]
        items.append(item_row)

    if not items:
        frappe.throw(_("At least one item is required."))

    doc = frappe.get_doc({
        "doctype": "Purchase Invoice",
        "supplier": data["supplier"],
        "supplier_address": data.get("supplier_address"),
        "billing_address": data.get("billing_address"),
        "shipping_address": data.get("shipping_address"),
        "posting_date": data.get("posting_date") or frappe.utils.today(),
        "due_date": data.get("due_date") or frappe.utils.add_days(frappe.utils.today(), 30),
        "bill_no": data.get("bill_no") or "",
        "bill_date": data.get("bill_date") or "",
        "company": data.get("company"),
        "currency": data.get("currency"),
        "items": items,
        "taxes_and_charges": data.get("tax_template") or "",
    })

    if data.get("tax_template"):
        doc.taxes_and_charges = data["tax_template"]
        doc.set_taxes()
        doc.run_method("set_missing_values")
        doc.run_method("calculate_taxes_and_totals")

    return doc


def _create_delivery_note(data: dict):
    """Create a Delivery Note."""
    import json as _json
    items = []
    for row in data.get("items", []):
        item_row = {
            "item_code": row["item_code"],
            "qty": row.get("qty", 1),
            "rate": row.get("rate", 0),
            "warehouse": row.get("warehouse") or data.get("warehouse") or "",
        }
        if row.get("uom"):
            item_row["uom"] = row["uom"]
        if row.get("description"):
            item_row["description"] = row["description"]
        if row.get("transaction_params"):
            item_row["custom_transaction_params_json"] = _json.dumps(row["transaction_params"])
        if row.get("custom_no_of_pkgs"):
            item_row["custom_no_of_pkgs"] = cint(row["custom_no_of_pkgs"])
        if row.get("custom_kind_of_pkgs"):
            item_row["custom_kind_of_pkgs"] = row["custom_kind_of_pkgs"]
        if row.get("custom_kind_of_pkgs_other"):
            item_row["custom_kind_of_pkgs_other"] = row["custom_kind_of_pkgs_other"]
        items.append(item_row)

    if not items:
        frappe.throw(_("At least one item is required."))

    doc = frappe.get_doc({
        "doctype": "Delivery Note",
        "customer": data["customer"],
        "customer_address": data.get("customer_address"),
        "custom_shipping_party": data.get("custom_shipping_party") or "",
        "shipping_address_name": data.get("shipping_address_name"),
        "posting_date": data.get("posting_date") or frappe.utils.today(),
        "company": data.get("company"),
        "currency": data.get("currency"),
        "po_no": data.get("po_no") or "",
        "po_date": data.get("po_date") or "",
        "items": items,
        "taxes_and_charges": data.get("tax_template") or "",
    })

    if data.get("tax_template"):
        doc.taxes_and_charges = data["tax_template"]
        doc.set_taxes()
        doc.run_method("set_missing_values")
        doc.run_method("calculate_taxes_and_totals")

    # Set transport/e-way bill fields
    for field in TRANSPORT_FIELDS:
        val = data.get(field)
        if val:
            doc.set(field, val)
    if any(data.get(f) for f in TRANSPORT_FIELDS):
        if not doc.get('mode_of_transport'):
            doc.mode_of_transport = 'Road'
        if not doc.get('gst_vehicle_type'):
            doc.gst_vehicle_type = 'Regular'

    return doc


def _create_purchase_receipt(data: dict):
    """Create a Purchase Receipt."""
    import json as _json
    items = []
    for row in data.get("items", []):
        item_row = {
            "item_code": row["item_code"],
            "qty": row.get("qty", 1),
            "rate": row.get("rate", 0),
            "warehouse": row.get("warehouse") or data.get("warehouse") or "",
        }
        if row.get("uom"):
            item_row["uom"] = row["uom"]
        if row.get("description"):
            item_row["description"] = row["description"]
        if row.get("transaction_params"):
            item_row["custom_transaction_params_json"] = _json.dumps(row["transaction_params"])
        if row.get("custom_no_of_pkgs"):
            item_row["custom_no_of_pkgs"] = cint(row["custom_no_of_pkgs"])
        if row.get("custom_kind_of_pkgs"):
            item_row["custom_kind_of_pkgs"] = row["custom_kind_of_pkgs"]
        if row.get("custom_kind_of_pkgs_other"):
            item_row["custom_kind_of_pkgs_other"] = row["custom_kind_of_pkgs_other"]
        items.append(item_row)

    if not items:
        frappe.throw(_("At least one item is required."))

    doc = frappe.get_doc({
        "doctype": "Purchase Receipt",
        "supplier": data["supplier"],
        "supplier_address": data.get("supplier_address"),
        "billing_address": data.get("billing_address"),
        "shipping_address": data.get("shipping_address"),
        "posting_date": data.get("posting_date") or frappe.utils.today(),
        "company": data.get("company"),
        "currency": data.get("currency"),
        "supplier_delivery_note": data.get("supplier_delivery_note") or "",
        "items": items,
        "taxes_and_charges": data.get("tax_template") or "",
    })

    if data.get("tax_template"):
        doc.taxes_and_charges = data["tax_template"]
        doc.set_taxes()
        doc.run_method("set_missing_values")
        doc.run_method("calculate_taxes_and_totals")

    # Set transport/e-way bill fields
    for field in TRANSPORT_FIELDS:
        val = data.get(field)
        if val:
            doc.set(field, val)
    if any(data.get(f) for f in TRANSPORT_FIELDS):
        if not doc.get('mode_of_transport'):
            doc.mode_of_transport = 'Road'
        if not doc.get('gst_vehicle_type'):
            doc.gst_vehicle_type = 'Regular'

    return doc


def _create_debit_note(data: dict):
    """Create a Debit Note (Purchase Invoice with is_return=1)."""
    import json as _json
    items = []
    for row in data.get("items", []):
        item_row = {
            "item_code": row["item_code"],
            "qty": -abs(frappe.utils.flt(row.get("qty", 1))),   # negative
            "rate": row.get("rate", 0),
            "warehouse": row.get("warehouse") or data.get("warehouse") or "",
        }
        if row.get("uom"):
            item_row["uom"] = row["uom"]
        if row.get("description"):
            item_row["description"] = row["description"]
        if row.get("reference_row"):
            item_row["purchase_invoice_item"] = row["reference_row"]
        if row.get("custom_no_of_pkgs"):
            item_row["custom_no_of_pkgs"] = cint(row["custom_no_of_pkgs"])
        if row.get("custom_kind_of_pkgs"):
            item_row["custom_kind_of_pkgs"] = row["custom_kind_of_pkgs"]
        if row.get("custom_kind_of_pkgs_other"):
            item_row["custom_kind_of_pkgs_other"] = row["custom_kind_of_pkgs_other"]
        items.append(item_row)

    if not items:
        frappe.throw(_("At least one item is required."))

    doc_data = {
        "doctype": "Purchase Invoice",
        "supplier": data["supplier"],
        "supplier_address": data.get("supplier_address"),
        "shipping_address": data.get("shipping_address") or "",
        "billing_address": data.get("billing_address") or "",
        "posting_date": data.get("posting_date") or frappe.utils.today(),
        "company": data.get("company"),
        "currency": data.get("currency"),
        "is_return": 1,
        "update_outstanding_for_self": cint(data.get("update_outstanding_for_self", 1)),
        "update_billed_amount_in_purchase_order": cint(data.get("update_billed_amount_in_purchase_order", 0)),
        "update_billed_amount_in_purchase_receipt": cint(data.get("update_billed_amount_in_purchase_receipt", 1)),
        "is_reverse_charge": cint(data.get("is_reverse_charge", 0)),
        "apply_tds": cint(data.get("apply_tds", 0)),
        "bill_no": data.get("bill_no") or "",
        "bill_date": data.get("bill_date") or "",
        "items": items,
        "taxes_and_charges": data.get("tax_template") or "",
    }

    if data.get("return_against"):
        doc_data["return_against"] = data["return_against"]

    doc = frappe.get_doc(doc_data)

    if data.get("tax_template"):
        doc.taxes_and_charges = data["tax_template"]
        doc.set_taxes()
        doc.run_method("set_missing_values")
        doc.run_method("calculate_taxes_and_totals")

    return doc


def _create_credit_note(data: dict):
    """Create a Credit Note (Sales Invoice with is_return=1)."""
    import json as _json
    items = []
    for row in data.get("items", []):
        item_row = {
            "item_code": row["item_code"],
            "qty": -abs(frappe.utils.flt(row.get("qty", 1))),   # negative
            "rate": row.get("rate", 0),
            "warehouse": row.get("warehouse") or data.get("warehouse") or "",
        }
        if row.get("uom"):
            item_row["uom"] = row["uom"]
        if row.get("description"):
            item_row["description"] = row["description"]
        if row.get("reference_row"):
            item_row["sales_invoice_item"] = row["reference_row"]
        if row.get("custom_no_of_pkgs"):
            item_row["custom_no_of_pkgs"] = cint(row["custom_no_of_pkgs"])
        if row.get("custom_kind_of_pkgs"):
            item_row["custom_kind_of_pkgs"] = row["custom_kind_of_pkgs"]
        if row.get("custom_kind_of_pkgs_other"):
            item_row["custom_kind_of_pkgs_other"] = row["custom_kind_of_pkgs_other"]
        items.append(item_row)

    if not items:
        frappe.throw(_("At least one item is required."))

    doc_data = {
        "doctype": "Sales Invoice",
        "customer": data["customer"],
        "customer_address": data.get("customer_address"),
        "custom_shipping_party": data.get("custom_shipping_party") or "",
        "shipping_address_name": data.get("shipping_address_name") or "",
        "posting_date": data.get("posting_date") or frappe.utils.today(),
        "company": data.get("company"),
        "currency": data.get("currency"),
        "is_return": 1,
        "update_outstanding_for_self": cint(data.get("update_outstanding_for_self", 1)),
        "update_billed_amount_in_sales_order": cint(data.get("update_billed_amount_in_sales_order", 0)),
        "update_billed_amount_in_delivery_note": cint(data.get("update_billed_amount_in_delivery_note", 1)),
        "is_reverse_charge": cint(data.get("is_reverse_charge", 0)),
        "apply_tds": cint(data.get("apply_tds", 0)),
        "po_no": data.get("po_no") or "",
        "po_date": data.get("po_date") or "",
        "items": items,
        "taxes_and_charges": data.get("tax_template") or "",
    }

    if data.get("return_against"):
        doc_data["return_against"] = data["return_against"]

    doc = frappe.get_doc(doc_data)

    if data.get("tax_template"):
        doc.taxes_and_charges = data["tax_template"]
        doc.set_taxes()
        doc.run_method("set_missing_values")
        doc.run_method("calculate_taxes_and_totals")

    return doc


def _create_stock_entry(data: dict):
    """Create a Stock Entry."""
    purpose = data.get("purpose", "Material Receipt")
    items = []
    for row in data.get("items", []):
        item_row = {
            "item_code": row["item_code"],
            "qty": row.get("qty", 1),
        }
        if row.get("uom"):
            item_row["uom"] = row["uom"]
        if row.get("description"):
            item_row["description"] = row["description"]
        if row.get("custom_no_of_pkgs"):
            item_row["custom_no_of_pkgs"] = cint(row["custom_no_of_pkgs"])
        if row.get("custom_kind_of_pkgs"):
            item_row["custom_kind_of_pkgs"] = row["custom_kind_of_pkgs"]
        if row.get("custom_kind_of_pkgs_other"):
            item_row["custom_kind_of_pkgs_other"] = row["custom_kind_of_pkgs_other"]
        # Source/target warehouse based on purpose
        if purpose in ("Material Transfer", "Material Transfer for Manufacture", "Send to Subcontractor"):
            item_row["s_warehouse"] = row.get("s_warehouse") or data.get("from_warehouse") or ""
            item_row["t_warehouse"] = row.get("t_warehouse") or data.get("to_warehouse") or ""
        elif purpose == "Material Receipt":
            item_row["t_warehouse"] = row.get("t_warehouse") or data.get("to_warehouse") or data.get("warehouse") or ""
        elif purpose == "Material Issue":
            item_row["s_warehouse"] = row.get("s_warehouse") or data.get("from_warehouse") or data.get("warehouse") or ""
        else:
            item_row["s_warehouse"] = row.get("s_warehouse") or data.get("from_warehouse") or ""
            item_row["t_warehouse"] = row.get("t_warehouse") or data.get("to_warehouse") or ""
        items.append(item_row)

    if not items:
        frappe.throw(_("At least one item is required."))

    doc = frappe.get_doc({
        "doctype": "Stock Entry",
        "stock_entry_type": purpose,
        "company": data.get("company"),
        "posting_date": data.get("posting_date") or frappe.utils.today(),
        "from_warehouse": data.get("from_warehouse") or "",
        "to_warehouse": data.get("to_warehouse") or "",
        "items": items,
    })

    # Set transport/e-way bill fields
    for field in TRANSPORT_FIELDS:
        val = data.get(field)
        if val:
            doc.set(field, val)
    if not doc.get('mode_of_transport'):
        doc.mode_of_transport = 'Road'
    if not doc.get('gst_vehicle_type'):
        doc.gst_vehicle_type = 'Regular'

    # Append JW instructions to item descriptions for subcontracting
    jw_desc = data.get('jw_description')
    if jw_desc and purpose == 'Send to Subcontractor':
        for item in doc.items:
            item.description = (item.description or '') + '\n\n' + jw_desc

    return doc


def _create_job_work_in(data: dict, submit: bool = False):
    """Job Work In: Create Sales Order (subcontracted) + Subcontracting Inward Order.

    The user provides:
    - customer
    - items: list of {item_code (service item), fg_item (finished good), gross_qty (service qty),
              net_qty (FG qty), rate (service charge), description, transaction_params}
    """
    import json as _json
    from kniterp.kniterp.doctype.kniterp_settings.kniterp_settings import KnitERPSettings

    company = data.get("company")
    customer = data.get("customer")
    if not customer:
        frappe.throw(_("Customer is required for Job Work In."))

    service_items = data.get("items", [])
    if not service_items:
        frappe.throw(_("At least one service item is required."))

    settings = KnitERPSettings.get_settings()
    delivery_date = data.get("delivery_date") or frappe.utils.add_days(frappe.utils.today(), 14)

    # 1. Create Sales Order with is_subcontracted = 1
    so_items = []
    for row in service_items:
        service_item = row.get("item_code")
        fg_item = row.get("fg_item") or ""
        if not fg_item:
            frappe.throw(_("Each row must have a Finished Good item for Job Work In."))

        _resolve_subcontracting_bom(service_item, fg_item)  # validate BOM exists

        so_item = {
            "item_code": service_item,
            "fg_item": fg_item,
            "fg_item_qty": frappe.utils.flt(row.get("net_qty", 1)),
            "qty": frappe.utils.flt(row.get("gross_qty", 1)),
            "rate": frappe.utils.flt(row.get("rate", 0)),
            "delivery_date": delivery_date,
            "warehouse": row.get("warehouse") or data.get("warehouse") or "",
        }
        if row.get("description"):
            so_item["description"] = row["description"]
        if row.get("transaction_params"):
            so_item["custom_transaction_params_json"] = _json.dumps(row["transaction_params"])
        so_items.append(so_item)

    so = frappe.get_doc({
        "doctype": "Sales Order",
        "customer": customer,
        "company": company,
        "transaction_date": data.get("posting_date") or frappe.utils.today(),
        "delivery_date": delivery_date,
        "is_subcontracted": 1,
        "customer_address": data.get("customer_address") or "",
        "custom_shipping_party": data.get("custom_shipping_party") or "",
        "shipping_address_name": data.get("shipping_address_name") or "",
        "items": so_items,
    })

    if data.get("tax_template"):
        so.taxes_and_charges = data["tax_template"]
        so.set_taxes()
        so.run_method("set_missing_values")
        so.run_method("calculate_taxes_and_totals")
    else:
        so.run_method("set_missing_values")

    if not so.dispatch_address_name and so.company_address:
        so.dispatch_address_name = so.company_address

    so.flags.ignore_mandatory = True
    so.insert()

    if submit:
        so.submit()

    # 2. Resolve customer warehouse (auto-create if needed)
    customer_warehouse = _get_or_create_customer_jw_warehouse(customer, company)
    delivery_wh = settings.jw_completed_warehouse or ""
    if not delivery_wh:
        frappe.throw(_("Please set 'Customer JW Completed Warehouse' in KnitERP Settings."))

    customer_name = frappe.db.get_value("Customer", customer, "customer_name") or customer

    # 3. Create Subcontracting Inward Order linked to the Sales Order
    scio_service_items = []
    for i, row in enumerate(service_items):
        so_item = so.items[i] if i < len(so.items) else None
        scio_service_items.append({
            "item_code": row.get("item_code"),
            "fg_item": row.get("fg_item", ""),
            "fg_item_qty": frappe.utils.flt(row.get("net_qty", 1)),
            "required_qty": frappe.utils.flt(row.get("gross_qty", 1)),
            "rate": frappe.utils.flt(row.get("rate", 0)),
            "sales_order_item": so_item.name if so_item else "",
        })

    scio = frappe.new_doc("Subcontracting Inward Order")
    scio.sales_order = so.name
    scio.customer = customer
    scio.customer_name = customer_name
    scio.company = company
    scio.transaction_date = data.get("posting_date") or frappe.utils.today()
    scio.customer_warehouse = customer_warehouse
    scio.set_delivery_warehouse = delivery_wh

    for si_row in scio_service_items:
        scio.append("service_items", si_row)

    scio_created = None
    try:
        # Populate raw materials (items) table BEFORE insert — ERPNext's
        # validate_service_items() filters service_items to only those whose
        # sales_order_item exists in items table, so items must be populated first.
        scio.run_method("populate_items_table")
        if scio.items:
            for item in scio.items:
                if not item.get("delivery_warehouse"):
                    item.delivery_warehouse = delivery_wh

        scio.flags.ignore_mandatory = True
        scio.insert()
        scio_created = scio

        if submit:
            scio.submit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Job Work In: SCIO creation failed")
        try:
            if so.docstatus == 1:
                so.cancel()
            frappe.delete_doc("Sales Order", so.name, force=True, ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Job Work In: SO rollback failed")
        frappe.throw(_("Failed to create Subcontracting Inward Order. The Sales Order has been rolled back. Please try again."))

    return {
        "name": scio_created.name,
        "doctype": "Subcontracting Inward Order",
        "docstatus": scio_created.docstatus,
        "sales_order": so.name,
        "grand_total": so.grand_total if hasattr(so, "grand_total") else 0,
    }


def _create_job_work_out(data: dict, submit: bool = False):
    """Job Work Out: Create Purchase Order (subcontracted) + Subcontracting Order.

    The user provides:
    - supplier
    - items: list of {item_code (service item), fg_item (finished good), gross_qty (service qty),
              net_qty (FG qty), rate (service charge), description, transaction_params}
    """
    import json as _json
    from kniterp.kniterp.doctype.kniterp_settings.kniterp_settings import KnitERPSettings

    company = data.get("company")
    supplier = data.get("supplier")
    if not supplier:
        frappe.throw(_("Supplier is required for Job Work Out."))

    service_items = data.get("items", [])
    if not service_items:
        frappe.throw(_("At least one service item is required."))

    settings = KnitERPSettings.get_settings()
    supplier_warehouse = settings.jw_outward_warehouse or ""
    schedule_date = data.get("schedule_date") or frappe.utils.add_days(frappe.utils.today(), 14)

    # 1. Create Purchase Order with is_subcontracted = 1
    po_items = []
    for row in service_items:
        service_item = row.get("item_code")
        fg_item = row.get("fg_item") or ""
        if not fg_item:
            frappe.throw(_("Each row must have a Finished Good item for Job Work Out."))

        sc_bom = _resolve_subcontracting_bom(service_item, fg_item)

        po_item = {
            "item_code": service_item,
            "fg_item": fg_item,
            "fg_item_qty": frappe.utils.flt(row.get("net_qty", 1)),
            "bom": sc_bom["finished_good_bom"],
            "uom": sc_bom["service_item_uom"],
            "stock_uom": sc_bom["service_item_uom"],
            "conversion_factor": sc_bom["conversion_factor"],
            "qty": frappe.utils.flt(row.get("gross_qty", 1)),
            "rate": frappe.utils.flt(row.get("rate", 0)),
            "schedule_date": schedule_date,
            "warehouse": row.get("warehouse") or data.get("warehouse") or "",
        }
        if row.get("description"):
            po_item["description"] = row["description"]
        if row.get("transaction_params"):
            po_item["custom_transaction_params_json"] = _json.dumps(row["transaction_params"])
        po_items.append(po_item)

    po = frappe.get_doc({
        "doctype": "Purchase Order",
        "supplier": supplier,
        "company": company,
        "transaction_date": data.get("posting_date") or frappe.utils.today(),
        "schedule_date": schedule_date,
        "is_subcontracted": 1,
        "supplier_warehouse": supplier_warehouse,
        "supplier_address": data.get("supplier_address") or "",
        "custom_deliver_to_customer": data.get("custom_deliver_to_customer") or "",
        "custom_deliver_to_address": data.get("custom_deliver_to_address") or "",
        "shipping_address": data.get("shipping_address") or "",
        "items": po_items,
    })

    if data.get("tax_template"):
        po.taxes_and_charges = data["tax_template"]
        po.set_taxes()
        po.run_method("set_missing_values")
        po.run_method("calculate_taxes_and_totals")
    else:
        po.run_method("set_missing_values")

    po.flags.ignore_mandatory = True
    po.insert()

    if not submit:
        # Draft mode: only create the PO; SCO requires a submitted PO
        return {
            "name": po.name,
            "doctype": "Purchase Order",
            "docstatus": po.docstatus,
            "grand_total": po.grand_total if hasattr(po, "grand_total") else 0,
        }

    sco = None
    try:
        po.submit()
        # PO.on_submit may auto-create a draft SCO if Buying Settings has
        # auto_create_subcontracting_order enabled — reuse it to avoid duplicates.
        from erpnext.buying.doctype.purchase_order.purchase_order import make_subcontracting_order
        existing_sco_name = frappe.db.get_value(
            "Subcontracting Order",
            {"purchase_order": po.name, "docstatus": 0},
            "name",
        )
        if existing_sco_name:
            sco = frappe.get_doc("Subcontracting Order", existing_sco_name)
        else:
            sco = make_subcontracting_order(po.name)
            sco.flags.ignore_mandatory = True
            sco.insert()
        # Propagate custom delivery fields from PO to SCO
        if po.custom_deliver_to_customer:
            sco.custom_deliver_to_customer = po.custom_deliver_to_customer
            sco.custom_deliver_to_address = po.custom_deliver_to_address or ""
            sco.save()
        sco.submit()
    except Exception:
        # Roll back the PO so we don't leave an orphaned document
        frappe.log_error(frappe.get_traceback(), "Job Work Out: SCO creation failed")
        try:
            if po.docstatus == 1:
                po.cancel()
            frappe.delete_doc("Purchase Order", po.name, force=True, ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Job Work Out: PO rollback failed")
        frappe.throw(_("Failed to create Subcontracting Order. The Purchase Order has been rolled back. Please try again."))

    return {
        "name": sco.name,
        "doctype": "Subcontracting Order",
        "docstatus": sco.docstatus,
        "purchase_order": po.name,
        "grand_total": po.grand_total if hasattr(po, "grand_total") else 0,
    }


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _get_company_gstin(company: str) -> str:
    """Get the primary GSTIN for a company from its linked address."""
    gstin = frappe.db.sql("""
        SELECT a.gstin FROM `tabAddress` a
        JOIN `tabDynamic Link` dl ON dl.parent = a.name
        WHERE dl.link_doctype = 'Company' AND dl.link_name = %s
        AND a.gstin IS NOT NULL AND a.gstin != ''
        LIMIT 1
    """, company, as_dict=True)
    return gstin[0]["gstin"] if gstin else ""

def _get_default_bank_account(company: str) -> str:
    """Get first bank account for the company."""
    accounts = frappe.get_all(
        "Account",
        filters={"company": company, "account_type": "Bank", "is_group": 0},
        pluck="name",
        limit=1,
    )
    return accounts[0] if accounts else ""


def _get_default_cash_account(company: str) -> str:
    """Get default cash account for the company."""
    accounts = frappe.get_all(
        "Account",
        filters={"company": company, "account_type": "Cash", "is_group": 0},
        pluck="name",
        limit=1,
    )
    return accounts[0] if accounts else ""


def _get_account_for_mode_of_payment(mode_of_payment: str, company: str) -> str:
    """Get the account linked to a mode of payment for the given company."""
    if not mode_of_payment:
        return ""
    account = frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": mode_of_payment, "company": company},
        "default_account",
    )
    return account or ""


def _resolve_subcontracting_bom(service_item: str, fg_item: str) -> dict:
    """Validate and return Subcontracting BOM details for a service_item + fg_item pair.

    Throws a user-facing error when no active BOM is found.
    Returns a dict with: service_item_uom, conversion_factor, finished_good_bom,
    finished_good_qty, service_item_qty.
    """
    from erpnext.subcontracting.doctype.subcontracting_bom.subcontracting_bom import (
        get_subcontracting_boms_for_finished_goods,
    )
    boms = get_subcontracting_boms_for_finished_goods([fg_item])
    sc_bom = boms.get(fg_item) if boms else None
    if not sc_bom:
        frappe.throw(
            _("No active Subcontracting BOM found for Finished Good {0} with Service Item {1}. "
              "Please create one in BOM Designer before creating a Job Work order.").format(
                frappe.bold(fg_item), frappe.bold(service_item)
            )
        )
    return {
        "service_item_uom": sc_bom.get("service_item_uom") or "Kg",
        "conversion_factor": frappe.utils.flt(sc_bom.get("conversion_factor") or 1),
        "finished_good_bom": sc_bom.get("finished_good_bom"),
        "finished_good_qty": frappe.utils.flt(sc_bom.get("finished_good_qty") or 1),
        "service_item_qty": frappe.utils.flt(sc_bom.get("service_item_qty") or 1),
    }


def _get_or_create_customer_jw_warehouse(customer: str, company: str) -> str:
    """Find or auto-create the inward warehouse for a customer's raw materials.

    Mirrors the logic in production_wizard.create_subcontracting_inward_order.
    Requires 'jw_inward_parent_warehouse' to be configured in KnitERP Settings.
    """
    from kniterp.kniterp.doctype.kniterp_settings.kniterp_settings import KnitERPSettings

    # Strategy 1: existing warehouse explicitly linked to this customer
    customer_warehouse = frappe.db.get_value(
        "Warehouse",
        {"customer": customer, "company": company, "is_group": 0},
        "name",
    )
    if customer_warehouse:
        return customer_warehouse

    # Strategy 2: create under configured parent warehouse
    settings = KnitERPSettings.get_settings()
    parent_wh = settings.jw_inward_parent_warehouse
    if not parent_wh:
        frappe.throw(
            _("Please set 'Customer JW Parent Warehouse' in KnitERP Settings before creating a Job Work In order.")
        )

    company_abbr = frappe.get_cached_value("Company", company, "abbr")
    customer_name = frappe.db.get_value("Customer", customer, "customer_name") or customer
    new_wh_name = f"JW-IN - {customer_name} - {company_abbr}"

    existing = frappe.db.exists("Warehouse", new_wh_name)
    if existing:
        wh_doc = frappe.get_doc("Warehouse", new_wh_name)
        if not wh_doc.customer:
            wh_doc.customer = customer
            wh_doc.save(ignore_permissions=True)
        return new_wh_name

    new_wh = frappe.new_doc("Warehouse")
    new_wh.warehouse_name = new_wh_name
    new_wh.parent_warehouse = parent_wh
    new_wh.is_group = 0
    new_wh.company = company
    new_wh.customer = customer
    new_wh.insert(ignore_permissions=True)
    frappe.msgprint(_("Created warehouse {0} for customer raw materials.").format(new_wh_name))
    return new_wh_name
