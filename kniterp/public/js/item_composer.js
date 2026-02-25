// ======================================================
// KNITERP ITEM COMPOSER — Phase 2
// Structured dialog for creating new items
// ======================================================

window.kniterp_open_item_composer = function (opts = {}) {
    const {
        on_select = null,
        prefill = {},
        classification = "Fabric",
        quick_fill_text = ""
    } = opts;

    frappe.call({
        method: "kniterp.api.item_composer.get_composer_options",
        callback(r) {
            const options = r.message || {};
            _show_composer_dialog(options, on_select, prefill, classification, quick_fill_text);
        }
    });
};


// ──────────────────────────────────────────────
// BUILD & SHOW DIALOG
// ──────────────────────────────────────────────
function _show_composer_dialog(options, on_select, prefill, initial_classification, quick_fill_text) {

    // Build autocomplete option lists per dimension
    const ac_lists = {};
    for (const dim of ["count", "fiber", "modifier", "structure", "lycra", "state"]) {
        ac_lists[dim] = (options[dim] || []).map(t => t.canonical);
    }

    const dialog = new frappe.ui.Dialog({
        title: __("Create New Item"),
        size: "large",
        fields: [
            // ── Row 1: Classification + Item Group + HSN ──
            {
                fieldtype: "Select",
                fieldname: "classification",
                label: __("Classification"),
                options: ["Fabric", "Yarn", "Other"],
                default: initial_classification,
                reqd: 1,
                onchange() { _toggle_fields(dialog); _update_preview(dialog); }
            },
            { fieldtype: "Column Break" },
            {
                fieldtype: "Link",
                fieldname: "item_group",
                label: __("Item Group"),
                options: "Item Group",
                reqd: 1,
                get_query() { return { filters: { is_group: 0 } }; }
            },
            { fieldtype: "Column Break" },
            {
                fieldtype: "Link",
                fieldname: "hsn_code",
                label: __("HSN Code"),
                options: "GST HSN Code",
                reqd: 1,
            },

            // ── QUICK FILL ──
            {
                fieldtype: "Section Break",
                fieldname: "quick_fill_section",
                label: __("Quick Fill — type what you know"),
            },
            {
                fieldtype: "Data",
                fieldname: "quick_fill",
                label: __("Quick Fill"),
                placeholder: __("e.g. 30 ctn slub sj raw — then press Enter"),
                description: __("Type any terms (aliases, short codes, names). Slots will auto-fill."),
            },
            { fieldtype: "Column Break" },
            { fieldtype: "HTML", fieldname: "quick_fill_btn" },
            { fieldtype: "HTML", fieldname: "quick_fill_result" },

            // ── TEXTILE SECTION ──
            {
                fieldtype: "Section Break",
                fieldname: "textile_section",
                label: __("Item Attributes"),
            },
            {
                fieldtype: "Autocomplete",
                fieldname: "count",
                label: __("Count"),
                options: ac_lists.count,
                onchange() { _update_preview(dialog); }
            },
            { fieldtype: "HTML", fieldname: "count_add_btn" },
            { fieldtype: "Column Break" },
            {
                fieldtype: "Autocomplete",
                fieldname: "fiber",
                label: __("Fiber"),
                options: ac_lists.fiber,
                onchange() { _update_preview(dialog); }
            },
            { fieldtype: "HTML", fieldname: "fiber_add_btn" },

            { fieldtype: "Section Break" },
            {
                fieldtype: "Autocomplete",
                fieldname: "modifier1",
                label: __("Modifier 1"),
                options: ac_lists.modifier,
                onchange() {
                    _filter_modifier2(dialog, ac_lists.modifier);
                    _update_preview(dialog);
                }
            },
            { fieldtype: "HTML", fieldname: "modifier_add_btn" },
            { fieldtype: "Column Break" },
            {
                fieldtype: "Autocomplete",
                fieldname: "modifier2",
                label: __("Modifier 2"),
                options: ac_lists.modifier,
                onchange() { _update_preview(dialog); }
            },

            { fieldtype: "Section Break", fieldname: "structure_section" },
            {
                fieldtype: "Autocomplete",
                fieldname: "structure",
                label: __("Structure"),
                options: ac_lists.structure,
                onchange() { _update_preview(dialog); }
            },
            { fieldtype: "HTML", fieldname: "structure_add_btn" },
            { fieldtype: "Column Break" },
            {
                fieldtype: "Autocomplete",
                fieldname: "lycra",
                label: __("Lycra / Denier"),
                options: ac_lists.lycra,
                onchange() { _update_preview(dialog); }
            },

            { fieldtype: "Section Break", fieldname: "state_section" },
            {
                fieldtype: "Autocomplete",
                fieldname: "state",
                label: __("State / Finish"),
                options: ac_lists.state,
                onchange() { _update_preview(dialog); }
            },
            { fieldtype: "Column Break" },
            // empty col for layout balance
            { fieldtype: "HTML", fieldname: "state_spacer" },

            // ── OTHER SECTION ──
            {
                fieldtype: "Section Break",
                fieldname: "other_section",
                label: __("Item Details"),
                hidden: 1,
            },
            {
                fieldtype: "Data",
                fieldname: "other_item_name",
                label: __("Item Name"),
            },
            {
                fieldtype: "Data",
                fieldname: "other_item_code",
                label: __("Item Code"),
            },
            { fieldtype: "Column Break" },
            {
                fieldtype: "Link",
                fieldname: "other_uom",
                label: __("UOM"),
                options: "UOM",
                default: "Nos",
            },
            {
                fieldtype: "Check",
                fieldname: "other_is_stock",
                label: __("Is Stock Item"),
                default: 1,
            },

            // ── PREVIEW ──
            {
                fieldtype: "Section Break",
                label: __("Preview"),
            },
            {
                fieldtype: "HTML",
                fieldname: "preview_area",
            },
        ],
        primary_action_label: __("Create & Select"),
        primary_action() {
            _create_item(dialog, on_select);
        },
    });

    dialog._composer_options = options;
    dialog._ac_lists = ac_lists;
    dialog._composer_on_select = on_select;
    dialog.show();

    // Setup awesomplete alias matching on autocomplete fields
    _setup_alias_autocomplete(dialog, options);

    // Add "+ Add New" buttons
    _setup_add_new_buttons(dialog, options);

    // Set initial field visibility
    _toggle_fields(dialog);

    // Setup Quick Fill
    _setup_quick_fill(dialog);

    // Apply prefill
    if (prefill.count) dialog.set_value("count", prefill.count);
    if (prefill.fiber) dialog.set_value("fiber", prefill.fiber);
    if (prefill.modifier) dialog.set_value("modifier1", prefill.modifier);
    if (prefill.structure) dialog.set_value("structure", prefill.structure);
    if (prefill.state) dialog.set_value("state", prefill.state);
    if (prefill.lycra) dialog.set_value("lycra", prefill.lycra);

    // Auto Quick Fill if text was provided (e.g., from Link field)
    if (quick_fill_text) {
        dialog.set_value("quick_fill", quick_fill_text);
        // Trigger quick fill after a short delay to let dialog render
        setTimeout(() => _do_quick_fill(dialog), 300);
    }
}


