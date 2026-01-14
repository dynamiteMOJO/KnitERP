frappe.ui.form.on("Sales Order", {
    refresh(frm) {
        frm.add_custom_button(
            "Select Item by Attributes",
            () => {
                kniterp_open_item_selector({
                    on_select(item_code) {
                        let row = frm.doc.items.find(r => !r.item_code);

                        if (!row) {
                            row = frm.add_child("items");
                        }

                        frappe.model.set_value(
                            row.doctype,
                            row.name,
                            "item_code",
                            item_code
                        );
                    }
                });
            }
        );
    }
});

frappe.ui.form.on("Purchase Order", {
    refresh(frm) {
        frm.add_custom_button(
            "Select Item by Attributes",
            () => {
                kniterp_open_item_selector({
                    on_select(item_code) {
                        let row = frm.doc.items.find(r => !r.item_code);

                        if (!row) {
                            row = frm.add_child("items");
                        }

                        frappe.model.set_value(
                            row.doctype,
                            row.name,
                            "item_code",
                            item_code
                        );
                    }
                });
            }
        );
    }
});
