window.kniterp_attach_item_selector = function (opts) {
    const {
        frm,
        label = "Select Item by Attributes",
        child_table = "items",
        item_field = "item_code"
    } = opts;

    frm.add_custom_button(label, () => {
        kniterp_open_item_selector({
            on_select(item_code) {
                let row = frm.doc[child_table]?.find(r => !r[item_field]);

                if (!row) {
                    row = frm.add_child(child_table);
                }

                frappe.model.set_value(
                    row.doctype,
                    row.name,
                    item_field,
                    item_code
                );
            }
        });
    });
};

frappe.ui.form.on("Sales Order", {
    refresh(frm) {
        kniterp_attach_item_selector({ frm });
    }
});

frappe.ui.form.on("Purchase Order", {
    refresh(frm) {
        kniterp_attach_item_selector({ frm });
    }
});

frappe.ui.form.on("Delivery Note", {
    refresh(frm) {
        kniterp_attach_item_selector({ frm });
    }
});