// ──────────────────────────────────────────────
// QUICK FILL — resolve free text into slots
// ──────────────────────────────────────────────
function _setup_quick_fill(dialog) {
    // Add "Fill Slots" button
    const btn_wrapper = dialog.get_field("quick_fill_btn")?.$wrapper;
    if (btn_wrapper) {
        btn_wrapper.html(`
            <button class="btn btn-sm btn-primary mt-4">
                <i class="fa fa-magic"></i> ${__("Fill Slots")}
            </button>
        `);
        btn_wrapper.find("button").on("click", () => _do_quick_fill(dialog));
    }

    // Enter key on the text field
    const qf_field = dialog.fields_dict.quick_fill;
    if (qf_field && qf_field.$input) {
        qf_field.$input.on("keydown", function (e) {
            if (e.key === "Enter") {
                e.preventDefault();
                _do_quick_fill(dialog);
            }
        });
    }
}


function _do_quick_fill(dialog) {
    const text = dialog.get_value("quick_fill");
    if (!text || !text.trim()) return;

    const result_wrapper = dialog.get_field("quick_fill_result")?.$wrapper;

    // Clear all dimension slots first
    ["count", "fiber", "modifier1", "modifier2", "structure", "lycra", "state"].forEach(f => {
        dialog.set_value(f, "");
    });

    frappe.call({
        method: "kniterp.api.item_composer.resolve_for_composer",
        args: { text },
        callback(r) {
            if (!r.message) return;

            const { resolved, unresolved } = r.message;

            // Fill slots from resolved values
            const slot_map = {
                count: "count",
                fiber: "fiber",
                modifier1: "modifier1",
                modifier2: "modifier2",
                structure: "structure",
                lycra: "lycra",
                state: "state",
            };

            for (const [key, val] of Object.entries(resolved)) {
                const field_name = slot_map[key] || key;
                if (dialog.fields_dict[field_name]) {
                    dialog.set_value(field_name, val);
                }
            }

            // Show feedback
            let feedback = "";
            const resolved_count = Object.keys(resolved).length;

            if (resolved_count) {
                const filled = Object.entries(resolved)
                    .map(([k, v]) => `<strong>${k}</strong>: ${v}`)
                    .join(", ");
                feedback += `<div class="text-success text-small mt-2">
                    <i class="fa fa-check"></i> Filled ${resolved_count} slots: ${filled}
                </div>`;
            }

            if (unresolved.length) {
                const btns = unresolved.map(t =>
                    `<button class="btn btn-xs btn-warning ml-1 kniterp-add-unresolved"
                             data-token="${frappe.utils.escape_html(t)}"
                             style="margin: 2px;">
                        <i class="fa fa-plus"></i> ${frappe.utils.escape_html(t)}
                    </button>`
                ).join("");

                feedback += `<div class="text-small mt-1">
                    <i class="fa fa-exclamation-triangle text-warning"></i>
                    Not recognized — click to add: ${btns}
                </div>`;
            }

            if (result_wrapper) {
                result_wrapper.html(feedback);

                // Bind click handlers for unresolved token buttons
                result_wrapper.find(".kniterp-add-unresolved").on("click", function () {
                    const token_text = $(this).data("token");
                    _open_add_token_from_quick_fill(token_text, dialog);
                });
            }

            _update_preview(dialog);
        }
    });
}


