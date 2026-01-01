frappe.ui.form.on("Sales Order", {
    refresh(frm) {
        frm.add_custom_button(
            "Select Item by Attributes",
            () => {
                kniterp_open_item_selector({
                    on_select(item_code) {
                        let row = frm.add_child("items");
                        row.item_code = item_code;
                        frm.refresh_field("items");
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
                        let row = frm.add_child("items");
                        row.item_code = item_code;
                        frm.refresh_field("items");
                    }
                });
            }
        );
    }
});
