import frappe
from frappe import _


# ──────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_item_details(item_code: str) -> dict:
    """Fetch item name, UOM, description, and selling price for transaction desk."""
    item = frappe.get_cached_doc("Item", item_code)
    result = {
        "item_name": item.item_name or "",
        "stock_uom": item.stock_uom or "",
        "description": (item.description or "").strip(),
    }

    # Try to get selling price
    price = frappe.db.get_value(
        "Item Price",
        {"item_code": item_code, "selling": 1},
        "price_list_rate",
    )
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
    if voucher_type in ("sales-order", "delivery-note", "credit-note"):
        defaults["warehouse"] = default_wh
    elif voucher_type in ("purchase-order", "receipt-note", "debit-note"):
        defaults["warehouse"] = default_wh

    # Tax templates
    if voucher_type in ("sales-order", "delivery-note", "credit-note"):
        templates = frappe.get_all(
            "Sales Taxes and Charges Template",
            filters={"company": company},
            fields=["name", "is_default"],
            order_by="is_default desc",
        )
        defaults["tax_templates"] = templates
        defaults["default_tax_template"] = next((t["name"] for t in templates if t["is_default"]), "")
    elif voucher_type in ("purchase-order", "receipt-note", "debit-note"):
        templates = frappe.get_all(
            "Purchase Taxes and Charges Template",
            filters={"company": company},
            fields=["name", "is_default"],
            order_by="is_default desc",
        )
        defaults["tax_templates"] = templates
        defaults["default_tax_template"] = next((t["name"] for t in templates if t["is_default"]), "")

    # Payment-specific defaults
    if voucher_type in ("payment-receive", "payment-pay"):
        defaults["modes_of_payment"] = frappe.get_all("Mode of Payment", pluck="name")
        defaults["default_receivable_account"] = company_doc.default_receivable_account or ""
        defaults["default_payable_account"] = company_doc.default_payable_account or ""
        defaults["default_bank_account"] = _get_default_bank_account(company)
        defaults["default_cash_account"] = _get_default_cash_account(company)

    # Journal Entry defaults
    if voucher_type in ("journal-entry", "contra-entry"):
        defaults["accounts"] = frappe.get_all(
            "Account",
            filters={"company": company, "is_group": 0},
            fields=["name", "account_type", "account_currency"],
            order_by="name",
            limit=200,
        )

    # Warehouses for item table
    if voucher_type not in ("payment-receive", "payment-pay", "journal-entry", "contra-entry"):
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
    }

    creator = creators.get(voucher_type)
    if not creator:
        frappe.throw(_("Unknown voucher type: {0}").format(voucher_type))

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

    if voucher_type in ("sales-order", "delivery-note", "credit-note"):
        parent_doctype = "Sales Taxes and Charges Template"
        child_doctype = "Sales Taxes and Charges"
    elif voucher_type in ("purchase-order", "receipt-note", "debit-note"):
        parent_doctype = "Purchase Taxes and Charges Template"
        child_doctype = "Purchase Taxes and Charges"
    else:
        return []

    return frappe.get_all(
        child_doctype,
        filters={"parent": template_name, "parenttype": parent_doctype},
        fields=["charge_type", "account_head", "description", "rate", "tax_amount", "total", "idx"],
        order_by="idx",
    )


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
    }

    if voucher_type and voucher_type in type_map:
        doctype = type_map[voucher_type]
        filters = {"owner": user}

        if voucher_type == "payment-receive":
            filters["payment_type"] = "Receive"
        elif voucher_type == "payment-pay":
            filters["payment_type"] = "Pay"

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

        return frappe.get_all(
            doctype,
            filters=filters,
            fields=fields,
            order_by="creation desc",
            limit=limit,
        )

    return []


# ──────────────────────────────────────────────────────────────
# Internal creators
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

    # Determine paid_from / paid_to based on payment type
    if payment_type == "Receive":
        paid_to = _get_account_for_mode_of_payment(mode_of_payment, company) or data.get("paid_to") or _get_default_bank_account(company)
        paid_from = ""  # Will be set by Payment Entry logic
    else:
        paid_from = _get_account_for_mode_of_payment(mode_of_payment, company) or data.get("paid_from") or _get_default_bank_account(company)
        paid_to = ""  # Will be set by Payment Entry logic

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
# Helpers
# ──────────────────────────────────────────────────────────────

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
