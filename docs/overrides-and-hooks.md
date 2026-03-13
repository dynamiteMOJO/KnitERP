# KnitERP Override & Hook Layer — Complete Analysis

> **Purpose**: This document maps every point where KnitERP intercepts, replaces, or extends
> standard ERPNext/Frappe behavior. It is the single source of truth for understanding
> what will break on an ERPNext upgrade and what to audit.
>
> **Last updated**: 2026-03-06 — ERPNext 16.7.3 / Frappe 16.10.6

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Import-Time Monkey Patches](#2-import-time-monkey-patches)
3. [Class Overrides (override_doctype_class)](#3-class-overrides)
4. [Whitelisted Method Overrides](#4-whitelisted-method-overrides)
5. [Document Event Hooks (doc_events)](#5-document-event-hooks)
6. [Client-Side Includes](#6-client-side-includes)
7. [Standard Queries](#7-standard-queries)
8. [Install / Migrate Hooks](#8-install--migrate-hooks)
9. [Fixtures](#9-fixtures)
10. [Upgrade Risk Matrix](#10-upgrade-risk-matrix)

---

## 1. Architecture Overview

KnitERP's override layer serves three core business needs:

1. **Textile Item Management** — Fabric items are always subcontracted; Yarn items always
   need dual versions (Base + Customer-Provided). Item codes are human-readable composites
   from the Item Composer, not auto-generated.

2. **Subcontracting ↔ Job Card Integration** — ERPNext's standard subcontracting and
   Job Card systems don't natively connect. KnitERP bridges them: Job Cards track
   subcontracted operations, SCRs/PRs update Job Card progress, Stock Entries update
   transferred quantities. Auto-completion is disabled — users complete manually via
   Production Wizard.

3. **Semi-Finished Goods (SFG) Tracking** — Multi-operation BOMs produce intermediate
   goods at different quantities. KnitERP calculates `planned_qty` per operation from
   BOM ratios and propagates overproduction downstream.

### Override Mechanisms Used

| Mechanism | Count | Fragility |
|-----------|-------|-----------|
| Monkey patches (function replacement at import) | 2 | **CRITICAL** — silent failure if upstream changes |
| `override_doctype_class` (class inheritance) | 4 | **HIGH** — complete method replacements don't inherit upstream changes |
| `override_whitelisted_methods` | 1 | **HIGH** — complete function replacement |
| `doc_events` hooks | 13 | **LOW-MEDIUM** — additive, don't replace parent logic |
| Client-side JS includes | 4 | **LOW** — mostly additive UI behavior |
| `standard_queries` | 1 | **LOW** — replaces link-field search |
| `after_migrate` hook | 1 | **LOW** — cosmetic workspace hiding |

---

## 2. Import-Time Monkey Patches

These are the **most fragile** overrides. They replace module-level functions at import
time, before any request is served.

### 2.1 SRE Dashboard Fix — `sre_dashboard_fix.py`

**Imported from**: `kniterp/__init__.py` (line 4) AND `kniterp/hooks.py` (line 2)
The `__init__.py` import fires first (package init); the hooks.py import is a no-op (Python module cache).

#### Patch A: `get_sre_reserved_qty_for_items_and_warehouses`

| Attribute | Detail |
|-----------|--------|
| **WHAT** | Replaces `erpnext.stock.doctype.stock_reservation_entry.stock_reservation_entry.get_sre_reserved_qty_for_items_and_warehouses` |
| **WHY** | Upstream calculates net reserved qty as `reserved_qty - delivered_qty`. It does NOT subtract `consumed_qty`, which **overstates reserved stock** in the item dashboard, SO reservation checks, and planning views after partial consumption. |
| **HOW** | Complete replacement. Builds a new PyPika query that subtracts both `delivered_qty` AND `consumed_qty`. Filter condition also changed: `(delivered_qty + consumed_qty) < reserved_qty`. |
| **GUARD** | At import time, inspects upstream source code for the string `"consumed_qty"`. If found, skips the patch and logs an info message. Self-documenting. |
| **RISK** | **CRITICAL**. If upstream changes the function signature (adds parameters, renames it, moves it to a different module), the patch either: (a) silently replaces the wrong thing, or (b) fails to patch. The guard only checks for `consumed_qty` presence, not structural changes. |
| **SIDE EFFECTS** | Affects ALL stock reservation calculations globally — every doctype that calls these helpers (SO, DN, SE, Item Dashboard, BIN updates) uses the patched version. This is intentional. |

#### Patch B: `get_sre_reserved_qty_details_for_voucher`

| Attribute | Detail |
|-----------|--------|
| **WHAT** | Replaces `erpnext.stock.doctype.stock_reservation_entry.stock_reservation_entry.get_sre_reserved_qty_details_for_voucher` |
| **WHY** | Same consumed_qty omission as Patch A, but for voucher-specific queries. |
| **HOW** | Complete replacement. Same consumed_qty subtraction pattern. |
| **GUARD** | Same `inspect.getsource()` check as Patch A. Both patches are applied or skipped together. |
| **RISK** | **CRITICAL**. Same risks as Patch A. |
| **SIDE EFFECTS** | Affects voucher-specific reservation lookups (used in SO/DN submission, reservation dialogs). |

**When to remove**: When upstream ERPNext includes `consumed_qty` in both functions. Check:
```bash
grep -n "consumed_qty" ../erpnext/stock/doctype/stock_reservation_entry/stock_reservation_entry.py
```

---

## 3. Class Overrides

Registered in `hooks.py` → `override_doctype_class`. These use Python class inheritance.

### 3.1 CustomItem — `overrides/item.py`

**Extends**: `erpnext.stock.doctype.item.item.Item`

#### 3.1.1 `autoname()`

| Attribute | Detail |
|-----------|--------|
| **WHAT** | Replaces `Item.autoname()` for Fabric/Yarn items |
| **WHY** | Item Composer generates human-readable codes (e.g., "Cotton 40s 2/60 - CP"). Standard ERPNext auto-naming would overwrite these. |
| **HOW** | **Conditional**: For Fabric/Yarn → uses `item_code` as `name` directly, appends " - CP" for customer-provided items. For all other items → calls `super().autoname()`. |
| **RISK** | **MEDIUM**. If ERPNext changes `Item.autoname()` signature or adds required logic before naming, Fabric/Yarn items won't get it. |
| **SIDE EFFECTS** | None beyond Item naming. |

#### 3.1.2 `validate()`

| Attribute | Detail |
|-----------|--------|
| **WHAT** | Extends `Item.validate()` |
| **WHY** | Fabric items must always be `is_sub_contracted_item = 1`. Service items must be `is_stock_item = 0`. |
| **HOW** | Sets flags BEFORE calling `super().validate()`. This means ERPNext's validation runs on the corrected values. |
| **RISK** | **LOW**. Calls super(). Additive flag-setting. |
| **SIDE EFFECTS** | Fabric items created through ANY path (API, import, UI) will be forced to subcontracted. |

#### 3.1.3 `after_insert()`

| Attribute | Detail |
|-----------|--------|
| **WHAT** | New method (Item doesn't have a standard `after_insert`) |
| **WHY** | Yarn items need dual versions: a purchasable Base item and a Customer-Provided (CP) item, linked as Item Alternatives. |
| **HOW** | For Yarn → calls `ensure_dual_yarn_versions()` which creates the missing counterpart and links them via Item Alternative. For non-Yarn CP items → legacy `create_purchase_item()`. |
| **RISK** | **LOW**. Purely additive. Creates new documents. |
| **SIDE EFFECTS** | Creating one Yarn item triggers creation of a second Item + an Item Alternative record. If the insert fails mid-way, you could have orphaned items. No explicit transaction management. |

### 3.2 CustomWorkOrder — `overrides/work_order.py`

**Extends**: `erpnext.manufacturing.doctype.work_order.work_order.WorkOrder`

#### 3.2.1 `validate_subcontracting_inward_order()`

| Attribute | Detail |
|-----------|--------|
| **WHAT** | **Complete replacement** of `WorkOrder.validate_subcontracting_inward_order()` |
| **WHY** | Two fixes: (1) Uses `flt(..., 3)` for all quantity comparisons to avoid floating-point errors at 8+ decimal places that blocked WO submission. (2) Changes insufficient CP item qty from `frappe.throw` → `frappe.msgprint` (warning instead of hard block). |
| **HOW** | No `super()` call. Entire method body rewritten. Logic structure is the same as upstream with precision fixes. |
| **RISK** | **HIGH**. Any new validation rules added upstream will NOT be inherited. Must manually diff on every ERPNext upgrade. |
| **SIDE EFFECTS** | The `msgprint` change means WOs can now submit with insufficient CP material — this is intentional (production proceeds, shortage tracked separately via Action Center). |

### 3.3 CustomJobCard — `overrides/job_card.py`

**Extends**: `erpnext.manufacturing.doctype.job_card.job_card.JobCard`

This is the **heaviest override** — 9 methods overridden/added. The Job Card is where
KnitERP's subcontracting-meets-manufacturing model diverges most from standard ERPNext.

#### 3.3.1 `set_status()` — **COMPLETE REPLACEMENT**

| Attribute | Detail |
|-----------|--------|
| **WHAT** | Replaces `JobCard.set_status()` entirely |
| **WHY** | **Disables auto-completion**. Standard ERPNext auto-completes Job Cards when `manufactured_qty >= for_quantity`. KnitERP requires manual completion via Production Wizard (business process control). |
| **HOW** | No `super()` call. Reimplements all status transitions (Open, Submitted, Cancelled, Work In Progress, Material Transferred, On Hold) EXCEPT the auto-completion branches. |
| **RISK** | **HIGH**. Any new status states or transitions added upstream will be silently lost. This is the most dangerous override in the codebase. |
| **SIDE EFFECTS** | Job Cards will NEVER auto-complete in this system. Any workflow that relies on auto-completion (e.g., WO auto-close when all JCs complete) will not trigger automatically. |

#### 3.3.2 `set_manufactured_qty()` — **COMPLETE REPLACEMENT**

| Attribute | Detail |
|-----------|--------|
| **WHAT** | Replaces `JobCard.set_manufactured_qty()` |
| **WHY** | Must use custom `set_status()` (above) and handle both SE-based and SCR-based manufacturing. |
| **HOW** | No `super()` call. Queries SE (for Manufacture) or SCR Item (for subcontracted) to sum manufactured qty. Calls custom `set_status(update_status=True)`. |
| **RISK** | **HIGH**. If ERPNext changes how manufactured_qty is calculated (new sources, new fields), this won't pick it up. |

#### 3.3.3 `set_items_from_work_order()` — **COMPLETE REPLACEMENT**

| Attribute | Detail |
|-----------|--------|
| **WHAT** | Replaces `JobCard.set_items_from_work_order()` |
| **WHY** | Clears and repopulates JC items from WO `required_items` filtered by operation. |
| **HOW** | No `super()` call. Simpler logic than upstream. |
| **RISK** | **MEDIUM**. If upstream adds fields to JC items or changes the mapping logic, this won't get them. |

#### 3.3.4 `make_stock_entry_for_semi_fg_item()` — **COMPLETE REPLACEMENT**

| Attribute | Detail |
|-----------|--------|
| **WHAT** | Replaces the whitelisted method `JobCard.make_stock_entry_for_semi_fg_item()` |
| **WHY** | Overproduction support: uses `total_completed_qty` (from time logs) instead of `for_quantity`. Scales raw material consumption proportionally using BOM ratios. |
| **HOW** | No `super()` call. Builds SE via `ManufactureEntry`, then manually adjusts RM quantities based on BOM ratios. |
| **RISK** | **HIGH**. Depends on `ManufactureEntry` API (its constructor kwargs). If ERPNext changes the SE creation flow for SFG, this will break. |
| **SIDE EFFECTS** | RM consumption may differ from standard ERPNext calculation. Overproduction creates larger SEs than planned. |

#### 3.3.5 `validate()` — Extends with `super()`

| Attribute | Detail |
|-----------|--------|
| **HOW** | Calls `super().validate()` first, then adds items from WO for subcontracted final FG operations. |
| **RISK** | **LOW**. Additive after super(). |

#### 3.3.6 `validate_time_logs()` — Conditional bypass

| Attribute | Detail |
|-----------|--------|
| **WHY** | Subcontracted operations don't have time logs — skip validation. |
| **HOW** | If `is_subcontracted` → return (skip). Otherwise → `super().validate_time_logs()`. |
| **RISK** | **MEDIUM**. If super() adds critical validation beyond time logs, subcontracted JCs won't get it. |

#### 3.3.7 `validate_transfer_qty()` — Conditional bypass

| Attribute | Detail |
|-----------|--------|
| **WHY** | Subcontracted operations don't use WIP warehouse transfer. |
| **HOW** | Same pattern: skip for subcontracted, otherwise super(). |
| **RISK** | **MEDIUM**. Same risk as above. |

#### 3.3.8 `validate_job_card()` — Conditional bypass

| Attribute | Detail |
|-----------|--------|
| **WHY** | Subcontracted JCs don't require time logs for submission. |
| **HOW** | Same pattern: skip for subcontracted, otherwise super(). |
| **RISK** | **MEDIUM**. Same risk as above. |

#### 3.3.9 `on_submit()` — Extends with `super()`

| Attribute | Detail |
|-----------|--------|
| **HOW** | Calls `super().on_submit()` first, then cascades overproduction to subsequent operations. |
| **WHY** | If operation A produces 320 instead of planned 316, operations B and C should plan for 320's ratio. |
| **RISK** | **LOW**. Additive. Only updates draft JCs. |
| **SIDE EFFECTS** | Modifies `for_quantity` of downstream draft Job Cards. If those JCs were already customized, the overproduction ratio overwrites manual edits. |

### 3.4 CustomSubcontractingInwardOrder — `overrides/subcontracting_inward_order.py`

**Extends**: `erpnext.subcontracting.doctype.subcontracting_inward_order.subcontracting_inward_order.SubcontractingInwardOrder`

#### 3.4.1 `get_production_items()` — **COMPLETE REPLACEMENT**

| Attribute | Detail |
|-----------|--------|
| **WHAT** | Replaces `SubcontractingInwardOrder.get_production_items()` |
| **WHY** | Fixes precision rounding on ratio calculation. Standard ERPNext rounds the intermediate ratio, causing over-production (e.g., 247.036 vs 246.999). KnitERP keeps the ratio at full precision and only rounds the final qty to 3 decimal places. |
| **HOW** | No `super()` call. Same logic structure but with `flt(ratio)` instead of `flt(ratio, precision)`. |
| **RISK** | **HIGH**. Complete replacement. New fields or logic upstream will be missed. |

#### 3.4.2 `make_subcontracting_delivery()` — **COMPLETE REPLACEMENT**

| Attribute | Detail |
|-----------|--------|
| **WHAT** | Replaces `SubcontractingInwardOrder.make_subcontracting_delivery()` |
| **WHY** | Fixes delivery qty to always subtract `delivered_qty`. Standard ERPNext had a path where already-delivered qty wasn't subtracted, allowing double-delivery. Also respects `allow_delivery_of_overproduced_qty` setting. |
| **HOW** | No `super()` call. Builds SE with `Subcontracting Delivery` purpose. Handles scrap items. |
| **RISK** | **HIGH**. Complete replacement. If upstream changes delivery flow (new fields, new item types), this diverges silently. |

---

## 4. Whitelisted Method Overrides

### 4.1 `make_subcontracting_po`

| Attribute | Detail |
|-----------|--------|
| **Registered in** | `hooks.py` → `override_whitelisted_methods` |
| **WHAT** | Replaces `erpnext.manufacturing.doctype.job_card.job_card.make_subcontracting_po` |
| **WHY** | Fixes bug where `source.finished_good` is `None` for certain SFG operations. Uses `production_item` as fallback: `fg_item = source.production_item or source.finished_good`. Also adds `require_production_write_access()` check. |
| **HOW** | Complete function replacement. Uses `get_mapped_doc` to create PO from JC. |
| **RISK** | **HIGH**. If ERPNext fixes the `finished_good` bug upstream or changes the PO creation flow, this override silently prevents the fix from taking effect. |
| **SIDE EFFECTS** | All "Create Subcontracting PO" buttons on Job Cards use this version. Access control enforced. |

---

## 5. Document Event Hooks

Registered in `hooks.py` → `doc_events`. These are **additive** — they don't replace
parent methods, they fire alongside them.

### 5.1 Item Events

| Event | Handler | Purpose |
|-------|---------|---------|
| `before_save` | `kniterp.api.item.enforce_batch_tracking_for_fabric_yarn` | Forces `has_batch_no = 1` for Fabric/Yarn items. Ensures lot tracking is always enabled. |
| `after_insert` | `kniterp.api.item_search.on_item_save` | Updates smart search token index for fuzzy item search. |
| `on_update` | `kniterp.api.item_search.on_item_save` | Same as above — rebuilds search index on any item change. |

**Risk**: LOW. Additive. No conflict with upstream.

### 5.2 Salary Slip — `before_save`

| Handler | `kniterp.payroll.calculate_variable_pay` |
|---------|------------------------------------------|
| **Purpose** | Calculates and injects 6 custom salary components: Sunday Pay, Dual Shift Pay, Machine Extra Pay, Conveyance Allowance, Rejected Holiday Deduction, Tea Allowance. |
| **How** | Queries Attendance, Machine Attendance, Monthly Conveyance tables. Appends earnings/deductions rows. Calls `slip.calculate_net_pay()` at end. |
| **Risk** | **LOW-MEDIUM**. Independent of HRMS internals, but calls `calculate_net_pay()` which may change. Custom doctypes (Machine Attendance, Monthly Conveyance) must exist. |
| **Side Effects** | Runs on EVERY salary slip save. Debug `print()` statements present in production code (lines 38-39). |

### 5.3 Sales Order / Purchase Order — Transaction Parameter Sync

| Event | Handler |
|-------|---------|
| SO `on_update` / `on_update_after_submit` | `kniterp.api.transaction_parameters.sync_so_params` |
| PO `on_update` / `on_update_after_submit` | `kniterp.api.transaction_parameters.sync_po_params` |

**Purpose**: Dual-storage pattern — syncs Transaction Parameter JSON from SO/PO Item rows to standalone denormalized doctypes (for Report Builder queries).
**Risk**: LOW. Purely additive.

### 5.4 Work Order — `before_submit`

| Handler | `kniterp.kniterp.overrides.work_order.set_planned_qty_on_work_order` |
|---------|----------------------------------------------------------------------|
| **Purpose** | Computes `planned_qty` on each Work Order Operation from BOM ratios (for SFG tracking). Final FG operation gets WO qty; intermediate operations get `wo_qty × bom_op_fg_qty / bom_qty`. |
| **Risk** | **LOW**. Writes to `planned_qty` field on WO Operation. Additive. |
| **Side Effects** | Only fires on submit. If BOM has no operations or qty is zero, silently skips. Errors are caught and logged (won't block submission). |

### 5.5 Job Card — `before_insert`

| Handler | `kniterp.kniterp.overrides.job_card.set_job_card_qty_from_planned_qty` |
|---------|------------------------------------------------------------------------|
| **Purpose** | Sets `for_quantity` from the WO Operation's `planned_qty` (computed in 5.4 above). |
| **Risk** | **LOW**. Runs before insert. Overwrites default `for_quantity`. |
| **Side Effects** | If `planned_qty` is missing/zero, falls back to keeping the default. Errors caught and logged. |

### 5.6 Purchase Receipt — `on_submit`

| Handler | `kniterp.subcontracting.on_pr_submit_complete_job_cards` |
|---------|----------------------------------------------------------|
| **Purpose** | When a subcontracted PR is submitted, updates linked Job Cards: sets `manufactured_qty` from total received across all SCRs, sets status to "Work In Progress". Also updates WO operation `completed_qty`. |
| **Risk** | **MEDIUM**. Directly writes to JC fields (`manufactured_qty`, `status`) via `db_set`, bypassing JC controller. If ERPNext adds JC status validation, these direct writes could create inconsistent state. |
| **Side Effects** | Does NOT auto-complete JCs (intentional). Updates WO operation status via `update_operation_status()`. |

### 5.7 Subcontracting Receipt — `before_validate` + `on_submit`

| Event | Handler | Purpose |
|-------|---------|---------|
| `before_validate` | `before_validate_set_customer_warehouse` | Injects `customer_warehouse` from `supplier_warehouse` when missing. ERPNext's subcontracting controller reads this field (~line 624) but SCR doesn't always carry it. |
| `on_submit` | `on_submit_complete_job_cards` | Updates JC `manufactured_qty` and `consumed_qty` (in JC Items table) from SCR supplied items. Sets JC status. |

**Risk**: **MEDIUM** for on_submit (same direct-write concerns as 5.6). **LOW** for before_validate (simple field injection).
**Side Effects**: The `consumed_qty` update in JC Items is a **custom extension** — ERPNext doesn't track RM consumption in Job Cards for subcontracting. This data is used by Production Wizard.

### 5.8 Stock Entry — `on_submit` + `on_cancel`

| Event | Handler | Purpose |
|-------|---------|---------|
| `on_submit` | `on_se_submit_update_job_card_transferred` | For "Send to Subcontractor" SEs, recalculates `transferred_qty` on linked JC items and header. Updates JC status. |
| `on_cancel` | `on_se_cancel_update_job_card_transferred` | Same recalculation on cancel (removes cancelled SE's qty). |

**Link chain**: SE → SCO → SCO Item → PO Item → Job Card (via `purchase_order_item` link).

**Risk**: **MEDIUM**. Complex SQL joins to find linked JCs. If ERPNext changes the SCO→PO linking structure, the SQL will return wrong results. Direct `db_set` on JC fields.

**Side Effects**: Status transitions: Open → Work In Progress → Material Transferred based on transferred_qty vs for_quantity. Never sets Completed (manual only).

---

## 6. Client-Side Includes

### 6.1 `app_include_js` (loaded on every desk page)

| File | Purpose |
|------|---------|
| `item_composer.js` | Global Item creation dialog (fuzzy search, classification-aware) |
| `sales_order_subcontracting_fix.js` | When SO `is_subcontracted`, filters item_code link to show only `is_stock_item = 0` (service items). Applies on onload, refresh, and field change. |
| `sales_order.js` | SO customizations (Transaction Parameters UI, etc.) |
| `purchase_order.js` | PO customizations (Transaction Parameters UI, etc.) |

### 6.2 `doctype_list_js`

| DocType | File | Purpose |
|---------|------|---------|
| Sales Order | `sales_order_list.js` | List view customizations |
| Purchase Order | `purchase_order_list.js` | List view customizations |

**Risk**: LOW. Client scripts are additive and don't replace core behavior.

---

## 7. Standard Queries

```python
standard_queries = {
    "Item": "kniterp.api.item_search.smart_search"
}
```

**What**: All Item link-field searches across the entire system use KnitERP's fuzzy
token-based search instead of ERPNext's standard `%LIKE%` search.

**Risk**: LOW. If the search breaks, link fields won't populate — highly visible, easy to diagnose.

---

## 8. Install / Migrate Hooks

```python
after_install = "kniterp.kniterp.install.after_migrate"
after_migrate = "kniterp.kniterp.install.after_migrate"
```

Both point to the same function: `hide_unwanted_workspaces()`.

**What**: Hides 29 standard workspaces (Selling, Buying, Stock, Manufacturing, etc.) by
setting `is_hidden=1`, `public=0`, and restricting to Administrator role. Pushes
non-KnitERP desktop icons and workspaces to bottom (idx + 100).

**Modules hidden**: Subscription, Share Management, Budget, Home, CRM, Selling, Buying,
Stock, Assets, Projects, Support, Quality, Manufacturing, Recruitment, Tenure,
Shift & Attendance, Performance, Expenses, Payroll, Frappe HR, Subcontracting, ERPNext,
Data, Printing, Automation, Email, Website, Users, Integrations, Build.

**Risk**: LOW. Cosmetic. Runs on every `bench migrate`.

**Side Effects**: If a new ERPNext version adds workspaces, they'll be visible until the
next migrate. The bulk SQL updates (`idx + 100`) run without WHERE guards on already-shifted
records — repeated migrations will keep incrementing.

---

## 9. Fixtures

| Fixture | Filter | Purpose |
|---------|--------|---------|
| Transaction Parameter | All | Custom doctype data |
| Item Token Alias | All | Fuzzy search aliases |
| Designation | Master, Helper, Operator | Worker classifications |
| Client Script | module = Kniterp | UI customizations |
| Property Setter | module = Kniterp | Field customizations |
| Custom Field | module = Kniterp | Schema extensions |
| Print Format | module = Kniterp | Custom print layouts |

---

## 10. Upgrade Risk Matrix

### CRITICAL — Check immediately on any ERPNext upgrade

| Override | File | What to Check |
|----------|------|---------------|
| SRE `get_sre_reserved_qty_for_items_and_warehouses` | `sre_dashboard_fix.py` | `grep "consumed_qty" erpnext/stock/doctype/stock_reservation_entry/stock_reservation_entry.py` — if found, **remove the patch**. If function moved/renamed, patch silently fails. |
| SRE `get_sre_reserved_qty_details_for_voucher` | `sre_dashboard_fix.py` | Same as above — both patched together. |

### HIGH — Diff upstream method on every upgrade

| Override | File | What to Check |
|----------|------|---------------|
| `JobCard.set_status()` | `job_card.py` | Diff `erpnext/manufacturing/doctype/job_card/job_card.py` → `set_status()`. Any new status states or transitions must be manually ported. |
| `JobCard.set_manufactured_qty()` | `job_card.py` | Diff same file → `set_manufactured_qty()`. New qty sources won't be picked up. |
| `JobCard.make_stock_entry_for_semi_fg_item()` | `job_card.py` | Check `ManufactureEntry` constructor kwargs. If SE creation for SFG changes, this breaks. |
| `JobCard.set_items_from_work_order()` | `job_card.py` | Diff for new fields in JC Item mapping. |
| `WorkOrder.validate_subcontracting_inward_order()` | `work_order.py` | Diff `work_order.py` → same method. New validation rules won't be inherited. |
| `SCIO.get_production_items()` | `subcontracting_inward_order.py` | Diff `subcontracting_inward_order.py` → same method. |
| `SCIO.make_subcontracting_delivery()` | `subcontracting_inward_order.py` | Diff same file → same method. New delivery logic missed. |
| `make_subcontracting_po` (whitelisted) | `job_card.py` | Check if ERPNext fixed the `finished_good = None` bug. If yes, consider removing override. |

### MEDIUM — Review on major version upgrades

| Override | File | What to Check |
|----------|------|---------------|
| `JobCard.validate_time_logs()` | `job_card.py` | If super() adds non-time-log validation, subcontracted JCs skip it. |
| `JobCard.validate_transfer_qty()` | `job_card.py` | Same — conditional bypass risk. |
| `JobCard.validate_job_card()` | `job_card.py` | Same — conditional bypass risk. |
| SCR `on_submit` → JC updates | `subcontracting_receipt.py` | Direct `db_set` on JC. If ERPNext adds JC status machine validation, writes may conflict. |
| PR `on_submit` → JC updates | `subcontracting.py` | Same risk as SCR on_submit. |
| SE `on_submit/cancel` → JC transferred_qty | `subcontracting.py` | Complex SQL chain (SE→SCO→POI→JC). If link structure changes, SQL returns wrong data. |
| `CustomItem.autoname()` | `item.py` | If Item naming scheme changes for non-Fabric/Yarn, the conditional branch may need updating. |

### LOW — Generally safe

| Override | File | What to Check |
|----------|------|---------------|
| `CustomItem.validate()` | `item.py` | Calls super(). Only risk: if validate() signature changes. |
| `CustomItem.after_insert()` | `item.py` | Additive. Creates new docs. |
| `CustomJobCard.validate()` | `job_card.py` | Calls super() first. Additive. |
| `CustomJobCard.on_submit()` | `job_card.py` | Calls super() first. Additive. |
| `set_planned_qty_on_work_order` (doc_event) | `work_order.py` | Additive. Error-caught. |
| `set_job_card_qty_from_planned_qty` (doc_event) | `job_card.py` | Additive. Error-caught. |
| `before_validate_set_customer_warehouse` (doc_event) | `subcontracting_receipt.py` | Simple field injection. |
| Payroll `calculate_variable_pay` | `payroll.py` | Independent of HRMS internals (mostly). |
| `after_migrate` workspace hiding | `install.py` | Cosmetic. |
| `standard_queries` (Item search) | hooks.py | If search breaks, link fields fail — visible. |
| Client-side JS | `public/js/` | Additive UI. |

---

## Appendix: Complete Hook Registration Map

```
hooks.py
├── app_include_js (4 files)
├── app_include_css (1 file)
├── override_doctype_class (4 doctypes)
│   ├── Item → CustomItem
│   ├── Job Card → CustomJobCard
│   ├── Subcontracting Inward Order → CustomSubcontractingInwardOrder
│   └── Work Order → CustomWorkOrder
├── override_whitelisted_methods (1)
│   └── make_subcontracting_po
├── standard_queries (1)
│   └── Item → smart_search
├── doc_events (13 hooks across 8 doctypes)
│   ├── Item: before_save, after_insert, on_update
│   ├── Salary Slip: before_save
│   ├── Sales Order: on_update, on_update_after_submit
│   ├── Purchase Order: on_update, on_update_after_submit
│   ├── Work Order: before_submit
│   ├── Job Card: before_insert
│   ├── Purchase Receipt: on_submit
│   ├── Subcontracting Receipt: before_validate, on_submit
│   └── Stock Entry: on_submit, on_cancel
├── fixtures (7 entries)
├── doctype_list_js (2 doctypes)
├── after_install → after_migrate
└── after_migrate → after_migrate

__init__.py
└── import sre_dashboard_fix (monkey patch, 2 functions)

hooks.py top-level imports
├── import job_card (logger setup only)
└── import sre_dashboard_fix (no-op, already imported by __init__)
```
