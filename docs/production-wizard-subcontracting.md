# Production Wizard: Subcontracting Path

Deep-dive reference for the subcontracting lifecycle as orchestrated by the Production Wizard.

---

## 1) Two Subcontracting Paths

KnitERP supports two distinct subcontracting models:

| Path | Direction | Trigger | Key Doctypes |
|------|-----------|---------|--------------|
| **Operation-level** (outward) | We send RM to supplier, they produce FG | Job Card marked `is_subcontracted=1` | PO + SCO + SE(Send) + SCR |
| **SCIO** (inward) | Customer sends RM to us, we produce for them | Sales Order marked `is_subcontracted=1` | SIO + WO + JC + SE(Delivery) |

This document covers both, with the operation-level outward path as the primary focus.

---

## 2) Subcontracting Lifecycle (Operation-Level)

### 2.1 Marking an Operation as Subcontracted

When a Work Order is started (`start_work_order`), Job Cards are created per BOM operation. If a BOM operation has `is_subcontracted = 1`, the resulting Job Card inherits this flag.

In the Production Wizard UI, subcontracted operations display:
- A `Subcontracted` badge on the operation card
- "Create Subcontracting Order" button (instead of "Update Manufactured Qty")
- Per-SCO action buttons: "Send Raw Material", "Receive Goods", "Complete Job Card"

### 2.2 Create Subcontracting Order

**API**: `kniterp.api.production_wizard.create_subcontracting_order`
**Args**: `work_order, operation, supplier, qty=None, rate=None`
**JS Dialog**: `create_subcontracting_order()` at `production_wizard.js:1747`

#### Sequence of operations:

1. **Validate prerequisites**:
   - Work Order must be submitted (`docstatus=1`)
   - Job Card must exist for this operation and be marked `is_subcontracted`
   - All previous operations must have at least some output (sequence check via `sequence_id`)

2. **Calculate available quantity**:
   - Finds immediate upstream operation's actual output (received_qty for subcontracted, total_completed_qty for in-house)
   - `effective_max_qty = max(planned for_quantity, upstream output)` — allows over-production flow
   - Subtracts `already_ordered_qty` (from existing POs linked to this Job Card)
   - Result: `remaining_to_subcontract`

3. **Resolve Subcontracting BOM**:
   - Uses `get_subcontracting_boms_for_finished_goods(fg_item)` from ERPNext
   - `fg_item` comes from `job_card.finished_good` or `wo.production_item`

4. **Create Purchase Order**:
   ```python
   po = frappe.new_doc("Purchase Order")
   po.supplier = supplier
   po.is_subcontracted = 1
   po.supplier_warehouse = "Job Work Outward - {company_abbr}"

   po.append("items", {
       "item_code": sc_bom.service_item,      # Service item from SC BOM
       "fg_item": fg_item,                      # Finished good
       "qty": order_qty * service_item_qty / fg_item_qty,  # Service qty ratio
       "fg_item_qty": order_qty,               # FG qty
       "job_card": job_card.name,              # CRITICAL LINK
       "bom": job_card.semi_fg_bom or sc_bom.finished_good_bom,
       "rate": rate,
       "warehouse": wo.fg_warehouse
   })
   ```

5. **Copy Transaction Parameters** from linked Sales Order Item to PO Item (JSON field `custom_transaction_params_json`)

6. **Submit PO** and check for auto-created SCO:
   - If ERPNext auto-creates SCO on PO submit (via Buying Settings): submit it if draft
   - If not auto-created: manually call `make_subcontracting_order(po.name)`, insert, submit

7. **Returns**: `{purchase_order, subcontracting_order, supplier_warehouse}`

#### Key link: `PO Item.job_card`
This field is the **bridge** between ERPNext subcontracting and KnitERP's Job Card tracking. It links:
- PO Item → Job Card
- SCO Item → PO Item → Job Card (via `scoi.purchase_order_item`)

### 2.3 Transfer Materials to Subcontractor

**Two methods** exist for this step:

#### Method A: Simple Transfer
**API**: `kniterp.api.production_wizard.transfer_materials_to_subcontractor`

