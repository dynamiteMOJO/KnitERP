# Transaction Desk

## 1. PURPOSE

Transaction Desk is a **unified, simplified voucher creation interface** that replaces the standard ERPNext form experience for creating 16 different transaction types from a single page (`/app/transaction-desk`).

**Business problem it solves:** ERPNext's native transaction forms (Sales Order, Purchase Invoice, Journal Entry, etc.) each have 50-100+ fields spread across multiple tabs. For a small knitting business with 2-3 non-tech-savvy users, this is overwhelming. Transaction Desk strips each transaction down to only the essential fields and presents them in a clean, Tally-like rapid-entry interface.

**Why it exists:** Users coming from Tally are accustomed to typing a voucher in seconds — party name, items, amounts, done. ERPNext's full forms feel heavy and confusing by comparison. Transaction Desk bridges that gap by providing a purpose-built entry screen that feels like a simplified voucher pad, while still creating proper ERPNext documents under the hood.

---

## 2. DATA MODEL

Transaction Desk is a **Frappe Page** (not a DocType), so it has no persistent data model of its own. It creates standard ERPNext documents via API calls.

### Page Definition
- **Type:** Frappe Page (`kniterp/page/transaction_desk/`)
- **Route:** `/app/transaction-desk`
- **Files:** `transaction_desk.json`, `.js`, `.css`, `.html`

### Supporting Doctypes

#### Transaction Parameter (Master)
A fixture-managed master list of parameter types (e.g., "GSM", "Color").

| Field | Type | Notes |
|-------|------|-------|
| `parameter_name` | Data | Unique, used as name (autoname) |
| `applies_to` | Data | Informational label (e.g., "Dyeing", "Any") |
| `is_active` | Check | Default 1 |
| `description` | Small Text | Optional |

**Fixture data:** GSM, Color

#### SO Transaction Parameter (Standalone)
Denormalized records for reporting on Sales Order item parameters.

| Field | Type | Notes |
|-------|------|-------|
| `sales_order` | Link → Sales Order | Read-only, required |
| `sales_order_item` | Data | Row name reference, required |
| `item_code` | Link → Item | Read-only |
| `parameter` | Link → Transaction Parameter | Required |
| `value` | Data | Required |

#### PO Transaction Parameter (Standalone)
Mirror of SO Transaction Parameter for Purchase Orders.

| Field | Type | Notes |
|-------|------|-------|
| `purchase_order` | Link → Purchase Order | Read-only, required |
| `purchase_order_item` | Data | Row name reference, required |
| `item_code` | Link → Item | Read-only |
| `parameter` | Link → Transaction Parameter | Required |
| `value` | Data | Required |

### Custom Field on Standard Doctypes
- `custom_transaction_params_json` — a JSON text field added to **Sales Order Item** and **Purchase Order Item** child tables. Stores `[{parameter, value}, ...]` per item row. This is the primary storage; the standalone doctypes above are denormalized copies for reporting.

---

## 3. BUSINESS LOGIC

### API Layer (`kniterp/api/transaction_desk.py`)

**7 whitelisted methods:**

| Method | Purpose |
|--------|---------|
| `get_defaults(voucher_type)` | Returns smart defaults: company, currency, cost center, posting date, warehouse, tax templates, payment modes, accounts list, warehouse list |
| `get_item_details(item_code, voucher_type)` | Fetches item name, UOM, description, and price (selling vs buying based on voucher type) |
| `create_transaction(voucher_type, data, submit)` | Main creation endpoint — dispatches to 14 internal creator functions, optionally submits |
| `get_tax_details(voucher_type, template_name)` | Returns tax rows for a template so the form can preview them |
| `get_default_tax_template(voucher_type, company)` | Uses India Compliance's GST logic to determine the default tax template |
| `get_party_tax_template(voucher_type, party, company)` | Uses India Compliance's GST logic to determine tax template based on party GSTIN |
| `get_recent_transactions(voucher_type, limit)` | Returns recent transactions by current user for the sidebar |

### Voucher Type Classification

```python
SALES_TYPES = ("sales-order", "sales-invoice", "delivery-note", "credit-note", "job-work-in")
PURCHASE_TYPES = ("purchase-order", "purchase-invoice", "purchase-receipt", "debit-note", "job-work-out")
ITEM_TYPES = SALES_TYPES + PURCHASE_TYPES + ("stock-entry",)
PAYMENT_TYPES = ("payment-receive", "payment-pay")
JOURNAL_TYPES = ("journal-entry", "contra-entry")
```

### Internal Creator Functions (14 total)

