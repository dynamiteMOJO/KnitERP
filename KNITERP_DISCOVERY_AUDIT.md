# KNITERP Discovery Audit (Frappe v16)

## Scope and Method
- Scope: `frappe-bench/apps/kniterp` only.
- Mode: static, read-only code/fixture discovery.
- Goal: complete production-grade ERP audit across discovery, analysis, risk, and roadmap.
- Scan basis: Python, JS, JSON fixtures, hooks, overrides, pages, doctypes, utilities.

## Executive Snapshot
- Total files scanned: 115 (`rg --files frappe-bench/apps/kniterp | wc -l`).
- Whitelisted endpoints discovered: 44 declared, 43 effective unique method paths (duplicate function collision in `production_wizard.py`).
- Override classes: 4 (`hooks.py:46`).
- Doc events: 6 doctypes / 7 event bindings (`hooks.py:57`).
- Override whitelisted methods: 1 (`hooks.py:53`).
- Active scheduler hooks: none (only commented template at `hooks.py:232`).
- Raw SQL call sites: 77 (`rg "frappe.db.sql("`).
- Dialogs found: 16 (`rg "new frappe.ui.Dialog("`).

## Coverage Gate (Mandatory 1-21)
| # | Category | Status | Evidence |
|---|---|---|---|
| 1 | All doctypes (incl. child tables) | Complete | Section 1 |
| 2 | `override_doctype_class` | Complete | Section 2 |
| 3 | `doc_events` | Complete | Section 3 |
| 4 | `override_whitelisted_methods` | Complete | Section 4 |
| 5 | Monkey patches | Complete | Section 5 |
| 6 | Custom SQL queries | Complete | Section 6 |
| 7 | Scheduled tasks | Complete (`none active`) | Section 7 |
| 8 | `hooks.py` configurations | Complete | Section 8 |
| 9 | API endpoints (`@frappe.whitelist`) | Complete | Section 9 |
| 10 | JS customizations | Complete | Section 10 |
| 11 | Dialog overrides / custom dialogs | Complete | Section 11 |
| 12 | ERPNext workflow interceptions | Complete | Section 12 |
| 13 | Payroll / HR / stock / manufacturing changes | Complete | Section 13 |
| 14 | Fixtures | Complete | Section 14 |
| 15 | Custom reports | Complete (`none found`) | Section 15 |
| 16 | Property setters | Complete | Section 16 |
| 17 | Client scripts | Complete | Section 17 |
| 18 | Patches / migrations | Complete | Section 18 |
| 19 | Naming logic overrides | Complete | Section 19 |
| 20 | Direct DB writes | Complete | Section 20 |
| 21 | Validation bypasses | Complete | Section 21 |

## Phase 1: Full Discovery

### 1) Custom DocTypes and Child Tables
| DocType | Type | File | Key lines | Key behavior | ERPNext impact | Risk |
|---|---|---|---:|---|---|---|
| Item Attribute Applies To | Child table (`istable`) | `frappe-bench/apps/kniterp/kniterp/kniterp/doctype/item_attribute_applies_to/item_attribute_applies_to.json` | 23, 28 | Maps Textile Attribute applicability to values (`item_attribute_applies_to` link). | Extends textile attribute model. | Medium |
| Item Attribute Applies To Values | Master | `frappe-bench/apps/kniterp/kniterp/kniterp/doctype/item_attribute_applies_to_values/item_attribute_applies_to_values.json` | 4, 28 | Uses expression naming `format:{type_of_item}`. | Drives filter options in item selector. | Medium |
| Item Textile Attribute | Child table (`istable`) | `frappe-bench/apps/kniterp/kniterp/kniterp/doctype/item_textile_attribute/item_textile_attribute.json` | 100, 105 | Item attribute rows with links to Textile Attribute and Textile Attribute Value. | Embedded into Item via custom table field. | High (SKU governance) |
| Item types for attributes | Master | `frappe-bench/apps/kniterp/kniterp/kniterp/doctype/item_types_for_attributes/item_types_for_attributes.json` | 27 | Classification helper doctype. | Supports attribute applicability taxonomy. | Low |
| Machine Attendance | Master | `frappe-bench/apps/kniterp/kniterp/kniterp/doctype/machine_attendance/machine_attendance.json` | 64 | Tracks operator/shift/machine production qty. | HR/payroll side-data source. | Medium |
| Machine Attendance Entry | Child table (`istable`) | `frappe-bench/apps/kniterp/kniterp/kniterp/doctype/machine_attendance_entry/machine_attendance_entry.json` | 55, 60 | Child rows for machine-attendance tool input. | Bulk generation input model. | Low |
| Machine Attendance Tool | Single (`issingle`) | `frappe-bench/apps/kniterp/kniterp/kniterp/doctype/machine_attendance_tool/machine_attendance_tool.json` | 42, 47 | Operational UI to generate Machine Attendance records. | Writes HR attendance-like operational data. | Medium |
| Monthly Conveyance | Master | `frappe-bench/apps/kniterp/kniterp/kniterp/doctype/monthly_conveyance/monthly_conveyance.json` | 59 | Employee conveyance ledger used in payroll math. | Payroll earning component source. | Medium |
| Production Wizard Note | Master | `frappe-bench/apps/kniterp/kniterp/kniterp/doctype/production_wizard_note/production_wizard_note.json` | 50 | Notes keyed to sales order item for production ops. | Planner collaboration data. | Low |
| Textile Attribute | Master | `frappe-bench/apps/kniterp/kniterp/kniterp/doctype/textile_attribute/textile_attribute.json` | 4, 107 | Attribute dictionary with sequencing and naming flags. | Core to item naming/build logic. | High |
| Textile Attribute Value | Master | `frappe-bench/apps/kniterp/kniterp/kniterp/doctype/textile_attribute_value/textile_attribute_value.json` | 4, 62 | Attribute values; expression naming `format:{kniterp_value}`. | Used by selectors and item generation. | High |

Controller-level validations in custom doctypes:
- `ItemTextileAttribute.validate` enforces value typing and derives display value (`item_textile_attribute.py:10`).
- `MachineAttendance.validate` enforces uniqueness/designation/qty constraints (`machine_attendance.py:11`).
- `MonthlyConveyance.validate` computes amount (`monthly_conveyance.py:10`).
- `MachineAttendanceTool.generate_attendance` inserts Machine Attendance with bypass (`machine_attendance_tool.py:9`, `machine_attendance_tool.py:43`).

### 2) `override_doctype_class`
Source: `frappe-bench/apps/kniterp/kniterp/hooks.py:46`