Creates a basic "Send to Subcontractor" Stock Entry from SCO supplied items:
```python
se = frappe.new_doc("Stock Entry")
se.stock_entry_type = "Send to Subcontractor"
se.subcontracting_order = sco.name

for item in sco.supplied_items:
    pending = item.required_qty - item.supplied_qty
    se.append("items", {
        "item_code": item.rm_item_code,
        "qty": pending,
        "s_warehouse": item.reserve_warehouse,
        "t_warehouse": sco.supplier_warehouse,  # Job Work Outward
    })
```
Creates as **draft** — user must review and submit manually.

#### Method B: Auto-Split by Batch (Preferred)
**API**: `kniterp.api.production_wizard.auto_split_subcontract_stock_entry`
**JS**: `send_raw_material_to_supplier()` at `production_wizard.js:1901`

More sophisticated — splits SE rows by available batches using FIFO:
1. Gets standard draft SE from `make_rm_stock_entry(sco_name)`
2. For each batch-tracked item, queries `get_available_batches(item_code, warehouse)`
3. Splits rows: one SE row per batch, each with its own **Serial and Batch Bundle** (Outward)
4. If total stock < required, appends a "dead row" for the remainder (forces user to add stock)
5. Saves as draft — user reviews batch allocations and submits

Returns existing draft SE if one already exists for this SCO (idempotent).

#### Stock Entry doc_event: `on_se_submit_update_job_card_transferred`

When the SE is submitted, the doc_event in `subcontracting.py:100` fires:

```
SE submit → _update_job_card_transferred_hook(se)
  → Find Job Cards: SCO Item → PO Item → Job Card (via SQL join)
  → For each JC: update_job_card_transferred_qty(jc_name)
    → Sum all SE Detail qty for this JC's SCOs
    → db.set_value each JC Item's transferred_qty
    → db_set JC header transferred_qty
    → Update JC status:
        - total_sent >= for_quantity → "Material Transferred"
        - total_sent > 0 → "Work In Progress"
        - total_sent == 0 → "Open"
```

**On cancel** (`on_se_cancel_update_job_card_transferred`): Same logic — recalculates from all remaining submitted SEs.

### 2.4 Receive Subcontracted Goods

**API**: `kniterp.api.production_wizard.receive_subcontracted_goods`
**Args**: `purchase_order, rate=None, supplier_delivery_note=None, subcontracting_order=None, received_batches=None`
**JS Dialog**: `receive_subcontracted_goods()` at `production_wizard.js:1938`

#### UI Dialog

The dialog captures:
- **Supplier Delivery Note** (required)
- **Quantity to Receive** (auto-calculated from batch rows)
- **Rate** (optional final rate)
- **Number of Output Batches**: Dynamic HTML table for multi-batch receipt
  - Each row: Qty + Output Dyeing Lot No
  - Total batch qty must equal overall qty

#### Backend Sequence:

1. **Ensure SCO exists**: If no SCO found for PO, creates one via `make_subcontracting_order`

2. **Create SCR from SCO**: Uses ERPNext's `make_subcontracting_receipt(sco)`

3. **Build Serial and Batch Bundles** for each non-scrap item row:
   ```python
   sabb = frappe.new_doc("Serial and Batch Bundle")
   sabb.type_of_transaction = "Inward"
   sabb.voucher_type = "Subcontracting Receipt"

   for batch in received_batches:
       ensure_batch_exists(batch_no, item_code, source_type="Supplier")
       sabb.append("entries", {"batch_no": batch_no, "qty": qty})
   ```
   - `ensure_batch_exists` auto-creates Batch records if new (source_type="Supplier")
   - Row qty is set to total batch qty (overrides SCR default)

4. **Insert and Submit SCR**:
   - Calls `scr.set_missing_values()` to recalculate RM consumption
   - Updates SABB with voucher_no and voucher_detail_no after insert
   - Submits SCR

5. **Check for linked Purchase Receipt** (draft) and submit it

6. **Rollback on failure**: Deletes any batches created during this operation

#### SCR doc_events (on_submit)

Two separate handlers fire when SCR is submitted:

**Handler 1**: `subcontracting_receipt.on_submit_complete_job_cards` (from `overrides/subcontracting_receipt.py:24`)