function _open_add_token_from_quick_fill(token_text, parent_dialog) {
    const options = parent_dialog._composer_options || {};

    const add_dialog = new frappe.ui.Dialog({
        title: __("Add: {0}", [token_text]),
        fields: [
            {
                fieldtype: "Data",
                fieldname: "canonical",
                label: __("Display Name"),
                reqd: 1,
                default: token_text,
            },
            {
                fieldtype: "Select",
                fieldname: "dimension",
                label: __("Dimension"),
                reqd: 1,
                options: ["count", "fiber", "modifier", "structure", "lycra", "state"],
                description: __("What type of attribute is this?"),
            },
            {
                fieldtype: "Data",
                fieldname: "short_code",
                label: __("Short Code"),
                reqd: 1,
                description: __("For item code, e.g. 'BMB'"),
            },
            {
                fieldtype: "Small Text",
                fieldname: "aliases",
                label: __("Aliases"),
                default: token_text,
                description: __("Comma-separated. The original typed text is pre-filled."),
            },
        ],
        primary_action_label: __("Add"),
        primary_action(values) {
            frappe.call({
                method: "kniterp.api.item_composer.add_new_token",
                args: {
                    canonical: values.canonical,
                    dimension: values.dimension,
                    short_code: values.short_code,
                    aliases: values.aliases || "",
                },
                freeze: true,
                callback(r) {
                    if (r.message) {
                        frappe.show_alert({
                            message: __("Added: {0}", [r.message.canonical]),
                            indicator: "green"
                        });
                        add_dialog.hide();

                        // Refresh dropdown and fill the slot
                        _refresh_autocomplete(parent_dialog, values.dimension, r.message.canonical);
                    }
                }
            });
        },
    });

    add_dialog.show();
}