Each voucher type has a dedicated `_create_*` function that:
1. Builds an ERPNext doc dict from the simplified payload
2. Handles type-specific logic (e.g., negative qty for returns, dual-doc creation for job work)
3. Applies tax template via `set_taxes()` + `calculate_taxes_and_totals()` if provided

**Special cases:**
- **Credit Note** (`_create_credit_note`): Can be created with or without items. Without items, creates a single-line invoice using the credit amount.
- **Debit Note** (`_create_debit_note`): Forces negative quantities (`-abs(qty)`), sets `is_return=1`.
- **Job Work In** (`_create_job_work_in`): Creates TWO documents — a subcontracted Sales Order + a Subcontracting Inward Order linked to it.
- **Job Work Out** (`_create_job_work_out`): Creates TWO documents — a subcontracted Purchase Order + a Subcontracting Order linked to it.

### Transaction Parameters Sync (`kniterp/api/transaction_parameters.py`)

Two doc_event hooks triggered on Sales Order and Purchase Order save:

- `sync_so_params(doc, method)` — On SO `on_update` and `on_update_after_submit`
- `sync_po_params(doc, method)` — On PO `on_update` and `on_update_after_submit`

**Logic:** For each item row, deletes existing standalone parameter records, then parses `custom_transaction_params_json` and creates fresh standalone records. This denormalization enables direct Report Builder queries on parameters without JSON parsing.

### Client-side Tax Calculation

The JS implements full ERPNext-accurate tax calculation supporting all 5 `charge_type` modes:
- On Net Total
- On Previous Row Amount
- On Previous Row Total
- On Item Quantity
- Actual

Also calculates per-item tax distribution for display.

---

## 4. WORKFLOW

### User Journey

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. ENTRY POINT                                                  │
│    • Navigate to /app/transaction-desk                          │
│    • OR click "+ Add" on Sales Order / Purchase Order list      │
│      (redirected via list view override)                        │
└──────────────────────┬──────────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. TYPE SELECTOR (if no type in route)                          │
│    Visual grid of 16 voucher types grouped by:                  │
│    • Sales (SO, SI, DN, Credit Note, Job Work In)               │
│    • Purchase (PO, PI, PR, Debit Note, Job Work Out)            │
│    • Payments (Receive, Pay)                                    │
│    • Accounting (Journal Entry)                                 │
│    • Stock (Stock Entry, Job Work In/Out)                       │
│    Keyboard navigable (arrow keys + Enter)                      │
└──────────────────────┬──────────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. FORM VIEW                                                    │
│    Layout: 9-col form + 3-col recent entries sidebar            │
│                                                                 │
│    Header fields (2-col grid):                                  │
│    • Company (default auto-filled)                              │
│    • Date (today)                                               │
│    • Party (Customer/Supplier)                                  │
│    • Addresses (auto-fetched on party select)                   │
│    • Delivery/Due Date                                          │
│    • Tax Template (auto-set via India Compliance GST logic)     │
│    • Type-specific fields (PO No, Bill No, Purpose, etc.)       │
│                                                                 │
│    Item table (or Accounts table for JV):                       │
│    • Add/remove rows dynamically                                │
│    • Item link uses smart fuzzy search                          │
│    • Auto-fills: item name, UOM, price, description             │
│    • Expandable detail panel per row (description + params)     │
│    • Transaction Parameters: badge display + dialog editor      │
│                                                                 │
│    Tax preview table (live-calculated from template)            │
│    Totals card: Net Total → Tax → Grand Total                   │
│                                                                 │
│    Sidebar: Last 10 transactions of same type by current user   │
└──────────────────────┬──────────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. CREATE ACTION                                                │
│    • "Create" button (or Alt+Enter)                             │
│    • Client-side validation (required fields, items, JV balance)│
│    • Dialog: "Submit" or "Save as Draft"                        │
│    • API call: create_transaction()                             │
│    • For Job Work: creates 2 linked documents                   │
└──────────────────────┬──────────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. SUCCESS SCREEN                                               │
│    • Animated checkmark                                         │
│    • Document link + status badge                               │
│    • Amount display                                             │
│    • For Job Work: links to both created documents              │
│    • Actions: "Create Another", "Open in Full Form", "Back"     │
└─────────────────────────────────────────────────────────────────┘
```

### Keyboard Shortcuts
- **Arrow keys** on type selector: navigate between cards
- **Enter/Space** on type selector: select type
- **Alt+Enter** in form: submit
- **Escape** in form: back to type selector

---

## 5. INTEGRATION

### Documents Created
Transaction Desk creates standard ERPNext documents — it's a UI layer, not a data layer:

| TD Voucher Type | ERPNext DocType Created | Special Notes |
|----------------|------------------------|---------------|
| sales-order | Sales Order | |
| purchase-order | Purchase Order | |
| sales-invoice | Sales Invoice | |
| purchase-invoice | Purchase Invoice | |
| delivery-note | Delivery Note | |
| purchase-receipt | Purchase Receipt | |
| credit-note | Sales Invoice | `is_return=1`, negative qty |
| debit-note | Purchase Invoice | `is_return=1`, negative qty |
| payment-receive | Payment Entry | `payment_type="Receive"` |
| payment-pay | Payment Entry | `payment_type="Pay"` |
| journal-entry | Journal Entry | |
| contra-entry | Journal Entry | `voucher_type="Contra Entry"` |
| stock-entry | Stock Entry | 5 purpose types supported |
| job-work-in | Sales Order + Subcontracting Inward Order | Both `is_subcontracted=1` |
| job-work-out | Purchase Order + Subcontracting Order | Both `is_subcontracted=1` |

### India Compliance Integration
- Tax template auto-selection uses `india_compliance.gst_india.overrides.transaction.get_gst_details`
- Resolves correct GST template based on company GSTIN and party GSTIN
- Gracefully falls back to empty string if India Compliance is not available

### ERPNext Party Details Integration
- On party selection, calls `erpnext.accounts.party.get_party_details` to auto-fill addresses
- Purchase-side also fetches company addresses for billing/shipping

### Smart Item Search Integration
- Item link fields use `kniterp.api.item_search.smart_search` (fuzzy token-based search)

### List View Overrides
- `sales_order_list.js`: Hijacks "+ Add" button → redirects to Transaction Desk with `type: 'sales-order'`
- `purchase_order_list.js`: Hijacks "+ Add" button → redirects to Transaction Desk with `type: 'purchase-order'`

### Hooks
```python
# hooks.py
doc_events = {
    "Sales Order": {
        "on_update": "kniterp.api.transaction_parameters.sync_so_params",
        "on_update_after_submit": "kniterp.api.transaction_parameters.sync_so_params"
    },
    "Purchase Order": {
        "on_update": "kniterp.api.transaction_parameters.sync_po_params",
        "on_update_after_submit": "kniterp.api.transaction_parameters.sync_po_params"
    },
}