```
SCR submit → for each SCR item with subcontracting_order:
  → Get SCO → Get PO → Get PO Items with job_card set
  → For each linked Job Card:
    1. Calculate total_received across ALL SCRs for this JC
    2. db_set("manufactured_qty", received_qty)
    3. _update_job_card_consumed_qty(jc, sco, received_qty)
       → Query SCR Supplied Items to get consumed RM per item_code
       → db.set_value each JC Item's consumed_qty
    4. If status not Completed/Submitted → db_set("status", "Work In Progress")
```

**Handler 2**: `subcontracting.on_pr_submit_complete_job_cards` (from `subcontracting.py:86`)

This fires on **Purchase Receipt** submit (not SCR), but serves the same role for PR-based subcontracting:
```
PR submit (is_subcontracted) → for each PR item with purchase_order:
  → Get PO Items with job_card
  → For each JC:
    1. Sum received qty from all submitted SCRs for this JC
    2. db_set("manufactured_qty", received_qty)
    3. If status not Completed/Submitted → db_set("status", "Work In Progress")
    4. update_work_order_from_job_card(jc, received_qty)
```

**Key difference**: The SCR handler also updates `consumed_qty` on JC Items; the PR handler does not.

### 2.5 Complete Subcontracted Job Card

**API**: `kniterp.api.production_wizard.complete_subcontracted_job_card`
**JS**: `.btn-complete-jc` handler at `production_wizard.js:1440`

This is a **manual** action — the system never auto-completes Job Cards (core design rule).

#### Two paths based on JC docstatus:

**Path A: Already submitted (docstatus=1)**
- Force status via `jc.db_set("status", "Completed")`
- Audit trail logged with `complete_subcontracted_job_card_force_status`

**Path B: Draft (docstatus=0)**
1. Query total received qty from all SCRs for this JC
2. Throw if received_qty <= 0
3. Add a time log with `completed_qty = received_qty`
4. Save and submit JC
5. Update Work Order: `wo.update_work_order_qty()` + `wo.update_status()`
6. Audit trail logged

### 2.6 SCR `before_validate` — Customer Warehouse Injection

**Handler**: `subcontracting_receipt.before_validate_set_customer_warehouse`
**Registered**: hooks.py doc_events (NOT a monkey patch)

```python
def before_validate_set_customer_warehouse(doc, method=None):
    if not getattr(doc, "customer_warehouse", None):
        doc.customer_warehouse = doc.supplier_warehouse
```

**Why**: ERPNext's `subcontracting_controller.py` (~line 624) reads `customer_warehouse` for RM routing, but SCR doesn't always carry it. This injects `supplier_warehouse` as fallback.

**Confirmed**: The old monkey patch (`SubcontractingReceipt.validate = patched_validate`) has been fully removed:
- No `patched_validate` references in code
- No import of `subcontracting_receipt` in `hooks.py` or `__init__.py`
- Only references exist in documentation (discovery-audit.md, architecture.md) noting the historical change

---

## 3) SCIO Path (Subcontracting Inward — Customer Provides RM)

This is the reverse flow: a customer sends us raw materials, we produce finished goods for them.

### 3.1 Create Subcontracting Inward Order

**API**: `kniterp.api.production_wizard.create_subcontracting_inward_order`
**Args**: `sales_order, sales_order_item`

1. Validates SO is marked `is_subcontracted`
2. **Customer Warehouse resolution** (3 strategies):
   - Strategy 1: Find existing warehouse with `customer = so.customer`
   - Strategy 2: Create `JW-IN - {customer_name} - {abbr}` under `Customer Owned - Job Work - {abbr}`
   - Sets `customer` field on warehouse (critical for stock routing)
3. **Delivery Warehouse**: `Customer Job Work Completed - {abbr}`
4. Creates SIO with service items from SO Item + populates items via `sio.populate_items_table()`
5. Inserts with `ignore_permissions=True`

### 3.2 CustomSCIO Overrides

**File**: `overrides/subcontracting_inward_order.py`
**Class**: `CustomSubcontractingInwardOrder` extends `SubcontractingInwardOrder`

