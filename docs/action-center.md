# Action Center

> **Route**: `/app/action-center`
> **Type**: Frappe Page (not a DocType)
> **Module**: Kniterp
> **Files**: `kniterp/page/action_center/` (HTML/JS/CSS/JSON) + `kniterp/api/action_center.py`

---

## 1. PURPOSE

Action Center is a **real-time operational dashboard** that surfaces all pending business actions across the entire order-to-invoice lifecycle. It answers the daily question: *"What needs my attention right now?"*

It aggregates data from Sales Orders, Purchase Orders, Work Orders, Delivery Notes, and Invoices into a single card-based view — eliminating the need to navigate 6+ different list views to find actionable items.

**Business problem it solves**: In a small knitting/textile manufacturing business, the owner or operator needs a single screen to see:
- Which orders are stuck waiting for raw material
- Which orders are ready to start production
- Which subcontracted items need material to be sent or received
- Which deliveries are pending
- Which invoices (sales and purchase) need to be created

Without this, the user would need to open Production Wizard, then check Purchase Orders list, then Delivery Notes list, then check billing status — a tedious multi-screen workflow for 2-3 non-tech-savvy users.

---

## 2. DATA MODEL

Action Center has **no doctype or database tables**. It is a read-only aggregation page that queries existing ERPNext documents in real-time.

### Data Sources Queried

| Card | Primary DocTypes Queried | Key Filters |
|------|--------------------------|-------------|
| Raw Material Shortage | Sales Order Item, BOM, BOM Item, Bin | SO submitted, not fully delivered, WO not started, RM stock < BOM requirement |
| Ready for Knitting | Sales Order Item, BOM, Bin | Same as above but RM stock >= BOM requirement |
| Send to Job Worker | Purchase Order (subcontracted), PO Item Supplied | PO submitted, material not fully supplied |
| Receive from Job Worker | Purchase Order (subcontracted) | PO status = Materials Transferred/Partially Received, per_received < 100 |
| Receive RM from Customer | Subcontracting Inward Order, SIO Item, SIO Received Item, BOM Item | SIO submitted, per_raw_material_received < 100 |
| Pending Purchase Receipt | Purchase Order (non-subcontracted) | PO submitted, per_received < 100 |
| Pending Purchase Invoice | Purchase Order (both types), Purchase Invoice Item | PO submitted, per_billed < 100 |
| Pending Delivery | Sales Order, SO Item, Work Order, Bin | SO submitted, manufactured_qty > delivered_qty |
| Pending Sales Invoice | Delivery Note, DN Item, Sales Invoice Item | DN submitted, per_billed < 100 |

### Access Control

Defined in `kniterp/api/access_control.py`:

- **Read access**: Manufacturing Manager, Manufacturing User, System Manager, Stock Manager (page roles)
- **Write access** (create/submit PI): `ACTION_CENTER_WRITE_ROLES` = Manufacturing Manager, Manufacturing User, System Manager, Stock Manager

---

## 3. BUSINESS LOGIC

### 3.1 Dashboard Cards (Summary View)

`get_action_items()` calls 9 category functions, each returning:
```python
{
    'count': int,        # Total items needing action
    'items': list[:5],   # Top 5 items for preview
    'label': str,        # Card title
    'color': str         # danger|warning|success|info
}
```

**Color coding priority**:
- **Red (danger)**: RM Shortage — production is blocked
- **Orange (warning)**: Knitting Pending, Send/Receive JW, Receive RM, Purchase Receipt/Invoice — needs action
- **Green (success)**: Pending Delivery, Pending Sales Invoice — money is close

**Key computation — RM availability check** (`check_rm_availability()`):
1. Find default active BOM for the FG item
2. For each BOM Item, calculate `needed = (bom_item_qty / bom_qty) * required_qty`
3. Check `SUM(actual_qty)` from `tabBin` across all warehouses
4. If any RM is short → item goes to "Shortage" card; otherwise → "Ready for Knitting"

**Key computation — Delivery readiness** (`get_pending_delivery_items()`):
1. For each pending SO Item, check linked Work Orders' `produced_qty`
2. `ready_to_deliver = manufactured_qty - delivered_qty`
3. If no Work Order exists, falls back to checking total stock in `tabBin`

### 3.2 Fix Dialogs (Detail View)

Each card has a "Fix" button (contextual label: Resolve/Produce/Send/Receive/Invoice/Deliver) that opens a detail dialog via `get_fix_details(action_key)`.

Fix dialogs provide:
- **Tabular detail view** with selectable rows (checkboxes)
- **Row actions**: Per-item actions (Create PO, Create WO, View, etc.)
- **Bulk actions**: Multi-select operations (Consolidated PO, Bulk Create WO, Bulk Create PI, Bulk Submit PI)

### 3.3 Row Actions (per card type)

