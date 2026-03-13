# BOM Designer

> **Route**: `/app/bom-designer`
> **Type**: Frappe Page (not a DocType)
> **Module**: Kniterp
> **Files**: `kniterp/page/bom_designer/` (JS/CSS/JSON/PY) + `kniterp/api/bom_tool.py`
> **LOC**: ~1,126 (JS) + ~538 (API) + ~438 (CSS)

---

## 1. PURPOSE

BOM Designer is a **visual multi-level BOM creation tool** purpose-built for textile manufacturing workflows. It replaces the standard ERPNext BOM form with a streamlined, stage-based UI that constructs the entire BOM hierarchy in a single action.

**Business problem it solves:** In textile manufacturing, a finished good (e.g., dyed fabric) typically passes through 2-3 processing stages -- yarn processing, knitting, and dyeing -- each with its own input materials, loss percentages, and subcontracting arrangements. ERPNext's standard BOM form requires creating each sub-BOM individually, manually linking them into a master BOM with operations, and separately creating Subcontracting BOMs for job work. This is a tedious multi-step process involving 3-6 separate document creations.

BOM Designer collapses this into a single page: the user defines all stages visually, configures inputs/outputs/loss/job-work per stage, and clicks "Generate BOMs." The backend atomically creates all Phase A BOMs, Subcontracting BOMs, and the Master BOM in one transaction.

**Who uses it:** Production planners (2-3 non-tech-savvy users). Typically invoked from the Production Wizard when a Sales Order Item lacks a BOM, or accessed directly at `/app/bom-designer`.

---

## 2. ROUTE, ROLES, ACCESS CONTROL

### Page Definition

| Property | Value |
|----------|-------|
| Route | `/app/bom-designer` |
| Page name | `bom_designer` |
| Icon | `fa fa-puzzle-piece` |
| Module | Kniterp |

Source: `kniterp/kniterp/page/bom_designer/bom_designer.json`

### Allowed Roles

Defined in the page JSON (`bom_designer.json:13-19`):

| Role |
|------|
| System Manager |
| Manufacturing Manager |

### Write Access (API-level)

The `create_multilevel_bom` endpoint calls `require_production_write_access()` (`bom_tool.py:9`), which checks against `PRODUCTION_WRITE_ROLES` from `api/access_control.py:5-8`:

| Role |
|------|
| System Manager |
| Manufacturing Manager |
| Manufacturing User |

The `get_multilevel_bom` endpoint has no explicit permission check beyond `@frappe.whitelist()`.

### URL Parameters

The page accepts several route options (via `frappe.route_options` or query string):

| Parameter | Purpose |
|-----------|---------|
| `item_code` | Pre-populate the Final Good field |
| `bom_no` | Load an existing BOM for editing/viewing |
| `sales_order_item` | SO Item context for BOM-to-SO linking and SC BOM validation |
| `return_to` | If `"production-wizard"`, redirects back to PW after BOM creation |

Source: `bom_designer.js:17-21`

---

## 3. BOM TYPES

BOM Designer creates up to three layers of BOM documents per operation stage. Understanding these types is essential.

### 3.1 Phase A BOM

A **Phase A BOM** is a simple, flat BOM for a single processing stage. It defines the input-to-output material relationship for one operation (e.g., "what yarns go into this grey fabric").

| Property | Value |
|----------|-------|
| `with_operations` | 0 (no operations) |
| `track_semi_finished_goods` | 0 |
| `quantity` | Always 100 (normalized) |
| `docstatus` | 1 (submitted) |

One Phase A BOM is created per operation stage. The input quantities are calculated from the mix percentage and loss percentage using:

```
qty = (100 * (mix% / 100)) / (1 - (loss% / 100))
```

For example, with 100% mix and 2% loss: `qty = 100 / 0.98 = 102.041`.

Phase A BOMs are **reused** if an existing submitted, active BOM matches the same output item, same inputs (item codes, quantities, and `sourced_by_supplier` flags). The matching logic is in `find_or_create_phase_a_bom()` (`bom_tool.py:132-192`).