// ──────────────────────────────────────────────
// ALIAS-AWARE AUTOCOMPLETE
// Overrides awesomplete filter so typing an alias
// (e.g., "ctn") will show "Cotton" in the dropdown
// ──────────────────────────────────────────────
function _setup_alias_autocomplete(dialog, options) {
    const fields = ["count", "fiber", "modifier1", "modifier2", "structure", "lycra", "state"];
    const dim_map = {
        count: "count", fiber: "fiber", modifier1: "modifier",
        modifier2: "modifier", structure: "structure",
        lycra: "lycra", state: "state"
    };

    fields.forEach(fname => {
        const field = dialog.fields_dict[fname];
        if (!field || !field.$input) return;

        const dim = dim_map[fname];
        const dim_tokens = options[dim] || [];

        // Build a lookup: alias → canonical
        const alias_to_canonical = {};
        dim_tokens.forEach(t => {
            // Short code also works as search term
            alias_to_canonical[t.short_code.toLowerCase()] = t.canonical;
            (t.aliases || []).forEach(a => {
                alias_to_canonical[a.toLowerCase()] = t.canonical;
            });
        });

        // Override the awesomplete filter
        const aw = field.awesomplete;
        if (aw) {
            aw.filter = function (text, input) {
                const q = input.toLowerCase().trim();
                if (!q) return true; // show all when empty
                const label = text.value.toLowerCase();
                // Match canonical name directly
                if (label.includes(q)) return true;
                // Match via aliases
                for (const [alias, canonical] of Object.entries(alias_to_canonical)) {
                    if (alias.includes(q) && canonical === text.value) return true;
                }
                return false;
            };
        }
    });
}


// ──────────────────────────────────────────────
// TOGGLE FIELDS BASED ON CLASSIFICATION
// Uses set_df_property for reliable Frappe dialog toggling
// ──────────────────────────────────────────────
function _toggle_fields(dialog) {
    const cls = dialog.get_value("classification");
    const is_textile = (cls === "Fabric" || cls === "Yarn");
    const is_yarn = (cls === "Yarn");

    // Textile fields
    const textile_fields = [
        "textile_section", "count", "count_add_btn",
        "fiber", "fiber_add_btn",
        "modifier1", "modifier_add_btn", "modifier2",
        "state_section", "state", "state_spacer",
    ];

    // Structure fields (hidden for Yarn)
    const structure_fields = [
        "structure_section", "structure", "structure_add_btn", "lycra",
    ];

    // Other fields
    const other_fields = [
        "other_section", "other_item_name", "other_item_code",
        "other_uom", "other_is_stock",
    ];

    // Show/hide textile fields
    textile_fields.forEach(f => {
        dialog.set_df_property(f, "hidden", is_textile ? 0 : 1);
    });

    // Structure: show for Fabric only, hide for Yarn and Other
    structure_fields.forEach(f => {
        dialog.set_df_property(f, "hidden", (cls === "Fabric") ? 0 : 1);
    });

    // Other fields: show only for Other
    other_fields.forEach(f => {
        dialog.set_df_property(f, "hidden", is_textile ? 1 : 0);
    });
}


