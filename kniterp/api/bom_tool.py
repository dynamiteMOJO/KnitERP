import frappe
from frappe import _
from frappe.utils import flt

@frappe.whitelist()
def create_multilevel_bom(data):
    if isinstance(data, str):
        data = frappe.parse_json(data)
    
    final_good = data.get('final_good')
    final_qty = data.get('final_qty', 100)
    operations_data = data.get('operations', [])
    
    # Detailed logging for debugging rates
    frappe.log_error(title="BOM Designer Data", message=frappe.as_json(data))
    
    bom_map = {} # Type -> BOM Name
    
    # Phase A: Create Sub-BOMS (100kg output)
    for op in operations_data:
        bom = create_phase_a_bom(op)
        bom_map[op['type']] = bom.name
        
        # Phase B: Create Subcontracting BOM if job work
        if op.get('is_job_work'):
            create_subcontracting_bom(op, bom.name)
            
    # Phase C: Create Master BOM
    create_master_bom(final_good, final_qty, operations_data, bom_map)
    
    return {"message": "BOMs Created Successfully"}

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
    sb = frappe.new_doc("Subcontracting BOM")
    sb.finished_good = op_data['output_item']
    sb.finished_good_qty = flt(op_data.get('output_qty', 100), 3)
    sb.finished_good_uom = frappe.db.get_value("Item", op_data['output_item'], "stock_uom")
    sb.finished_good_bom = bom_no
    
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
