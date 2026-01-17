window.kniterp_attach_item_selector = function (opts) {
    const {
        frm,
        label = __("Select Item by Attributes"),
        child_table = "items",
        item_field = "item_code",
        condition = () => true
    } = opts;

    // avoid duplicate buttons
    if (frm._kniterp_btn_added) return;
    frm._kniterp_btn_added = true;

    frm.add_custom_button(label, () => {
        if (!condition(frm)) return;

        kniterp_open_item_selector({
            on_select(item_code) {
                let row = frm.doc[child_table]?.find(r => !r[item_field]);
                if (!row) row = frm.add_child(child_table);

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


function kniterp_bind_item_dblclick({
    frm,
    child_table = "items",
    item_field = "item_code",
    condition = () => true
}) {
    if (frm._kniterp_dblclick_bound) return;
    frm._kniterp_dblclick_bound = true;

    const grid = frm.fields_dict[child_table]?.grid;
    if (!grid || !grid.wrapper) return;

    // Tooltip
    grid.wrapper.on(
        "mouseenter",
        `input[data-fieldname="${item_field}"]`,
        function () {
            if (!condition(frm)) return;
            $(this).attr(
                "title",
                __("Double-click to select item by attributes")
            );
        }
    );

    // Double-click
    grid.wrapper.on(
        "dblclick",
        `input[data-fieldname="${item_field}"]`,
        function (e) {
            if (!condition(frm)) return;

            e.preventDefault();
            e.stopPropagation();

            const cdn = $(this).closest(".grid-row").attr("data-name");
            if (!cdn) return;

            kniterp_open_item_selector({
                on_select(item_code) {
                    frappe.model.set_value(
                        grid.doctype,
                        cdn,
                        item_field,
                        item_code
                    );
                }
            });
        }
    );
}

frappe.ui.form.on("Sales Order", {
    refresh(frm) {
        // Button (safety net)
        kniterp_attach_item_selector({
            frm,
            condition: frm => !frm.doc.is_subcontracted
        });

        // Double-click (main)
        kniterp_bind_item_dblclick({
            frm,
            condition: frm => !frm.doc.is_subcontracted
        });
    }
});

frappe.ui.form.on("Purchase Order", {
    refresh(frm) {
        // Button (safety net)
        kniterp_attach_item_selector({
            frm,
            condition: frm => !frm.doc.is_subcontracted
        });

        // Double-click (main)
        kniterp_bind_item_dblclick({
            frm,
            condition: frm => !frm.doc.is_subcontracted
        });
    }
});

frappe.ui.form.on("Delivery Note", {
    refresh(frm) {
        // Button (safety net)
        kniterp_attach_item_selector({
            frm,
            condition: frm => !frm.doc.is_subcontracted
        });

        // Double-click (main)
        kniterp_bind_item_dblclick({
            frm,
            condition: frm => !frm.doc.is_subcontracted
        });
    }
});


window.kniterp_open_fg_selector = function ({
    subcontracting_boms,
    on_select
}) {
    kniterp_open_item_selector({
        title: __("Select Finished Good"),
        mode: "fg",
        on_select(item_code) {

            const bom = Object.values(subcontracting_boms)
                .find(b => b.finished_good === item_code);

            if (!bom) {
                frappe.msgprint(__("Invalid finished good selected"));
                return;
            }

            on_select(bom);
        }
    });
};


window.kniterp_handle_subcontracted_service_item = async function ({
    frm,
    row,
    set_fg
}) {
    if (!frm.doc.is_subcontracted) return;
    if (!row.item_code || row.fg_item) return;

    const result =
        await frm.events.get_subcontracting_boms_for_service_item(row.item_code);    

    if (!result?.message) return;

    const finished_goods = Object.keys(result.message);
    if (!finished_goods.length) return;

    // single FG → auto-set
    if (finished_goods.length === 1) {
        const bom = result.message[finished_goods[0]];
        set_fg(bom);
        return;
    }

    // ✅ multiple FG → open selector
    row.fg_item = "__KNITERP_PENDING__";

    kniterp_open_fg_selector({
        subcontracting_boms: result.message,
        on_select: (bom) => {
            // overwrite dummy value
            frappe.model.set_value(row.doctype, row.name, "fg_item", bom.finished_good);
            frappe.model.set_value(row.doctype, row.name, "uom", bom.finished_good_uom);
            refresh_field("items");
        }
    });

    return;
};


frappe.ui.form.on("Sales Order Item", {
    item_code: async function (frm, cdt, cdn) {
        const row = locals[cdt][cdn];

        // keep ERPNext logic
        if (frm.doc.delivery_date) {
            row.delivery_date = frm.doc.delivery_date;
            refresh_field("delivery_date", cdn, "items");
        } else {
            frm.script_manager.copy_from_first_row("items", row, ["delivery_date"]);
        }

        await kniterp_handle_subcontracted_service_item({
            frm,
            row,
            set_fg: (bom) => {
                frappe.model.set_value(row.doctype, row.name, "fg_item", bom.finished_good);
                frappe.model.set_value(row.doctype, row.name, "uom", bom.finished_good_uom);
                refresh_field("items");
            }
        });
    }
});


frappe.ui.form.on("Purchase Order Item", {
    item_code: async function (frm, cdt, cdn) {

        const row = locals[cdt][cdn];

        await kniterp_handle_subcontracted_service_item({
            frm,
            row,
            set_fg: (bom) => {
                frappe.model.set_value(row.doctype, row.name, "fg_item", bom.finished_good);
                frappe.model.set_value(row.doctype, row.name, "uom", bom.finished_good_uom);
                refresh_field("items");
            }
        });
    }
});
