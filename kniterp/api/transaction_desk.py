import frappe
from frappe import _


# ──────────────────────────────────────────────────────────────
# Type classification helpers
# ──────────────────────────────────────────────────────────────

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
    """Return recent transactions created by the current user."""
    user = frappe.session.user
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
        filters = {"owner": user}

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
        items.append(item_row)

    if not items:
        frappe.throw(_("At least one item is required."))

    doc = frappe.get_doc({
        "doctype": "Sales Order",
        "customer": data["customer"],
        "customer_address": data.get("customer_address"),
        "shipping_address_name": data.get("shipping_address_name"),
        "transaction_date": data.get("posting_date") or frappe.utils.today(),
        "delivery_date": data.get("delivery_date") or frappe.utils.add_days(frappe.utils.today(), 7),
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
        items.append(item_row)

    if not items:
        frappe.throw(_("At least one item is required."))

    doc = frappe.get_doc({
        "doctype": "Sales Invoice",
        "customer": data["customer"],
        "customer_address": data.get("customer_address"),
        "shipping_address_name": data.get("shipping_address_name"),
        "posting_date": data.get("posting_date") or frappe.utils.today(),
        "due_date": data.get("due_date") or frappe.utils.add_days(frappe.utils.today(), 30),
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
        items.append(item_row)

    if not items:
        frappe.throw(_("At least one item is required."))

    doc = frappe.get_doc({
        "doctype": "Delivery Note",
        "customer": data["customer"],
        "customer_address": data.get("customer_address"),
        "shipping_address_name": data.get("shipping_address_name"),
        "posting_date": data.get("posting_date") or frappe.utils.today(),
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
        "items": items,
        "taxes_and_charges": data.get("tax_template") or "",
    })

    if data.get("tax_template"):
        doc.taxes_and_charges = data["tax_template"]
        doc.set_taxes()
        doc.run_method("set_missing_values")
        doc.run_method("calculate_taxes_and_totals")

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
        items.append(item_row)

    if not items:
        frappe.throw(_("At least one item is required."))

    doc_data = {
        "doctype": "Purchase Invoice",
        "supplier": data["supplier"],
        "supplier_address": data.get("supplier_address"),
        "posting_date": data.get("posting_date") or frappe.utils.today(),
        "company": data.get("company"),
        "currency": data.get("currency"),
        "is_return": 1,
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
    """Create a Credit Note (Sales Invoice with is_return=1).
    Can be with or without items.
    """
    import json as _json
    items = []

    if data.get("items"):
        for row in data["items"]:
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
            items.append(item_row)

    # Credit note without items — just an amount
    if not items:
        # Create a single item row if no items provided but amount is given
        amount = frappe.utils.flt(data.get("credit_amount", 0))
        if amount:
            income_account = frappe.db.get_value(
                "Company", data.get("company"), "default_income_account"
            ) or ""
            items.append({
                "item_name": "Credit Note",
                "description": data.get("remarks") or "Credit Note",
                "qty": -1,
                "rate": amount,
                "income_account": income_account,
            })
        else:
            frappe.throw(_("Either items or credit amount is required for a Credit Note."))

    doc_data = {
        "doctype": "Sales Invoice",
        "customer": data["customer"],
        "customer_address": data.get("customer_address"),
        "posting_date": data.get("posting_date") or frappe.utils.today(),
        "company": data.get("company"),
        "currency": data.get("currency"),
        "is_return": 1,
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

    return doc


def _create_job_work_in(data: dict, submit: bool = False):
    """Job Work In: Create Sales Order (subcontracted) + Subcontracting Inward Order.

    The user provides:
    - customer
    - items: list of {item_code (service item), fg_item (finished good), gross_qty (service qty),
              net_qty (FG qty), rate (service charge)}
    """
    company = data.get("company")
    customer = data.get("customer")
    if not customer:
        frappe.throw(_("Customer is required for Job Work In."))

    service_items = data.get("items", [])
    if not service_items:
        frappe.throw(_("At least one service item is required."))

    # 1. Create Sales Order with is_subcontracted = 1
    so_items = []
    for row in service_items:
        so_items.append({
            "item_code": row.get("item_code"),  # service item
            "qty": frappe.utils.flt(row.get("gross_qty", 1)),
            "rate": frappe.utils.flt(row.get("rate", 0)),
            "delivery_date": data.get("delivery_date") or frappe.utils.add_days(frappe.utils.today(), 14),
            "warehouse": row.get("warehouse") or data.get("warehouse") or "",
        })

    so = frappe.get_doc({
        "doctype": "Sales Order",
        "customer": customer,
        "company": company,
        "transaction_date": data.get("posting_date") or frappe.utils.today(),
        "delivery_date": data.get("delivery_date") or frappe.utils.add_days(frappe.utils.today(), 14),
        "is_subcontracted": 1,
        "items": so_items,
    })

    if data.get("tax_template"):
        so.taxes_and_charges = data["tax_template"]
        so.set_taxes()
        so.run_method("set_missing_values")
        so.run_method("calculate_taxes_and_totals")

    so.insert()

    if submit:
        so.submit()

    # 2. Create Subcontracting Inward Order linked to the Sales Order
    scio_service_items = []
    for i, row in enumerate(service_items):
        so_item = so.items[i] if i < len(so.items) else None
        scio_service_items.append({
            "item_code": row.get("item_code"),  # service item
            "fg_item": row.get("fg_item", ""),  # finished good
            "fg_item_qty": frappe.utils.flt(row.get("net_qty", 1)),
            "required_qty": frappe.utils.flt(row.get("gross_qty", 1)),
            "rate": frappe.utils.flt(row.get("rate", 0)),
            "sales_order_item": so_item.name if so_item else "",
        })

    scio = frappe.get_doc({
        "doctype": "Subcontracting Inward Order",
        "sales_order": so.name,
        "customer": customer,
        "company": company,
        "transaction_date": data.get("posting_date") or frappe.utils.today(),
        "service_items": scio_service_items,
    })

    scio.run_method("set_missing_values")
    scio.insert()

    if submit:
        scio.submit()

    return {
        "name": scio.name,
        "doctype": "Subcontracting Inward Order",
        "docstatus": scio.docstatus,
        "sales_order": so.name,
        "grand_total": so.grand_total if hasattr(so, "grand_total") else 0,
    }


def _create_job_work_out(data: dict, submit: bool = False):
    """Job Work Out: Create Purchase Order (subcontracted) + Subcontracting Order.

    The user provides:
    - supplier
    - items: list of {item_code (service item), fg_item (finished good), gross_qty (service qty),
              net_qty (FG qty), rate (service charge)}
    """
    company = data.get("company")
    supplier = data.get("supplier")
    if not supplier:
        frappe.throw(_("Supplier is required for Job Work Out."))

    service_items = data.get("items", [])
    if not service_items:
        frappe.throw(_("At least one service item is required."))

    # 1. Create Purchase Order with is_subcontracted = 1
    po_items = []
    for row in service_items:
        po_items.append({
            "item_code": row.get("item_code"),  # service item
            "qty": frappe.utils.flt(row.get("gross_qty", 1)),
            "rate": frappe.utils.flt(row.get("rate", 0)),
            "schedule_date": data.get("schedule_date") or frappe.utils.add_days(frappe.utils.today(), 14),
            "warehouse": row.get("warehouse") or data.get("warehouse") or "",
        })

    po = frappe.get_doc({
        "doctype": "Purchase Order",
        "supplier": supplier,
        "company": company,
        "transaction_date": data.get("posting_date") or frappe.utils.today(),
        "schedule_date": data.get("schedule_date") or frappe.utils.add_days(frappe.utils.today(), 14),
        "is_subcontracted": 1,
        "items": po_items,
    })

    if data.get("tax_template"):
        po.taxes_and_charges = data["tax_template"]
        po.set_taxes()
        po.run_method("set_missing_values")
        po.run_method("calculate_taxes_and_totals")

    po.insert()

    if submit:
        po.submit()

    # 2. Create Subcontracting Order linked to the Purchase Order
    sco_service_items = []
    for i, row in enumerate(service_items):
        po_item = po.items[i] if i < len(po.items) else None
        sco_service_items.append({
            "item_code": row.get("item_code"),  # service item
            "fg_item": row.get("fg_item", ""),  # finished good
            "fg_item_qty": frappe.utils.flt(row.get("net_qty", 1)),
            "qty": frappe.utils.flt(row.get("gross_qty", 1)),
            "rate": frappe.utils.flt(row.get("rate", 0)),
            "purchase_order_item": po_item.name if po_item else "",
        })

    sco = frappe.get_doc({
        "doctype": "Subcontracting Order",
        "purchase_order": po.name,
        "supplier": supplier,
        "company": company,
        "transaction_date": data.get("posting_date") or frappe.utils.today(),
        "schedule_date": data.get("schedule_date") or frappe.utils.add_days(frappe.utils.today(), 14),
        "service_items": sco_service_items,
    })

    sco.run_method("set_missing_values")
    sco.insert()

    if submit:
        sco.submit()

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