#### `get_production_items` (precision fix)

The core issue: ERPNext rounds the RM-to-FG ratio too aggressively, which can cause over-production (e.g., 247.036 vs 246.999).

**Fix**: Removed precision rounding on the intermediate ratio calculation:
```python
# Original ERPNext: ratio = flt(item.required_qty / d.qty, 3)  ← too aggressive
# KnitERP fix:
ratio = flt(flt(item.required_qty, 3) / flt(d.qty, 3))  # Full precision intermediate
qty = flt((...) / ratio, 3)  # Only round the final result
```

#### `make_subcontracting_delivery` (qty derivation fix)

Custom delivery qty logic:
```python
produced_limit = flt(fg_item.produced_qty, 3)
if not allow_over:
    produced_limit = min(fg_item.qty, fg_item.produced_qty)

qty = produced_limit - fg_item.delivered_qty  # Always subtract delivered
```

**Fix**: ERPNext's standard doesn't always subtract `delivered_qty`, risking double-delivery.

### 3.3 SCIO Sales Invoice

**API**: `kniterp.api.production_wizard.create_scio_sales_invoice`

Calculates invoiceable qty using service-to-FG ratio:
```
ratio = service_qty / fg_item_qty
service_qty_for_delivered = fg_delivered * ratio
invoiceable_qty = service_qty_for_delivered - already_billed_qty
```

---

## 4) Standalone Subcontracting API

**File**: `api/subcontracting.py` (74 lines, 2 endpoints)

These are simpler endpoints used from the **Sales Order form** (not Production Wizard):

### `get_subcontract_po_items(sales_order)`
Returns PO item data for each SO Item: service_item, fg_item, fg_qty, delivery_date.
Hardcoded `supplier_warehouse: "Job Work Outward - O"`.

### `make_subcontract_purchase_order(sales_order, supplier, items)`
Creates a PO from SO items with subcontracting fields. Copies transaction parameters from SO Items to PO Items.

**Note**: This is a legacy/standalone path. The Production Wizard's `create_subcontracting_order` is the primary path with richer logic (sequence checks, overproduction handling, SCO auto-creation).

---

## 5) Lot Number Traceability Chain

### 5.1 Custom Fields for Traceability

| DocType | Field | Type | Purpose |
|---------|-------|------|---------|
| Job Card | `custom_consumed_lot_no` | Small Text | Yarn/fabric batch consumed in this operation |
| Job Card | `custom_output_batch_no` | Small Text | New batch/lot produced by this operation |
| SCR Item | `custom_consumed_batch_no` | Small Text | Knitting batch sent for dyeing |
| SCR Item | `custom_output_dyeing_lot` | Small Text | Dyeing lot produced by subcontractor |
| Batch | `custom_parent_batch` | Link (Batch) | Upstream parent batch linkage |
| Batch | `source_type` | Select | Material origin: Supplier / Customer / In-house |

### 5.2 How Lots Flow Through the Subcontracting Chain

```
PROCUREMENT
  Yarn purchased → Batch created (source_type="Supplier")
    e.g. "YARN-LOT-001"

KNITTING (In-house Job Card)
  JC.custom_consumed_lot_no = "YARN-LOT-001"     ← input yarn batch
  JC.custom_output_batch_no = "KB-001"            ← knitting output batch
    → Saved via save_lot_references("Job Card", jc_name, ...)

SEND TO SUBCONTRACTOR
  Stock Entry: Send to Subcontractor
    Items carry batch via Serial and Batch Bundle
    s_warehouse: Stores/WIP → t_warehouse: Job Work Outward

DYEING (Subcontracted via SCR)
  SCR Item.custom_consumed_batch_no = "KB-001"    ← knitting batch sent for dyeing
  SCR Item.custom_output_dyeing_lot = "DL-001"    ← dyeing lot from subcontractor
    → Received batches auto-created with source_type="Supplier"
    → Saved via save_lot_references("Subcontracting Receipt Item", ...)

BATCH LINKAGE
  Batch "DL-001".custom_parent_batch = "KB-001"   ← links dyeing → knitting
  Batch "KB-001".custom_parent_batch = "YARN-LOT-001" ← links knitting → yarn
```