// ──────────────────────────────────────────────
// MODIFIER DEDUP: filter modifier2 to exclude modifier1
// ──────────────────────────────────────────────
function _filter_modifier2(dialog, all_modifiers) {
    const m1 = dialog.get_value("modifier1");
    const m2_field = dialog.fields_dict.modifier2;

    if (m2_field && m2_field.awesomplete) {
        // Filter out the selected modifier1 from modifier2 options
        const filtered = all_modifiers.filter(v => v !== m1);
        m2_field.set_data(filtered);

        // If modifier2 has same value as m1, clear it
        if (dialog.get_value("modifier2") === m1) {
            dialog.set_value("modifier2", "");
        }
    }
}


// ──────────────────────────────────────────────
// LIVE PREVIEW (debounced)
// ──────────────────────────────────────────────
const _update_preview = frappe.utils.debounce(function (dialog) {
    const cls = dialog.get_value("classification");

    if (cls === "Other") {
        const name = dialog.get_value("other_item_name") || "";
        const code = dialog.get_value("other_item_code") || "";
        _render_preview(dialog, name, code, []);
        return;
    }

    const selections = _get_selections(dialog);

    if (!selections.count && !selections.fiber) {
        _render_preview(dialog, "", "", []);
        return;
    }

    frappe.call({
        method: "kniterp.api.item_composer.preview_item",
        args: {
            selections: JSON.stringify(selections),
            classification: cls,
        },
        callback(r) {
            if (r.message) {
                _render_preview(dialog, r.message.item_name, r.message.item_code, r.message.duplicates);
            }
        }
    });
}, 400);


function _get_selections(dialog) {
    const modifiers = [];
    const m1 = dialog.get_value("modifier1");
    const m2 = dialog.get_value("modifier2");
    if (m1) modifiers.push(m1);
    if (m2) modifiers.push(m2);

    return {
        count: dialog.get_value("count") || "",
        fiber: dialog.get_value("fiber") || "",
        modifier: modifiers,
        structure: dialog.get_value("structure") || "",
        lycra: dialog.get_value("lycra") || "",
        denier: "",
        state: dialog.get_value("state") || "",
    };
}


function _render_preview(dialog, name, code, duplicates) {
    const wrapper = dialog.get_field("preview_area").$wrapper;

    if (!name && !code) {
        wrapper.html(`<div class="text-muted text-small">${__("Select attributes to see preview")}</div>`);
        return;
    }

    let dup_html = "";
    if (duplicates && duplicates.length) {
        dup_html = `<div class="text-danger mt-2">
            <i class="fa fa-exclamation-triangle"></i>
            <strong>${__("Existing item found — click to use:")}</strong>
            <div class="mt-1">`;
        duplicates.forEach(d => {
            dup_html += `<button class="btn btn-xs btn-default mr-1 mb-1 kniterp-use-existing"
                                 data-item="${frappe.utils.escape_html(d.item_code)}"
                                 style="text-align: left;">
                <i class="fa fa-check-circle text-success"></i>
                <strong>${frappe.utils.escape_html(d.item_code)}</strong>
                — ${frappe.utils.escape_html(d.item_name)}
            </button>`;
        });
        dup_html += `</div></div>`;
    } else {
        dup_html = `<div class="text-success mt-2">
            <i class="fa fa-check"></i> ${__("No duplicate found")}
        </div>`;
    }

    wrapper.html(`
        <div class="border rounded p-3 bg-light">
            <div><strong>${__("Name")}:</strong> ${name}</div>
            <div><strong>${__("Code")}:</strong> <code>${code}</code></div>
            ${dup_html}
        </div>
    `);

    // Bind click on existing items
    wrapper.find(".kniterp-use-existing").on("click", function () {
        const item_code = $(this).attr("data-item");
        const on_select = dialog._composer_on_select;
        dialog.hide();
        // Delay callback so dialog fully closes first
        setTimeout(() => {
            if (on_select) {
                on_select(item_code);
            }
            frappe.show_alert({
                message: __("Selected existing: {0}", [item_code]),
                indicator: "blue"
            });
        }, 200);
    });
}


