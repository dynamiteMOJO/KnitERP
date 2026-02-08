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
    
    # Detailed logging for debugging rates
    frappe.log_error(title="BOM Designer Data", message=frappe.as_json(data))

    # Check for existing identical Master BOM
    existing_bom = find_matching_master_bom(final_good, final_qty, operations_data)
    if existing_bom:
        return {"message": "Existing BOM Selected", "name": existing_bom}
    
    bom_map = {} # Type -> BOM Name
    
    # Phase A: Create Sub-BOMS (100kg output)
    for op in operations_data:
        # Check/Create Phase A BOM
        bom_name = find_or_create_phase_a_bom(op)
        bom_map[op['type']] = bom_name
        
        # Phase B: Create Subcontracting BOM if job work
        if op.get('is_job_work'):
             # Subcontracting BOMs are "virtual" mostly, but let's check duplicates? 
             # For now, just create new as they are cheap rows. 
             # ACTUALLY: Subcontracting BOM is a specific DocType. checking duplicates is good.
             create_subcontracting_bom(op, bom_name)
            
    # Phase C: Create Master BOM
    bom = create_master_bom(final_good, final_qty, operations_data, bom_map)
    
    return {"message": "BOMs Created Successfully", "name": bom.name}

def find_matching_master_bom(final_good, final_qty, operations_data):
    """
    Check if a BOM exists for this item with the exact same operations and inputs.
    This is complex, so we'll do a "good enough" check based on operations sequence and input BOMs.
    """
    # Get all active BOMs for this item
    boms = frappe.get_all("BOM", filters={"item": final_good, "is_active": 1, "docstatus": 1}, fields=["name", "quantity"])
    
    for b in boms:
        if flt(b.quantity) != final_qty:
            continue
            
        # Check operations
        bom_ops = frappe.get_all("BOM Operation", filters={"parent": b.name}, 
                                fields=["operation", "bom_no", "sequence_id", "workstation_type"], 
                                order_by="sequence_id asc")
        
        if len(bom_ops) != len(operations_data):
            continue
            
        match = True
        for i, op_data in enumerate(operations_data):
            b_op = bom_ops[i]
            # Compare basics
            if frappe.unscrub(op_data['type']) != b_op.operation:
                match = False; break
                
            # Compare sub-BOMs
            # We need to see if the sub-BOM used in this operation allows for the same inputs as op_data
            # This requires recursively checking the sub-BOMs, OR just checking if we returned an existing sub-BOM earlier.
            # Simpler approach: We can't easily check 'bom_no' against op_data without reconstructing.
            
            # Let's rely on finding/creating sub-BOMs deterministically first. 
            # If we do that, then 'bom_no' in BOM Operation will match the 'existing' sub-BOMs.
            # But here we haven't created them yet.
            
            # REVISION: We should check Phase A BOMs first in the main loop, get their names.
            # Then we can check if Master BOM uses those names.
            pass

    return None # For now, let's skip complex master matching to avoid risk. The logic below handles sub-BOM reuse.

def find_or_create_phase_a_bom(op_data):
    """
    Find an existing BOM for the output item that matches the inputs and ratios.
    """
    output_item = op_data['output_item']
    loss = flt(op_data.get('loss_percent', 0))
    
    # We construct a signature of inputs: (item, mix_percent) sorted by item
    data_inputs = sorted(op_data['inputs'], key=lambda x: x['item'])
    
    # Get candidates
    candidates = frappe.get_all("BOM", filters={"item": output_item, "is_active": 1, "docstatus": 1, "quantity": 100}, fields=["name"])
    
    for cand in candidates:
        # Check items
        bom_items = frappe.get_all("BOM Item", filters={"parent": cand.name}, fields=["item_code", "qty"])
        if len(bom_items) != len(data_inputs):
            continue
            
        bom_items_sorted = sorted(bom_items, key=lambda x: x.item_code)
        
        match = True
        for i, d_inp in enumerate(data_inputs):
            b_inp = bom_items_sorted[i]
            
            if d_inp['item'] != b_inp.item_code:
                match = False; break
            
            # Calc expected qty
            mix = flt(d_inp.get('mix', 0))
            expected_qty = (100 * (mix / 100.0)) / (1 - (loss / 100.0))
            
            if abs(flt(b_inp.qty) - expected_qty) > 0.01:
                match = False; break
        
        if match:
            return cand.name
            
    return create_phase_a_bom(op_data).name

