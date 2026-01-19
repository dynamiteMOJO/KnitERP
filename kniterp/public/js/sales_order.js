frappe.ui.form.on("Sales Order", {
    refresh(frm) {
        if (frm.doc.docstatus === 1 && frm.doc.is_subcontracted) {
            frm.add_custom_button(
                __("Subcontracted Purchase Order"),
                () => {
                    open_subcontract_po_dialog(frm);
                },
                __("Create")
            );
        }
    }
});

function open_subcontract_po_dialog(frm) {
    

    frappe.call({
        method: "kniterp.api.subcontracting.get_subcontract_po_items",
        args: { sales_order: frm.doc.name },
        freeze: true,
        callback(r) {
            open_subcontract_po_dialog_ui(frm, r.message);
        }
    });
}

function open_subcontract_po_dialog_ui(frm, items) {
    

    const dialog = new frappe.ui.Dialog({
        title: __("Create Subcontracted Purchase Order"),
        size: "large",
        fields: [
            {
                fieldtype: "Link",
                fieldname: "supplier",
                label: __("Supplier"),
                options: "Supplier",
                reqd: 1
            },
            {
                fieldtype: "Table",
                fieldname: "items",
                label: __("Items"),
                cannot_add_rows: true,
                in_place_edit: false,
                data: items,
                fields: [
                    {
                        fieldtype: "Check",
                        fieldname: "select",
                        label: __("Select"),
                        in_list_view: 1
                    },
                    {
                        fieldtype: "Data",
                        fieldname: "service_item",
                        label: "Service Item",
                        read_only: 1,
                        in_list_view: 1
                    },
                    {
                        fieldtype: "Data",
                        fieldname: "service_item_name",
                        label: "Service Name",
                        read_only: 1,
                        in_list_view: 1
                    },
                    {
                        fieldtype: "Data",
                        fieldname: "fg_item",
                        label: "Finished Good",
                        read_only: 1,
                        in_list_view: 1
                    },
                    {
                        fieldtype: "Float",
                        fieldname: "fg_qty",
                        label: "FG Qty",
                        read_only: 1,
                        in_list_view: 1
                    },
                    {
                        fieldtype: "Float",
                        fieldname: "service_qty",
                        label: "Service Qty",
                        read_only: 1,
                        in_list_view: 1
                    },
                    {
                        fieldtype: "Date",
                        fieldname: "delivery_date",
                        label: "Delivery Date",
                        read_only: 1,
                        in_list_view: 1
                    }
                ]
            }
        ],
        primary_action_label: __("Create Purchase Order"),
        primary_action(values) {
            
            create_subcontract_po(frm, values);
            dialog.hide();
        }
    });

    dialog.show();
}


function create_subcontract_po(frm, values) {
    const selected = values.items.filter(i => i.select);

    if (!selected.length) {
        frappe.throw("Select at least one service item");
    }

    frappe.call({
        method: "kniterp.api.subcontracting.make_subcontract_purchase_order",
        args: {
            sales_order: frm.doc.name,
            supplier: values.supplier,
            items: selected
        },
        freeze: true
    }).then(r => {
        frappe.set_route("Form", "Purchase Order", r.message);
    });
}