### 3.2 Master BOM

The **Master BOM** is the top-level BOM linked to the final good. It ties together all Phase A BOMs as operations with semi-finished-good tracking.

| Property | Value |
|----------|-------|
| `with_operations` | 1 |
| `track_semi_finished_goods` | 1 |
| `quantity` | User-specified (default 100) |
| `docstatus` | 1 (submitted) |

Each operation row in the Master BOM references:
- The `operation` name (e.g., "Knitting", "Dyeing")
- The `bom_no` pointing to the Phase A BOM for that stage
- The `finished_good` (output item of that stage)
- The `workstation_type` (auto-determined)
- `is_subcontracted` flag
- `skip_material_transfer` flag
- `is_final_finished_good` (set on the last operation only)

Master BOMs are also **reused** if an existing one matches all operations, Phase A BOM links, workstation types, and subcontracting flags. See `find_or_create_master_bom()` (`bom_tool.py:364-465`).

### 3.3 Subcontracting BOM

A **Subcontracting BOM** is an ERPNext `Subcontracting BOM` document that maps a finished good to a service item for subcontracting workflows (Purchase Order / Subcontracting Order creation).

| Property | Notes |
|----------|-------|
| `finished_good` | Output item of the job work operation |
| `finished_good_bom` | Links to the Phase A BOM |
| `finished_good_qty` | From operation output qty |
| `service_item` | Auto-determined or forced from SO Item |
| `service_item_qty` | Sum of all input quantities |
| `is_active` | 1 |

Created only for operations where `is_job_work` is true. See `find_or_create_subcontracting_bom()` (`bom_tool.py:229-329`).