// ──────────────────────────────────────────────
// CREATE ITEM
// ──────────────────────────────────────────────
function _create_item(dialog, on_select) {
    const cls = dialog.get_value("classification");
    const item_group = dialog.get_value("item_group");
    const hsn_code = dialog.get_value("hsn_code");

    if (!item_group) {
        frappe.msgprint(__("Please select an Item Group"));
        return;
    }
    if (!hsn_code) {
        frappe.msgprint(__("Please select an HSN Code"));
        return;
    }

    let selections, stock_uom, is_stock_item;

    if (cls === "Other") {
        selections = {
            item_name: dialog.get_value("other_item_name"),
            item_code: dialog.get_value("other_item_code"),
        };
        stock_uom = dialog.get_value("other_uom") || "Nos";
        is_stock_item = dialog.get_value("other_is_stock") ? 1 : 0;

        if (!selections.item_name || !selections.item_code) {
            frappe.msgprint(__("Item Name and Item Code are required"));
            return;
        }
    } else {
        selections = _get_selections(dialog);
        stock_uom = "Kg";
        is_stock_item = 1;

        if (!selections.count && !selections.fiber) {
            frappe.msgprint(__("Please select at least a Count or Fiber"));
            return;
        }
    }

    frappe.call({
        method: "kniterp.api.item_composer.create_composer_item",
        args: {
            selections: JSON.stringify(selections),
            classification: cls,
            item_group: item_group,
            hsn_code: hsn_code,
            stock_uom: stock_uom,
            is_stock_item: is_stock_item,
        },
        freeze: true,
        freeze_message: __("Creating item..."),
        callback(r) {
            if (r.message) {
                frappe.show_alert({
                    message: __("Created: {0}", [r.message.item_code]),
                    indicator: "green"
                });
                dialog.hide();
                if (on_select) {
                    on_select(r.message.item_code);
                }
            }
        }
    });
}


// ──────────────────────────────────────────────
// "+ ADD NEW" BUTTONS & SUB-DIALOG
// ──────────────────────────────────────────────
function _setup_add_new_buttons(dialog, options) {
    const dims = [
        { field: "count_add_btn", dimension: "count", label: "Count" },
        { field: "fiber_add_btn", dimension: "fiber", label: "Fiber" },
        { field: "modifier_add_btn", dimension: "modifier", label: "Modifier" },
        { field: "structure_add_btn", dimension: "structure", label: "Structure" },
    ];

    dims.forEach(({ field, dimension, label }) => {
        const wrapper = dialog.get_field(field)?.$wrapper;
        if (!wrapper) return;

        wrapper.html(`
            <button class="btn btn-xs btn-default mt-1">
                <i class="fa fa-plus"></i> ${__("Add New")}
            </button>
        `);

        wrapper.find("button").on("click", () => {
            _open_add_token_dialog(dimension, label, dialog, options);
        });
    });
}


function _open_add_token_dialog(dimension, label, parent_dialog, options) {
    const add_dialog = new frappe.ui.Dialog({
        title: __("Add New {0}", [label]),
        fields: [
            {
                fieldtype: "Data",
                fieldname: "canonical",
                label: __("Display Name"),
                reqd: 1,
                description: __("Official name, e.g. 'Bamboo Cotton'"),
            },
            {
                fieldtype: "Data",
                fieldname: "short_code",
                label: __("Short Code"),
                reqd: 1,
                description: __("For item code, e.g. 'BMB'. Must be unique within this dimension."),
            },
            {
                fieldtype: "Small Text",
                fieldname: "aliases",
                label: __("Aliases"),
                description: __("Comma-separated ways users might type this, e.g. 'bamboo, bmb, bmbctn'"),
            },
        ],
        primary_action_label: __("Add"),
        primary_action(values) {
            frappe.call({
                method: "kniterp.api.item_composer.add_new_token",
                args: {
                    canonical: values.canonical,
                    dimension: dimension,
                    short_code: values.short_code,
                    aliases: values.aliases || "",
                },
                freeze: true,
                callback(r) {
                    if (r.message) {
                        frappe.show_alert({
                            message: __("Added: {0}", [r.message.canonical]),
                            indicator: "green"
                        });
                        add_dialog.hide();

                        // Refresh dropdown in parent
                        _refresh_autocomplete(parent_dialog, dimension, r.message.canonical);
                    }
                }
            });
        },
    });

    add_dialog.show();
}