| Card | Row Actions | What It Does |
|------|-------------|--------------|
| RM Shortage | Create PO, View | Opens new PO pre-filled with shortage item; or navigates to Production Wizard |
| Ready for Knitting | Create WO, View | Calls `production_wizard.create_work_order()` API; or navigates to PW |
| Send to Job Worker | Send, View PO | Navigates to Production Wizard (with SO item context) or PO form |
| Receive from Job Worker | Receive, View PO | Same pattern — PW or PO form |
| Receive RM from Customer | Receive, View | Opens Subcontracting Inward Order form |
| Pending Purchase Receipt | Create PR, View PO | Calls ERPNext's `make_purchase_receipt()` mapper |
| Pending Purchase Invoice | Create PI, View PO | Calls ERPNext's `make_purchase_invoice()` mapper |
| Pending Delivery | Create DN, View | Opens new DN pre-filled with customer |
| Pending Sales Invoice | Create Invoice, View DN | Calls ERPNext's `make_sales_invoice()` mapper; shows "View Draft" if draft exists |

### 3.4 Bulk Actions

| Action | Trigger | Behavior |
|--------|---------|----------|
| Consolidated PO | RM Shortage: select multiple items | Aggregates shortages by RM item → supplier selection dialog → calls `production_wizard.create_purchase_orders_for_shortage()` |
| Bulk Create WO | Knitting Pending: select multiple | Sequential sync calls to `production_wizard.create_work_order()` for each |
| Bulk Create PI | Purchase Invoice: select multiple | Opens bill_no/bill_date input dialog → sequential sync calls to `action_center.create_purchase_invoice()` |
| Bulk Submit PI | Draft invoices section | Confirmation dialog → sequential sync calls to `action_center.submit_purchase_invoice()` |
| Bulk Create Sales Invoice | Pending Invoice: select multiple | Confirmation → sequential calls to ERPNext's `make_sales_invoice()` |

### 3.5 Purchase Invoice Handling (Write Operations)

The only two write APIs on this module:

- **`create_purchase_invoice(po_name, bill_no, bill_date)`**: Wraps ERPNext's `make_purchase_invoice()`, sets bill_no/bill_date, and saves as Draft
- **`submit_purchase_invoice(invoice_name)`**: Submits a Draft Purchase Invoice

Both enforce `require_action_center_write_access()` before execution.

The PI fix dialog has a **split table design**:
- Top table: POs without draft invoices (with "Create Invoice" actions)
- Bottom table ("Draft Invoices"): POs that already have draft PIs (with "View Draft" and bulk submit)

---

## 4. WORKFLOW

### Daily Usage Pattern

```
User opens /app/action-center
        │
        ▼
   ┌─────────────────────────────────────┐
   │  Dashboard: 9 cards with counts     │
   │  (only cards with count > 0 shown)  │
   └─────────────────────────────────────┘
        │
        ├── Click card item → Navigate to relevant form/wizard
        │
        ├── Click "Resolve/Produce/Send/..." button on card
        │       │
        │       ▼
        │   ┌──────────────────────────────────┐
        │   │  Fix Dialog: detail table         │
        │   │  ☐ Select rows for bulk action    │
        │   │  [Row Action] per item            │
        │   │  [Bulk Action] for selection      │
        │   └──────────────────────────────────┘
        │
        └── Click "View All" → Navigate to filtered list/wizard
```

### Navigation Flow

- **RM Shortage / Knitting Pending / Delivery / Invoice cards** → Link to Production Wizard with pre-set filters (`materials_status`, `invoice_status`, `selected_item`)
- **Purchase Receipt / Purchase Invoice cards** → Link to Purchase Order list with filters
- **JW Send/Receive cards** → Production Wizard (if SO item linked) or direct PO form
- **Customer RM Receive** → Subcontracting Inward Order form

### "View All" Button Destinations

| Card | View All Target |
|------|-----------------|
| Raw Material Shortage | Production Wizard (materials_status=Shortage) |
| Ready for Knitting | Production Wizard (materials_status=Ready) |
| Pending Delivery | Production Wizard (invoice_status=Ready to Deliver) |
| Pending Sales Invoice | Production Wizard (invoice_status=Ready to Invoice) |
| Pending Purchase Receipt | Purchase Order List (filtered) |
| Pending Purchase Invoice | Purchase Order List (filtered) |
| JW cards | First item's link (PW or PO form) |

---

## 5. INTEGRATION

### With Production Wizard
- **Heavy dependency**: Uses `production_wizard.get_pending_production_items()` as the base dataset for RM Shortage and Knitting Pending
- Uses `production_wizard.get_production_details()` for BOM breakdown in shortage details
- Uses `production_wizard.create_work_order()` for WO creation
- Uses `production_wizard.create_purchase_orders_for_shortage()` for consolidated PO creation
- Deep-links to Production Wizard with route_options for filtered views