| Doctype | Override class | File | Behavioral delta vs ERPNext | ERPNext behavior modified | Risk |
|---|---|---|---|---|---|
| Item | `CustomItem` | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/item.py` | Custom `autoname` for Fabric/Yarn (`item.py:7`), forced CP suffix logic (`item.py:16`), textile-driven code/name building (`item.py:75`, `item.py:96`), post-insert Yarn dual-item auto-creation + alternatives (`item.py:120`, `item.py:130`). | Yes (core Item naming/validation lifecycle). | High |
| Job Card | `CustomJobCard` | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/job_card.py` | Removes ERPNext auto-complete semantics in `set_status` (`job_card.py:188`), overrides manufactured qty/status write path (`job_card.py:232`), custom stock-entry logic for semi-FG overproduction (`job_card.py:325`), skips validations for subcontracted cards (`job_card.py:292`, `job_card.py:302`, `job_card.py:313`). | Yes (manufacturing execution/status). | Critical |
| Subcontracting Inward Order | `CustomSubcontractingInwardOrder` | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/subcontracting_inward_order.py` | Changes `get_production_items` precision behavior (`subcontracting_inward_order.py:8`) and custom delivery quantity derivation (`subcontracting_inward_order.py:66`). | Yes (subcontracting inward production/delivery). | High |
| Work Order | `CustomWorkOrder` | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/work_order.py` | Custom subcontracting inward validations (`work_order.py:42`), custom planned qty update strategy via hook (`work_order.py:152`). | Yes (manufacturing validation/operation planning). | High |

### 3) `doc_events`
Source: `frappe-bench/apps/kniterp/kniterp/hooks.py:57`

| Doctype | Event | Handler | Hook line | Handler file:line | Side effects | ERPNext impact | Risk |
|---|---|---|---:|---|---|---|---|
| Salary Slip | `before_save` | `kniterp.payroll.calculate_variable_pay` | 59 | `frappe-bench/apps/kniterp/kniterp/payroll.py:9` | Recomputes earnings/deductions and invokes `calculate_net_pay()`. | Yes (payroll settlement logic). | High |
| Work Order | `before_submit` | `...set_planned_qty_on_work_order` | 62 | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/work_order.py:152` | Updates operation planned qty using BOM and custom ratios. | Yes | High |
| Job Card | `before_insert` | `...set_job_card_qty_from_planned_qty` | 65 | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/job_card.py:108` | Sets Job Card `for_quantity` from Work Order operation planned qty. | Yes | Medium |
| Purchase Receipt | `on_submit` | `kniterp.subcontracting.on_pr_submit_complete_job_cards` | 68 | `frappe-bench/apps/kniterp/kniterp/subcontracting.py:86` | Updates JC manufactured/status and WO operation status. | Yes | High |
| Subcontracting Receipt | `on_submit` | `...subcontracting_receipt.on_submit_complete_job_cards` | 71 | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/subcontracting_receipt.py:24` | Updates JC manufactured/status and JC item consumed qty. | Yes | High |
| Stock Entry | `on_submit` | `...on_se_submit_update_job_card_transferred` | 74 | `frappe-bench/apps/kniterp/kniterp/subcontracting.py:100` | Recomputes JC transferred qty from subcontracting stock transfers. | Yes | High |
| Stock Entry | `on_cancel` | `...on_se_cancel_update_job_card_transferred` | 75 | `frappe-bench/apps/kniterp/kniterp/subcontracting.py:106` | Recomputes JC transferred qty after reversal. | Yes | High |

### 4) `override_whitelisted_methods`
Source: `frappe-bench/apps/kniterp/kniterp/hooks.py:53`

| Original ERPNext method | Override method | Hook line | Override file:line | Caller path | ERPNext impact | Risk |
|---|---|---:|---|---|---|---|
| `erpnext.manufacturing.doctype.job_card.job_card.make_subcontracting_po` | `kniterp.kniterp.overrides.job_card.make_subcontracting_po` | 54 | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/job_card.py:51` | No direct local JS call found; effective call path is ERPNext Job Card action invoking the original dotted path. | Yes (subcontracting PO mapping payload). | High |

### 5) Monkey Patches and Import-Time Side Effects
| Patch type | Evidence | File:line | What changes | ERPNext impact | Risk |
|---|---|---:|---|---|---|
| Runtime monkey patch | `SubcontractingReceipt.validate = patched_validate` | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/subcontracting_receipt.py:21` | Injects `customer_warehouse` fallback before original validate. | Yes | Critical (upgrade fragility) |
| Runtime monkey patch | `stock_reservation_entry.get_sre_reserved_qty_for_items_and_warehouses = ...` | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/sre_dashboard_fix.py:64` | Replaces SRE reserved qty computation including consumed qty. | Yes | High |
| Runtime monkey patch | `stock_reservation_entry.get_sre_reserved_qty_details_for_voucher = ...` | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/sre_dashboard_fix.py:65` | Replaces voucher-level reserved qty details. | Yes | High |
| Hook import side effect | `import kniterp.kniterp.overrides.subcontracting_receipt` | `frappe-bench/apps/kniterp/kniterp/hooks.py:1` | Import activates patch assignment at import time. | Yes | High |
| Hook import side effect | `import kniterp.kniterp.overrides.job_card` | `frappe-bench/apps/kniterp/kniterp/hooks.py:2` | Import-time logger setup and method definitions loaded globally. | Indirect | Medium |
| Package import side effect | `import kniterp.kniterp.overrides.sre_dashboard_fix` | `frappe-bench/apps/kniterp/kniterp/__init__.py:4` | Patch applied at app import time, outside hooks granularity. | Yes | High |
| Module import side effect | `setup_logger()` called at import | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/job_card.py:47`, `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/work_order.py:33` | Creates file handlers during import. | Indirect | Medium |

### 6) Custom SQL Inventory (All discovered `frappe.db.sql` call sites)
Legend: `H` high-risk, `M` medium, `L` low (scale/complexity risk), with emphasis on production volumes.

#### 6.1 `api/production_wizard.py` (largest hotspot)
- `check_rm_availability`: `production_wizard.py:36` (`M`) per-RM stock sum query in loop.
- `get_unique_parties`: `production_wizard.py:105` (`M`) dynamic SQL with formatted `where_clause`.
- `get_pending_production_items`: `production_wizard.py:187`, `production_wizard.py:299` (`M`) dynamic filters + per-item stock query.
- `get_production_details`: `production_wizard.py:530`, `557`, `712`, `738`, `748`, `763` (`H`) nested/iterative queries over WO/JC/PO/SCO/SCR/SE.
- `create_subcontracting_order`: `production_wizard.py:1261`, `1276`, `1294` (`H`) previous-op checks and aggregate ordered qty.
- `complete_operation`: `production_wizard.py:1742` (`M`) aggregate timelog reconciliation.
- `get_status_summary`: `production_wizard.py:2292`, `2302` (`L`).
- `create_delivery_note`: `production_wizard.py:2379` (`M`) subcontract receipt aggregation.
- `create_sales_invoice`: `production_wizard.py:2524`, `2552`, `2595` (`H`) DN/SI cross-link billing loops.
- `create_scio_sales_invoice`: `production_wizard.py:2691` (`M`) billed qty aggregate.
- `get_batch_production_summary`: `production_wizard.py:2992`, `3015`, `3037`, `3047`, `3068` (`M-H`) multi-join batch history.
- duplicate `complete_job_card` implementation: `production_wizard.py:3111` (`M`) subcontract receipt qty sum.

#### 6.2 `api/action_center.py`
- Query-heavy dashboard/fix functions at lines:
`161, 181, 223, 238, 384, 396, 463, 485, 492, 574, 638, 686, 782, 793, 850, 884, 908, 927, 942, 987, 1002, 1026, 1036, 1057, 1072`.
- Risk: mostly `M`, with `H` where repeated per-row queries amplify (e.g., delivery/invoice fix detail builders).

