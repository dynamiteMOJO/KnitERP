// ======================================================
// KNITERP ITEM SELECTOR (TABLE + QUICK ADD)
// ======================================================

window.kniterp_open_item_selector = function (opts = {}) {

    const {
        title = __("Select Item by Attributes"),
        mode = "item"   // "item" | "fg"
    } = opts;

    const state = {
        classification: null,
        attributes: []   // same structure as Item Textile Attribute
    };

    const dialog = new frappe.ui.Dialog({
        title,
        size: "large",
        fields: [
            {
                fieldtype: "Select",
                fieldname: "classification",
                label: __("Item Classification"),
                options: ["Fabric", "Yarn"],
                reqd: 1,
                onchange() {
                    state.classification = dialog.get_value("classification");
                    state.attributes = [];
                    dialog.get_field("selected_attrs").$wrapper.html("");
                }
            },
            {
                fieldtype: "Data",
                fieldname: "add_attribute",
                label: __("Add Attribute"),
                placeholder: __("Type 30, ctn, lyc…")
            },

            // 👇 ADD THIS
            {
                fieldtype: "Section Break",
                label: __("Selected Attributes Preview")
            },
            {
                fieldtype: "HTML",
                fieldname: "selected_attrs"
            },

            {
                fieldtype: "Section Break",
                label: __("Matching Items")
            },
            {
                fieldtype: "HTML",
                fieldname: "results_area"
            }
        ],
        primary_action_label: __("Search"),
        primary_action() {
            search_items(state, dialog);
        }
    });

    dialog._kniterp_opts = opts;
    dialog._kniterp_mode = mode;

    dialog.show();
    setup_selector_autocomplete(dialog, state);
};

// ======================================================
// AUTOCOMPLETE (same behavior as Item form)
// ======================================================
function setup_selector_autocomplete(dialog, state) {

    const field = dialog.get_field("add_attribute");
    if (field._awesomplete) return;

    field._awesomplete = new Awesomplete(
        field.$input.get(0),
        { minChars: 1, autoFirst: true }
    );

    field.$input.on("input", frappe.utils.debounce(() => {
        const txt = field.get_value();
        if (!txt || !state.classification) return;

        frappe.call({
            method: "kniterp.api.item_selector.search_textile_attribute_values",
            args: {
                txt,
                classification: state.classification
            },
            callback: r => {
                field._awesomplete._map = {};
                field._awesomplete.list = (r.message || []).map(d => {
                    const key = `${d.kniterp_value} (${d.kniterp_attribute_name})`;
                    field._awesomplete._map[key] = d;
                    return { label: key, value: key };
                });
            }
        });
    }, 300));

    field.$input.on("awesomplete-selectcomplete", e => {
        const s = e.originalEvent?.text;
        if (!s) return;

        const d = field._awesomplete._map[s.value];
        if (!d) return;

        // prevent duplicate attribute
        if (state.attributes.some(a => a.kniterp_attribute === d.attribute)) {
            frappe.msgprint("Attribute already added");
            return;
        }

        state.attributes.push({
            kniterp_attribute: d.attribute,
            kniterp_value: d.name,
            kniterp_numeric_value: null,
            kniterp_display_value: d.kniterp_value,
            kniterp_sequence: d.kniterp_sequence,
            kniterp_affects_naming: d.kniterp_affects_naming
        });


        render_selected_attrs(dialog, state);
        auto_search_items(state, dialog);

        field.$input.val("");
        field._awesomplete.list = [];
        field.$input.focus();
    });
}

const auto_search_items = frappe.utils.debounce(
    (state, dialog) => {
        search_items(state, dialog);
    },
    300
);