### With ERPNext Core
- **Purchase Order**: Queries for subcontracted and regular POs; uses ERPNext mappers for PR/PI creation
- **Work Order**: Queries `produced_qty` to determine delivery readiness
- **Delivery Note**: Queries for unbilled DNs; uses ERPNext mapper for Sales Invoice creation
- **Sales Order**: Primary source for production pipeline data
- **BOM/BOM Item**: Used for RM availability calculations
- **Bin**: Stock availability checks via `SUM(actual_qty)`
- **Subcontracting Inward Order**: Custom KnitERP doctype for job work inward

### With Access Control
- Imports `require_action_center_write_access` from `kniterp/api/access_control.py`
- Read operations have no explicit permission check (page-level role restriction handles it)
- Write operations (create/submit PI) explicitly check roles

---

## 6. GOTCHAS

### Performance
- **26 SQL call sites** in action_center.py (flagged in discovery audit)
- `get_action_items()` makes 9 sequential function calls, each with multiple DB queries
- RM shortage check iterates ALL pending production items and checks BOM + stock for each — O(n) DB calls per item
- No caching — every refresh re-queries everything
- Dashboard card items are limited to top 5 (`items[:5]`) but full count is computed

### Fragile Areas
- **Bulk actions use `async: false`** — synchronous sequential API calls that block the browser. If one fails midway, some items are processed and some are not (no transaction rollback across bulk)
- `check_rm_availability()` uses total stock across ALL warehouses (`SUM(actual_qty) FROM tabBin`) — doesn't respect warehouse-specific allocation
- `get_available_stock()` (used in delivery readiness) also checks all warehouses globally
- The Subcontracting Inward Order handling has a defensive `try/except` that silently swallows errors (lines 281-290) — if the doctype changes, the card just shows empty

### Data Quirks
- RM Shortage and Knitting Pending both call `get_pending_production_items()` separately — the same data is fetched twice on every refresh
- `get_pending_production_items()` wraps `production_wizard.get_pending_production_items()` and enriches with WO status — another N+1 query pattern
- Purchase Invoice fix dialog separates POs into two tables (no-draft vs has-draft) using a `draft_data` key — the JS has duplicated column rendering logic for both tables
- The `_raw_shortage` field exists alongside `shortage` to preserve unrounded values for PO creation

### XSS Note
- Item titles and descriptions are injected into HTML via template literals without escaping (e.g., `${item.title}`) — safe as long as item names don't contain HTML, which ERPNext generally prevents

---

## 7. INTENT

### Why Not Just Use ERPNext List Views?

ERPNext's default approach requires users to:
1. Open Sales Order list, filter for pending production
2. Open each SO, check BOM, check stock levels
3. Navigate to Purchase Order list for pending receipts
4. Navigate to Delivery Note list for pending invoices
5. Understand complex status fields (per_delivered, per_billed, per_received)

**For 2-3 non-tech-savvy users** who think in Tally-style workflows, this is overwhelming. They want a single screen that says:
- "You have 5 orders waiting for yarn" → Click to fix
- "3 orders are ready to start knitting" → Click to produce
- "2 deliveries are ready" → Click to deliver

### The Tally Mental Model

Tally users are accustomed to a **task-oriented dashboard** — not document-oriented navigation. They think:
- "What do I need to buy?" (not "filter Purchase Orders by status")
- "What can I deliver today?" (not "check Work Order produced_qty vs SO delivered_qty")
- "Which supplier bills do I need to enter?" (not "filter POs by per_billed < 100")

Action Center translates ERPNext's document-centric data into **action-oriented cards** with plain language labels and one-click resolution.

### Why a Page and Not a Dashboard/Workspace?

- **Frappe Workspaces** are layout-based and can't run complex aggregation queries or show interactive dialogs
- **Number Cards/Charts** can show counts but can't provide drill-down fix dialogs with bulk actions
- A custom **Page** gives full control over the UI, allows the fix dialog pattern, and supports the card → drill-down → action workflow

### Why Fix Dialogs Instead of Just Linking to List Views?

The fix dialog pattern provides:
1. **Context-aware actions**: Each row has relevant actions (Create PO for shortage, Create WO for ready items)
2. **Bulk operations**: Select multiple items and act on them together (consolidated PO, bulk WO creation)
3. **Pre-populated forms**: When creating a PO from shortage, the item and qty are already filled in
4. **No context switching**: The user stays in Action Center while resolving items, only leaving when they need to fill in details (like supplier selection)

### Design Trade-offs

- **Read-heavy, compute-on-demand**: No materialized views or cached counts — ensures data is always fresh but at a performance cost
- **Tight coupling with Production Wizard**: Reuses PW's data fetching and action APIs rather than duplicating logic
- **Sequential bulk operations**: Uses `async: false` for simplicity (guaranteed order) at the cost of UX responsiveness — acceptable for small data volumes (dozens, not thousands)