#### 6.3 `api/bom_tool.py`
- `find_or_create_subcontracting_bom`: `bom_tool.py:265` (`M`) cross-SO impact check query.

#### 6.4 Item/textile selector SQL
- `api/item_selector.py:56`, `api/item_selector.py:62` (`M`) attribute matching search query.
- `api/textile_attributes.py:9`, `api/textile_attributes.py:30` (`L-M`) lookup queries.

#### 6.5 Payroll/HR SQL
- `payroll.py:76, 88, 104, 118, 137` (`M`) repeated attendance/payroll aggregation queries.
- `machine_attendance_tool.py:74` (`L`) prior-employee lookup.

#### 6.6 Subcontracting hooks and overrides
- `subcontracting.py:57, 124, 157` (`M-H`) receipt and transfer rollups; `157` uses dynamic f-string SQL.
- `overrides/subcontracting_receipt.py:56, 100` (`M`) JC receipt and consumed qty rollups.

#### 6.7 Utility SQL (destructive admin scripts)
- `utils/__init__.py:25, 33, 34, 35` (`Critical`) direct DELETE/UPDATE DML.
- `utils/reset_transactions.py:25, 33, 34, 35, 118` (`Critical`) direct DML and orphan cleanup deletes.

Dynamic SQL constructs explicitly found:
- `subcontracting.py:157` (`frappe.db.sql(f"""...""")`).
- `production_wizard.py:530` with runtime placeholder interpolation + `IN ({placeholders})`.
- `production_wizard.py:111`, `production_wizard.py:218` with string `.format(where_clause=...)`.

### 7) Scheduled Tasks
- Active scheduler hooks: none.
- Evidence: only commented template block at `frappe-bench/apps/kniterp/kniterp/hooks.py:232` to `hooks.py:248`.

### 8) Full `hooks.py` Configuration Inventory
Source: `frappe-bench/apps/kniterp/kniterp/hooks.py`

Active keys:
- `app_include_js` (`hooks.py:34`):
  - `/assets/kniterp/js/kniterp_item_selector.js`
  - `/assets/kniterp/js/item_selector_form_botton.js`
  - `/assets/kniterp/js/item_client_script.js`
  - `/assets/kniterp/js/sales_order_subcontracting_fix.js`
  - `/assets/kniterp/js/sales_order.js`
- `app_include_css` (`hooks.py:42`): `/assets/kniterp/css/kniterp.css`.
- `override_doctype_class` (`hooks.py:46`): Item, Job Card, Subcontracting Inward Order, Work Order overrides.
- `override_whitelisted_methods` (`hooks.py:53`): Job Card subcontracting PO override.
- `doc_events` (`hooks.py:57`): Salary Slip, Work Order, Job Card, Purchase Receipt, Subcontracting Receipt, Stock Entry.
- `fixtures` (`hooks.py:80`): Page, Textile Attribute(+Value), Item Attribute Applies To Values, Designation, Client Script, Property Setter, Custom Field, Workspace.

Import-time side effects in hooks:
- `hooks.py:1`, `hooks.py:2` imports override modules.

Commented but notable:
- `scheduler_events` template (`hooks.py:232`).
- dormant hook templates for request/auth/permission/etc.

### 9) API Endpoint Catalog (`@frappe.whitelist`)

