import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def create_multilevel_bom(data):
    if isinstance(data, str):
        data = frappe.parse_json(data)

    final_good = data.get('final_good')
    final_qty = flt(data.get('final_qty', 100))
    operations_data = data.get('operations', [])
    rm_cost_as_per = data.get('rm_cost_as_per', 'Valuation Rate')
    sales_order_item = data.get('sales_order_item')
    sales_order = None
    service_item_code = None

    if sales_order_item:
        sales_order, service_item_code = frappe.db.get_value(
            "Sales Order Item", sales_order_item, ["parent", "item_code"]
        )

    # --- Step 1: Validate all inputs ---
    validate_operations_data(operations_data)

    try:
        # --- Step 2: Find or create Phase A BOMs ---
        bom_map = {}  # type -> BOM name
        for op in operations_data:
            process_cp_item_swap(op)
            bom_name = find_or_create_phase_a_bom(op, rm_cost_as_per)
            bom_map[op['type']] = bom_name

        # --- Step 3: Find or create Subcontracting BOMs ---
        # --- Step 3: Find or create Subcontracting BOMs ---
        for op in operations_data:
            if op.get('is_job_work'):
                is_inward = op.get('job_work_direction') == 'inward'
                # For Inward Job Work (primary service), use the SO Item as Service Item
                # Only if this operation matches the main service (e.g. Knitting)
                # Assuming 'knitting' is the main service for now, or if single operation?
                # Actually, find_or_create handles service item lookup.
                # But for Inward, we MUST use the SO Item Code as Service Item if it matches.
                
                target_service_item = service_item_code if is_inward and op['type'] == 'knitting' else None
                
                find_or_create_subcontracting_bom(
                    op, bom_map[op['type']], 
                    sales_order=sales_order, 
                    forced_service_item=target_service_item
                )

        # --- Step 4: Find or create Master BOM ---
        bom = find_or_create_master_bom(
            final_good, final_qty, operations_data, bom_map, rm_cost_as_per
        )

        if isinstance(bom, str):
            # Existing BOM was found
            return {"message": "Existing BOM Selected", "name": bom}

        return {"message": "BOMs Created Successfully", "name": bom.name}

    except Exception:
        frappe.db.rollback()
        raise


def validate_operations_data(operations_data):
    """Validate all operation data before any BOM creation."""
    for op in operations_data:
        loss = flt(op.get('loss_percent', 0))
        if loss < 0 or loss >= 10:
            frappe.throw(
                _("Loss % for {0} must be greater than or equal to 0 and less than 10. Got: {1}").format(
                    frappe.unscrub(op['type']), loss
                )
            )

        if not op.get('output_item'):
            frappe.throw(
                _("Output item is required for {0} operation").format(
                    frappe.unscrub(op['type'])
                )
            )

        if not op.get('inputs'):
            frappe.throw(
                _("At least one input item is required for {0} operation").format(
                    frappe.unscrub(op['type'])
                )
            )

        for inp in op['inputs']:
            if not inp.get('item'):
                frappe.throw(
                    _("Input item code is required in {0} operation").format(
                        frappe.unscrub(op['type'])
                    )
                )


def process_cp_item_swap(op_data):
    """
    For job work inward operations, swap items marked as customer_provided
    to their -CP version.
    """
    if not op_data.get('is_job_work') or op_data.get('job_work_direction') != 'inward':
        return

    for inp in op_data.get('inputs', []):
        if inp.get('customer_provided'):
            base_item = inp['item']
            cp_item = base_item + " - CP" if not base_item.endswith(" - CP") else base_item

            # Verify the CP item exists
            if frappe.db.exists("Item", cp_item):
                inp['item'] = cp_item
            else:
                frappe.throw(
                    _("Customer Provided version '{0}' not found for item '{1}'. "
                      "Please ensure the CP item exists in the Item master.").format(
                        cp_item, base_item
                    )
                )


