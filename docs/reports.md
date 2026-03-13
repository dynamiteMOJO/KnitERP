# KnitERP Custom Reports -- Technical Reference

> Two Script Reports ship with KnitERP: **Subcontracted Batch Traceability** (lot/batch
> provenance across manufacturing and subcontracting) and **Monthly Salary Register**
> (per-employee payroll breakdown for a given month). Both are standard Frappe Script
> Reports under the `Kniterp` module.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Subcontracted Batch Traceability](#2-subcontracted-batch-traceability)
   - [Purpose](#21-purpose)
   - [Report Type and Access](#22-report-type-and-access)
   - [Filters](#23-filters)
   - [Columns](#24-columns)
   - [Data Sources](#25-data-sources)
   - [Key Logic](#26-key-logic)
   - [Performance Considerations](#27-performance-considerations)
3. [Monthly Salary Register](#3-monthly-salary-register)
   - [Purpose](#31-purpose)
   - [Report Type and Access](#32-report-type-and-access)
   - [Filters](#33-filters)
   - [Columns](#34-columns)
   - [Data Sources](#35-data-sources)
   - [Key Logic](#36-key-logic)
   - [Performance Considerations](#37-performance-considerations)
4. [Integration Points](#4-integration-points)
5. [File Reference Index](#5-file-reference-index)

---

## 1. Overview

| Report | Ref DocType | Type | LOC (py + js) | Primary Use Case |
|--------|-------------|------|---------------|-----------------|
| Subcontracted Batch Traceability | Batch | Script Report | ~656 + 113 | Trace a batch/serial backward to raw materials or forward to finished goods and delivery |
| Monthly Salary Register | Salary Slip | Script Report | ~261 + 114 | Monthly payroll register with attendance, variable pay components, and payable salary per employee |

Both reports define columns dynamically in Python (the JSON definition has `"columns": []`) and use the `execute(filters)` entry point pattern standard for Frappe Script Reports.

---

## 2. Subcontracted Batch Traceability

### 2.1 Purpose

Answers: **"Where did this batch/serial come from, and where did it go?"**

In KnitERP's textile manufacturing pipeline, raw materials (yarn batches) flow through in-house manufacturing (Stock Entries of type Manufacture/Repack) and subcontracted operations (Subcontracting Receipts). This report lets users trace:

- **Backward**: from a finished-goods batch back through every manufacturing step to the original raw material batches, including supplier information on Purchase Receipts.
- **Forward**: from a raw material batch forward through manufacturing and subcontracting to finished goods and delivery, including customer information on Delivery Notes.
- **Both**: a combined view showing the full provenance chain in both directions.

The output is a hierarchical (indented) tree structure where each level represents one manufacturing/subcontracting stage, with raw materials nested under their finished-good parent rows.

### 2.2 Report Type and Access

- **Type**: Script Report (`is_standard: "Yes"`)
- **Module**: Kniterp
- **Route**: `/app/query-report/Subcontracted Batch Traceability`
- **Roles**: No explicit role restrictions in the report JSON (`"roles": []`). Access governed by standard Frappe report permissions and read access to the Batch doctype.
- **`add_total_row`**: `0` (no totals row -- data is hierarchical, totals would be meaningless)

### 2.3 Filters

Defined in the JS file (`subcontracted_batch_traceability.js:5-57`):

| Filter | Fieldtype | Options | Required | Default | Notes |
|--------|-----------|---------|----------|---------|-------|
| `item_code` | Link | Item | No | -- | Uses ERPNext's `serial_and_batch_bundle.item_query` to filter only batch/serial tracked items. When set, constrains the Batch/Serial No filter suggestions. |
| `batches` | MultiSelectList | Batch | No | -- | Multi-select batch filter. If `item_code` is set, suggestions are filtered to batches belonging to that item. Only enabled (non-disabled) batches shown. |
| `serial_nos` | MultiSelectList | Serial No | No | -- | Multi-select serial number filter. If `item_code` is set, suggestions are filtered to serial numbers of that item. |
| `traceability_direction` | Select | Backward / Forward / Both | No | Backward | Controls which tracing algorithm runs. |

**Validation** (Python, `ReportData.validate_filters`, line 43): At least one of `item_code`, `batches`, or `serial_nos` must be provided, otherwise the report returns empty.

### 2.4 Columns

Columns are generated dynamically based on the data (`get_columns`, line 525). The presence of Serial No and Batch No columns depends on whether the result data contains serial/batch values (`check_has_serial_no_in_data`, line 22).

**Base columns (always present):**

| Fieldname | Label | Fieldtype | Width |
|-----------|-------|-----------|-------|
| `item_code` | Item Code | Link (Item) | 180 |
| `item_name` | Item Name | Data | 120 |
| `qty` | Quantity | Float | 90 |
| `reference_doctype` | Voucher Type | Data | 130 |
| `reference_name` | Source Document No | Dynamic Link | 200 |
| `warehouse` | Warehouse | Link (Warehouse) | 120 |
| `posting_datetime` | Posting Datetime | Datetime | 120 |
| `work_order` | Work Order | Link (Work Order) | 160 |

**Conditional columns:**

| Condition | Fieldname | Label | Fieldtype | Width |
|-----------|-----------|-------|-----------|-------|
| Data contains serial numbers | `serial_no` | Serial No | Link (Serial No) | 120 |
| Data contains batch numbers | `batch_no` | Batch No | Link (Batch) | 120 |
| Data contains batch numbers | `batch_expiry_date` | Batch Expiry Date | Date | 150 |
| Direction = Backward | `supplier` | Supplier | Link (Supplier) | 150 |
| Direction != Backward | `customer` | Customer | Link (Customer) | 150 |
| Data contains serial numbers | `warranty_expiry_date` | Warranty Expiry (Serial) | Date | 200 |
| Data contains serial numbers | `amc_expiry_date` | AMC Expiry (Serial) | Date | 160 |

**Row-level `indent` field**: Each row carries an `indent` value (0, 1, 2, ...) that Frappe's DataTable renders as a tree. Finished goods are at indent 0; their consumed raw materials at indent 1; and so on recursively.

**Empty separator rows**: Between top-level (indent 0) batch entries, the report inserts an empty dict `{}` to create visual separation in the DataTable.

### 2.5 Data Sources

The report reads from the following tables via `frappe.qb` (Query Builder):

| Table | Alias | Purpose |
|-------|-------|---------|
| `tabBatch` | `doctype` (when tracing batches) | Starting point -- batch metadata, `reference_doctype`, `reference_name` |
| `tabSerial No` | `doctype` (when tracing serials) | Starting point -- serial metadata |
| `tabSerial and Batch Bundle` | `SABB` / `sabb` | Links vouchers to their batch/serial entries; filtered by `is_cancelled=0` |
| `tabSerial and Batch Entry` | `SABE` / `sabb_entry` | Individual batch/serial line items within a bundle; filtered by `docstatus=1` |
| `tabStock Entry` | `stock_entry` | Manufacturing/Repack stock entries (source materials) |
| `tabStock Entry Detail` | `stock_entry_detail` | Line items in stock entries; `s_warehouse` = source, `t_warehouse` = target |
| `tabSubcontracting Receipt` | `scr` | Subcontracting receipts (finished goods from subcontractors) |
| `tabSubcontracting Receipt Item` | -- | FG items received via subcontracting |
| `tabSubcontracting Receipt Supplied Item` | `scr_item` | Raw materials consumed in subcontracting |
| `tabPurchase Receipt` | -- | Supplier lookup for backward tracing |
| `tabDelivery Note` | -- | Customer lookup for forward tracing |

**Doctype auto-detection** (`get_doctype`, line 264): If `item_code` is set, the report checks `has_serial_no` / `has_batch_no` on the Item to decide whether to query `Serial No` or `Batch`. If only `serial_nos` filter is provided, it defaults to `Serial No`. Otherwise defaults to `Batch`.

### 2.6 Key Logic

The report is implemented as the `ReportData` class (line 38). The core architecture splits into two independent algorithms depending on the traceability direction.

#### 2.6.1 Entry Point: `get_data()` (line 48)

```
get_data()
  |-- if Backward or Both:
  |     get_serial_no_batches()       # fetch starting batches/serials from filters
  |     prepare_source_data()          # build dict keyed by (item, ref_name, value)
  |     for each source entry:
  |       set_backward_data()          # recursive: find consumed raw materials
  |     parse_batch_details()          # flatten tree into indented row list
  |
  |-- if Forward or Both:
        get_serial_no_batches()
        for each batch/serial:
          set_forward_data()           # find all outward movements
        parse_batch_details()
```

#### 2.6.2 Backward Tracing

**Goal**: Given a batch (typically finished goods), find what raw materials were consumed to produce it.

1. **`get_serial_no_batches()`** (line 221): Queries the `Batch` or `Serial No` doctype using filter values. Returns the batch's `reference_doctype` and `reference_name` (the voucher that created it).

2. **`prepare_source_data()`** (line 133): For each batch, calls `get_data_from_sabb()` to join against `Serial and Batch Bundle` + `Serial and Batch Entry` to get qty, warehouse, and posting_datetime. Builds a dict keyed by `(item_code, reference_name, batch_or_serial)`.

3. **`set_backward_data()`** (line 180): The recursive core. For each source entry:
   - Calls `get_materials()` to find consumed items.
   - For Stock Entries (Manufacture/Repack): queries `Stock Entry Detail` joined with `Serial and Batch Entry`, filtering for source-warehouse rows (`s_warehouse IS NOT NULL`). Computes proportional qty as `(detail.qty / fg_completed_qty) * sabb_data.qty`.
   - For Subcontracting Receipts: queries `Subcontracting Receipt Supplied Item` joined with `Serial and Batch Entry`. Computes proportional qty as `(consumed_qty / total_qty) * sabb_data.qty`.
   - For each consumed material that itself has a batch/serial: recursively calls `set_backward_data()` to trace further upstream.
   - Materials without batch/serial are added as leaf nodes with just item_code, item_name, qty, warehouse.

4. **`parse_batch_details()`** (line 80): Recursively flattens the nested `raw_materials` tree into a flat list with `indent` levels. Also enriches each row with contextual data (supplier from Purchase Receipt, work_order from Stock Entry, customer from Delivery Note).

#### 2.6.3 Forward Tracing

**Goal**: Given a batch (typically raw material), find what finished goods were produced from it.

1. **`get_serial_no_batches()`**: Same starting query as backward.

2. **`set_forward_data()`** (line 374): For each batch/serial value, calls `get_sabb_entries()` to find all Outward `Serial and Batch Bundle` entries referencing this value. Then dispatches by voucher type:
   - **Stock Entry** -> `process_manufacture_or_repack_entry()` (line 425): Looks up the SE's purpose. If Manufacture/Repack, finds the finished item via `get_finished_item_from_stock_entry()` (line 499, queries `Stock Entry Detail` where `is_finished_item=1`). Gets the FG's batch/serial via `get_serial_batch_no()`. Builds the FG as a top-level entry with the consumed RM as a nested child.
   - **Subcontracting Receipt** -> `process_subcontracting_receipt_entry()` (line 456): Finds the FG via `get_finished_item_from_subcontracting_receipt()` (line 483, queries `Subcontracting Receipt Item`). Same pattern as above.
   - **Other voucher types** (Delivery Note, Purchase Receipt, etc.) -> `add_direct_outward_entry()` (line 385): Added as flat top-level entries.

3. **`parse_batch_details()`**: Same recursive flattening as backward, but forward rows with positive qty get their `direction` flipped to "Backward" for CSS coloring purposes (line 103-104).

#### 2.6.4 SABB Entry Lookup: `get_sabb_entries()` (line 391)

Central query used by forward tracing. Joins `Serial and Batch Bundle` with `Serial and Batch Entry`, filtering by:
- `is_cancelled = 0`
- `docstatus = 1`
- `type_of_transaction` (default "Outward", can be "Inward" for backward fallback)
- Matches on `serial_no` or `batch_no` value

Ordered by `posting_datetime` to maintain chronological sequence.

#### 2.6.5 JS Formatter (line 59-112)

The JS formatter adds colored hyperlinks to batch/serial columns:
- Batches/serials that are in the user's filter list AND match the item_code get colored by direction: green (`text-success`) for Backward, red (`text-danger`) for Forward.
- All values link to their respective `/app/batch/` or `/app/serial-no/` detail pages.
- The `qty` cell is blanked for separator rows (where `item_code` is empty).

### 2.7 Performance Considerations

**Recursive N+1 pattern**: The backward algorithm is inherently recursive. For each batch in the trace, `set_backward_data()` may issue multiple queries:
- 1 call to `get_materials()` (1 SQL query)
- For each consumed material with a batch: 1 call to `get_serial_no_batches()` + 1 call to `get_data_from_sabb()` + recursive `set_backward_data()`
- Fallback: if `get_serial_no_batches()` returns nothing, tries `get_sabb_entries()` as well

For a 3-level BOM (yarn -> knitted fabric -> dyed fabric), tracing one batch could issue 10-20+ queries. Tracing multiple batches multiplies linearly.

**Forward tracing**: `get_sabb_entries()` runs once per starting batch. Then for each outward entry, `process_manufacture_or_repack_entry()` or `process_subcontracting_receipt_entry()` each issue 2-3 queries (SE lookup, FG item lookup, SABB serial/batch lookup). Shallower than backward but still O(movements * queries_per_movement).

**No caching**: Results are computed fresh on every run. No `prepared_report` flag is set.

**Mitigation**: The report requires at least one filter (item_code, batches, or serial_nos), which bounds the starting set. In practice, users trace specific batches, not unbounded sets.

---

## 3. Monthly Salary Register

### 3.1 Purpose

Answers: **"What is each employee's payroll breakdown for this month?"**

Produces a tabular register showing, for every active employee: attendance counts (present, absent, half day, overtime, leave), variable pay components (Sunday pay, dual shift, machine extra, tea allowance, conveyance), rejected holiday deductions, and the final payable salary. When a Salary Slip exists for the period, actual slip values are used; otherwise, the report computes estimated values from attendance and Salary Structure Assignment data.

### 3.2 Report Type and Access

- **Type**: Script Report (`is_standard: "Yes"`)
- **Module**: Kniterp
- **Route**: `/app/query-report/Monthly Salary Register`
- **Ref DocType**: Salary Slip
- **Roles**: No explicit role restrictions in the report JSON (`"roles": []`).
- **`add_total_row`**: `1` (Frappe auto-adds a totals row for numeric columns)

### 3.3 Filters

Defined in the JS file (`monthly_salary_register.js:79-113`):

| Filter | Fieldtype | Options | Required | Default | Notes |
|--------|-----------|---------|----------|---------|-------|
| `year` | Select | Current year down to current-3 | Yes | Current year | Dynamic option list generated at load time |
| `month` | Select | January through December | Yes | Previous month | Defaults to previous month (wraps Dec for Jan) |
| `employee` | Link | Employee | No | -- | Filter to a single employee |

### 3.4 Columns

Defined in `get_columns()` (line 233). Fixed set of 21 columns:

| Fieldname | Label | Fieldtype | Width | Notes |
|-----------|-------|-----------|-------|-------|
| `employee` | Employee | Link (Employee) | 100 | Sticky column (see JS) |
| `employee_name` | Name | Data | 120 | Sticky column (see JS) |
| `absence` | Absence | Int | 70 | Count of Absent attendance records |
| `presence` | Presence | Int | 75 | Count of Present attendance records |
| `overtime` | Over Time | Int | 75 | Dual-shift days (2+ attendance records same day) |
| `half_day` | Half Day | Int | 75 | Count of Half Day attendance records |
| `sunday_rejected` | Sunday Rejected | Int | 80 | Holidays rejected due to adjacent absences |
| `paid_leave` | Paid Leave | Int | 75 | Count of On Leave attendance records |
| `festival` | Festival | Int | 70 | Non-Sunday holidays in the period |
| `days_in_month` | Days In Month | Int | 70 | Calendar days in selected month |
| `sunday_pay` | Sunday Pay | Float (precision 1) | 80 | Count of Sundays worked (0.5 for Half Day) |
| `double_mc` | Double M/C | Int | 80 | Extra machine count (machines beyond first) |
| `double_mc_amt` | Double M/C Amt | Currency | 95 | Machine extra pay amount (count * 150) |
| `tea` | Tea | Currency | 80 | Tea Allowance amount |
| `km` | Km | Float | 60 | Total conveyance kilometers |
| `conveyance` | Conv. | Currency | 80 | Conveyance allowance amount |
| `payable_days` | Payable Days | Float (precision 1) | 80 | Days eligible for payment |
| `basic_salary` | Basic Salary | Currency | 95 | Base from Salary Structure Assignment |
| `per_day_salary` | Per Day Salary | Currency | 95 | `base / days_in_month` (integer division) |
| `payable_salary` | Payable Salary | Currency | 110 | Final net pay (from slip or computed) |
| `salary_slip` | Salary Slip | Link (Salary Slip) | 120 | Link to actual slip if it exists |

**Sticky columns (JS)**: The JS file (`monthly_salary_register.js:1-78`) injects CSS and scroll event handling in `after_datatable_render` to make the Employee and Name columns sticky (frozen) during horizontal scrolling. Uses `position: sticky` with z-index layering and alternating row background colors for readability.

### 3.5 Data Sources

| Table / DocType | Query Function | Purpose |
|-----------------|---------------|---------|
| `tabEmployee` | `get_employees()` (line 118) | Active employees, optionally filtered by employee ID |
| `tabAttendance` | `get_attendance_summary()` (line 131) | Attendance counts grouped by employee and status (Present, Absent, Half Day, On Leave) |
| `tabSalary Slip` | `get_salary_slip_data()` (line 147) | Existing salary slips for the period (docstatus 0 or 1) |
| `tabSalary Detail` | within `get_salary_slip_data()` (line 167) | Earnings breakdown from salary slip (for Tea Allowance extraction) |
| `tabSalary Structure Assignment` | `get_ssa_data()` (line 178) | Latest `base` and `variable` amounts per employee effective on or before the period start |
| `tabHoliday` | `get_holiday_count_map()` (line 194), `get_festival_count()` (line 209) | Holiday counts and non-Sunday holiday identification |
| `tabAttendance` | via `payroll.get_sunday_pay()` | Sunday attendance (Present/Half Day on weekday=6) |
| `tabAttendance` | via `payroll.get_dual_shift_days()` | Days with 2+ Present attendance records |
| `tabMachine Attendance` | via `payroll.get_machine_extra_pay()` | Days with 2+ machine attendance records (production_qty_kg > 30) |
| `tabMonthly Conveyance` | via `payroll.get_conveyance()` | Monthly conveyance amount and kilometers |
| `tabAttendance` + `tabHoliday` | via `payroll.get_rejected_holiday_days()` | Holidays where employee was absent both the day before and after |

### 3.6 Key Logic

#### 3.6.1 Entry Point: `execute(filters)` (line 23)

```
execute(filters)
  |-- Parse year/month into start_date and end_date
  |-- get_employees(filters)           # all active, or filtered by employee
  |-- Bulk-fetch data:
  |     get_attendance_summary()        # 1 SQL: grouped by employee+status
  |     get_salary_slip_data()          # ORM + per-slip earnings query
  |     get_ssa_data()                  # 1 SQL: latest SSA per employee
  |     get_holiday_count_map()         # 1 query per employee (N+1)
  |-- For each employee:
  |     Call 5 payroll helper functions (per-employee queries)
  |     get_festival_count()            # 1 query per employee
  |     Build row dict
  |-- Return columns + data
```

#### 3.6.2 Two Computation Paths

For each employee, the report checks whether a Salary Slip exists for the period:

**Path A -- Salary Slip exists** (`has_slip = True`, line 68):
- `payable_days` = `ss.payment_days` (from the slip)
- `tea` = extracted from slip's earnings via `get_component_value(ss, "Tea Allowance")`
- `payable_salary` = `ss.net_pay`
- `per_day_salary` = `ss.custom_per_day_salary` (set by payroll hook) or fallback to `base / days_in_month`

**Path B -- No Salary Slip** (`has_slip = False`, line 74):
- `payable_days` = `days_in_month - absent_days - rejected_holiday_days`
- `tea` = `min(tea_days * (variable / days_in_month), variable)` where `tea_days = payable_days - rejected`
- `payable_salary` is computed as:

```
payable_salary = per_day_salary * payable_days
               + sunday_pays * per_day_salary
               + dual_shifts * per_day_salary
               + machine_pay
               + conveyance_amt
               + tea
               - rejected * per_day_salary
```

This mirrors the logic in `payroll.py:calculate_variable_pay` but assembled from scratch without an actual Salary Slip.

#### 3.6.3 SSA Lookup: `get_ssa_data()` (line 178)

Uses a subquery pattern to find the latest Salary Structure Assignment effective on or before the month start:

```sql
SELECT ssa.employee, ssa.base, ssa.variable
FROM `tabSalary Structure Assignment` ssa
INNER JOIN (
    SELECT employee, MAX(from_date) as max_date
    FROM `tabSalary Structure Assignment`
    WHERE employee IN (...) AND from_date <= start AND docstatus = 1
    GROUP BY employee
) latest ON ssa.employee = latest.employee AND ssa.from_date = latest.max_date
WHERE ssa.docstatus = 1
```

This correctly handles mid-period SSA changes by picking the most recent assignment as of the period start.

#### 3.6.4 Festival Count: `get_festival_count()` (line 209)

Counts holidays that fall on non-Sunday weekdays. Uses `getdate(h).weekday() != 6` to exclude Sundays from the festival count. This distinguishes "festival holidays" (Diwali, etc.) from regular weekly Sundays.

#### 3.6.5 Payroll Helper Functions

The report imports 5 functions from `kniterp/payroll.py` (the same module used by the Salary Slip `before_save` hook):

| Function | Source | Returns | SQL per call |
|----------|--------|---------|-------------|
| `get_sunday_pay(emp, start, end)` | `payroll.py:97` | Float (count of Sundays worked, 0.5 for half day) | 1 query on Attendance |
| `get_dual_shift_days(emp, start, end)` | `payroll.py:113` | Int (days with 2+ Present attendance) | 1 query on Attendance |
| `get_machine_extra_pay(emp, start, end)` | `payroll.py:127` | Int (total machine extra pay in rupees) | 1 query on Machine Attendance |
| `get_conveyance(emp, start, end)` | `payroll.py:146` | Tuple (amount, total_km) | 1 query on Monthly Conveyance |
| `get_rejected_holiday_days(emp, start, end)` | `payroll.py:158` | Int (count of rejected holidays) | 1 query for holidays + 2 queries per holiday (is_absent checks) |

### 3.7 Performance Considerations

**Per-employee query pattern**: For N employees, the report issues:
- 3 bulk queries (attendance summary, salary slips, SSA data)
- N queries for holiday count (`get_holiday_count_map` loops over employees)
- N queries for festival count
- 5N queries from payroll helpers (sunday_pay, dual_shift, machine_extra, conveyance, rejected_holidays)
- For rejected holidays: additionally 2 queries per holiday per employee (is_present, is_absent checks)

**Total**: Roughly `3 + 7N + 2NH` queries where H = average holidays per month. For 50 employees and 4 holidays, that is approximately 753 queries.

**Salary Slip earnings**: When slips exist, each slip triggers an additional `frappe.get_all` to fetch `Salary Detail` rows (`get_salary_slip_data`, line 167). This is another N queries.

**No caching**: All data is computed fresh per request.

**Mitigation for current scale**: KnitERP targets 2-3 users with a small workforce. At current scale this is not a bottleneck. If the employee count grows significantly, the payroll helper queries (especially `get_rejected_holiday_days` with its per-holiday per-employee attendance lookups) would benefit from batch fetching.

---

## 4. Integration Points

### 4.1 Subcontracted Batch Traceability and Production Wizard

The traceability report is the read-only complement to the Production Wizard's lot tracking system:

| Production Wizard Feature | Report Usage |
|--------------------------|--------------|
| `JC.custom_consumed_lot_no` (yarn batch consumed) | Report traces backward from fabric batch through Stock Entry to find consumed yarn batches |
| `JC.custom_output_batch_no` (fabric batch produced) | Report traces forward from yarn batch through Stock Entry Manufacture to find produced fabric batches |
| `SCR Item.custom_consumed_batch_no` (fabric sent for dyeing) | Report traces backward from dyed batch through Subcontracting Receipt to find consumed fabric batches |
| `SCR Item.custom_output_dyeing_lot` (dyeing lot produced) | Report traces forward from fabric batch through Subcontracting Receipt to find dyed output lots |
| `Batch.custom_parent_batch` (upstream linkage) | Not directly used by the report -- the report traces via Serial and Batch Bundle entries instead |

The report operates at the Serial and Batch Bundle level (ERPNext's v16 batch tracking infrastructure), not at the KnitERP custom field level. This means it traces the actual stock ledger movements rather than the metadata annotations on Job Cards and SCR Items.

### 4.2 Monthly Salary Register and Payroll System

The salary register directly reuses the payroll calculation functions:

| Payroll Hook (`payroll.py`) | Report Usage |
|----------------------------|-------------|
| `calculate_variable_pay()` (Salary Slip `before_save`) | Not called directly. The report independently computes the same components using the same helper functions. |
| `get_sunday_pay()` | Called per employee (line 57) |
| `get_dual_shift_days()` | Called per employee (line 58) |
| `get_machine_extra_pay()` | Called per employee (line 59) |
| `get_conveyance()` | Called per employee (line 60) |
| `get_rejected_holiday_days()` | Called per employee (line 61) |

When a Salary Slip exists, the report reads its computed values (net_pay, payment_days, Tea Allowance, custom_per_day_salary). When no slip exists, the report reconstructs the payroll calculation from the same data sources. This dual-path approach means the register can show projected payroll before slips are generated.

### 4.3 Monthly Salary Register and HR Doctypes

| KnitERP DocType | Report Usage |
|----------------|-------------|
| Machine Attendance | Queried via `get_machine_extra_pay()` -- counts days with 2+ machines where `production_qty_kg > 30` |
| Monthly Conveyance | Queried via `get_conveyance()` -- sums amount and total_km for the month |

Both are KnitERP-specific doctypes (not standard ERPNext/HRMS) that extend the payroll calculation with textile-industry-specific components.

---

## 5. File Reference Index

| File | Path | Lines | Purpose |
|------|------|------:|---------|
| SBT Python | `kniterp/kniterp/report/subcontracted_batch_traceability/subcontracted_batch_traceability.py` | 656 | Report logic -- ReportData class, backward/forward tracing algorithms |
| SBT JavaScript | `kniterp/kniterp/report/subcontracted_batch_traceability/subcontracted_batch_traceability.js` | 113 | Filter panel (item_code, batches, serial_nos, direction) + custom formatter with colored batch links |
| SBT JSON | `kniterp/kniterp/report/subcontracted_batch_traceability/subcontracted_batch_traceability.json` | 24 | Report definition (ref_doctype: Batch, Script Report) |
| MSR Python | `kniterp/kniterp/report/monthly_salary_register/monthly_salary_register.py` | 261 | Report logic -- employee iteration, attendance summary, payroll component computation |
| MSR JavaScript | `kniterp/kniterp/report/monthly_salary_register/monthly_salary_register.js` | 114 | Filter panel (year, month, employee) + sticky column CSS injection in `after_datatable_render` |
| MSR JSON | `kniterp/kniterp/report/monthly_salary_register/monthly_salary_register.json` | 24 | Report definition (ref_doctype: Salary Slip, Script Report, add_total_row: 1) |
| Payroll helpers | `kniterp/payroll.py` | 231 | Shared functions: get_sunday_pay, get_dual_shift_days, get_machine_extra_pay, get_conveyance, get_rejected_holiday_days |

All paths are relative to `/workspace/development/frappe-bench/apps/kniterp/`.
