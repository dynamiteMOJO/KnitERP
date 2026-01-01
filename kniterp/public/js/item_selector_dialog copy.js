// ===============================
// 1️⃣ STATE
// ===============================
let kniterp_selector_state = {
    classification: null,
    attributes: {}
};

// ===============================
// 2️⃣ HELPER FUNCTIONS (DECLARE FIRST)
// ===============================

function render_attribute_inputs(dialog, attributes) {
    if (!attributes.length) {
        dialog.fields_dict.attribute_area.$wrapper.html(
            `<div class="text-muted">No attributes found</div>`
        );
        return;
    }

    let html = `<div class="kniterp-attr-grid">`;

    attributes.forEach(attr => {
        html += `
            <div class="form-group">
                <label class="control-label">
                    ${attr.kniterp_attribute_name}
                </label>
                ${render_input_for_type(attr)}
            </div>
        `;
    });

    html += `</div>`;

    dialog.fields_dict.attribute_area.$wrapper.html(html);

    attributes.forEach(attr => {
        bind_attribute_change(dialog, attr);
    });
}

function render_input_for_type(attr) {
    if (attr.kniterp_field_type === "Select") {
        return `
            <select class="form-control"
                data-attribute="${attr.name}">
                <option value="">Select</option>
            </select>
        `;
    }

    if (["Int", "Float"].includes(attr.kniterp_field_type)) {
        return `
            <input type="number"
                class="form-control"
                data-attribute="${attr.name}" />
        `;
    }

    return `<input type="text" class="form-control" disabled />`;
}

function populate_select_options(attr_name, select_el) {
    frappe.call({
        method: "kniterp.api.textile_attributes.get_attribute_values",
        args: { attribute: attr_name },
        callback(r) {
            (r.message || []).forEach(v => {
                select_el.append(
                    `<option value="${v.name}"
                        data-short-code="${v.kniterp_short_code || ""}">
                        ${v.kniterp_value}
                    </option>`
                );
            });
        }
    });
}


function bind_attribute_change(dialog, attr) {
    const el = dialog.fields_dict.attribute_area.$wrapper
        .find(`[data-attribute="${attr.name}"]`);

    if (attr.kniterp_field_type === "Select") {
        populate_select_options(attr.name, el);
    }

    el.on("change", function () {
        kniterp_selector_state.attributes[attr.name] = {
            attribute: attr.name,
            field_type: attr.kniterp_field_type,
            value: $(this).val() || null
        };

        update_selector_preview(dialog);
    });
}

function update_selector_preview(dialog) {
    const parts = [];

    Object.values(kniterp_selector_state.attributes).forEach(a => {
        if (a.value) parts.push(a.value);
    });

    dialog.set_value("preview_name", parts.join(" "));
    dialog.set_value("preview_code", "");
    search_exact_items(dialog);
}

// ===============================
// 3️⃣ SERVER LOADER
// ===============================
function load_textile_attributes(dialog, classification) {

    kniterp_selector_state.attributes = {};
    kniterp_selector_state.classification = classification;

    dialog.fields_dict.attribute_area.$wrapper.html(
        `<div class="text-muted">Loading attributes…</div>`
    );

    frappe.call({
        method: "kniterp.api.textile_attributes.get_textile_attributes_for",
        args: { classification },
        callback(r) {
            render_attribute_inputs(dialog, r.message || []);
        }
    });
}


function search_exact_items(dialog) {

    const attrs = [];

    Object.values(kniterp_selector_state.attributes).forEach(a => {
        if (!a.value) return;

        if (a.field_type === "Select") {
            attrs.push({
                attribute: a.attribute,
                value: a.value
            });
        } else {
            attrs.push({
                attribute: a.attribute,
                numeric_value: a.value
            });
        }
    });

    if (!attrs.length) {
        dialog.fields_dict.results_area.$wrapper.html(
            `<div class="text-muted">Select attributes to search</div>`
        );
        return;
    }

    frappe.call({
        method: "kniterp.api.item_selector.find_exact_items",
        args: {
            classification: kniterp_selector_state.classification,
            attributes: attrs
        },
        callback(r) {
            render_search_results(dialog, r.message || []);
        }
    });
}

