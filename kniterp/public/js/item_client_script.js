frappe.ui.form.on("Item", {
    refresh(frm) {
        const field = frm.get_field("custom_add_attribute");
        if (!field || field._awesomplete) return;

        field._awesomplete = new Awesomplete(
            field.$input.get(0),
            { minChars: 1, autoFirst: true }
        );

        field._awesomplete._item_map = {};

        bind_attribute_input(frm, field);
    }
});

function bind_attribute_input(frm, field) {
    field.$input.on(
        "input",
        frappe.utils.debounce(() => {
            const txt = field.get_value();
            if (!txt) {
                field._awesomplete.list = [];
                return;
            }

            frappe.call({
                method: "kniterp.api.item_selector.search_textile_attribute_values",
                args: {
                    txt,
                    classification: frm.doc.custom_item_classification
                },
                callback: r => {
                    field._awesomplete._item_map = {};

                    field._awesomplete.list = (r.message || []).map(d => {
                        const key = `${d.kniterp_value} (${d.kniterp_attribute_name})`;
                        field._awesomplete._item_map[key] = d;

                        return {
                            label: key,
                            value: key
                        };
                    });
                }
            });
        }, 300)
    );

    bind_attribute_select(frm, field);
}

function bind_attribute_select(frm, field) {
    field.$input.on("awesomplete-selectcomplete", function (e) {
        const suggestion = e.originalEvent?.text;
        if (!suggestion) return;

        const key = suggestion.value;
        const data = field._awesomplete._item_map[key];
        if (!data) return;

        add_textile_attribute_row(frm, data);

        // Clear UI only (do NOT use set_value)
        field.$input.val("");
        field._awesomplete.list = [];

        // Keep cursor active
        setTimeout(() => field.$input.focus(), 0);
    });
}


function add_textile_attribute_row(frm, data) {
    // Prevent duplicate attribute
    if (
        frm.doc.custom_textile_attributes?.some(
            r => r.kniterp_attribute === data.attribute
        )
    ) {
        frappe.msgprint(__("Attribute already added"));
        return;
    }

    const row = frm.add_child("custom_textile_attributes");

    frappe.model.set_value(
        row.doctype,
        row.name,
        "kniterp_attribute",
        data.attribute
    );

    frappe.model.set_value(
        row.doctype,
        row.name,
        "kniterp_value",
        data.name
    );

    frm.refresh_field("custom_textile_attributes");
}