def create_phase_a_bom(op_data):
    # Output is always 100kg for stability
    bom = frappe.new_doc("BOM")
    bom.item = op_data['output_item']
    bom.quantity = 100
    bom.with_operations = 0
    bom.track_semi_finished_goods = 0
    bom.rm_cost_as_per_valuation_rate = 1 # Use system valuation rates
    
    for inp in op_data['inputs']:
        # Formula: (100 * (Mix% / 100)) / (1 - (Loss% / 100))
        mix = flt(inp.get('mix', 0))
        loss = flt(op_data.get('loss_percent', 0))
        
        # Scaling input to 100kg output
        qty = (100 * (mix / 100.0)) / (1 - (loss / 100.0))
        
        bom.append("items", {
            "item_code": inp['item'],
            "qty": flt(qty, 3),
            "uom": frappe.db.get_value("Item", inp['item'], "stock_uom")
        })
    
    bom.insert(ignore_permissions=True)
    bom.submit()
    return bom

def create_subcontracting_bom(op_data, bom_no):
    # Check if an exact match exists (same finished good, same sub-BOM)
    exists = frappe.db.get_value("Subcontracting BOM", {
        "finished_good": op_data['output_item'],
        "finished_good_bom": bom_no,
        "is_active": 1
    }, "name")
    if exists:
        return exists
    
    # Check if there's a different Subcontracting BOM for this finished good
    # ERPNext only allows one active Subcontracting BOM per finished good
    existing_sb = frappe.db.get_value("Subcontracting BOM", {
        "finished_good": op_data['output_item'],
        "is_active": 1
    }, ["name", "finished_good_bom"], as_dict=True)
    
    if existing_sb and existing_sb.finished_good_bom != bom_no:
        # Check if any other Sales Orders are using this finished good
        # We need to find SOs that have this item and are not yet fully delivered
        other_sos = frappe.db.sql("""
            SELECT DISTINCT soi.parent
            FROM `tabSales Order Item` soi
            INNER JOIN `tabSales Order` so ON so.name = soi.parent
            WHERE soi.item_code = %s
            AND so.docstatus = 1
            AND soi.delivered_qty < soi.qty
            AND so.name != %s
        """, (op_data['output_item'], frappe.flags.get('current_sales_order', '')), as_dict=True)
        
        if other_sos:
            # There are other active SOs using this item
            so_list = ', '.join([so.parent for so in other_sos[:5]])
            if len(other_sos) > 5:
                so_list += f' and {len(other_sos) - 5} more'
            
            frappe.throw(_(
                "Cannot modify the Subcontracting BOM for {0} because other Sales Orders are using it: {1}. "
                "Changing the BOM will affect all Sales Orders for this item. "
                "Please complete or cancel those orders first, or use a different finished good item code for this variation."
            ).format(frappe.bold(op_data['output_item']), so_list))
        
        # No other SOs, safe to deactivate the old one
        frappe.db.set_value("Subcontracting BOM", existing_sb.name, "is_active", 0)
        frappe.db.commit()
    
    # Create new Subcontracting BOM
    sb = frappe.new_doc("Subcontracting BOM")
    sb.finished_good = op_data['output_item']
    sb.finished_good_qty = flt(op_data.get('output_qty', 100), 3)
    sb.finished_good_uom = frappe.db.get_value("Item", op_data['output_item'], "stock_uom")
    sb.finished_good_bom = bom_no
    sb.is_active = 1  # Set as active
    
    service_item = op_data.get('service_item')
    if not service_item:
        # Map operation types to service item names
        service_name_map = {
            'knitting': 'Knitting Jobwork',
            'dyeing': 'Dyeing Jobwork',
            'yarn_processing': 'Yarn Processing'
        }
        
        op_type = op_data['type'].lower()
        service_name = service_name_map.get(op_type)
        
        if service_name:
            service_item = frappe.db.get_value("Item", {"item_name": service_name}, "name")
        
        # Fallback to old naming conventions if not found
        if not service_item:
            service_item = frappe.db.get_value("Item", {"item_name": op_data['type']}, "name")
        if not service_item:
            # Fallback to unscrubbed name if type is 'yarn_processing' etc
            service_item = frappe.db.get_value("Item", {"item_name": frappe.unscrub(op_data['type'])}, "name")
        
    sb.service_item = service_item
    
    # service_item_qty should be equal to total raw material quantity of this operation
    total_input_qty = sum(flt(inp.get('qty', 0)) for inp in op_data.get('inputs', []))
    sb.service_item_qty = flt(total_input_qty, 3)
    sb.conversion_factor = 1
    
    sb.insert(ignore_permissions=True)
    return sb