### 5.3 `save_lot_references` API

**API**: `kniterp.api.production_wizard.save_lot_references`
**Args**: `doctype, docname, consumed_lot_no=None, output_batch_no=None`

Supports two target doctypes:
- **Job Card**: Sets `custom_consumed_lot_no` and `custom_output_batch_no`
- **Subcontracting Receipt Item**: Sets `custom_consumed_batch_no` and `custom_output_dyeing_lot`

Input parsing: `consumed_lot_no` can be:
- A direct string: `"YARN-LOT-001"`
- A comma-separated string: `"YARN-LOT-001, YARN-LOT-002"`
- A JSON dict (from complete_operation): `{"item_code": [{batch_no, qty}, ...]}`

Validates all batch IDs exist in Batch master before saving.

### 5.4 `ensure_batch_exists` API

**API**: `kniterp.api.production_wizard.ensure_batch_exists`
**Args**: `batch_no, item_code, source_type=None, parent_batch=None`

Creates a Batch record if it doesn't exist:
```python
batch = frappe.get_doc({
    "doctype": "Batch",
    "batch_id": batch_no,
    "item": item_code,
    "source_type": source_type or "In-house",
    "custom_parent_batch": parent_batch
})
```

Called from:
- `receive_subcontracted_goods` — creates batches with `source_type="Supplier"`
- `complete_operation` — creates batches with `source_type="In-house"`
- Production Wizard UI when user types a new batch name

### 5.5 `get_lot_traceability` API

**API**: `kniterp.api.production_wizard.get_lot_traceability`
**Args**: `batch_no, direction="backward"|"forward"`

BFS traversal through the lot chain. Uses `FIND_IN_SET` for comma-separated field matching.

**Backward** (given output lot, trace to source):
```
DL-001 (output)
  → SCR Item where custom_output_dyeing_lot contains "DL-001"
    → Extract custom_consumed_batch_no → "KB-001"
      → Job Card where custom_output_batch_no contains "KB-001"
        → Extract custom_consumed_lot_no → "YARN-LOT-001"
          → Batch "YARN-LOT-001" (terminal: source_type="Supplier")
            → If custom_parent_batch set, continue tracing
```

**Forward** (given source lot, trace to output):
```
YARN-LOT-001 (source)
  → Job Card where custom_consumed_lot_no contains "YARN-LOT-001"
    → Extract custom_output_batch_no → "KB-001"
      → SCR Item where custom_consumed_batch_no contains "KB-001"
        → Extract custom_output_dyeing_lot → "DL-001" (terminal)
```

Returns a list of `{node_type, doctype, docname, batch_no, extra}` nodes.

---

## 6) Document Link Chain

```
Sales Order Item
  ↓ (sales_order_item)
Work Order
  ↓ (work_order)
Job Card (is_subcontracted=1)
  ↓ (job_card on PO Item)
Purchase Order (is_subcontracted=1)
  ↓ (purchase_order on SCO)
Subcontracting Order
  ↓ (subcontracting_order on SE / SCR Item)
Stock Entry (Send to Subcontractor)
  ↓ (material transfer)
Subcontracting Receipt
  ↓ (updates JC manufactured_qty, consumed_qty)
Job Card → Completed (manual)
```

**Key link fields**:
- `Purchase Order Item.job_card` — bridges PO ↔ JC
- `Subcontracting Order Item.purchase_order_item` — bridges SCO ↔ PO
- `Stock Entry.subcontracting_order` — bridges SE ↔ SCO
- `Subcontracting Receipt Item.subcontracting_order` — bridges SCR ↔ SCO
- `Subcontracting Receipt Item.job_card` — direct SCR ↔ JC link (used in qty queries)

---

## 7) Warehouse Topology

| Warehouse | Purpose | Used By |
|-----------|---------|---------|
| `Job Work Outward - {abbr}` | Transit warehouse for RM sent to subcontractor | PO.supplier_warehouse, SE.t_warehouse |
| `JW-IN - {customer_name} - {abbr}` | Customer-provided RM storage (SCIO path) | SIO.customer_warehouse |
| `Customer Job Work Completed - {abbr}` | FG storage before delivery back to customer | SIO item.delivery_warehouse |
| WO's `fg_warehouse` | FG warehouse for received goods | PO Item.warehouse, SCR receiving |
| Item's `reserve_warehouse` on SCO | Source for RM transfer | SE.s_warehouse |

