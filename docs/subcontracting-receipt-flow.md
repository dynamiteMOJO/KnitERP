# Subcontracting Receipt & Purchase Receipt — ERPNext Behaviour Reference

Reference doc for understanding ERPNext's native subcontracting receipt flow. Use this when building or modifying kniterp custom features that interact with subcontracting.

---

## Flow Overview

```
Subcontracting Order (SCO)
    │
    ├──► Stock Entry (Send to Subcontractor)
    │       SLE: RM qty out of your warehouse → supplier warehouse
    │
    ├──► Subcontracting Receipt (SCR) on submit
    │       ├── SLE: Finished goods IN to accepted warehouse
    │       ├── SLE: Raw materials OUT of supplier warehouse (consumed)
    │       ├── GL entries (if perpetual inventory)
    │       ├── SCO status updates (received_qty, consumed_qty)
    │       ├── Job Card update (if linked)
    │       ├── India Compliance: GST validation, ITC-04, e-Waybill
    │       └── Auto-creates Purchase Receipt (if Buying Settings enabled)
    │
    └──► Purchase Receipt (PR) — created from SCR
            ├── GL: recognises supplier payable (creditor liability)
            ├── PO fulfillment (received_qty, per_received)
            └── India Compliance: GST validation, e-Waybill
```

---

## Subcontracting Receipt — on_submit

Source: `erpnext/subcontracting/doctype/subcontracting_receipt/subcontracting_receipt.py`

### Stock Ledger Entries

**Finished Goods IN** (per item in `items` table):
- `actual_qty = +qty` into `warehouse` (accepted warehouse)
- `incoming_rate` = rm_cost_per_qty + service_cost_per_qty + additional_cost_per_qty − scrap_cost_per_qty
- Rejected qty (if any) goes to `rejected_warehouse` at incoming_rate = 0

**Raw Materials OUT** (per row in `supplied_items` table):
- `actual_qty = -consumed_qty` from `supplier_warehouse`
- This consumes RM that was previously sent via Stock Entry

### GL Entries (Perpetual Inventory Only)

For each finished good item:

| Entry | Account | Debit | Credit |
|-------|---------|-------|--------|
| FG into warehouse | Stock In Hand (warehouse inventory account) | stock_value_diff | — |
| RM cost absorption | Expense Account (e.g. Stock Received But Not Billed) | — | stock_value_diff − service_cost |
| Service cost | Service Expense Account | — | service_cost |
| RM consumed | Supplier Warehouse Inventory Account | — | rm_item.amount |
| RM to expense | Expense Account | rm_item.amount | — |
| Additional costs (if any) | Expense Account | qty × additional_cost_per_qty | — |
| Additional cost source | Additional Cost Expense Account | — | base_amount |
| Divisional loss (rounding) | Stock Adjustment Account ↔ Expense Account | if any | if any |

### Other Updates

| What | Detail |
|------|--------|
| SCO received_qty | `status_updater` updates `received_qty` on SCO Items |
| SCO consumed_qty | `set_consumed_qty_in_subcontract_order()` updates consumed_qty in SCO Supplied Items |
| SCO status | Sets per_received and overall status on the SCO |
| Stock Reservation | Releases any reserved stock entries |
| Serial/Batch Bundles | Creates/updates bundles for items and supplied_items |
| Job Card | Updates manufactured qty if linked |
| Repost future SLE/GLE | Triggers if transaction is backdated |
| Auto Purchase Receipt | If `Buying Settings > auto_create_purchase_receipt` is on |

---

## Purchase Receipt — created from SCR

Source: `make_purchase_receipt()` in `subcontracting_receipt.py`

The PR is mapped from the **Purchase Order** (not the SCR directly):
- Sets `is_subcontracted = 1`, `is_old_subcontracting_flow = 0`
- Uses the SCR's posting_date and posting_time
- Maps PO items matching the SCR items via `purchase_order_item`

**Primary purpose**: Recognise the creditor/supplier liability for service charges. The stock valuation is already handled by the SCR.

The PR creates:
- **GL entries**: Typically `Stock Received But Not Billed Dr` ↔ `Creditors/Supplier Account Cr`
- **PO fulfillment**: Updates `received_qty` and `per_received` on the Purchase Order
- **Bin update**: Updates projected qty

---

## India Compliance App — Subcontracting Receipt

Source: `india_compliance/gst_india/overrides/subcontracting_transaction.py`
Hooks: `india_compliance/hooks.py`

### Hooks Triggered

| Event | What happens |
|-------|-------------|
| `onload` | Loads e-Waybill info if exists |
| `validate` | CustomTaxController sets GST taxes/totals; validates GSTIN, place of supply, GST accounts (IGST vs CGST+SGST), GST category |
| `before_save` | Validates charge types (no "Actual" allowed); validates ITC-04 document references |
| `before_cancel` | Checks e-Waybill cancellation requirement |
| `before_mapping` | Maps India Compliance Taxes and Charges child table |

### Key Features

- **GST Tax Calculation**: `CustomTaxController` computes GST based on inter/intra state supply (IGST or CGST+SGST)
- **e-Waybill**: Supported if `GST Settings > enable_e_waybill_for_sc` is on. Dashboard shows e-Waybill log links.
- **ITC-04 Reporting**: `validate_doc_references()` requires selecting Original Document References (Stock Entries / Subcontracting Receipt returns) for ITC-04 filing — the return for goods sent to/received from job workers.
- **Audit Trail**: Subcontracting Receipt is in `audit_trail_doctypes` — all amendments are tracked.

### India Compliance on Purchase Receipt

The auto-created PR also triggers standard India Compliance hooks:
- GST transaction validation
- GST details update on save/submit
- e-Waybill applicability check

---

## Item Rate Composition in SCR

The finished good rate in the SCR is calculated as:

```
rate = rm_cost_per_qty + service_cost_per_qty + additional_cost_per_qty + lcv_cost_per_qty − scrap_cost_per_qty
```

Where:
- `rm_cost_per_qty` = sum of (consumed_qty × rate) for all supplied items mapped to this FG item, divided by FG qty
- `service_cost_per_qty` = from SCO (the subcontracting service charge)
- `additional_cost_per_qty` = from Additional Costs table (transport, etc.)
- `lcv_cost_per_qty` = from any Landed Cost Voucher applied later
- `scrap_cost_per_qty` = value of scrap items produced (reduces FG cost)