doctype_list_js = {
    "Sales Order": "public/js/sales_order_list.js",
    "Purchase Order": "public/js/purchase_order_list.js",
}

fixtures = ["Transaction Parameter", ...]
```

### Permission Model
Page accessible to: Accounts User, Stock User, Sales User, Purchase User, System Manager.

---

## 6. GOTCHAS

### Link Field Value Tracking
Frappe's `Link` controls behave differently outside a `Form` context. The code manually wraps `get_value()` and tracks `_selected_value` via `awesomplete-selectcomplete` and `blur` events. This pattern is repeated for every Link control (form fields, item rows, account rows, UOM fields). **If this breaks, values silently become empty strings.**

### Tax Template Fallback Chain
The `load_tax_details()` method has a triple-fallback to read the tax template value:
1. `get_field_value('tax_template')` (control's get_value)
2. `form_controls.tax_template._selected_value`
3. Direct `$input.val()`

This exists because the Link control's value tracking is unreliable outside a Form.

### Transaction Parameters: JSON + Denormalized Records
Parameters are stored in TWO places:
1. `custom_transaction_params_json` on SO/PO Item rows (JSON string, primary source)
2. `SO Transaction Parameter` / `PO Transaction Parameter` standalone records (for reporting)

The sync runs `ignore_permissions=True` and does a delete-all-then-reinsert on every save. This means:
- If the sync hook fails silently, the standalone records become stale
- The standalone records are **not authoritative** — the JSON field is

### Job Work Creates Multiple Documents
Job Work In/Out are special: they create 2 documents in a single API call and manage their own `frappe.db.commit()`. The success screen shows links to both.

### Credit Note Without Items
Credit Notes can be created with just an amount (no items). The API creates a synthetic item row with `item_name="Credit Note"` and the company's default income account.

### Contra Entry is a Journal Entry
"Contra Entry" in the type selector maps to `Journal Entry` with `voucher_type="Contra Entry"`. It's the same doctype, different entry_type.

### No Warehouse for Some Types
Payment types and journal types skip warehouse fields entirely (`NO_WAREHOUSE_TYPES`).

### No Test Files
There are **no automated tests** for Transaction Desk. All testing is manual.

### `_get_raw_value` Hack
The JS uses a custom `_get_raw_value()` method that strips non-numeric characters from input values. This handles intermediate typing states (e.g., "1,0" while typing "1,000") but can be fragile with locale-specific number formatting.

---

## 7. INTENT

### Why Transaction Desk Exists (The Tally User's Perspective)

**The core insight:** In Tally, creating a voucher is a 30-second keyboard-driven flow. You press a shortcut, type the party name, add items with quantities and rates, and press Enter to save. That's it.

In ERPNext, creating even a simple Sales Order requires:
- Navigating to the Sales Order list
- Clicking "New"
- Scrolling through a form with 80+ fields across multiple sections
- Figuring out which fields are relevant (most aren't for a small business)
- Dealing with mandatory fields you don't understand
- Saving, then optionally submitting

**Transaction Desk collapses this into a Tally-like experience:**

1. **Single entry point for all transactions** — Instead of remembering routes to 12+ different doctypes, users go to one page and pick from a visual menu. This mirrors Tally's "Accounting Vouchers" menu.

2. **Only essential fields** — A Sales Order in Transaction Desk shows ~8 fields. The real ERPNext form has 80+. The API fills in everything else with smart defaults.

3. **Inline item entry** — Items are added in a simple table with just Item, Qty, UOM, Rate, Amount. No child table navigation, no scrolling through 20 columns.

4. **Transaction Parameters** — This is a textile-specific need. When ordering fabric, every line item needs metadata like GSM (grams per square meter) and Color. ERPNext has no native concept of this. Rather than fighting with Custom Fields on child tables (which would add columns to every transaction globally), Transaction Desk stores these as structured JSON with a clean badge UI.

5. **Auto-tax via India Compliance** — Tax template selection in ERPNext requires understanding CGST/SGST/IGST rules based on party GSTIN. Transaction Desk auto-resolves this, so users never need to think about it.

6. **Draft vs Submit in one flow** — ERPNext's two-step save-then-submit is confusing. Transaction Desk shows a single dialog: "Submit or Save as Draft?"

7. **Success feedback** — After creation, users see a clear confirmation with the document link, amount, and options to continue. This replaces ERPNext's redirect-to-form-view behavior, which can feel disorienting.

### Why a Page, Not a Custom Form/Web Form

- **Pages allow full JS control** — Custom forms are constrained by Frappe's form framework. A Page lets the code build completely custom UI, handle keyboard navigation, manage multiple table types, and show real-time tax calculations.
- **Decoupled from ERPNext upgrades** — Since it creates documents via API (not by extending forms), ERPNext upgrades don't break the UI.
- **Intentionally separate from Production Wizard** — Transaction Desk is for standalone ad-hoc entries. Production Wizard is for SO-driven manufacturing flows. Different contexts, different UX needs.

### Why Denormalized Transaction Parameters

The `custom_transaction_params_json` field stores parameters as JSON on the SO/PO Item row. This is the simplest storage mechanism. But Frappe's Report Builder can't query inside JSON fields, so the standalone `SO/PO Transaction Parameter` doctypes exist purely to enable reports like "show all SOs where GSM = 180".

---

## File Reference

| File | Purpose |
|------|---------|
| `kniterp/page/transaction_desk/transaction_desk.json` | Page definition (roles, metadata) |
| `kniterp/page/transaction_desk/transaction_desk.html` | Minimal root div |
| `kniterp/page/transaction_desk/transaction_desk.js` | Full client-side logic (~2250 lines) |
| `kniterp/page/transaction_desk/transaction_desk.css` | All styling (~490 lines) |
| `kniterp/api/transaction_desk.py` | 7 whitelisted API methods + 14 internal creators (~1089 lines) |
| `kniterp/api/transaction_parameters.py` | SO/PO parameter sync hooks (~61 lines) |
| `kniterp/doctype/transaction_parameter/` | Master parameter doctype (fixture) |
| `kniterp/doctype/so_transaction_parameter/` | SO item parameter records (denormalized) |
| `kniterp/doctype/po_transaction_parameter/` | PO item parameter records (denormalized) |
| `kniterp/fixtures/transaction_parameter.json` | Seed data: GSM, Color |
| `kniterp/public/js/sales_order_list.js` | List view override: redirect "+ Add" to TD |
| `kniterp/public/js/purchase_order_list.js` | List view override: redirect "+ Add" to TD |
| `kniterp/hooks.py` | doc_events, doctype_list_js, fixtures config |