---

## 8) Risk Areas

### 8.1 No `frappe.db.commit()` in Subcontracting Path

**Confirmed**: Neither `subcontracting_receipt.py` nor `subcontracting.py` contain manual `db.commit()` calls. All mutations rely on the request transaction boundary.

**Note**: The discovery audit references a historical `db.commit()` in `subcontracting_receipt.py:129` — this was in a now-removed `_check_and_complete_work_order` function. Current code does not have this.

### 8.2 SE Cancel After JC Close

**Scenario**: Stock Entry (Send to Subcontractor) is cancelled after the linked Job Card has been completed.

**What happens**:
1. `on_se_cancel_update_job_card_transferred` fires
2. `update_job_card_transferred_qty` recalculates from all remaining submitted SEs
3. Status update logic checks: `if current_status not in ["Completed", "Submitted"]`
4. **Result**: If JC is already Completed, the status is NOT downgraded. But `transferred_qty` IS recalculated to a lower value.

**Risk**: `transferred_qty` becomes inconsistent with the JC's Completed status. The JC shows "Completed" with `transferred_qty < for_quantity`. This is cosmetic but could confuse reporting.

### 8.3 Dual SCR/PR Update Paths

Both `subcontracting_receipt.on_submit_complete_job_cards` (SCR) and `subcontracting.on_pr_submit_complete_job_cards` (PR) update Job Card `manufactured_qty` and status. If both fire for the same subcontracting flow:

- SCR handler queries `tabSubcontracting Receipt Item` for received qty
- PR handler also queries `tabSubcontracting Receipt Item` for received qty
- Both set the same `manufactured_qty` — should converge but are redundant

**Risk**: Low if only one fires per flow, but theoretically both could fire if ERPNext creates both SCR and PR for the same subcontracting receipt.

### 8.4 `db_set` Bypass Pattern

All subcontracting doc_event handlers use `db_set` with `update_modified=False` to update JC fields:
- `manufactured_qty`
- `status`
- `transferred_qty`
- `consumed_qty` (via `db.set_value` on JC Item)

This bypasses document validation. Since these are JC updates triggered by downstream docs (SCR, SE, PR), this is intentional to avoid circular validation. But it means:
- No `validate` or `before_save` hooks fire on the JC
- CustomJobCard's `set_status` logic is bypassed (status set directly)

### 8.5 Multiple SCOs Per Job Card

The system supports multiple POs/SCOs per Job Card (partial subcontracting). The `already_ordered_qty` calculation aggregates across all POs for a JC:
```sql
SELECT COALESCE(SUM(poi.fg_item_qty), 0)
FROM `tabPurchase Order Item` poi
JOIN `tabPurchase Order` po ON po.name = poi.parent
WHERE poi.job_card = %s AND po.docstatus != 2
```

Similarly, received qty is summed across all SCRs. This is correct but requires all SCR Items to have `job_card` set for accurate tracking.

### 8.6 Hardcoded Warehouse in `api/subcontracting.py`

`get_subcontract_po_items` hardcodes `supplier_warehouse: "Job Work Outward - O"`. This only works for companies with abbreviation "O". The Production Wizard's `create_subcontracting_order` correctly derives it from company abbreviation.

### 8.7 `receive_subcontracted_goods` Batch Rollback

If the SCR creation/submit fails after batches have been auto-created, the exception handler attempts to delete them:
```python
except Exception as e:
    for b in created_batches:
        frappe.delete_doc("Batch", b, ignore_permissions=True, force=1)
    raise e
```

**Risk**: If the batch has already been referenced in a committed SABB entry, deletion could fail. The `force=1` flag helps but is not guaranteed in all edge cases.

### 8.8 `auto_split_subcontract_stock_entry` Creates SABBs Before SE Save