function render_selected_attrs(dialog, state) {

    const sorted = state.attributes
        .filter(a => a.kniterp_affects_naming && a.kniterp_display_value)
        .sort((a, b) => (a.kniterp_sequence || 0) - (b.kniterp_sequence || 0));

    if (!sorted.length) {
        dialog.get_field("selected_attrs").$wrapper.html(
            `<div class="text-muted">Select attributes</div>`
        );
        return;
    }

    const html = `
        <div class="mb-2">
            <small class="text-muted">Preview Item Name</small>
            <div class="kniterp-preview-name">
                ${sorted.map(a => `
                    <span class="kniterp-attr-pill" data-attr="${a.kniterp_attribute}">
                        ${a.kniterp_display_value}
                        <span class="kniterp-remove-attr">✕</span>
                    </span>
                `).join(" ")}
            </div>
        </div>
    `;

    const wrapper = dialog.get_field("selected_attrs").$wrapper;
    wrapper.html(html);

    // 🔴 bind remove
    wrapper.find(".kniterp-remove-attr").on("click", function (e) {
        e.stopPropagation();
        const attr = $(this).closest(".kniterp-attr-pill").data("attr");
        remove_selected_attribute(attr, state, dialog);
    });
}

function remove_selected_attribute(attribute, state, dialog) {

    state.attributes = state.attributes.filter(
        a => a.kniterp_attribute !== attribute
    );

    render_selected_attrs(dialog, state);
    auto_search_items(state, dialog);
}

function search_items(state, dialog) {

    if (!state.attributes.length) {
        frappe.msgprint("Add at least one attribute");
        return;
    }

    frappe.call({
        method: "kniterp.api.item_selector.find_exact_items",
        args: {
            classification: state.classification,
            attributes: state.attributes.map(a => ({
                attribute: a.kniterp_attribute,
                value: a.kniterp_value
            }))
        },
        callback: r => {
            render_results(dialog, r.message || [], state);
        }
    });
}



// ======================================================
// RENDER RESULTS + CREATE ITEM
// ======================================================
function render_results(dialog, items, state) {

    const wrapper = dialog.get_field("results_area").$wrapper;

    let html = `
        <div class="mb-2">
            <button class="btn btn-primary btn-sm kniterp-create-item">
                Create New Item
            </button>
        </div>
    `;

    if (!items.length) {
        html += `<div class="text-muted">No matching items</div>`;
    } else {
        html += `
            <table class="table table-sm table-hover">
                <thead>
                    <tr>
                        <th>Item Code</th>
                        <th>Item Name</th>
                        <th>Match</th>
                    </tr>
                </thead>
                <tbody>
        `;

        items.forEach(it => {
            html += `
                <tr class="kniterp-item-row"
                    data-item="${it.item_code}">
                    <td>${it.item_code}</td>
                    <td>${it.item_name}</td>
                    <td>
                        ${it.match_count === state.attributes.length && it.total_attr_count === state.attributes.length
                    ? '<span class="badge badge-success">Exact</span>'
                    : '<span class="badge badge-warning">Partial</span>'
                }
                    </td>
                </tr>
            `;
        });

        html += `</tbody></table>`;
    }

    wrapper.html(html);

    // create always available
    wrapper.find(".kniterp-create-item").on("click", () => {
        console.log("Kniterp: Create New Item clicked", state);
        create_item_from_selector(state);
    });

    // select item
    wrapper.find(".kniterp-item-row").on("click", function () {
        const item = $(this).data("item");
        console.log("Kniterp: Item selected", item);
        dialog.hide();
        if (dialog._kniterp_opts?.on_select) {
            dialog._kniterp_opts.on_select(item);
        }
    });
}

// ======================================================
// CREATE ITEM (reuse your existing preload logic)
// ======================================================
function create_item_from_selector(state) {
    console.log("Kniterp: Preparing payload for new item", state);

    // 🔑 Use your existing preload mechanism
    sessionStorage.setItem(
        "kniterp_new_item_payload",
        JSON.stringify({
            classification: state.classification,
            textile_attributes: state.attributes
        })
    );

    console.log("Kniterp: Opening new item form in new tab");
    frappe.open_in_new_tab = true;
    frappe.set_route("Form", "Item", "new-item");
}