function create_new_item_from_selector(dialog) {

    const attrs = [];

    Object.values(kniterp_selector_state.attributes).forEach(a => {
        if (!a.value) return;

        if (a.field_type === "Select") {
            attrs.push({
                kniterp_attribute: a.attribute,
                kniterp_value: a.value
            });
        } else {
            attrs.push({
                kniterp_attribute: a.attribute,
                kniterp_numeric_value: a.value
            });
        }
    });

    const payload = {
        classification: kniterp_selector_state.classification,
        textile_attributes: attrs
    };

    // console.log("KNITERP FINAL PAYLOAD:", payload);

    // 🔐 STORE SAFELY
    sessionStorage.setItem(
        "kniterp_new_item_payload",
        JSON.stringify(payload)
    );

    dialog.hide();
    frappe.set_route("Form", "Item", "new-item");

    frappe.new_doc("Item", {}, itm => {
        itm.sales_invoice_id = frm.doc.name;
        itm.customer = frm.doc.customer;
        itm.company = frm.doc.company;
        itm.invoice_date = frm.doc.posting_date;
        attrs.forEach(attr => {
            let item_attr = frappe.model.add_child(itm, 'invoice_items');
            item_attr.item_code = attr.item_code;
            item_attr.item_name = attr.item_name;
            item_attr.qty = attr.qty;
            item_attr.uom = attr.uom;
            item_attr.rate = attr.rate;
            item_attr.am = attr.rate;

        });

    });
}

function render_search_results(dialog, items) {

    const wrapper = dialog.fields_dict.results_area.$wrapper;

    if (!items.length) {
        wrapper.html(`
            <div class="text-muted mb-2">
                No exact match found
            </div>
            <button class="btn btn-sm btn-primary kniterp-create-item">
                Create New Item
            </button>
        `);

        wrapper.find(".kniterp-create-item").on("click", () => {
            create_new_item_from_selector(dialog);
        });

        return;
    }

    if (!items.length) {
        dialog.fields_dict.results_area.$wrapper.html(
            `<div class="text-muted">No exact match found</div>`
        );
        return;
    }

    let html = `
        <table class="table table-bordered">
            <thead>
                <tr>
                    <th>Item Code</th>
                    <th>Item Name</th>
                </tr>
            </thead>
            <tbody>
    `;

    items.forEach(it => {
        html += `
            <tr class="kniterp-item-row" data-item="${it.item_code}">
                <td>${it.item_code}</td>
                <td>${it.item_name}</td>
            </tr>
        `;
    });

    html += `</tbody></table>`;

    dialog.fields_dict.results_area.$wrapper.html(html);

    // click to select
    dialog.fields_dict.results_area.$wrapper
        .find(".kniterp-item-row")
        .on("click", function () {
            const item = $(this).data("item");
            dialog.selected_item = item;
            $(this).addClass("table-active").siblings().removeClass("table-active");
        });
}

// ===============================
// 4️⃣ DIALOG OPENER (LAST)
// ===============================
window.kniterp_open_item_selector = function (opts = {}) {

    const dialog = new frappe.ui.Dialog({
        title: "Select Item by Attributes",
        size: "extra-large",
        fields: [
            {
                fieldtype: "Select",
                label: "Item Classification",
                fieldname: "classification",
                options: ["Fabric", "Yarn"],
                reqd: 1,
                onchange() {
                    load_textile_attributes(
                        dialog,
                        dialog.get_value("classification")
                    );
                }
            },
            { fieldtype: "Section Break", label: "Attributes" },
            { fieldtype: "HTML", fieldname: "attribute_area" },
            { fieldtype: "Section Break", label: "Preview" },
            {
                fieldtype: "Data",
                fieldname: "preview_name",
                label: "Preview Item Name",
                read_only: 1
            },
            {
                fieldtype: "Data",
                fieldname: "preview_code",
                label: "Preview Item Code",
                read_only: 1
            },

            { fieldtype: "Section Break", label: "Matching Items" },
            {
                fieldtype: "HTML",
                fieldname: "results_area"
            }
        ],
        primary_action_label: "Select Item",
        primary_action() {

            if (!dialog.selected_item) {
                frappe.msgprint("Please select an item from the list");
                return;
            }

            if (opts.on_select) {
                opts.on_select(dialog.selected_item);
            }

            dialog.hide();
        }
    });

    dialog.show();
};