SABBs are created (inserted) before the SE is saved. If SE insert fails, orphaned SABB records remain. No cleanup logic exists for this path.

### 8.9 CustomJobCard Validation Bypass for Subcontracted Cards

`CustomJobCard` in `overrides/job_card.py` early-returns from:
- `validate_time_logs` — skips time log validation
- `validate_transfer_qty` — skips transfer qty validation
- `validate_job_card` — skips general JC validation

This is necessary because subcontracted JCs don't follow the standard in-house flow, but it means any validation ERPNext adds to these methods in future versions will be silently skipped.

---

## 9) Summary: Methods by File

### `api/production_wizard.py` (subcontracting methods)

| Method | Line | Purpose |
|--------|------|---------|
| `create_subcontracting_order` | 1314 | PO + SCO creation from JC |
| `transfer_materials_to_subcontractor` | 2633 | Simple SE creation for RM transfer |
| `auto_split_subcontract_stock_entry` | 2691 | FIFO batch-split SE creation |
| `receive_subcontracted_goods` | 2406 | SCR creation with multi-batch support |
| `complete_subcontracted_job_card` | 3840 | Manual JC completion |
| `create_subcontracting_inward_order` | 3284 | SCIO creation from SO |
| `create_scio_sales_invoice` | 3173 | SI for SCIO items |
| `save_lot_references` | 4487 | Lot traceability on JC/SCR Item |
| `ensure_batch_exists` | 4556 | Auto-create Batch records |
| `get_lot_traceability` | 4594 | BFS lot chain traversal |

### `api/subcontracting.py` (2 endpoints)

| Method | Line | Purpose |
|--------|------|---------|
| `get_subcontract_po_items` | 5 | SO → PO item mapping |
| `make_subcontract_purchase_order` | 32 | PO creation from SO form |

### `subcontracting.py` (doc_event hooks, 199 lines)

| Function | Line | Trigger | Purpose |
|----------|------|---------|---------|
| `on_pr_submit_complete_job_cards` | 86 | PR.on_submit | Update JC manufactured_qty from PR |
| `on_se_submit_update_job_card_transferred` | 100 | SE.on_submit | Recalc JC transferred_qty |
| `on_se_cancel_update_job_card_transferred` | 106 | SE.on_cancel | Recalc JC transferred_qty |
| `update_job_card_transferred_qty` | 136 | (internal) | Core transferred_qty recalculation |
| `update_work_order_from_job_card` | 4 | (internal) | WO operation completed_qty update |
| `complete_job_card_from_po_item` | 39 | (internal) | JC update from PO/PR submit |

### `overrides/subcontracting_receipt.py` (123 lines)

| Function | Line | Trigger | Purpose |
|----------|------|---------|---------|
| `before_validate_set_customer_warehouse` | 5 | SCR.before_validate | Inject customer_warehouse fallback |
| `on_submit_complete_job_cards` | 24 | SCR.on_submit | Update JC manufactured/consumed/status |
| `_update_job_card_consumed_qty` | 85 | (internal) | Sync RM consumed_qty from SCR to JC Items |

### `overrides/subcontracting_inward_order.py` (143 lines)

| Method | Line | Purpose |
|--------|------|---------|
| `get_production_items` | 8 | Precision fix for RM-to-FG ratio |
| `make_subcontracting_delivery` | 65 | Custom delivery qty derivation |

---

## 10) JS UI Methods (production_wizard.js)

| Method | Line | Purpose |
|--------|------|---------|
| `create_subcontracting_order` | 1747 | Dialog: supplier + qty + rate → PO/SCO |
| `_submit_sco` | 1872 | API call for SCO creation |
| `send_raw_material_to_supplier` | 1901 | SE creation via auto_split or lookup |
| `receive_subcontracted_goods` | 1938 | Dialog: multi-batch receipt → SCR |
| `.btn-complete-jc` handler | 1440 | Confirm + complete_subcontracted_job_card |
| `.btn-create-sio` handler | 1476 | Create SCIO from details panel |
| `send_subcontracting_delivery` | 1573 | SIO delivery via make_subcontracting_delivery |
| `create_scio_sales_invoice` | 3446 | SI for SCIO items |