def find_or_create_phase_a_bom(op_data, rm_cost_as_per="Valuation Rate"):
    """
    Find an existing BOM for the output item that matches the inputs, ratios,
    and sourced_by_supplier flags. If not found, create a new one.
    """
    output_item = op_data['output_item']
    loss = flt(op_data.get('loss_percent', 0))

    # Construct signature of inputs: (item, mix_percent) sorted by item
    data_inputs = sorted(op_data['inputs'], key=lambda x: x['item'])

    # Get candidates
    candidates = frappe.get_all(
        "BOM",
        filters={
            "item": output_item,
            "is_active": 1,
            "docstatus": 1,
            "quantity": 100,
            "with_operations": 0
        },
        fields=["name"]
    )

    for cand in candidates:
        bom_items = frappe.get_all(
            "BOM Item",
            filters={"parent": cand.name},
            fields=["item_code", "qty", "sourced_by_supplier"]
        )
        if len(bom_items) != len(data_inputs):
            continue

        bom_items_sorted = sorted(bom_items, key=lambda x: x.item_code)

        match = True
        for i, d_inp in enumerate(data_inputs):
            b_inp = bom_items_sorted[i]

            if d_inp['item'] != b_inp.item_code:
                match = False
                break

            # Calculate expected qty
            mix = flt(d_inp.get('mix', 0))
            expected_qty = (100 * (mix / 100.0)) / (1 - (loss / 100.0))

            if abs(flt(b_inp.qty) - expected_qty) > 0.01:
                match = False
                break

            # Check sourced_by_supplier flag
            expected_sbs = 1 if d_inp.get('sourced_by_supplier') else 0
            if int(b_inp.sourced_by_supplier or 0) != expected_sbs:
                match = False
                break

        if match:
            return cand.name

    return create_phase_a_bom(op_data, rm_cost_as_per).name


def create_phase_a_bom(op_data, rm_cost_as_per="Valuation Rate"):
    """Create a Phase A BOM with 100kg output."""
    bom = frappe.new_doc("BOM")
    bom.item = op_data['output_item']
    bom.quantity = 100
    bom.with_operations = 0
    bom.track_semi_finished_goods = 0
    bom.rm_cost_as_per = rm_cost_as_per

    loss = flt(op_data.get('loss_percent', 0))

    for inp in op_data['inputs']:
        mix = flt(inp.get('mix', 0))

        # Formula: (100 * (Mix% / 100)) / (1 - (Loss% / 100))
        qty = (100 * (mix / 100.0)) / (1 - (loss / 100.0))

        item_row = {
            "item_code": inp['item'],
            "qty": flt(qty, 3),
            "uom": frappe.db.get_value("Item", inp['item'], "stock_uom")
        }

        # Set sourced_by_supplier for job work outward RMs
        if inp.get('sourced_by_supplier'):
            item_row["sourced_by_supplier"] = 1

        bom.append("items", item_row)

    bom.insert(ignore_permissions=True)
    bom.submit()
    return bom