#### 9.1 Endpoint catalog (required format)
| method_path | type | file | line | args | writes | permission_risk | erpnext_impact |
|---|---|---|---:|---|---|---|---|
| `/api/method/kniterp.kniterp.api.action_center.get_action_items` | `function` | `frappe-bench/apps/kniterp/kniterp/api/action_center.py` | 6 | `-` | `read-only` | Low | No |
| `/api/method/kniterp.kniterp.api.action_center.get_fix_details` | `function` | `frappe-bench/apps/kniterp/kniterp/api/action_center.py` | 34 | `action_key` | `read-only` | Low | No |
| `/api/method/kniterp.kniterp.api.action_center.create_purchase_invoice` | `function` | `frappe-bench/apps/kniterp/kniterp/api/action_center.py` | 1138 | `po_name, bill_no, bill_date` | `save` | Medium-High (write API, no explicit permission check in function body) | No |
| `/api/method/kniterp.kniterp.api.action_center.submit_purchase_invoice` | `function` | `frappe-bench/apps/kniterp/kniterp/api/action_center.py` | 1156 | `invoice_name` | `submit` | Medium-High (write API, no explicit permission check in function body) | Yes |
| `/api/method/kniterp.kniterp.api.bom_tool.create_multilevel_bom` | `function` | `frappe-bench/apps/kniterp/kniterp/api/bom_tool.py` | 7 | `data` | `transitive writes (BOM/Subcontracting BOM creation via internal calls)` | Medium-High | Yes |
| `/api/method/kniterp.kniterp.api.bom_tool.get_multilevel_bom` | `function` | `frappe-bench/apps/kniterp/kniterp/api/bom_tool.py` | 466 | `bom_no` | `read-only` | Low | Yes |
| `/api/method/kniterp.kniterp.api.item_selector.find_exact_items` | `function` | `frappe-bench/apps/kniterp/kniterp/api/item_selector.py` | 5 | `classification, attributes` | `read-only` | Medium (read SQL endpoint) | No |
| `/api/method/kniterp.kniterp.api.item_selector.search_textile_attribute_values` | `function` | `frappe-bench/apps/kniterp/kniterp/api/item_selector.py` | 60 | `txt, classification` | `read-only` | Medium (read SQL endpoint) | No |
| `/api/method/kniterp.kniterp.api.production_wizard.get_unique_parties` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 48 | `filters` | `read-only` | Medium (read SQL endpoint) | No |
| `/api/method/kniterp.kniterp.api.production_wizard.get_pending_production_items` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 117 | `filters` | `read-only` | Medium (read SQL endpoint) | Yes |
| `/api/method/kniterp.kniterp.api.production_wizard.get_production_details` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 339 | `sales_order_item` | `read-only` | Medium (read SQL endpoint) | Yes |
| `/api/method/kniterp.kniterp.api.production_wizard.create_work_order` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 938 | `sales_order, sales_order_item` | `insert` | Medium-High | Yes |
| `/api/method/kniterp.kniterp.api.production_wizard.start_work_order` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 1135 | `work_order, operation_settings` | `save, submit` | Medium-High | Yes |
| `/api/method/kniterp.kniterp.api.production_wizard.create_subcontracting_order` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 1229 | `work_order, operation, supplier, qty, rate` | `insert, submit` | Medium-High | Yes |
| `/api/method/kniterp.kniterp.api.production_wizard.complete_operation` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 1507 | `work_order, operation, qty, workstation, employee` | `db_set, insert, save, submit` | Medium-High | Yes |
| `/api/method/kniterp.kniterp.api.production_wizard.complete_job_card` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 1761 | `job_card, additional_qty, process_loss_qty, wip_warehouse, skip_material_transfer, source_warehouses` | `save, submit` | Medium-High | Yes |
| `/api/method/kniterp.kniterp.api.production_wizard.get_production_logs` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 1846 | `job_card` | `read-only` | Low | Yes |
| `/api/method/kniterp.kniterp.api.production_wizard.revert_production_entry` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 1893 | `stock_entry` | `cancel, db_set, delete_doc, save` | High (bypass flags present) | Yes |
| `/api/method/kniterp.kniterp.api.production_wizard.update_production_entry` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 2038 | `stock_entry, qty, employee, workstation` | `transitive write (calls revert + complete_operation)` | High | Yes |
| `/api/method/kniterp.kniterp.api.production_wizard.receive_subcontracted_goods` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 2079 | `purchase_order, qty, rate, supplier_delivery_note, items, subcontracting_order` | `insert, submit` | Medium-High | Yes |
| `/api/method/kniterp.kniterp.api.production_wizard.create_purchase_orders_for_shortage` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 2148 | `items, supplier, schedule_date, warehouse, submit` | `insert, submit` | Medium-High | Yes |
| `/api/method/kniterp.kniterp.api.production_wizard.transfer_materials_to_subcontractor` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 2231 | `subcontracting_order` | `insert` | Medium-High | Yes |
| `/api/method/kniterp.kniterp.api.production_wizard.get_supplier_list` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 2272 | `-` | `read-only` | Low | No |
| `/api/method/kniterp.kniterp.api.production_wizard.get_status_summary` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 2287 | `-` | `read-only` | Medium (read SQL endpoint) | Yes |
| `/api/method/kniterp.kniterp.api.production_wizard.create_delivery_note` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 2326 | `sales_order, items` | `insert` | Medium-High | Yes |
| `/api/method/kniterp.kniterp.api.production_wizard.get_consolidated_shortages` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 2429 | `filters` | `read-only` | Low | No |
| `/api/method/kniterp.kniterp.api.production_wizard.create_sales_invoice` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 2499 | `sales_order` | `insert` | Medium-High | Yes |
| `/api/method/kniterp.kniterp.api.production_wizard.create_scio_sales_invoice` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 2628 | `sales_order_item` | `insert` | Medium-High | Yes |
| `/api/method/kniterp.kniterp.api.production_wizard.create_subcontracting_inward_order` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 2737 | `sales_order, sales_order_item` | `insert, save` | High (`ignore_permissions=True` path) | Yes |
| `/api/method/kniterp.kniterp.api.production_wizard.get_notes` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 2880 | `sales_order_item` | `read-only` | Low | No |
| `/api/method/kniterp.kniterp.api.production_wizard.add_production_note` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 2899 | `sales_order_item, note` | `insert` | Medium-High | Yes |
| `/api/method/kniterp.kniterp.api.production_wizard.delete_production_note` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 2921 | `note_name` | `delete via document API` | Medium | Yes |
| `/api/method/kniterp.kniterp.api.production_wizard.update_so_item_bom` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 2938 | `sales_order_item, bom_no` | `db.set_value` | Medium-High | Yes |
| `/api/method/kniterp.kniterp.api.production_wizard.get_batch_production_summary` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 2947 | `sales_order_item` | `read-only` | Medium (read SQL endpoint) | Yes |
| `/api/method/kniterp.kniterp.api.production_wizard.complete_job_card` | `function` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 3092 | `job_card` | `db.commit, db_set, save, submit` | High (manual commit in API) | Yes |
| `/api/method/kniterp.kniterp.api.subcontracting.get_subcontract_po_items` | `function` | `frappe-bench/apps/kniterp/kniterp/api/subcontracting.py` | 4 | `sales_order` | `read-only` | Low | Yes |
| `/api/method/kniterp.kniterp.api.subcontracting.make_subcontract_purchase_order` | `function` | `frappe-bench/apps/kniterp/kniterp/api/subcontracting.py` | 31 | `sales_order, supplier, items` | `insert` | Medium-High | Yes |
| `/api/method/kniterp.kniterp.api.textile_attributes.get_textile_attributes_for` | `function` | `frappe-bench/apps/kniterp/kniterp/api/textile_attributes.py` | 4 | `classification` | `read-only` | Medium (read SQL endpoint) | No |
| `/api/method/kniterp.kniterp.api.textile_attributes.get_attribute_values` | `function` | `frappe-bench/apps/kniterp/kniterp/api/textile_attributes.py` | 28 | `attribute` | `read-only` | Medium (read SQL endpoint) | No |
| `/api/method/kniterp.kniterp.kniterp.doctype.machine_attendance_tool.machine_attendance_tool.generate_attendance` | `function` | `frappe-bench/apps/kniterp/kniterp/kniterp/doctype/machine_attendance_tool/machine_attendance_tool.py` | 10 | `date, company, entries` | `transitive write (creates Machine Attendance)` | Medium-High | Yes |
| `/api/method/kniterp.kniterp.kniterp.overrides.job_card.make_subcontracting_po` | `function` | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/job_card.py` | 51 | `source_name, target_doc` | `mapped doc creation` | Medium-High | Yes |
| `/api/method/kniterp.kniterp.kniterp.overrides.job_card.CustomJobCard.make_stock_entry_for_semi_fg_item` | `class_method` | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/job_card.py` | 325 | `self, auto_submit` | `save, submit` | Medium-High | Yes |
| `/api/method/kniterp.kniterp.kniterp.overrides.subcontracting_inward_order.CustomSubcontractingInwardOrder.make_subcontracting_delivery` | `class_method` | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/subcontracting_inward_order.py` | 66 | `self, target_doc` | `returns mapped Stock Entry doc` | Medium | Yes |
| `/api/method/kniterp.kniterp.kniterp.page.kniterp_home.kniterp_home.get_dashboard_metrics` | `function` | `frappe-bench/apps/kniterp/kniterp/kniterp/page/kniterp_home/kniterp_home.py` | 7 | `-` | `read-only` | Low | Yes |

#### 9.2 API collision finding
- `production_wizard.py` defines `complete_job_card` twice: `production_wizard.py:1761` and `production_wizard.py:3092`.
- Effective export: second definition wins in Python module namespace.
- Impact: earlier signature (`additional_qty`, `process_loss_qty`, warehouses, skip flags) is shadowed; UI callers may hit unintended semantics.

### 10) JS Customization Inventory

Hook-included global scripts (loaded on desk):
- `frappe-bench/apps/kniterp/kniterp/public/js/kniterp_item_selector.js` (dialog-driven item selector; server calls at lines `90`, `201`).
- `frappe-bench/apps/kniterp/kniterp/public/js/item_selector_form_botton.js` (injects selector on Sales Order/Purchase Order/Delivery Note forms; lines `86`, `102`, `118`, child-row handlers `198`, `223`).
- `frappe-bench/apps/kniterp/kniterp/public/js/item_client_script.js` (Item form enhancements and awesomplete search; line `1`).
- `frappe-bench/apps/kniterp/kniterp/public/js/sales_order_subcontracting_fix.js` (Sales Order item query filter mutation by `is_subcontracted`; line `16`, hooks line `37`).
- `frappe-bench/apps/kniterp/kniterp/public/js/sales_order.js` (Subcontracted PO creation dialog and API bridge; line `1`, dialog at `31`).

Page controllers:
- `frappe-bench/apps/kniterp/kniterp/kniterp/page/production_wizard/production_wizard.js` (3136 lines; primary orchestrator).
- `frappe-bench/apps/kniterp/kniterp/kniterp/page/action_center/action_center.js` (898 lines; remediation dashboard and bulk actions).
- `frappe-bench/apps/kniterp/kniterp/kniterp/page/bom_designer/bom_designer.js` (1079 lines; BOM generation/edit UI).
- `frappe-bench/apps/kniterp/kniterp/kniterp/page/kniterp_home/kniterp_home.js` (home metrics page).

Doctype JS:
- Active logic in `machine_attendance_tool.js` (form actions + API call at line `93`).
- Minimal/stub/commented scripts for other doctypes.

Dormant/unreferenced artifact:
- `frappe-bench/apps/kniterp/kniterp/public/js/item_selector_dialog copy.js` (legacy selector; not in `app_include_js`).

### 11) Dialog Inventory (workflow impact)
| File | Line | Dialog title/purpose | Workflow impact | Risk |
|---|---:|---|---|---|
| `public/js/kniterp_item_selector.js` | 17 | Select item by attributes | Item master lookup/creation path entrypoint | Medium |
| `public/js/sales_order.js` | 31 | Create subcontracted PO | Sales->Purchase subcontracting bridge | High |
| `page/action_center/action_center.js` | 226 | Fix dialog container | Bulk operational remediation | High |
| `page/action_center/action_center.js` | 644 | Consolidated PO dialog | Creates shortage procurement | High |
| `page/action_center/action_center.js` | 739 | Bulk PI invoice metadata dialog | Purchase invoicing control | Medium |
| `page/production_wizard/production_wizard.js` | 1631 | Start Production | WO/JC startup configuration | High |
| `page/production_wizard/production_wizard.js` | 1755 | Create Subcontracting Order | JC->PO/SCO transition | High |
| `page/production_wizard/production_wizard.js` | 1898 | Receive Subcontracted Goods | SCR creation/submit | High |
| `page/production_wizard/production_wizard.js` | 2105 | Update Manufactured Quantity | Batch completion and stock mutation | High |
| `page/production_wizard/production_wizard.js` | 2191 | Production logs viewer | Operational audit trail interaction | Medium |
| `page/production_wizard/production_wizard.js` | 2283 | Edit production log entry | Revert/recreate production entries | High |
| `page/production_wizard/production_wizard.js` | 2440 | Complete Job Card | Draft->submitted lifecycle transition | High |
| `page/production_wizard/production_wizard.js` | 2541 | PO for shortage / consolidated PO | Material procurement from shortages | High |
| `page/production_wizard/production_wizard.js` | 2866 | Consolidated procurement wizard | Cross-order shortage aggregation | High |
| `page/production_wizard/production_wizard.js` | 3095 | Select supplier | Finalization step for consolidated PO | Medium |
| `public/js/item_selector_dialog copy.js` | 296 | Legacy selector dialog | Dormant alternative flow | Medium |

### 12) ERPNext Workflow Interceptions

Manufacturing / subcontracting:
- Job Card core overridden (`hooks.py:48`, `overrides/job_card.py:160`) including status semantics and stock-entry behavior.
- Work Order core overridden (`hooks.py:50`, `overrides/work_order.py:41`) with custom subcontracting inward validation.
- Subcontracting Inward Order core overridden (`hooks.py:49`, `overrides/subcontracting_inward_order.py:7`).
- Whitelisted method override for subcontracting PO mapping (`hooks.py:54`, `overrides/job_card.py:51`).
- Subcontracting Receipt validation monkey patch (`overrides/subcontracting_receipt.py:21`).
- SRE dashboard function monkey patches (`overrides/sre_dashboard_fix.py:64`, `overrides/sre_dashboard_fix.py:65`).

Stock lifecycle:
- Manual SRE creation/cancellation/adjustment in production flows (`production_wizard.py:1674`, `production_wizard.py:1915`, `production_wizard.py:1967`).
- Direct Bin reservation/projected updates (`production_wizard.py:1713`, `production_wizard.py:1992`).

Payroll / HR:
- Salary Slip `before_save` intercept (`hooks.py:59`, `payroll.py:9`).
- Machine attendance generation tool writes operational attendance records (`machine_attendance_tool.py:10`).

Accounting / buying / selling:
- Action center wrappers create/submit Purchase Invoice (`action_center.py:1138`, `action_center.py:1156`).
- Production wizard creates DN/SI and purchase docs from shortage/subcontracting (`production_wizard.py:2326`, `2499`, `2148`, `2079`).

### 13) Payroll / HR / Stock / Manufacturing Modifications
| Domain | File:line | Modification | Impact | Risk |
|---|---|---|---|---|
| Payroll | `payroll.py:9` | Variable pay recalculation in Salary Slip save cycle. | Net pay changes at save-time. | High |
| Payroll | `payroll.py:29`-`40` | Adds Sunday/Dual Shift/Machine/Conveyance/Tea components and rejected-holiday deduction. | Statutory/payroll correctness sensitivity. | High |
| HR Ops | `machine_attendance_tool.py:10` | API bulk-generates Machine Attendance entries with permission bypass. | Data creation outside standard role checks. | High |
| HR data quality | `machine_attendance.py:11` | Duplicate/operator checks on Machine Attendance doctype. | Prevents invalid ops records. | Medium |
| Manufacturing | `overrides/job_card.py:188` | Disables auto-complete status logic; manual completion required. | Operational behavior divergence from ERPNext. | High |
| Manufacturing | `production_wizard.py:938` | Custom WO creation path with SCIO integration. | Bypasses standard UX; central custom dependency. | High |
| Subcontracting | `production_wizard.py:1229` | Custom PO/SCO creation with partial sequencing checks. | Critical for jobwork flow. | High |
| Stock | `subcontracting.py:100` | Stock Entry submit/cancel hooks recalc transferred qty on JC. | Inventory transfer status consistency. | High |
| Stock reservations | `overrides/sre_dashboard_fix.py:64` | Replaces ERPNext reservation dashboard calculations. | Dashboard correctness but patch fragility. | High |
| Accounting | `action_center.py:1138` | Purchase invoice creation wrapper on action-center flow. | Invoice lifecycle from custom UI. | Medium |

### 14) Fixtures Inventory
| Fixture file | Records | Evidence | Notes / impact | Risk |
|---|---:|---|---|---|
| `fixtures/client_script.json` | 1 | `client_script.json:4` | Item form script "Auto textile attribute validation" (`client_script.json:9`). | High (duplicates logic with static JS) |
| `fixtures/custom_field.json` | 5 | `custom_field.json:15`, `74`, `133`, `192`, `251` | Adds Item/WO/JC custom fields incl. textile attributes and planned output qty. | High |
| `fixtures/property_setter.json` | 18 | starts `property_setter.json:4` | Item naming field behavior, field order, list-view settings for WO/PO/JC. | High (upgrade conflicts) |
| `fixtures/page.json` | 4 | `page.json:9`, `33`, `60`, `90` | Custom pages: bom_designer, production-wizard, kniterp-home, action-center. | Medium |
| `fixtures/workspace_sidebar.json` | 39 | `workspace_sidebar.json:5` | Re-exports large cross-module workspace sidebars (many non-Kniterp modules). | High governance/upgrade risk |
| `fixtures/workspace.json` | 0 | empty file | No workspace records despite fixture hook. | Low |
| `fixtures/designation.json` | 3 | `designation.json:9`, `19`, `29` | Seeds `Master`, `Helper`, `Operator`. | Low |
| `fixtures/item_attribute_applies_to_values.json` | 2 | `...:6`, `...:13` | Seeds Fabric/Yarn applicability values. | Low |
| `fixtures/textile_attribute.json` | 9 | names at `textile_attribute.json:22`...`213` | Textile attribute masters. | Medium |
| `fixtures/textile_attribute_value.json` | 44 | file size 529 lines | Textile attribute values master data. | Medium |

### 15) Custom Reports
- No report files found under app path.
- Evidence:
  - `find frappe-bench/apps/kniterp -type d -name report` => none.
  - `rg --files frappe-bench/apps/kniterp | rg '/report/'` => none.

### 16) Property Setters
Primary fixture property setters (`fixtures/property_setter.json`):
- Item naming/UI changes:
  - `Item-naming_series-reqd` (`property_setter.json:12`) value `0`.
  - `Item-naming_series-hidden` (`property_setter.json:28`) value `1`.
  - `Item-item_code-reqd` (`property_setter.json:60`) value `1`.
  - `Item-main-field_order` (`property_setter.json:124`) large custom field order.
- Work Order list visibility:
  - `production_item` (`property_setter.json:140`), `sales_order` (`156`), `subcontracting_inward_order` (`172`).
- Purchase Order list visibility:
  - `supplier_name` (`188`), `per_billed` (`204`), `per_received` (`220`), `transaction_date` (`236`), `grand_total` (`252`), `is_subcontracted` (`268`).
- Job Card visual tweak:
  - `Job Card-barcode-hidden` (`property_setter.json:284`).

Additional property setters embedded in custom JSON:
- `kniterp/kniterp/custom/item_textile_attribute.json` (`line 6`) includes read-only dependency setters.
- `kniterp/kniterp/custom/work_order.json` (`line 6`) repeats WO list-view setters.
- `kniterp/kniterp/custom/item.json` includes Item naming/property modifications (`item.json:481`, `item.json:504`).

### 17) Client Scripts
- Fixture-managed `Client Script` doctype:
  - `frappe-bench/apps/kniterp/kniterp/fixtures/client_script.json:4` (`dt=Item`, `view=Form`).
- Static desk-included form scripts (functionally client scripts):
  - `item_client_script.js` Item form hooks.
  - `item_selector_form_botton.js` Sales/Purchase/Delivery item-row selector integration.
  - `sales_order_subcontracting_fix.js` Sales Order item query interception.
  - `sales_order.js` subcontracted PO creation dialog.

### 18) Patches / Migration Scripts
- `frappe-bench/apps/kniterp/kniterp/patches.txt` has no patch entries (`patches.txt:1` to `patches.txt:6`).
- Patch-like modules with `execute()` exist but are not registered in `patches.txt`:
  - `frappe-bench/apps/kniterp/kniterp/utils/__init__.py:110`
  - `frappe-bench/apps/kniterp/kniterp/utils/reset_transactions.py:126`
- These modules are destructive transaction reset scripts and represent operational risk if run.

### 19) Naming Logic Overrides
| Naming logic | Evidence | Behavior | ERPNext impact | Risk |
|---|---|---|---|---|
| Item `autoname` override | `overrides/item.py:7` | Fabric/Yarn item names/codes generated from textile attributes; `self.name=self.item_code`. | Yes | High |
| CP suffix naming mutation | `overrides/item.py:16` | Appends ` - CP` for customer-provided item variants. | Yes | High |
| Yarn dual-item creation naming | `overrides/item.py:130` | Ensures base/CP pair and alternatives. | Yes | High |
| Doctype expression naming | `item_attribute_applies_to_values.json:4`, `textile_attribute.json:4`, `textile_attribute_value.json:4` | Expression-based naming for textile masters. | No (custom doctypes) | Medium |
| Property setter naming-series suppression | `property_setter.json:12`, `property_setter.json:28` | Hides/derestricts Item naming_series in favor of code logic. | Yes | High |

### 20) Direct DB Mutation Map (required format)
| operation | doctype/table | function | file | line | bypass_flags | transaction_behavior |
|---|---|---|---|---:|---|---|
| `db.set_value` | `Subcontracting BOM` | `find_or_create_subcontracting_bom` | `frappe-bench/apps/kniterp/kniterp/api/bom_tool.py` | 288 | `-` | implicit in request txn |
| `db_set` | `process_loss_qty` | `complete_operation` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 1551 | `-` | implicit in request txn |
| `db_set` | `reserved_qty_for_production` | `complete_operation` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 1713 | `update_modified=False` | implicit in request txn |
| `db_set` | `projected_qty` | `complete_operation` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 1715 | `update_modified=False` | implicit in request txn |
| `db_set` | `total_completed_qty` | `complete_operation` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 1749 | `-` | implicit in request txn |
| `db_set` | `reserved_qty` | `revert_production_entry` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 1967 | `-` | implicit in request txn |
| `db_set` | `reserved_qty_for_production` | `revert_production_entry` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 1992 | `update_modified=False` | implicit in request txn |
| `db_set` | `projected_qty` | `revert_production_entry` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 1994 | `update_modified=False` | implicit in request txn |
| `delete_doc` | `Job Card Time Log` | `revert_production_entry` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 2014 | `ignore_permissions=True` | implicit in request txn |
| `db_set` | `(dict multi-field)` | `revert_production_entry` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 2020 | `-` | implicit in request txn |
| `db.set_value` | `Sales Order Item` | `update_so_item_bom` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 2942 | `-` | implicit in request txn |
| `db_set` | `status` | `complete_job_card` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 3101 | `-` | implicit in request txn |
| `db.commit` | `-` | `complete_job_card` | `frappe-bench/apps/kniterp/kniterp/api/production_wizard.py` | 3141 | `-` | manual commit |
| `db.set_value` | `Item` | `CustomItem.ensure_dual_yarn_versions` | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/item.py` | 140 | `-` | implicit in request txn |
| `db_set` | `status` | `CustomJobCard.set_status` | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/job_card.py` | 226 | `-` | implicit in request txn |
| `db_set` | `manufactured_qty` | `CustomJobCard.set_manufactured_qty` | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/job_card.py` | 254 | `-` | implicit in request txn |
| `db.set_value` | `Job Card` | `CustomJobCard.update_subsequent_operations` | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/job_card.py` | 492 | `-` | implicit in request txn |
| `db_set` | `manufactured_qty` | `on_submit_complete_job_cards` | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/subcontracting_receipt.py` | 66 | `update_modified=False` | implicit in request txn |
| `db_set` | `status` | `on_submit_complete_job_cards` | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/subcontracting_receipt.py` | 74 | `update_modified=False` | implicit in request txn |
| `db.set_value` | `Job Card Item` | `_update_job_card_consumed_qty` | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/subcontracting_receipt.py` | 116 | `-` | implicit in request txn |
| `db.commit` | `-` | `_check_and_complete_work_order` | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/subcontracting_receipt.py` | 129 | `-` | manual commit |
| `db.set_value` | `Work Order Operation` | `set_planned_qty_on_work_order` | `frappe-bench/apps/kniterp/kniterp/kniterp/overrides/work_order.py` | 188 | `-` | implicit in request txn |
| `db.set_value` | `Work Order Operation` | `update_work_order_from_job_card` | `frappe-bench/apps/kniterp/kniterp/subcontracting.py` | 13 | `-` | implicit in request txn |
| `db.set_value` | `Work Order Operation` | `update_work_order_from_job_card` | `frappe-bench/apps/kniterp/kniterp/subcontracting.py` | 26 | `-` | implicit in request txn |
| `db_set` | `status` | `complete_job_card_from_po_item` | `frappe-bench/apps/kniterp/kniterp/subcontracting.py` | 68 | `update_modified=False` | implicit in request txn |
| `db_set` | `manufactured_qty` | `complete_job_card_from_po_item` | `frappe-bench/apps/kniterp/kniterp/subcontracting.py` | 71 | `update_modified=False` | implicit in request txn |
| `db.set_value` | `Job Card Item` | `update_job_card_transferred_qty` | `frappe-bench/apps/kniterp/kniterp/subcontracting.py` | 170 | `-` | implicit in request txn |
| `db_set` | `transferred_qty` | `update_job_card_transferred_qty` | `frappe-bench/apps/kniterp/kniterp/subcontracting.py` | 178 | `update_modified=False` | implicit in request txn |
| `db_set` | `status` | `update_job_card_transferred_qty` | `frappe-bench/apps/kniterp/kniterp/subcontracting.py` | 193 | `update_modified=False` | implicit in request txn |
| `db.delete` | `(var dt)` | `clear_all_transactions` | `frappe-bench/apps/kniterp/kniterp/utils/__init__.py` | 23 | `-` | implicit in request txn |
| `db.sql(DML)` | `DELETE FROM tabStock Entry Detail` | `clear_all_transactions` | `frappe-bench/apps/kniterp/kniterp/utils/__init__.py` | 25 | `-` | implicit in request txn |
| `db.commit` | `-` | `clear_all_transactions` | `frappe-bench/apps/kniterp/kniterp/utils/__init__.py` | 28 | `-` | manual commit |
| `db.sql(DML)` | `UPDATE tabJob Card ...` | `clear_all_transactions` | `frappe-bench/apps/kniterp/kniterp/utils/__init__.py` | 33 | `-` | implicit in request txn |
| `db.sql(DML)` | `UPDATE tabWork Order ...` | `clear_all_transactions` | `frappe-bench/apps/kniterp/kniterp/utils/__init__.py` | 34 | `-` | implicit in request txn |
| `db.sql(DML)` | `UPDATE tabPurchase Order Item ...` | `clear_all_transactions` | `frappe-bench/apps/kniterp/kniterp/utils/__init__.py` | 35 | `-` | implicit in request txn |
| `db.commit` | `-` | `clear_all_transactions` | `frappe-bench/apps/kniterp/kniterp/utils/__init__.py` | 36 | `-` | manual commit |
| `delete_doc` | `(var dt,name)` | `clear_all_transactions` | `frappe-bench/apps/kniterp/kniterp/utils/__init__.py` | 90 | `-` | implicit in request txn |
| `db.delete` | `(var dt)` | `clear_all_transactions` | `frappe-bench/apps/kniterp/kniterp/utils/__init__.py` | 102 | `-` | implicit in request txn |
| `db.commit` | `-` | `clear_all_transactions` | `frappe-bench/apps/kniterp/kniterp/utils/__init__.py` | 106 | `-` | manual commit |
| `db.delete` | `(var dt)` | `clear_all_transactions` | `frappe-bench/apps/kniterp/kniterp/utils/reset_transactions.py` | 23 | `-` | implicit in request txn |
| `db.sql(DML)` | `DELETE FROM tabStock Entry Detail` | `clear_all_transactions` | `frappe-bench/apps/kniterp/kniterp/utils/reset_transactions.py` | 25 | `-` | implicit in request txn |
| `db.commit` | `-` | `clear_all_transactions` | `frappe-bench/apps/kniterp/kniterp/utils/reset_transactions.py` | 28 | `-` | manual commit |
| `db.sql(DML)` | `UPDATE tabJob Card ...` | `clear_all_transactions` | `frappe-bench/apps/kniterp/kniterp/utils/reset_transactions.py` | 33 | `-` | implicit in request txn |
| `db.sql(DML)` | `UPDATE tabWork Order ...` | `clear_all_transactions` | `frappe-bench/apps/kniterp/kniterp/utils/reset_transactions.py` | 34 | `-` | implicit in request txn |
| `db.sql(DML)` | `UPDATE tabPurchase Order Item ...` | `clear_all_transactions` | `frappe-bench/apps/kniterp/kniterp/utils/reset_transactions.py` | 35 | `-` | implicit in request txn |
| `db.commit` | `-` | `clear_all_transactions` | `frappe-bench/apps/kniterp/kniterp/utils/reset_transactions.py` | 36 | `-` | manual commit |
| `delete_doc` | `(var dt,name)` | `clear_all_transactions` | `frappe-bench/apps/kniterp/kniterp/utils/reset_transactions.py` | 91 | `-` | implicit in request txn |
| `db.delete` | `(var dt)` | `clear_all_transactions` | `frappe-bench/apps/kniterp/kniterp/utils/reset_transactions.py` | 103 | `-` | implicit in request txn |
| `db.commit` | `-` | `clear_all_transactions` | `frappe-bench/apps/kniterp/kniterp/utils/reset_transactions.py` | 107 | `-` | manual commit |
| `db.commit` | `-` | `clear_all_transactions` | `frappe-bench/apps/kniterp/kniterp/utils/reset_transactions.py` | 122 | `-` | manual commit |

### 21) Validation Bypass Inventory
Explicit bypass flags and validation short-circuits:

Bypass flags:
- `ignore_mandatory`:
  - `production_wizard.py:1125`, `1372`, `1391`, `1612`
  - `overrides/job_card.py:374`
- `ignore_validate`:
  - `production_wizard.py:1126`, `1216`, `1218`
- `ignore_permissions=True`:
  - `production_wizard.py:2014`, `2810`, `2819`, `2876`
  - `overrides/item.py:218`, `228`
  - `machine_attendance_tool.py:43`
  - `api/bom_tool.py:221`, `325`, `460`

Validation bypass patterns (logic-level):
- Subcontracted JC validation suppression:
  - `CustomJobCard.validate_time_logs` early return (`overrides/job_card.py:292`).
  - `CustomJobCard.validate_transfer_qty` early return (`overrides/job_card.py:302`).
  - `CustomJobCard.validate_job_card` early return (`overrides/job_card.py:313`).
- Direct status and qty mutations with `db_set` on transactional docs (Sections 20, 12).
- Forced manual commit inside request handlers (`production_wizard.py:3141`, `subcontracting_receipt.py:129`).

---

## Phase 3: Critical Analysis (4 perspectives)

### 1) Frappe Framework Expert
Critical findings:
1. Duplicate exported function collision in `production_wizard.py` (`1761` and `3092`) shadows intended API contract.
2. Runtime monkey patching of ERPNext internals (`subcontracting_receipt.py:21`, `sre_dashboard_fix.py:64`) is fragile across minor upgrades.
3. Import-time patch activation in package `__init__` (`kniterp/__init__.py:4`) reduces control and makes app load order significant.
4. Heavy override footprint on core doctypes (Item, Job Card, Work Order, SIO) materially increases merge conflict and cross-app incompatibility risk.
5. Utility reset scripts in regular module namespace (`utils/__init__.py`, `utils/reset_transactions.py`) are dangerous if invoked accidentally.

Maintainability concerns:
- Monolithic files: `production_wizard.py` 3151 lines, `production_wizard.js` 3136 lines.
- Business logic duplicated between API and UI-layer assumptions.
- Mixed approaches (standard APIs + direct `db_set` + monkey patches) create inconsistent invariants.

### 2) ERPNext Manufacturing Consultant (textile context)
- Item strategy is strong in intent (attribute-driven naming and CP/base dual yarn creation), but lacks centralized SKU governance guardrails for 10k-100k combinations.
- BOM strategy (Phase A + Master + Subcontracting BOM) is powerful but operationally complex; SC BOM deactivation logic (`bom_tool.py:288`) can impact concurrent SOs.
- Subcontracting integration is deeply customized and likely business-critical; SCIO/SCO/PO/JC/WO coupling is high and brittle under edge cases.
- Job Card status model intentionally diverges from ERPNext auto-completion, improving manual control but requiring strict SOP discipline.
- Naming convention and property-setter customization suit textile UX, but dependency on generated code patterns risks duplicate semantics if attributes drift.

### 3) Performance Engineer
Primary hotspots:
1. `get_consolidated_shortages` calls `get_production_details` per pending item (`production_wizard.py:2442` to `2450`): classic N+1 explosion.
2. `get_production_details` itself runs many nested queries per BOM item and operation (`production_wizard.py:530`, `557`, `712`, `738`, `748`, `763`).
3. Action Center fix-detail builders re-query inside loops (`action_center.py` multiple SQL callsites).
4. Dynamic SQL with interpolated clauses (`production_wizard.py:111`, `218`) and f-string SQL (`subcontracting.py:157`) increases plan instability and review complexity.
5. UI endpoints perform heavy synchronous operations without caching/pagination, risky at large SKU/order volumes.

100k SKU readiness assessment:
- Current implementation is not ready without query consolidation, async jobs, caching, and index validation for high-frequency filters.

### 4) Product & Business Architect (textile factory)
- UX positives: single-pane production wizard, action center operational queue, BOM designer flow.
- UX risks: critical operations (WO/SCO/SCR/DN/SI/stock reversals) concentrated in custom pages with broad mutation permissions.
- Duplicate SKU risk: naming-by-attributes is deterministic but uniqueness governance is fragmented across client script, overrides, and fixtures.
- Data governance risk: large fixture exports (`workspace_sidebar.json`) and property setters widen blast radius during migration.
- Operational risk: manual override paths (`db_set`, forced status writes, manual commits) can mask process exceptions and make reconciliation harder.

---

## Phase 4: Risk Audit

### Technical Risks
1. Critical: API collision (`production_wizard.py:1761`, `production_wizard.py:3092`) causes behavior ambiguity.
2. High: deep override + monkey patch stack (`hooks.py:46`, `subcontracting_receipt.py:21`, `sre_dashboard_fix.py:64`).
3. High: huge monolithic modules hinder testability and safe change windows.

### Performance Risks
1. High: nested query chains in `get_production_details` and `get_consolidated_shortages`.
2. High: action-center bulk operations with per-row blocking calls (`action_center.js` `async:false` loops around lines `718`, `776`, `840`, `872`).
3. Medium: repeated `frappe.get_doc` inside loops across production flow.

### Upgrade Risks
1. Critical: runtime monkey patches against ERPNext internals.
2. High: override of core methods and doctype classes across manufacturing/subcontracting.
3. High: property setters and workspace sidebar fixtures override standard UX metadata and may conflict on migrate.

### Data Integrity Risks
1. Critical: direct status/qty `db_set` on transactional records bypasses full validation/state machine.
2. Critical: manual commits inside business APIs (`production_wizard.py:3141`, `subcontracting_receipt.py:129`).
3. High: destructive reset scripts in app module path with broad DML.

### Security Risks
1. High: many write-capable whitelisted endpoints with no explicit role/permission checks in function body.
2. High: `ignore_permissions=True` use in write paths (`production_wizard.py:2014`, `2810`, `2819`, `2876`; item/bom/machine attendance insert paths).
3. Medium: broad mutation surface exposed via custom pages and client-side orchestration.

### Business Risks
1. High: wrong endpoint resolution (duplicate `complete_job_card`) can break production closing behavior.
2. High: stock reservation inconsistencies can directly impact dispatch and subcontracting settlements.
3. High: payroll component recalculation on save without isolated audit trail risks payroll disputes.

---

## Phase 5: Roadmap

### P0 (Critical fixes)
1. Remove duplicate `complete_job_card` definition and version API explicitly (`production_wizard.py:1761`, `3092`).
2. Eliminate manual commits from request handlers (`production_wizard.py:3141`, `subcontracting_receipt.py:129`); rely on request transaction boundaries.
3. Add explicit permission/role checks on all write APIs (WO/PO/SCO/SCR/DN/SI/SO field update endpoints).
4. Gate or remove destructive reset utilities from runtime import path; move to private admin scripts.
5. Add regression tests for overridden Job Card/Work Order/Subcontracting lifecycles.

### P1 (Important improvements)
1. Replace monkey patches with extension points where possible; if unavoidable, wrap with version guards and fail-safe logging.
2. Consolidate stock reservation mutation logic into a single service layer to avoid dual updates and drift.
3. Harden `update_so_item_bom` and other direct mutation endpoints with workflow-state guards.
4. Add audit logging for manual completion/revert operations.

### P2 (Structural refactor)
1. Split `production_wizard.py` into domain services: planning, execution, subcontracting, invoicing, note management.
2. Split `production_wizard.js` into modular controllers/components and typed API client wrapper.
3. Refactor SQL-heavy flows to repository/query layer with centralized pagination and caching.
4. Reduce override surface by moving behavior to explicit custom actions/hooks where feasible.

### P3 (Long-term scalability)
1. Introduce async job queue for heavy aggregation (`get_consolidated_shortages`, action center summaries).
2. Add observability: structured event logs, endpoint timings, SQL latency and cardinality dashboards.
3. Implement SKU governance service for attribute canonicalization and duplicate-prevention at source.
4. Add performance test suite with realistic textile SKU/order scales (10k-100k).

---

## Acceptance Criteria Check
1. Coverage gate: passed (all 1-21 categories present; `none` explicitly called where applicable).
2. Traceability gate: passed (findings include `file:line` references throughout).
3. Hook/API gate: passed (all hooks and whitelisted APIs cataloged and caller paths mapped).
4. Mutation gate: passed (direct DB mutation map + bypass flags + transaction behavior documented).
5. Diagram gate: see `KNITERP_ARCHITECTURE_REVIEW.md` (8 Mermaid diagrams provided).
6. Analysis gate: passed (4 expert lenses + concrete evidence).
7. Roadmap gate: passed (P0-P3 prioritized and tied to findings).

## Assumptions and Limits
- Static analysis only; no runtime DB profiling, no live data validation.
- Cross-app conflict assessment is inferred from ERPNext/Frappe touchpoints referenced by this app.
- Some permission implications depend on role assignment and desk route access configuration at deployment time.
