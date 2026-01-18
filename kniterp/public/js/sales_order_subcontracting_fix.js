function apply_subcontracting_item_filter(frm, source) {

    const grid = frm.fields_dict.items?.grid;
    if (!grid) {

        return;
    }

    const item_field = grid.get_field("item_code");
    if (!item_field) {

        return;
    }


    item_field.get_query = function (doc, cdt, cdn) {



        if (doc.is_subcontracted) {
    
            return {
                filters: {
                    is_stock_item: 0
                }
            };
        }


        return {};
    };

    // Force editor rebuild
    grid.refresh();
}

frappe.ui.form.on("Sales Order", {
    onload(frm) {

        apply_subcontracting_item_filter(frm, "onload");
    },

    onload_post_render(frm) {

        apply_subcontracting_item_filter(frm, "onload_post_render");
    },

    refresh(frm) {

        apply_subcontracting_item_filter(frm, "refresh");
    },

    is_subcontracted(frm) {

        apply_subcontracting_item_filter(frm, "is_subcontracted");
    }
});
