# Production Wizard — Manufacturing Lifecycle (Session 1/3)

> **Scope**: Work Order creation, starting, in-house operation completion,
> Job Card completion, revert, and lot tracking helpers.
> Excludes: subcontracting flow, delivery, invoicing (sessions 2-3).
>
> **Source files analysed**:
> - `kniterp/api/production_wizard.py` (4,727 lines) — 38 API endpoints
> - `kniterp/kniterp/page/production_wizard/production_wizard.js` (3,873 lines)
> - `kniterp/kniterp/overrides/work_order.py` (233 lines) — CustomWorkOrder
> - `kniterp/kniterp/overrides/job_card.py` (513 lines) — CustomJobCard
> - `kniterp/api/stock_reservation_service.py` (289 lines) — SRE/Bin service
>
> **Last updated**: 2026-03-06 — ERPNext 16.7.3 / Frappe 16.10.6

---

## Table of Contents

1. [Manufacturing Lifecycle Overview](#1-manufacturing-lifecycle-overview)
2. [Document Creation Chain](#2-document-creation-chain)
3. [Step 1: Pending Production Items](#3-step-1-pending-production-items)
4. [Step 2: Create Work Order](#4-step-2-create-work-order)
5. [Step 3: Start Work Order (Submit + Create Job Cards)](#5-step-3-start-work-order)
6. [Step 4: Complete Operation (In-House)](#6-step-4-complete-operation-in-house)
7. [Step 5: Complete Job Card](#7-step-5-complete-job-card)
8. [Step 6: Revert Production Entry](#8-step-6-revert-production-entry)
9. [Incremental Production](#9-incremental-production)
10. [Overproduction Handling](#10-overproduction-handling)
11. [Lot Tracking Helpers](#11-lot-tracking-helpers)
12. [Custom Fields Used](#12-custom-fields-used)
13. [Doc Event Hooks (Manufacturing)](#13-doc-event-hooks-manufacturing)
14. [Override Layer (Manufacturing)](#14-override-layer-manufacturing)
15. [Known Issues & Technical Debt](#15-known-issues--technical-debt)
16. [API Method Reference](#16-api-method-reference)
17. [JS UI Dialog Reference](#17-js-ui-dialog-reference)

---

## 1. Manufacturing Lifecycle Overview

```
User sees SO items in wizard
        |
        v
[get_pending_production_items]  ──>  List of SO items with BOM, WO status
        |
        v
[create_work_order]  ──>  Draft Work Order (linked to SO Item + BOM)
        |
        v
[start_work_order]  ──>  Submit WO → Job Cards created (1 per operation)
        |                  Hook: set_planned_qty_on_work_order (WO.before_submit)
        |                  Hook: set_job_card_qty_from_planned_qty (JC.before_insert)
        v
[complete_operation]  ──>  Per-batch production (can call N times)
   |     |                   Creates: Time Log + Stock Entry (Manufacture)
   |     |                   Handles: lot traceability (SABB), batch creation
   |     v
   |  [revert_production_entry]  ──>  Cancel SE + remove Time Log
   |
   v
[complete_job_card]  ──>  Submit Job Card → close operation
   |                       For subcontracted: complete_subcontracted_job_card
   v
Next steps: Delivery Note → Sales Invoice (sessions 2-3)
```

---

## 2. Document Creation Chain

### Full Chain: Which ERPNext Documents Are Created, When, and In What Order

```
Step 1: create_work_order()
├── 1. Work Order (Draft)
│     Fields: production_item, bom_no, qty, sales_order, sales_order_item
│     For SCIO: subcontracting_inward_order, source_warehouse, reserve_stock=1
│     Calls: set_work_order_operations(), set_required_items()
│     Sets: custom_planned_output_qty on each WO Operation
│     Insert flags: ignore_mandatory=True, ignore_validate=True

Step 2: start_work_order()
├── 2. Work Order → Submitted (wo.submit())
│     Triggers before_submit hook → set_planned_qty_on_work_order()
│       └── Computes planned_qty on each WO Operation from BOM ratios
├── 3. Job Cards (Draft, one per operation — created by ERPNext on WO submit)
│     Triggers before_insert hook → set_job_card_qty_from_planned_qty()
│       └── Sets for_quantity from WO Operation.planned_qty
│     Updated by start_work_order: workstation, wip_warehouse, skip_material_transfer
│     Save flags: ignore_validate=True

Step 3: complete_operation() — called once per production batch
├── 4. Job Card Time Log (appended to JC.time_logs child table)
│     Fields: from_time, to_time, completed_qty, employee, workstation
├── 5. Machine Attendance (if knitting operation + employee + date + shift)
│     Linked via: ma.job_card_time_log = time_log.name
│     Insert flags: ignore_permissions=True
├── 6. Batch record (via ensure_batch_exists — output batch)
│     Fields: batch_id, item, source_type="In-house", custom_parent_batch
│     Insert flags: ignore_permissions=True
├── 7. Serial and Batch Bundle — Outward (per consumed RM with batch tracking)
│     Links consumed lot(s) to Stock Entry Detail row
│     Insert flags: ignore_permissions=True
├── 8. Serial and Batch Bundle — Inward (for output FG batch)
│     Links output batch to Stock Entry finished item row
│     Insert flags: ignore_permissions=True
├── 9. Stock Entry (Manufacture purpose) — SUBMITTED
│     Created via ManufactureEntry helper
│     RM rows: s_warehouse → consumed from source/WIP
│     FG row: t_warehouse → produced to target warehouse
│     fg_completed_qty = batch qty
│     job_card linked, work_order linked
│     Flags: ignore_mandatory=True
├── 10. Stock Reservation Entry (for SCIO WOs only)
│      Created by ensure_scio_fg_sre() — reserves produced FG
└── 11. Bin updates (reserved_qty_for_production adjusted)
       Via recalculate_bin_reserved_for_direct_consumption()

Step 4: complete_job_card() — called once to finalize
├── 12. Job Card → Submitted (jc.submit())
│      Triggers on_submit → update_subsequent_operations() if overproduction
│      CustomJobCard.set_status() prevents auto-completion
│      CustomJobCard.make_stock_entry_for_semi_fg_item() creates final SE
└── 13. Work Order status updated (wo.update_status())
```

### Revert Chain: revert_production_entry()

```
revert_production_entry(stock_entry)
├── Release SCIO FG SREs (release_scio_fg_sres_on_revert)
├── Cancel Stock Entry (se.cancel())
├── Recalculate Bin reserved_qty_for_production
├── Delete matching Job Card Time Log (frappe.delete_doc, ignore_permissions=True)
├── Delete linked Machine Attendance (ma.delete())
├── Rebuild lot references from remaining active SEs
├── Update JC: total_completed_qty, total_time_in_mins (db_set)
├── Recalculate manufactured_qty (jc.set_manufactured_qty())
└── Reset process_loss_qty to 0 (db_set)
```

---

## 3. Step 1: Pending Production Items

**API**: `get_pending_production_items(filters)` — [production_wizard.py:184](../kniterp/api/production_wizard.py#L184)

**Purpose**: Fetches all SO items pending manufacture to populate the wizard's main list.

**Query**: Single SQL query joining `tabSales Order Item` + `tabSales Order` with dynamic WHERE conditions.

**Filters supported**:
- `customer`, `from_date`, `to_date`, `item_code`
- `urgent` — delivery_date < today
- `invoice_status` — "Pending Production", "Ready to Deliver", "Ready to Invoice"
- `job_work` — "Inward" (is_subcontracted=1), "Outward" (has active SCO), "Standard"
- `materials_status` — "Ready" / "Shortage" (post-query filter)

**Key computed fields**:
- `bom_no` — from SOI.bom_no or default active BOM lookup (COALESCE subquery)
- `pending_qty` — `qty - delivered_qty` (adjusted for SCIO fg_item_qty ratio)
- `production_item` — `fg_item` if subcontracted, else `item_code`
- `work_order`, `work_order_status`, `produced_qty` — from linked WO (with SIO fallback for subcontracted)

**Post-query enrichment**: Per-item `frappe.db.get_value("Work Order", ...)` lookup for WO status. For "Ready to Deliver" filter, also queries Bin for stock availability.

---

## 4. Step 2: Create Work Order

**API**: `create_work_order(sales_order, sales_order_item)` — [production_wizard.py:1019](../kniterp/api/production_wizard.py#L1019)

**JS trigger**: `.btn-create-wo` button → direct API call (no dialog) — [production_wizard.js:1622](../kniterp/kniterp/page/production_wizard/production_wizard.js#L1622)

**Access control**: `require_production_write_access("create work orders")`

**Guard**: Checks for existing non-cancelled WO for this SO+SOI combination.

### Work Order Fields Set

| Field | Source | Notes |
|-------|--------|-------|
| `production_item` | `soi.fg_item` if subcontracted, else `soi.item_code` | Determines what gets manufactured |
| `bom_no` | `soi.bom_no` or default active BOM | BOM linked to production_item |
| `qty` | `soi.qty - soi.delivered_qty` | Adjusted by fg_item_qty/qty ratio for subcontracted |
| `sales_order` | SO name | Links WO to SO |
| `sales_order_item` | SOI name | Links WO to specific SO line |
| `company` | From SO | |
| `project` | From SO | |
| `fg_warehouse` | `soi.warehouse` | Target for finished goods |

### SCIO Integration (Subcontracted Orders)

When `is_subcontracted=1`, additional fields are set from SCIO:
- `subcontracting_inward_order` / `subcontracting_inward_order_item`
- `source_warehouse` = SCIO `customer_warehouse`
- `reserve_stock = 1`
- `use_multi_level_bom` from SCIO item
- `fg_warehouse` from SCIO delivery_warehouse
- `max_producible_qty` computed from SCIO received items (informational, does NOT cap wo.qty)

### Operation Planned Qty Calculation

After `set_work_order_operations()`, each WO Operation gets `custom_planned_output_qty`:
1. If BOM Operation has `finished_good_qty` > 0: `wo.qty * (bom_op.finished_good_qty / bom.quantity)`
2. Else if not last operation: uses next operation's consumed item qty from BOM
3. Fallback: `wo.qty`

### Insert Behavior
- `ignore_mandatory=True`, `ignore_validate=True`
- WO remains in **Draft** status until `start_work_order()` is called

---

## 5. Step 3: Start Work Order

**API**: `start_work_order(work_order, operation_settings)` — [production_wizard.py:1218](../kniterp/api/production_wizard.py#L1218)

**JS trigger**: `.btn-start-wo` button → "Start Production" dialog — [production_wizard.js:1645](../kniterp/kniterp/page/production_wizard/production_wizard.js#L1645)

**Dialog fields** (per-operation table):
| Column | Type | Notes |
|--------|------|-------|
| operation | Data (read-only) | Operation name from BOM |
| workstation | Link (Workstation) | Required; defaults from BOM |
| skip_material_transfer | Check | Default: 1 for knitting, 0 for others |
| wip_warehouse | Link (Warehouse) | Default: "Job Work Outward - O" for dyeing |

### Execution Flow

```python
1. wo.submit()
     ├── ERPNext creates Job Cards (1 per WO Operation)
     ├── Hook: set_planned_qty_on_work_order() [work_order.py:152]
     │     Computes planned_qty on each WO Operation:
     │       - Final FG operation: planned_qty = wo.qty
     │       - SFG operation: planned_qty = wo.qty * bom_op.finished_good_qty / bom.quantity
     │       - Fallback: planned_qty = wo.qty
     └── Per JC Hook: set_job_card_qty_from_planned_qty() [job_card.py:110]
           Sets jc.for_quantity = WO Operation.planned_qty

2. Post-submit: Update created Job Cards
     For each JC:
       - for_quantity ← custom_planned_output_qty (if set)
       - skip_material_transfer ← from user settings
       - wip_warehouse ← from user settings
       - workstation ← from user settings (with fallback to first matching)
       - jc.save(ignore_validate=True)
```

### Planned Qty Flow (SFG Tracking)

The planned_qty propagation ensures each operation knows its expected output:

```
BOM: Quantity = 100
  Op 1 (Knitting): finished_good_qty = 320 → planned_qty = WO_qty * 320/100
  Op 2 (Dyeing):   is_final_FG = True       → planned_qty = WO_qty
```

Two hooks work in sequence:
1. `WO.before_submit` → `set_planned_qty_on_work_order()` writes `planned_qty` on WO Operations
2. `JC.before_insert` → `set_job_card_qty_from_planned_qty()` reads WO Op `planned_qty` → sets JC `for_quantity`

---

## 6. Step 4: Complete Operation (In-House)

**API**: `complete_operation(work_order, operation, qty, workstation, employee, attendance_date, shift, consumed_lots, output_batch_no)` — [production_wizard.py:1631](../kniterp/api/production_wizard.py#L1631)

**JS trigger**: `.btn-complete-op` → "Update Manufactured Quantity" dialog — [production_wizard.js:2101](../kniterp/kniterp/page/production_wizard/production_wizard.js#L2101)

This is the **core production execution endpoint**. It can be called multiple times per operation for incremental/batch production.

### Dialog Fields

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| workstation | Link (Workstation) | Yes | Machine used; defaults from JC |
| employee | Link (Employee) | Knitting only | Operator |
| attendance_date | Date | Knitting only | |
| shift | Link (Shift Type) | Knitting only | |
| qty | Float | Yes | Quantity produced in this batch |
| lot_tables_html | HTML | — | FIFO batch allocation tables (per RM item) |
| output_batch_no | Data | Optional | Auto-derived from input lots; user can override |

### Execution Flow (Detailed)

```python
# 1. FIND JOB CARD
jc = get Job Card for (work_order, operation, docstatus != 2)

# 2. PARSE CONSUMED LOTS
# Supports two formats:
#   New: {"item_code": [{"batch_no": "Lot-1", "qty": 30}, ...]}
#   Old: {"item_code": "batch_no"}
# Normalizes to: consumed_lot_map = {item_code: [{batch_no, qty}]}
# For each consumed batch: ensure_batch_exists(source_type="Supplier")

# 3. ADD TIME LOG
jc.append("time_logs", {
    completed_qty: qty,
    employee: employee,
    workstation: workstation
})
jc.save()

# 4. CREATE MACHINE ATTENDANCE (knitting only)
# Linked: ma.job_card_time_log = time_log.name

# 5. RESET PROCESS LOSS
# ERPNext auto-calculates process_loss_qty = for_qty - completed_qty
# For partial batches this is wrong → reset to 0 via db_set

# 6. SYNC WORK ORDER
jc.update_work_order()

# 7. CREATE STOCK ENTRY (if job_card.finished_good exists)
ste = ManufactureEntry({
    for_quantity: qty,           # THIS batch's qty, not total
    job_card: jc.name,
    work_order: jc.work_order,
    purpose: "Manufacture",
    production_item: jc.finished_good,
    wip_warehouse: jc.wip_warehouse,
    fg_warehouse: jc.target_warehouse,
    bom_no: jc.semi_fg_bom or wo.bom_no,
})

# 7a. CUMULATIVE REMAINDER APPROACH for RM consumption
# Prevents rounding drift across multiple batches
for each RM row:
    cumulative_target = jc_required * (total_completed / for_quantity)
    already_consumed = SUM(SE.qty) for prior submitted SEs
    row.qty = max(0, cumulative_target - already_consumed)

# 7b. BATCH TRACKING via Serial and Batch Bundles (SABB)
# For each consumed RM: Outward SABB with batch_no entries
# For output FG: Inward SABB with output_batch_no

# 7c. SUBMIT STOCK ENTRY
ste.stock_entry.submit()

# 7d. LINK SABBs to submitted SE
# Update SABB.voucher_no = SE.name

# 7e. SCIO SRE MANAGEMENT (for SCIO WOs)
sync_scio_sre_before_manufacture(wo)   # Sync new RM SREs
ensure_scio_fg_sre(wo, se)             # Create FG SRE
recalculate_bin_reserved_for_direct_consumption(wo, se)  # Adjust Bin

# 8. SAVE LOT REFERENCES on Job Card
save_lot_references("Job Card", jc.name, consumed_lots, output_batch_no)

# 9. DEFENSIVE RE-SYNC
# Recalculate total_completed_qty from actual time log sum
# (guards against stale in-memory state from SE submission hooks)
```

### WIP → FG Warehouse Handling

- **WIP warehouse**: `jc.wip_warehouse` (set during `start_work_order`)
- **FG warehouse**: `jc.target_warehouse` or fallback to `wo.fg_warehouse`
- **Skip material transfer**: If `jc.skip_material_transfer=1`, RM consumed directly from source warehouse (no WIP transfer needed)
- Stock Entry has `s_warehouse` (source) on RM rows and `t_warehouse` (target) on FG row

### Lot Tracking on Job Card

After each `complete_operation` call:
- `custom_consumed_lot_no` — comma-separated list of all consumed batch names
- `custom_output_batch_no` — comma-separated list of all output batch names

These are updated via `save_lot_references()` which appends to existing values.

---

## 7. Step 5: Complete Job Card

### In-House Path

**API**: `complete_job_card(job_card, ...)` → `_complete_job_card_inhouse()` — [production_wizard.py:2006](../kniterp/api/production_wizard.py#L2006)

**JS trigger**: `.btn-finish-jc` → "Complete Job Card" dialog — [production_wizard.js:2861](../kniterp/kniterp/page/production_wizard/production_wizard.js#L2861)

**Dialog**: Summary-only (planned qty, produced qty, balance). No lot/batch entry — batches are tracked incrementally via `complete_operation`.

```python
# 1. Apply user-provided settings
jc.skip_material_transfer = ...
jc.wip_warehouse = ...
# Update source_warehouses on JC items

# 2. Optional: Add final additional qty time log
if additional_qty > 0:
    jc.append("time_logs", {completed_qty: additional_qty})

# 3. Set process loss
jc.process_loss_qty = process_loss_qty

# 4. Validate source warehouses on all JC items
# (throws if any item missing source_warehouse)

# 5. SUBMIT Job Card
jc.submit()
  └── CustomJobCard.on_submit():
        └── If overproduction: update_subsequent_operations()
              (cascades ratio to downstream draft JCs)

# 6. Update Work Order status
wo.update_status()
```

### Subcontracted Path

**API**: `complete_subcontracted_job_card(job_card)` → `_complete_job_card_subcontracted()` — [production_wizard.py:3840](../kniterp/api/production_wizard.py#L3840)

Two cases:
1. **Already submitted JC** (docstatus=1): Force status via `jc.db_set("status", "Completed")` — high-risk path, audited
2. **Draft JC** (docstatus=0):
   - Queries total received qty from Subcontracting Receipts
   - Adds time log with received_qty
   - Submits JC
   - Updates WO qty and status

---

## 8. Step 6: Revert Production Entry

**API**: `revert_production_entry(stock_entry)` — [production_wizard.py:2171](../kniterp/api/production_wizard.py#L2171)

**JS trigger**: "Revert" button on production logs table row → confirmation dialog — [production_wizard.js:2753](../kniterp/kniterp/page/production_wizard/production_wizard.js#L2753)

**Confirmation**: "Are you sure you want to revert Stock Entry {name}? This will: 1. Cancel the Stock Entry. 2. Remove the corresponding Time Log from the Job Card."

### Execution Flow

```python
# 1. Release SCIO FG SREs (for SCIO WOs)
release_scio_fg_sres_on_revert(wo_doc, se)

# 2. Cancel Stock Entry
se.cancel()
# → ERPNext reverses stock ledger entries, GL entries
# → CustomJobCard.set_manufactured_qty() recalculates from remaining SEs

# 3. Recalculate Bin reserved_qty_for_production
recalculate_bin_reserved_for_direct_consumption(wo_doc, se, mode="revert")

# 4. Find matching Time Log (by qty, searching from end)
# Delete via frappe.delete_doc("Job Card Time Log", ..., ignore_permissions=True)

# 5. Delete linked Machine Attendance (if exists)

# 6. Rebuild lot references from remaining active Stock Entries
# Queries all active SE SABBs to reconstruct consumed/output batch lists

# 7. Update JC fields via db_set:
#    total_completed_qty, total_time_in_mins
#    custom_consumed_lot_no, custom_output_batch_no

# 8. Recalculate manufactured_qty and status
jc.set_manufactured_qty()  # CustomJobCard override
jc.update_work_order()

# 9. Reset process_loss_qty to 0
```

**Note on Time Log deletion**: Uses `frappe.delete_doc(..., ignore_permissions=True)` because the JC is draft and standard save would trigger `validate_job_card` which throws when `total_completed_qty != for_quantity` after removing a log.

---

## 9. Incremental Production

The system supports **batch-by-batch production** — the user manufactures partial quantities across multiple sessions.

### Example: WO for 100 units

```
Day 1: complete_operation(qty=50)
  └── Time Log 1: completed_qty=50
  └── Stock Entry 1: fg_completed_qty=50
  └── JC: total_completed_qty=50, manufactured_qty=50

Day 2: complete_operation(qty=50)
  └── Time Log 2: completed_qty=50
  └── Stock Entry 2: fg_completed_qty=50
  └── JC: total_completed_qty=100, manufactured_qty=100

Day 3: complete_job_card()
  └── JC submitted → operation closed
```

### Cumulative Quantity Tracking

| Field | Source | Calculation |
|-------|--------|-------------|
| `total_completed_qty` | JC field | `SUM(time_logs.completed_qty)` — defensive re-sync after each operation |
| `manufactured_qty` | JC field | `SUM(SE.fg_completed_qty)` where SE.purpose='Manufacture' AND docstatus=1 — via `CustomJobCard.set_manufactured_qty()` |
| `completed_qty` | WO Operation field | Updated via `jc.update_work_order()` |
| `produced_qty` | WO field | Standard ERPNext aggregation from WO operations |

### Cumulative Remainder Approach for RM Consumption

To prevent rounding drift across batches, RM consumption uses a self-correcting formula:

```python
cumulative_ratio = (previously_completed + this_batch_qty) / for_quantity
cumulative_target = jc_required_qty * cumulative_ratio
already_consumed = SUM(prior SE consumed qty for this item)
this_batch_consumption = max(0, cumulative_target - already_consumed)
```

This ensures the final batch consumes exactly the remainder, even if intermediate batches had rounding.

---

## 10. Overproduction Handling

### Is Manufacturing Settings Tolerance Respected?

**No.** KnitERP does not explicitly check `Manufacturing Settings.overproduction_percentage_for_work_order`. The `complete_operation` API accepts any qty. The overproduction is handled downstream:

### Overproduction Cascade

When a Job Card is submitted with `total_completed_qty > for_quantity`:

```python
# CustomJobCard.on_submit() [job_card.py:433]
if self.total_completed_qty > self.for_quantity:
    self.update_subsequent_operations()

# update_subsequent_operations() [job_card.py:440]
ratio = total_completed_qty / for_quantity  # e.g., 320/316.2 = 1.012
# Find all subsequent draft Job Cards in the same Work Order
# Update their for_quantity *= ratio
# Add comment: "Planned quantity updated from X to Y based on over-production"
```

### Stock Entry for Overproduction

`CustomJobCard.make_stock_entry_for_semi_fg_item()` [job_card.py:327] uses:
```python
actual_qty_to_manufacture = max(total_completed_qty, for_quantity) - manufactured_qty
```
This ensures the Stock Entry covers the full overproduced quantity. RM consumption is scaled proportionally using BOM ratios.

---

## 11. Lot Tracking Helpers

### save_lot_references()

**API**: `save_lot_references(doctype, docname, consumed_lot_no, output_batch_no)` — [production_wizard.py:4487](../kniterp/api/production_wizard.py#L4487)

Saves batch/lot traceability on:
- **Job Card**: `custom_consumed_lot_no`, `custom_output_batch_no`
- **Subcontracting Receipt Item**: `custom_consumed_batch_no`, `custom_output_dyeing_lot`

Validates all batch IDs exist in Batch master. Saves with `ignore_permissions=True`.

### ensure_batch_exists()

**API**: `ensure_batch_exists(batch_no, item_code, source_type, parent_batch)` — [production_wizard.py:4556](../kniterp/api/production_wizard.py#L4556)

Creates a Batch record if it doesn't exist. Used when:
- Operator types a new output batch name in the production dialog
- Consumed lots reference supplier batches not yet in the system

Fields set: `batch_id`, `item`, `source_type` ("Supplier"/"Customer"/"In-house"), `custom_parent_batch`.

---

## 12. Custom Fields Used

| DocType | Field | Type | Purpose |
|---------|-------|------|---------|
| Work Order Operation | `custom_planned_output_qty` | Float (read-only) | BOM-ratio-based planned output per operation |
| Job Card | `custom_consumed_lot_no` | Small Text | Comma-separated consumed batch names |
| Job Card | `custom_output_batch_no` | Small Text | Comma-separated output batch names |
| Job Card Time Log | `workstation` | Link (Workstation) | Workstation used in this specific time log |
| Batch | `source_type` | Select | "Supplier" / "Customer" / "In-house" |
| Batch | `custom_parent_batch` | Link (Batch) | Upstream parent batch for traceability |

---

## 13. Doc Event Hooks (Manufacturing)

| DocType | Event | Handler | Purpose |
|---------|-------|---------|---------|
| Work Order | `before_submit` | `set_planned_qty_on_work_order` [work_order.py:152] | Compute planned_qty per operation from BOM ratios |
| Job Card | `before_insert` | `set_job_card_qty_from_planned_qty` [job_card.py:110] | Set JC for_quantity from WO Operation planned_qty |

### set_planned_qty_on_work_order (Detail)

For each WO Operation:
1. If `bom_op.is_final_finished_good` → `planned_qty = wo.qty`
2. Else → `planned_qty = wo.qty * bom_op.finished_good_qty / bom.quantity`
3. Fallback (op not in BOM) → `planned_qty = wo.qty`

Errors are caught and logged — will not block WO submission.

### set_job_card_qty_from_planned_qty (Detail)

Looks up WO Operation by `(parent=jc.work_order, operation=jc.operation)`.
If `planned_qty` is set and > 0, overwrites `jc.for_quantity`.
Errors caught and logged.

---

## 14. Override Layer (Manufacturing)

### CustomWorkOrder [work_order.py:41]

| Method | Type | Purpose |
|--------|------|---------|
| `validate_subcontracting_inward_order()` | Complete replacement | Fixes floating-point precision (flt(..., 3)), changes insufficient CP material from throw to msgprint |

### CustomJobCard [job_card.py:162]

| Method | Type | Purpose |
|--------|------|---------|
| `set_status()` | Complete replacement | **Removes auto-completion**. JCs never auto-complete — users must complete manually via Production Wizard. |
| `set_manufactured_qty()` | Complete replacement | Queries SE or SCR Item for qty. Calls custom `set_status(update_status=True)`. |
| `set_items_from_work_order()` | Complete replacement | Clears and repopulates JC items from WO required_items filtered by operation. |
| `make_stock_entry_for_semi_fg_item()` | Complete replacement | Uses `max(total_completed_qty, for_quantity)` for overproduction. Scales RM using BOM ratios. |
| `validate()` | Extends super | Adds items from WO for subcontracted final FG operations. |
| `validate_time_logs()` | Conditional bypass | Skips validation for subcontracted operations. |
| `validate_transfer_qty()` | Conditional bypass | Skips for subcontracted operations. |
| `validate_job_card()` | Conditional bypass | Skips for subcontracted operations. |
| `on_submit()` | Extends super | Cascades overproduction to subsequent operations. |

**Core design rule**: No auto-completion of Job Cards — enforced in `set_status()` and `set_manufactured_qty()`.

---

## 15. Known Issues & Technical Debt

### 15.1 complete_job_card Duplicate — RESOLVED

The discovery audit (older version) flagged duplicate `complete_job_card` definitions. Current code has two **separate** functions:
- Line 2006: `complete_job_card()` — for in-house operations
- Line 3840: `complete_subcontracted_job_card()` — for subcontracted operations (different name)

No collision. The earlier audit finding is outdated.

### 15.2 frappe.db.commit() — NOT in Manufacturing Flow

`frappe.db.commit()` found at lines 3500 and 3546 — these are in `save_transaction_parameters()` and `save_po_transaction_parameters()`, which are transaction parameter sync functions, NOT manufacturing methods. All manufacturing methods rely on implicit request transaction boundaries.

### 15.3 Bin db_set — Still Present (Service Layer)

`stock_reservation_service.py:279`:
```python
stock_bin.db_set("reserved_qty_for_production", adjusted, update_modified=False)
```

This bypasses Bin's standard update mechanism. The service first calls `stock_bin.update_reserved_qty_for_production()` (standard ERPNext), then adjusts downward for consumed_qty. The mutation is logged but remains a direct write.

**Risk**: If ERPNext adds Bin validation or triggers on `reserved_qty_for_production` changes, this bypass won't fire them.

### 15.4 N+1 Pattern in get_consolidated_shortages — CONFIRMED

```python
# production_wizard.py:2985-2993
pending_items = get_pending_production_items(filters)     # 1 batch query
for item in pending_items:
    details = get_production_details(item.sales_order_item)  # ~10+ queries each
```

`get_production_details()` makes per-item queries for: BOM doc load, Bin lookups per RM item, Stock Entry consumed qty per RM, PO data per RM, SCO/SCR data per subcontracted op. For 50 pending items, this generates **500+ database queries**.

**Mitigation**: Currently acceptable for the user base (2-3 users, small order volume). Would need query consolidation for scale.

### 15.5 ignore_permissions and ignore_validate Flags

| Location | Flag | Justification |
|----------|------|---------------|
| WO insert (line 1208) | `ignore_mandatory`, `ignore_validate` | WO may have incomplete fields at draft stage |
| JC save in start_work_order (line 1301) | `ignore_validate` | Applying initial settings, not completing operations |
| Time Log delete in revert (line 2230) | `ignore_permissions` | Cannot save submitted JC after removing time log |
| Machine Attendance insert (line 1736) | `ignore_permissions` | Created as side-effect of production action |
| Batch insert (line 4587) | `ignore_permissions` | Batch created during production flow |
| SABB insert (lines 1854, 1886) | `ignore_permissions` | SABB created during SE creation |

### 15.6 Direct db_set Mutations in Revert

`revert_production_entry` uses `jc.db_set()` for `total_completed_qty`, `total_time_in_mins`, `custom_consumed_lot_no`, `custom_output_batch_no`, `process_loss_qty` — bypassing JC validation. This is intentional: the JC is draft and standard save would trigger `validate_job_card()` which throws when quantities don't match after removing a time log.

### 15.7 Stock Entry Rollback on Failure

If SE submission fails in `complete_operation` (e.g., negative stock), the Time Log has already been saved. The function does NOT remove the Time Log — instead it re-raises the error, relying on the Frappe request transaction to rollback the entire request (including the Time Log save). This is correct behavior since Frappe uses a single DB transaction per request.

However, the output Batch record is explicitly deleted on SE failure (line 1940) because `ensure_batch_exists` may have committed via a separate insert.

---

## 16. API Method Reference

| Method | Line | Type | Arguments |
|--------|------|------|-----------|
| `get_pending_production_items` | 184 | Read | filters (JSON) |
| `get_production_details` | 406 | Read | sales_order_item |
| `get_consolidated_shortages` | 2972 | Read | filters (JSON) |
| `create_work_order` | 1019 | Write | sales_order, sales_order_item |
| `start_work_order` | 1218 | Write | work_order, operation_settings (JSON) |
| `complete_operation` | 1631 | Write | work_order, operation, qty, workstation, employee, attendance_date, shift, consumed_lots (JSON), output_batch_no |
| `complete_job_card` | 2006 | Write | job_card, additional_qty, process_loss_qty, wip_warehouse, skip_material_transfer, source_warehouses |
| `complete_subcontracted_job_card` | 3840 | Write | job_card |
| `revert_production_entry` | 2171 | Write | stock_entry |
| `update_production_entry` | 2313 | Write | stock_entry, qty, employee, workstation |
| `get_production_logs` | 2124 | Read | job_card |
| `save_lot_references` | 4487 | Write | doctype, docname, consumed_lot_no, output_batch_no |
| `ensure_batch_exists` | 4556 | Write | batch_no, item_code, source_type, parent_batch |
| `get_available_batches` | 4266 | Read | item_code, warehouse |
| `get_available_batches_with_context` | 4359 | Read | item_code, warehouse |
| `get_lot_traceability` | 4594 | Read | batch_no, direction |
| `get_batch_production_summary` | 3679 | Read | sales_order_item |
| `get_order_activity_log` | 3941 | Read | sales_order_item |

---

## 17. JS UI Dialog Reference

| Dialog | Function | Lines | API Called | Key Fields |
|--------|----------|-------|-----------|------------|
| (none — direct call) | `create_work_order()` | 1622-1643 | `create_work_order` | SO, SOI |
| Start Production | `start_work_order()` | 1645-1745 | `start_work_order` | Per-op table: workstation, skip_material_transfer, wip_warehouse |
| Update Manufactured Qty | `complete_operation()` | 2101-2681 | `complete_operation` | qty, workstation, employee, consumed_lots (FIFO tables), output_batch_no |
| Complete Job Card | `complete_job_card()` | 2861-2976 | `complete_job_card` | Summary only (planned/produced/balance) |
| Production Logs | `show_production_logs()` | 2683-2860 | `get_production_logs` | Table with Edit/Revert buttons per row |
| Edit Production Entry | (nested in logs) | 2783-2830 | `update_production_entry` | employee, workstation, qty |
| Revert Confirmation | (nested in logs) | 2753-2773 | `revert_production_entry` | frappe.confirm only |

### FIFO Batch Allocation (Complete Operation Dialog)

The dialog pre-fetches available batches via `get_available_batches_with_context` and renders a FIFO allocation table per RM item. When the user changes qty:
1. Calculates RM need from BOM ratio
2. Runs `_fifo_allocate()` to assign batch quantities in FIFO order
3. Auto-derives output batch name from consumed lots
4. Validates sufficient batch stock before allowing submission