def create_master_bom(final_good, final_qty, operations_data, bom_map):
    # Check existing before creating
    # Matching strategy: Check if a BOM exists for this item with the exact same operations (and linked sub-BOMs)
    candidates = frappe.get_all("BOM", filters={"item": final_good, "quantity": final_qty, "is_active": 1, "docstatus": 1}, fields=["name"])
    
    for cand in candidates:
        bom_ops = frappe.get_all("BOM Operation", filters={"parent": cand.name}, 
                                fields=["operation", "bom_no", "workstation_type"], 
                                order_by="sequence_id asc")
        
        if len(bom_ops) != len(operations_data):
            continue
            
        match = True
        for i, op_data in enumerate(operations_data):
            b_op = bom_ops[i]
            intended_sub_bom = bom_map.get(op_data['type'])
            
            if frappe.unscrub(op_data['type']) != b_op.operation:
                match = False; break
            
            if intended_sub_bom and b_op.bom_no != intended_sub_bom:
                match = False; break
                
            # Check workstation type if relevant
            if op_data.get('workstation_type') and b_op.workstation_type != op_data.get('workstation_type'):
                match = False; break
        
        if match:
            return frappe.get_doc("BOM", cand.name)

    bom = frappe.new_doc("BOM")
    bom.item = final_good
    bom.quantity = final_qty
    bom.with_operations = 1
    bom.track_semi_finished_goods = 1
    bom.rm_cost_as_per_valuation_rate = 1 # Use system valuation rates
    
    for i, op in enumerate(operations_data):
        is_final = (i == len(operations_data) - 1)
        
        bom.append("operations", {
            "sequence_id": i + 1,
            "operation": frappe.unscrub(op['type']),
            "finished_good": op['output_item'],
            "finished_good_qty": flt(op['output_qty'], 3),
            "is_subcontracted": 1 if op.get('is_job_work') else 0,
            "is_final_finished_good": 1 if is_final else 0,
            "bom_no": bom_map.get(op['type']),
            "time_in_mins": 60,
            "workstation_type": op.get('workstation_type')
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
        "operations": []
    }
    
    for op in bom.operations:
        op_data = {
            "type": frappe.scrub(op.operation),
            "output_item": op.finished_good,
            "output_qty": op.finished_good_qty,
            "is_job_work": op.is_subcontracted,
            "loss_percent": 0, # Calculated back
            "workstation_type": op.workstation_type,
            "inputs": []
        }
        
        # If there's a sub-BOM, get inputs from there
        if op.bom_no:
            sub_bom = frappe.get_doc("BOM", op.bom_no)
            
            # Helper to calculate loss and mix from sub-BOM items
            # Sub-BOM is standard 100kg output usually in this system
            # Logic: InputQty = (OutputQty * (Mix/100)) / (1 - Loss/100)
            # Sum(InputQty) = OutputQty / (1 - Loss/100)  [if Mix sums to 100]
            # So: TotalInput / Output = 1 / (1 - Loss/100)
            # 1 - Loss/100 = Output / TotalInput
            # Loss/100 = 1 - (Output / TotalInput)
            # Loss = 100 * (1 - Output/TotalInput)
            
            total_input = sum(flt(item.qty) for item in sub_bom.items)
            output = sub_bom.quantity
            
            if total_input > 0:
                loss_val = 100.0 * (1.0 - (flt(output) / flt(total_input)))
                op_data["loss_percent"] = max(0, float("{:.2f}".format(loss_val)))
            
            for item in sub_bom.items:
                # Calculate Mix
                # Qty = (Output * Mix/100) / (1 - Loss/100)
                # Qty * (1 - Loss/100) = Output * Mix/100
                # Mix = (Qty * (1 - Loss/100) / Output) * 100
                # Mix = (Qty / TotalInput) * 100 roughly
                
                mix_val = (flt(item.qty) / total_input) * 100
                
                op_data["inputs"].append({
                    "item": item.item_code,
                    "qty": item.qty, # This is qty for Sub-BOM output (100kg), NOT operation output. Designer recalculates.
                    "mix": float("{:.2f}".format(mix_val))
                })
                
        data["operations"].append(op_data)
        
    return data