def find_or_create_subcontracting_bom(op_data, bom_no, sales_order=None, forced_service_item=None):
    """
    Find an existing Subcontracting BOM that matches FG, BOM, and ratios.
    If not found, create a new one. If a different one exists, deactivate it.
    """
    output_item = op_data['output_item']

    # Check if an exact match exists (same finished good, same sub-BOM)
    existing_exact = frappe.get_all(
        "Subcontracting BOM",
        filters={
            "finished_good": output_item,
            "finished_good_bom": bom_no,
            "is_active": 1
        },
        fields=["name", "finished_good_qty", "service_item_qty"]
    )

    if existing_exact:
        sb = existing_exact[0]
        # Also check ratios (quantities)
        expected_fg_qty = flt(op_data.get('output_qty', 100), 3)
        total_input_qty = flt(sum(flt(inp.get('qty', 0)) for inp in op_data.get('inputs', [])), 3)

        if (flt(sb.finished_good_qty, 3) == expected_fg_qty and
                flt(sb.service_item_qty, 3) == total_input_qty):
            return sb.name

    # Check if there's a different Subcontracting BOM for this finished good
    existing_sb = frappe.db.get_value(
        "Subcontracting BOM",
        {"finished_good": output_item, "is_active": 1},
        ["name", "finished_good_bom"],
        as_dict=True
    )

    if existing_sb:
        if existing_sb.finished_good_bom != bom_no:
            # Check if any other Sales Orders are using this finished good
            other_sos = frappe.db.sql("""
                SELECT DISTINCT soi.parent
                FROM `tabSales Order Item` soi
                INNER JOIN `tabSales Order` so ON so.name = soi.parent
                WHERE soi.item_code = %s
                AND so.docstatus = 1
                AND soi.delivered_qty < soi.qty
                AND so.name != %s
            """, (output_item, sales_order or ''), as_dict=True)

            if other_sos:
                so_list = ', '.join([so.parent for so in other_sos[:5]])
                if len(other_sos) > 5:
                    so_list += f' and {len(other_sos) - 5} more'

                frappe.throw(_(
                    "Cannot modify the Subcontracting BOM for {0} because other Sales Orders "
                    "are using it: {1}. Changing the BOM will affect all Sales Orders for this item. "
                    "Please complete or cancel those orders first, or use a different finished good "
                    "item code for this variation."
                ).format(frappe.bold(output_item), so_list))

        # Deactivate old SC BOM (different BOM or different ratios)
        frappe.db.set_value("Subcontracting BOM", existing_sb.name, "is_active", 0)

    # Create new Subcontracting BOM
    sb = frappe.new_doc("Subcontracting BOM")
    sb.finished_good = output_item
    sb.finished_good_qty = flt(op_data.get('output_qty', 100), 3)
    sb.finished_good_uom = frappe.db.get_value("Item", output_item, "stock_uom")
    sb.finished_good_bom = bom_no
    sb.is_active = 1

    service_item = forced_service_item or op_data.get('service_item')
    if not service_item:
        service_name_map = {
            'knitting': 'Knitting Jobwork',
            'dyeing': 'Dyeing Jobwork',
            'yarn_processing': 'Yarn Processing'
        }

        op_type = op_data['type'].lower()
        service_name = service_name_map.get(op_type)

        if service_name:
            service_item = frappe.db.get_value("Item", {"item_name": service_name}, "name")

        if not service_item:
            service_item = frappe.db.get_value("Item", {"item_name": op_data['type']}, "name")
        if not service_item:
            service_item = frappe.db.get_value(
                "Item", {"item_name": frappe.unscrub(op_data['type'])}, "name"
            )

    sb.service_item = service_item

    total_input_qty = sum(flt(inp.get('qty', 0)) for inp in op_data.get('inputs', []))
    sb.service_item_qty = flt(total_input_qty, 3)
    sb.conversion_factor = 1

    sb.insert(ignore_permissions=True)
    return sb.name


def determine_workstation_type(op_type, is_job_work, job_work_direction=None):
    """Auto-determine workstation type based on operation and job work settings."""
    if op_type == 'knitting':
        if is_job_work:
            return 'Knitting Job Work'
        return 'Knitting in-house'
    elif op_type == 'dyeing':
        return 'Dyeing Job Work'
    elif op_type == 'yarn_processing':
        return 'Yarn Processing'
    return ''


def should_skip_material_transfer(op_type, is_job_work, job_work_direction=None):
    """
    Determine if skip_material_transfer should be set.
    True for: in-house knitting OR inward job work knitting.
    """
    if op_type != 'knitting':
        return False

    if not is_job_work:
        # In-house knitting
        return True

    if job_work_direction == 'inward':
        # Inward job work knitting
        return True

    return False