**Service item resolution** (in order, `bom_tool.py:301-320`):
1. `forced_service_item` parameter (used for inward knitting -- takes SO Item's item_code)
2. `op_data.service_item` (if passed from frontend)
3. Lookup by `item_name` from a hardcoded map: `knitting` -> "Knitting Jobwork", `dyeing` -> "Dyeing Jobwork", `yarn_processing` -> "Yarn Processing"
4. Fallback: lookup by `item_name` matching the operation type name

**Deactivation behavior**: If a different Subcontracting BOM already exists for the same finished good, the old one is deactivated (`is_active = 0`) before creating the new one. However, if other active Sales Orders reference the same finished good, a validation error is thrown (`bom_tool.py:268-288`).

### Relationship Diagram

```
Master BOM (FG = "Dyed Fabric X", qty=100, with_operations=1)
  |
  +-- Operation 1: Yarn Processing
  |     bom_no -> Phase A BOM (output="Processed Yarn Y", qty=100)
  |     Subcontracting BOM (FG="Processed Yarn Y", service="Yarn Processing")
  |
  +-- Operation 2: Knitting
  |     bom_no -> Phase A BOM (output="Grey Fabric Z", qty=100)
  |     Subcontracting BOM (FG="Grey Fabric Z", service="Knitting Jobwork")  [if job work]
  |
  +-- Operation 3: Dyeing
        bom_no -> Phase A BOM (output="Dyed Fabric X", qty=100)
        Subcontracting BOM (FG="Dyed Fabric X", service="Dyeing Jobwork")
```

---

## 4. UI FLOW

### 4.1 Page Layout

The page is a single-column Frappe app page with three sections:

1. **Header Card** -- Final Good selector (Link to Item), Total Quantity input (default 100 Kg), RM Cost Based On selector (Valuation Rate / Last Purchase Rate / Price List)
2. **Sequence Bar** -- Three stage-add buttons: Yarn Processing, Knitting, Dyeing (color-coded)
3. **Workflow Stack** -- Vertically stacked operation cards connected by down-arrow icons

### 4.2 Adding Stages

The user clicks one of the three stage buttons to add an operation card. Each operation type can only exist once -- clicking a duplicate triggers `frappe.msgprint`. Operations are always sorted in fixed order regardless of click order (`bom_designer.js:384-387`):

| Sort Order | Operation | Default Job Work | Color Theme |
|------------|-----------|-------------------|-------------|
| 1 | Yarn Processing | Always checked + disabled | Orange (`#f6ad55`) |
| 2 | Knitting | Unchecked (toggleable) | Blue (`#63b3ed`) |
| 3 | Dyeing | Always checked + disabled | Purple (`#b794f4`) |

### 4.3 Operation Card Structure

Each operation card has three columns:

**Left Column -- Inputs:**
- Input item rows, each with a Link field (Item) and a mix percentage input
- Knitting cards show "Yarns Mix" label and allow multiple inputs with an "Add Item" button
- Yarn Processing and Dyeing cards have a single input row with hidden 100% mix
- Each input row can have checkboxes: "Sourced by Supplier" (outward job work) or "Customer Provided" (inward job work)

**Middle Column -- Settings:**
- Job Work checkbox (forced on for Yarn Processing and Dyeing, toggleable for Knitting)
- Job Work Direction radio buttons (Knitting only, when Job Work is checked): "Out-House" or "In-House"
- Target Output (SFG) Link field (Knitting and Yarn Processing only -- shown on Knitting only when Dyeing stage exists)
- Workstation Type display (read-only, auto-determined)
- Process Loss % input (default 2%)

**Right Column -- Output:**
- Output item name display (auto-synced from context)
- Calculated output quantity in Kg

### 4.4 Auto-Sync Behavior

The UI has several automatic synchronization rules:

| Trigger | Behavior | Source |
|---------|----------|--------|
| Final Good selected | Dyeing output = Final Good; Knitting output = Final Good (if no Dyeing stage) | `sync_dyeing()`, `sync_knitting_output()` at JS:754, JS:441 |
| Dyeing stage added | Knitting SFG selector becomes visible; Knitting output changes to SFG value | `update_sfg_visibility()` at JS:420 |
| Dyeing stage removed | Knitting SFG selector hides; Knitting output reverts to Final Good | `update_sfg_visibility()` at JS:420 |
| Knitting SFG selected | Dyeing input auto-populated with Knitting's SFG | `sync_dyeing()` at JS:768-779 |
| Yarn Processing SFG selected | Yarn output propagated to Knitting input (or Dyeing input if no Knitting) | `sync_yarn_output()` at JS:782-830 |
| Job Work checkbox toggled | Workstation type display updates; RM checkboxes show/hide | `update_workstation_display()`, `update_rm_checkboxes()` at JS:857, JS:868 |
| Job Work direction changed | Sourced-by-supplier vs Customer-provided checkboxes toggle | `update_rm_checkboxes()` at JS:868-907 |

### 4.5 Quantity Calculation

Quantities are calculated in reverse order (last stage first) using backward propagation (`bom_designer.js:911-934`):

1. Start with `current_output_qty = final_qty` (e.g., 100 Kg)
2. For each operation from last to first:
   - Display `current_output_qty` as the operation's output
   - For each input row: `row_qty = (current_output_qty * mix% / 100) / (1 - loss% / 100)`
   - Sum all row quantities to get `total_input_for_op`
   - Set `current_output_qty = total_input_for_op` for the next (earlier) operation

This means each operation's input becomes the output requirement for the previous operation, accounting for loss at each stage.

### 4.6 Loading an Existing BOM

When `bom_no` is passed as a URL parameter, or when the user selects a Final Good that has an existing default BOM (detected via `check_and_load_bom()` at JS:46-86), the page reconstructs the full state:

1. Calls `get_multilevel_bom` API
2. Populates Final Good, quantity, RM cost setting
3. Adds operation cards for each BOM operation
4. Sets loss percentages, job work flags, direction, SFG items, and input items with mix percentages
5. Restores checkbox states (sourced_by_supplier, customer_provided)
6. Uses `setTimeout` cascades to handle async Frappe control initialization (`bom_designer.js:88-173`)

### 4.7 Validation

Frontend validation (`validate_data()` at JS:938-989) checks:

| Rule | Scope |
|------|-------|
| All input items must be filled | All operations |
| Mix percentages must sum to 100% | Knitting only |
| SFG must be selected when Dyeing exists | Knitting only |
| No duplicate items within an operation | All operations |
| Loss % must be >= 0 and < 10 | All operations |

Backend validation (`validate_operations_data()` at `bom_tool.py:73-105`) checks:

| Rule | Scope |
|------|-------|
| Loss % must be >= 0 and < 10 | All operations |
| `output_item` is required | All operations |
| At least one input is required | All operations |
| Each input must have an `item` code | All operations |

### 4.8 BOM Generation

When the user clicks "Generate BOMs" (primary action):

1. Frontend collects data via `get_data()` (JS:1007-1070)
2. Frontend validates via `validate_data()` (JS:938-989)
3. Confirmation dialog shown
4. Calls `create_multilevel_bom` API
5. On success:
   - If `return_to === 'production-wizard'`: calls `update_so_item_bom` to link the BOM to the SO Item, then navigates back to Production Wizard
   - Otherwise: navigates to BOM list filtered by the final good item

---

## 5. API REFERENCE

### 5.1 `create_multilevel_bom(data)` -- Whitelisted

**File**: `kniterp/api/bom_tool.py:7`

Creates the entire multi-level BOM hierarchy in a single atomic transaction.

**Arguments** (`data` is a JSON object):

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `final_good` | string | Yes | -- | Item code of the finished good |
| `final_qty` | float | No | 100 | Master BOM quantity |
| `operations` | list | Yes | -- | Array of operation objects (see below) |
| `rm_cost_as_per` | string | No | "Valuation Rate" | BOM costing method |
| `sales_order_item` | string | No | -- | SO Item name for SC BOM validation context |

**Operation object structure:**

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Operation type: `yarn_processing`, `knitting`, or `dyeing` |
| `output_item` | string | Item code of the operation's output |
| `output_qty` | float | Calculated output quantity |
| `is_job_work` | bool | Whether this is a subcontracted operation |
| `job_work_direction` | string | `"outward"` or `"inward"` (knitting only) |
| `loss_percent` | float | Process loss percentage (0-9.99) |
| `inputs` | list | Array of input objects |
| `inputs[].item` | string | Input item code |
| `inputs[].mix` | float | Mix percentage (must sum to 100 for knitting) |
| `inputs[].qty` | float | Calculated input quantity |
| `inputs[].sourced_by_supplier` | bool | RM sourced by supplier (outward job work) |
| `inputs[].customer_provided` | bool | RM provided by customer (inward job work) |

**Processing steps** (`bom_tool.py:27-66`):

1. Validate all operations (`validate_operations_data`)
2. For each operation: swap CP items if inward job work (`process_cp_item_swap`), then find or create Phase A BOM (`find_or_create_phase_a_bom`)
3. For each job work operation: find or create Subcontracting BOM (`find_or_create_subcontracting_bom`)
4. Find or create Master BOM (`find_or_create_master_bom`)

**Returns:**

```python
{"message": "BOMs Created Successfully", "name": "BOM-ITEM-001"}
# or if existing BOM matched:
{"message": "Existing BOM Selected", "name": "BOM-ITEM-001"}
```

**Error handling**: On any exception, rolls back the entire transaction (`bom_tool.py:69`).

**Permission**: Requires `PRODUCTION_WRITE_ROLES` (`bom_tool.py:9`).

### 5.2 `get_multilevel_bom(bom_no)` -- Whitelisted

**File**: `kniterp/api/bom_tool.py:468`

Reconstructs the BOM Designer data structure from an existing Master BOM so the UI can load and display it.

**Arguments:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `bom_no` | string | Yes | BOM name to load |

**Returns:** A dict matching the `create_multilevel_bom` input structure, with additional fields:

- `loss_percent` is back-calculated from the Phase A BOM's total input vs output: `loss = 100 * (1 - output / total_input)`
- `mix` per input is calculated as: `(item.qty / total_input) * 100`
- For CP items (ending in " - CP"), `customer_provided: true` and `base_item` (original item code without suffix) are added
- Job work direction is inferred from `is_subcontracted` + `skip_material_transfer` flags on the BOM Operation

**Permission**: No explicit check beyond `@frappe.whitelist()`.

---

## 6. KEY INTERNAL FUNCTIONS

### Backend (`bom_tool.py`)

| Function | Line | Purpose |
|----------|------|---------|
| `validate_operations_data(operations_data)` | 73 | Pre-flight validation of all operations before any BOM creation. Checks loss range, output item presence, input item presence. |
| `process_cp_item_swap(op_data)` | 107 | For inward job work operations, appends " - CP" suffix to input items marked `customer_provided`. Throws if the CP item does not exist in Item master. |
| `find_or_create_phase_a_bom(op_data, rm_cost_as_per)` | 132 | Searches for an existing active, submitted BOM with `quantity=100`, `with_operations=0` that matches the output item, input items, calculated quantities, and `sourced_by_supplier` flags. Creates new if no match. Tolerance: 0.01 on qty comparison. |
| `create_phase_a_bom(op_data, rm_cost_as_per)` | 195 | Creates and submits a new Phase A BOM. Uses `ignore_permissions=True` on insert. |
| `find_or_create_subcontracting_bom(op_data, bom_no, sales_order, forced_service_item)` | 229 | Finds existing SC BOM matching FG + BOM + quantities. If a different SC BOM exists for the same FG, checks for conflicting active SOs before deactivating it. Creates new SC BOM with auto-resolved service item. |
| `determine_workstation_type(op_type, is_job_work, job_work_direction)` | 332 | Returns workstation type string based on operation type and job work settings. |
| `should_skip_material_transfer(op_type, is_job_work, job_work_direction)` | 345 | Returns `True` for in-house knitting or inward job work knitting. Used to set `skip_material_transfer` on BOM Operation. |
| `find_or_create_master_bom(final_good, final_qty, operations_data, bom_map, rm_cost_as_per)` | 364 | Searches for an existing active, submitted Master BOM matching all operations, Phase A BOM links, workstation types, subcontracting flags, and `skip_material_transfer` values. Creates new if no match. |

### Frontend (`bom_designer.js`)

| Method | Line | Purpose |
|--------|------|---------|
| `constructor()` | 9 | Initializes page, reads URL params, sets up UI, loads existing BOM if `bom_no` provided. |
| `load_existing_bom(bom_no)` | 33 | Calls `get_multilevel_bom` API and delegates to `populate_from_data`. |
| `check_and_load_bom(item_code)` | 46 | When a Final Good is selected, checks for an existing default BOM and offers to load it via `frappe.confirm`. |
| `populate_from_data(data)` | 88 | Reconstructs the full UI state from API response -- sets Final Good, adds operations, populates inputs, loss, checkboxes. Uses cascading `setTimeout` calls for async control initialization. |
| `setup_ui()` | 175 | Renders the HTML layout, creates Frappe Link/Select controls for Final Good and RM Cost, binds the primary action button ("Generate BOMs"). |
| `bind_events()` | 317 | Delegates click handlers for add/remove operations, add/remove inputs, and change handlers for loss/mix/qty/job-work/direction. |
| `add_operation(type)` | 356 | Adds a new operation card. Prevents duplicates. Sorts operations and triggers sync/calculation. |
| `sort_operations()` | 384 | Enforces fixed order: yarn_processing=1, knitting=2, dyeing=3. |
| `render_op_card(type, step_num)` | 473 | Builds the HTML for an operation card with all three columns (inputs, settings, output). Initializes SFG Link control for non-dyeing cards. |
| `add_input_row($el)` | 637 | Adds a new input row with Item Link control, mix percentage input, and RM flag checkboxes. |
| `sync_dyeing()` | 754 | Auto-sets Dyeing output to Final Good and Dyeing input to Knitting's SFG output. |
| `sync_yarn_output()` | 782 | Propagates Yarn Processing's SFG output to Knitting's input rows (or Dyeing if no Knitting). |
| `calculate_quantities()` | 911 | Reverse-propagation quantity calculation from last to first operation. |
| `validate_data(data)` | 938 | Client-side validation before API call. |
| `get_data()` | 1007 | Collects the full data structure from DOM state for the API call. |
| `create_bom()` | 1072 | Orchestrates the BOM generation: validates, confirms, calls API, handles return navigation. |

---

## 7. DATA MODEL

BOM Designer creates and queries standard ERPNext doctypes. It has no custom doctypes of its own.

### Documents Created

| DocType | Created By | Submitted | `ignore_permissions` |
|---------|------------|-----------|---------------------|
| BOM (Phase A) | `create_phase_a_bom` | Yes | Yes (`bom_tool.py:224`) |
| BOM (Master) | `find_or_create_master_bom` | Yes | Yes (`bom_tool.py:463`) |
| Subcontracting BOM | `find_or_create_subcontracting_bom` | N/A (not submittable) | Yes (`bom_tool.py:328`) |

### Documents Queried

| DocType | Queried By | Purpose |
|---------|------------|---------|
| BOM | `find_or_create_phase_a_bom` | Find matching existing Phase A BOM |
| BOM | `find_or_create_master_bom` | Find matching existing Master BOM |
| BOM Item | `find_or_create_phase_a_bom` | Compare candidate BOM inputs |
| BOM Operation | `find_or_create_master_bom` | Compare candidate Master BOM operations |
| Subcontracting BOM | `find_or_create_subcontracting_bom` | Find/deactivate existing SC BOMs |
| Sales Order Item | `find_or_create_subcontracting_bom` | Check for conflicting active SOs |
| Sales Order | `find_or_create_subcontracting_bom` | Check SO delivery status |
| Item | `create_phase_a_bom`, `find_or_create_subcontracting_bom`, `process_cp_item_swap` | Get stock UOM, verify CP item exists, resolve service items |

### Key BOM Fields Used

**Phase A BOM (flat, no operations):**

| Field | Value |
|-------|-------|
| `item` | Operation output item |
| `quantity` | 100 (always normalized) |
| `with_operations` | 0 |
| `track_semi_finished_goods` | 0 |
| `rm_cost_as_per` | User selection |
| `items[].item_code` | Input item |
| `items[].qty` | Calculated from mix% and loss% |
| `items[].sourced_by_supplier` | From user checkbox (outward job work) |

**Master BOM (with operations):**

| Field | Value |
|-------|-------|
| `item` | Final Good |
| `quantity` | User-specified |
| `with_operations` | 1 |
| `track_semi_finished_goods` | 1 |
| `rm_cost_as_per` | User selection |
| `operations[].operation` | `frappe.unscrub(type)` (e.g., "Yarn Processing") |
| `operations[].bom_no` | Phase A BOM name |
| `operations[].finished_good` | Operation output item |
| `operations[].finished_good_qty` | Calculated output qty |
| `operations[].is_subcontracted` | 1 if outward job work, else 0 |
| `operations[].workstation_type` | Auto-determined |
| `operations[].skip_material_transfer` | 1 for in-house or inward knitting |
| `operations[].is_final_finished_good` | 1 for last operation only |
| `operations[].time_in_mins` | 60 (hardcoded) |

---

## 8. WORKSTATION TYPE AND SUBCONTRACTING LOGIC

### Workstation Type Determination

`determine_workstation_type()` (`bom_tool.py:332-342`) and its JS mirror `get_workstation_type()` (`bom_designer.js:462-471`):

| Operation | Job Work? | Direction | Workstation Type |
|-----------|-----------|-----------|-----------------|
| Knitting | No | -- | `Knitting in-house` |
| Knitting | Yes | outward | `Knitting Job Work` |
| Knitting | Yes | inward | `Knitting Job Work` |
| Dyeing | Yes (always) | outward | `Dyeing Job Work` |
| Yarn Processing | Yes (always) | outward | `Yarn Processing` |

### Subcontracting Flags on Master BOM Operations

`is_subcontracted` (`bom_tool.py:453`):
- Set to `1` when `is_job_work=True` AND `job_work_direction != 'inward'`
- Inward job work (customer sends material to us) does NOT set `is_subcontracted` on the BOM operation

`skip_material_transfer` (`bom_tool.py:345-361`):
- Set to `1` for knitting operations that are either in-house or inward job work
- All other operations: `0`
- This controls whether ERPNext requires a material transfer Stock Entry before production can start

### Customer Provided (CP) Item Swap

For inward job work operations, `process_cp_item_swap()` (`bom_tool.py:107-129`) transforms input items:
- If an input has `customer_provided=True`, the item code is changed to `"{item_code} - CP"`
- The CP item must exist in the Item master (validated; throws if missing)
- This leverages the dual yarn versioning system (see `docs/item-system.md`) where every yarn/fabric item has a base version and a " - CP" (Customer Provided) counterpart

---

## 9. INTEGRATION POINTS

### 9.1 Production Wizard

BOM Designer is the primary way BOMs are created for Production Wizard items.

**Inbound** (PW -> BOM Designer):
- Production Wizard navigates to BOM Designer with `item_code`, `sales_order_item`, and `return_to=production-wizard` when a SO Item needs a BOM
- Source: `production_wizard.js` (triggers via route navigation)

**Outbound** (BOM Designer -> PW):
- After BOM creation, if `return_to === 'production-wizard'`, calls `production_wizard.update_so_item_bom()` to write the BOM name onto the SO Item, then navigates back to Production Wizard
- Source: `bom_designer.js:1098-1114`

### 9.2 Item Composer / Item System

- All Link fields in BOM Designer use `options: 'Item'`, which triggers KnitERP's smart search (`api/item_search.smart_search`) for fuzzy token-based item lookup
- CP item creation is a prerequisite: the dual yarn versioning system must have already created the " - CP" item variant before BOM Designer can use it for inward job work

### 9.3 ERPNext Manufacturing

The BOMs created by BOM Designer are standard ERPNext BOM documents. They are consumed by:
- **Work Order** creation: uses the Master BOM to generate operations and material requirements
- **Job Card** creation: Work Order operations (from Master BOM) become Job Cards
- **Subcontracting Order** creation: uses the Subcontracting BOM to map FG to service items
- **Stock Entry (Manufacture)**: uses Phase A BOMs for material consumption/production

### 9.4 Sales Order Item

The `sales_order_item` parameter provides SO context for:
1. Extracting the `sales_order` name for SC BOM conflict validation (`bom_tool.py:22-25`)
2. For inward knitting: using the SO Item's `item_code` as the forced `service_item` in the Subcontracting BOM (`bom_tool.py:49`)
3. Post-creation BOM linking via `update_so_item_bom` (`bom_designer.js:1102-1107`)

---

## 10. CSS AND VISUAL DESIGN

Source: `kniterp/kniterp/page/bom_designer/bom_designer.css` (438 lines)

The page uses a scoped CSS design with CSS custom properties to support both light and dark modes. Key design elements:

| Element | CSS Class | Visual |
|---------|-----------|--------|
| Container | `.bom-designer-container` | Full-height, padded, inherits Frappe theme variables |
| Header | `.header-card` | Card with shadow, rounded corners |
| Stage buttons | `.op-pill` | Rounded, color-coded with hover glow effects |
| Operation cards | `.op-card` | Rounded, left border accent color per type |
| Card header | `.op-card-header` | Subtle background with step label badge |
| Input rows | `.input-row-mini` | Compact, removable, with focus z-index management |
| Output display | `.output-box` | Green-tinted background |

Color themes per operation type:
- **Yarn Processing**: Orange (`#f6ad55`) -- `.card-yarn-processing`, `.pill-yarn`
- **Knitting**: Blue (`#63b3ed`) -- `.card-knitting`, `.pill-knit`
- **Dyeing**: Purple (`#b794f4`) -- `.card-dyeing`, `.pill-dye`

Dark mode is handled via `[data-theme="dark"]` selectors with explicit overrides for backgrounds, borders, and shadows.

---

## 11. KNOWN ISSUES, EDGE CASES, AND GOTCHAS

### Timing-dependent UI initialization

The `populate_from_data()` method uses cascading `setTimeout` calls (150ms, 200ms, 300ms, 500ms) to wait for Frappe Link controls to initialize before setting values (`bom_designer.js:124-172`). This is fragile -- on slow machines or heavy pages, controls may not be ready in time, causing values to be silently dropped.

### Phase A BOM quantity normalization

All Phase A BOMs use `quantity=100` regardless of the actual production quantity. The Master BOM's operation `finished_good_qty` holds the real output quantity. This normalization enables BOM reuse but means the Phase A BOM quantities do not directly correspond to the actual production run.

### `ignore_permissions=True` on all BOM inserts

All three creation functions (`create_phase_a_bom`, `find_or_create_subcontracting_bom`, `find_or_create_master_bom`) use `ignore_permissions=True` when inserting documents. Permission is checked once at the API entry point (`require_production_write_access`), not per-document.

### Subcontracting BOM deactivation risk

When a new SC BOM is needed for a finished good that already has an active one, the old SC BOM is deactivated (`bom_tool.py:291`). This is guarded by a check for other active SOs using the same finished good (`bom_tool.py:268-288`), but the check only looks at submitted SOs with undelivered quantities. Draft SOs or SOs in other states are not considered.

### Job work direction inference on BOM load

When loading an existing BOM via `get_multilevel_bom`, the job work direction for knitting is inferred from the `skip_material_transfer` flag (`bom_tool.py:489`). If `is_subcontracted=True` and `skip_material_transfer=True`, it's "inward"; otherwise "outward." This heuristic works for the current operation types but would break if `skip_material_transfer` were set for other reasons.

### Inward job work only supported for knitting

The `process_cp_item_swap` function runs for all inward operations (`bom_tool.py:112`), but the UI only shows the "In-House" direction option for knitting (`bom_designer.js:518-532`). Yarn Processing and Dyeing are hardcoded as always-outward in the frontend. The forced service item logic also only triggers for `op['type'] == 'knitting'` (`bom_tool.py:49`).

### Mix percentage validation gap

The frontend validates that knitting mix percentages sum to 100% (`bom_designer.js:954-958`). However, the backend does not validate this -- it simply uses whatever mix values are passed. For non-knitting operations, mix is always 100% (hidden input), so this is not an issue in practice.

### `time_in_mins` hardcoded to 60

All Master BOM operations are created with `time_in_mins: 60` (`bom_tool.py:456`). This value is not configurable from the UI and may not reflect actual operation times.

### No BOM amendment support

BOM Designer can load and display an existing BOM but does not support amending it. Generating BOMs always creates new documents (or reuses exact matches). There is no workflow to modify a single operation in an existing BOM hierarchy.

### Service item map is hardcoded

The mapping from operation type to service item name (`bom_tool.py:303-307`) is hardcoded:
```python
{'knitting': 'Knitting Jobwork', 'dyeing': 'Dyeing Jobwork', 'yarn_processing': 'Yarn Processing'}
```
If these Item records are renamed or deleted, SC BOM creation will fail or fall through to less reliable name-based lookups.

### Single SQL in SC BOM validation

The `find_or_create_subcontracting_bom` function has one raw SQL query (`bom_tool.py:268-276`) to check for conflicting Sales Orders. This is the only raw SQL in `bom_tool.py`; all other queries use the Frappe ORM.