function _refresh_autocomplete(dialog, dimension, new_value) {
    const field_map = {
        count: ["count"],
        fiber: ["fiber"],
        modifier: ["modifier1", "modifier2"],
        structure: ["structure"],
        lycra: ["lycra"],
        state: ["state"],
    };

    const fields = field_map[dimension] || [];

    // Re-fetch all options
    frappe.call({
        method: "kniterp.api.item_composer.get_composer_options",
        callback(r) {
            const new_options = r.message || {};
            dialog._composer_options = new_options;
            const dim_opts = (new_options[dimension] || []).map(t => t.canonical);
            dialog._ac_lists[dimension] = dim_opts;

            fields.forEach(fname => {
                const field = dialog.fields_dict[fname];
                if (field && field.awesomplete) {
                    const current = dialog.get_value(fname);
                    field.set_data(dim_opts);
                    if (!current && fname === fields[0]) {
                        dialog.set_value(fname, new_value);
                    } else {
                        dialog.set_value(fname, current);
                    }
                }
            });

            // Re-setup alias matching
            _setup_alias_autocomplete(dialog, new_options);
            _update_preview(dialog);
        }
    });
}


// ======================================================
// INTERCEPT "Create a new Item" IN LINK FIELDS
// Monkey-patch ControlLink.new_doc:
//   - If doctype is "Item" → open Composer with typed text
//   - All other doctypes → original Frappe behavior
// ======================================================
(function () {
    const _original_new_doc = frappe.ui.form.ControlLink.prototype.new_doc;

    frappe.ui.form.ControlLink.prototype.new_doc = function () {
        const doctype = this.get_options();

        if (doctype !== "Item") {
            return _original_new_doc.call(this);
        }

        // Capture full context before opening dialog
        const typed_text = this.get_label_value() || "";
        const link_control = this;
        const fieldname = this.df.fieldname;
        const frm = this.frm;
        const cdt = this.doctype;
        const cdn = this.doc?.name;

        kniterp_open_item_composer({
            quick_fill_text: typed_text,
            on_select(item_code) {
                // Wait for Composer dialog to fully close before setting value
                setTimeout(() => {
                    // Tier 1: Standard form child table row
                    if (frm && cdt && cdn && fieldname) {
                        frappe.model.set_value(cdt, cdn, fieldname, item_code).then(() => {
                            frm.dirty();
                            frm.refresh_fields();
                        });
                        return;
                    }

                    // Tier 2: Standard form parent-level field
                    if (frm && fieldname) {
                        frm.set_value(fieldname, item_code);
                        return;
                    }

                    // Tier 3: Custom pages (BOM designer, dialogs, etc.)
                    // IMPORTANT: Do NOT use set_value() — it triggers async validation
                    // that clears the value when the control has no frm/doc.
                    // Instead, bypass validation by setting internal state directly,
                    // exactly as Frappe does after awesomplete-select confirmation.
                    if (link_control) {
                        // Set internal value state (bypasses validation)
                        link_control.value = item_code;
                        link_control.last_value = item_code;

                        // Set the visible input text
                        if (link_control.$input) {
                            link_control.$input.val(item_code);
                        }

                        // Trigger BOM designer's change callback (uses df.change)
                        if (typeof link_control.df?.change === "function") {
                            link_control.df.change();
                        } else if (typeof link_control.df?.onchange === "function") {
                            link_control.df.onchange();
                        }
                    }
                }, 300);
            }
        });

        return false;
    };

})();