def find_or_create_master_bom(final_good, final_qty, operations_data, bom_map, rm_cost_as_per="Valuation Rate"):
    """
    Check if an existing Master BOM matches this exact combination of
    Phase A BOMs, workstation types, and subcontracting flags.
    If found, return its name. Otherwise create a new one.
    """
    candidates = frappe.get_all(
        "BOM",
        filters={
            "item": final_good,
            "quantity": final_qty,
            "is_active": 1,
            "docstatus": 1,
            "with_operations": 1,
        },
        fields=["name"]
    )

    for cand in candidates:
        bom_ops = frappe.get_all(
            "BOM Operation",
            filters={"parent": cand.name},
            fields=["operation", "bom_no", "workstation_type", "is_subcontracted",
                     "skip_material_transfer"],
            order_by="sequence_id asc"
        )

        if len(bom_ops) != len(operations_data):
            continue

        match = True
        for i, op_data in enumerate(operations_data):
            b_op = bom_ops[i]
            intended_sub_bom = bom_map.get(op_data['type'])

            # Check Operation Name
            if frappe.unscrub(op_data['type']) != b_op.operation:
                match = False
                break

            # Check Sub-BOM Link
            if intended_sub_bom and b_op.bom_no != intended_sub_bom:
                match = False
                break

            # Check Workstation Type
            is_job_work = op_data.get('is_job_work')
            jw_direction = op_data.get('job_work_direction')
            expected_ws = determine_workstation_type(op_data['type'], is_job_work, jw_direction)
            if expected_ws and b_op.workstation_type != expected_ws:
                match = False
                break

            # Check Subcontracting (Job Work)
            expected_sc = 1 if (is_job_work and jw_direction != 'inward') else 0
            if int(b_op.is_subcontracted or 0) != expected_sc:
                match = False
                break

            # Check skip_material_transfer
            expected_smt = 1 if should_skip_material_transfer(
                op_data['type'], is_job_work, jw_direction
            ) else 0
            if int(b_op.skip_material_transfer or 0) != expected_smt:
                match = False
                break

        if match:
            # Found existing match
            return cand.name

    # No match found — create new Master BOM
    bom = frappe.new_doc("BOM")
    bom.item = final_good
    bom.quantity = final_qty
    bom.with_operations = 1
    bom.track_semi_finished_goods = 1
    bom.rm_cost_as_per = rm_cost_as_per

    for i, op in enumerate(operations_data):
        is_final = (i == len(operations_data) - 1)
        is_job_work = op.get('is_job_work')
        jw_direction = op.get('job_work_direction')

        bom.append("operations", {
            "sequence_id": i + 1,
            "operation": frappe.unscrub(op['type']),
            "finished_good": op['output_item'],
            "finished_good_qty": flt(op['output_qty'], 3),
            "is_subcontracted": 1 if (is_job_work and jw_direction != 'inward') else 0,
            "is_final_finished_good": 1 if is_final else 0,
            "bom_no": bom_map.get(op['type']),
            "time_in_mins": 60,
            "workstation_type": determine_workstation_type(op['type'], is_job_work, jw_direction),
            "skip_material_transfer": 1 if should_skip_material_transfer(
                op['type'], is_job_work, jw_direction
            ) else 0,
        })

    bom.insert(ignore_permissions=True)
    bom.submit()
    return bom


@frappe.whitelist()
def get_multilevel_bom(bom_no):
    """
    Reconstruct the BOM Designer data structure from an existing Master BOM.
    """
    bom = frappe.get_doc("BOM", bom_no)

    data = {
        "final_good": bom.item,
        "final_qty": bom.quantity,
        "rm_cost_as_per": bom.rm_cost_as_per or "Valuation Rate",
        "operations": []
    }

    for op in bom.operations:
        is_job_work = bool(op.is_subcontracted)

        # Determine job work direction from workstation type and operation
        jw_direction = ''
        if is_job_work and frappe.scrub(op.operation) == 'knitting':
            # Check if skip_material_transfer is set — indicates inward
            if op.skip_material_transfer:
                jw_direction = 'inward'
            else:
                jw_direction = 'outward'
        elif is_job_work:
            jw_direction = 'outward'

        op_data = {
            "type": frappe.scrub(op.operation),
            "output_item": op.finished_good,
            "output_qty": op.finished_good_qty,
            "is_job_work": is_job_work,
            "job_work_direction": jw_direction,
            "loss_percent": 0,
            "workstation_type": op.workstation_type,
            "inputs": []
        }

        # If there's a sub-BOM, get inputs from there
        if op.bom_no:
            sub_bom = frappe.get_doc("BOM", op.bom_no)

            total_input = sum(flt(item.qty) for item in sub_bom.items)
            output = sub_bom.quantity

            if total_input > 0:
                loss_val = 100.0 * (1.0 - (flt(output) / flt(total_input)))
                op_data["loss_percent"] = max(0, float("{:.2f}".format(loss_val)))

            for item in sub_bom.items:
                mix_val = (flt(item.qty) / total_input) * 100

                inp_data = {
                    "item": item.item_code,
                    "qty": item.qty,
                    "mix": float("{:.2f}".format(mix_val)),
                    "sourced_by_supplier": bool(item.sourced_by_supplier),
                }

                # Check if this is a CP item (for inward job work)
                if item.item_code.endswith(" - CP"):
                    inp_data["customer_provided"] = True
                    # Store original base item code for display
                    inp_data["base_item"] = item.item_code.rsplit(" - CP", 1)[0]

                op_data["inputs"].append(inp_data)

        data["operations"].append(op_data)

    return data
