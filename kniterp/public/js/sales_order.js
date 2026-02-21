frappe.ui.form.on("Sales Order", {
    refresh(frm) {
        if (frm.doc.docstatus === 1 && frm.doc.is_subcontracted) {
            frm.add_custom_button(
                __("Subcontracted Purchase Order"),
                () => { open_subcontract_po_dialog(frm); },
                __("Create")
            );
        }
    }
});

// ── Helpers to read/write params from the hidden JSON field ──
function get_item_params(row) {
    try {
        return JSON.parse(row.custom_transaction_params_json || '[]');
    } catch (e) {
        return [];
    }
}

function set_item_params(frm, row, params) {
    frappe.model.set_value(row.doctype, row.name, 'custom_transaction_params_json',
        JSON.stringify(params));
    frm.dirty();
}

// ── Render teal badges ──
function render_params_badges($wrapper, params) {
    $wrapper.find('.tx-params-display').remove();
    if (!params || !params.length) return;

    const badges = params.map(p =>
        `<span style="display:inline-block; background:#e6f7f5; color:#0d7377; border:1px solid #b2e0db;
            font-size:12px; font-weight:500; padding:3px 8px; border-radius:12px; margin:2px 4px 2px 0;">
            <span style="opacity:0.7;">${frappe.utils.escape_html(p.parameter)}:</span>
            <strong>${frappe.utils.escape_html(p.value)}</strong>
        </span>`
    ).join('');

    const $display = $(`
        <div class="tx-params-display" style="padding:8px 15px; border-bottom:1px solid var(--border-color, #d1d8dd); background:var(--bg-light-gray, #f7f7f7);">
            <span style="font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:0.5px; color:var(--text-muted); margin-right:6px;">
                <i class="fa fa-sliders"></i> ${__('Parameters')}:
            </span>
            ${badges}
        </div>
    `);

    $wrapper.find('.grid-form-heading').after($display);
}

// ── Update button appearance based on param count ──
function update_param_button($btn, count) {
    if (count > 0) {
        $btn.html(`<i class="fa fa-sliders"></i> ${__('Parameters')} <span class="badge" style="background:#0d7377;color:#fff;margin-left:4px;">${count}</span>`);
        $btn.removeClass('btn-default').addClass('btn-primary');
    } else {
        $btn.html(`<i class="fa fa-sliders"></i> ${__('Set Parameters')}`);
        $btn.removeClass('btn-primary').addClass('btn-default');
    }
}

// ── Per-row Transaction Parameters button for SO Items ──
frappe.ui.form.on("Sales Order Item", {
    form_render(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        const grid_row = frm.fields_dict.items.grid.grid_rows_by_docname[cdn];
        if (!grid_row || !grid_row.grid_form) return;

        const $wrapper = grid_row.grid_form.wrapper;

        // Clean up previous renders
        $wrapper.find('.btn-set-tx-params').remove();
        $wrapper.find('.tx-params-display').remove();

        // Read params from the JSON field (client-side, no API call)
        const params = get_item_params(row);

        // ── The Button ──
        const $btn = $(`<button class="btn btn-xs btn-default btn-set-tx-params"
            style="margin-left:8px; border-radius:4px;">
            <i class="fa fa-sliders"></i> ${__('Set Parameters')}
        </button>`);

        $wrapper.find('.grid-form-heading .toolbar .panel-title').after($btn);
        update_param_button($btn, params.length);

        // Display existing params as badges
        render_params_badges($wrapper, params);

        // ── Button click → open dialog ──
        $btn.on('click', (e) => {
            e.stopPropagation();

            const current_params = get_item_params(locals[cdt][cdn]);
            const item_code = row.item_code || '';
            const item_name = row.item_name || '';

            const dialog = new frappe.ui.Dialog({
                title: __('Transaction Parameters') + (item_name ? ` — ${item_name}` : ''),
                size: 'large',
                fields: [
                    {
                        fieldtype: 'HTML',
                        fieldname: 'item_info',
                        options: `<div class="mb-3 text-muted small">
                            <strong>${__('Item')}:</strong> ${frappe.utils.escape_html(item_code)}
                            ${item_name ? ` — ${frappe.utils.escape_html(item_name)}` : ''}
                        </div>`
                    },
                    {
                        fieldtype: 'Table',
                        fieldname: 'params',
                        label: __('Parameters'),
                        cannot_add_rows: false,
                        in_place_edit: true,
                        data: current_params.map(p => ({
                            parameter: p.parameter,
                            value: p.value
                        })),
                        fields: [
                            {
                                fieldtype: 'Link',
                                fieldname: 'parameter',
                                label: __('Parameter'),
                                options: 'Transaction Parameter',
                                in_list_view: 1,
                                reqd: 1,
                                columns: 4
                            },
                            {
                                fieldtype: 'Data',
                                fieldname: 'value',
                                label: __('Value'),
                                in_list_view: 1,
                                reqd: 1,
                                columns: 6
                            }
                        ]
                    }
                ],
                primary_action_label: __('Done'),
                primary_action(values) {
                    const new_params = (values.params || [])
                        .filter(p => p.parameter && p.value)
                        .map(p => ({ parameter: p.parameter, value: p.value }));

                    // Write to the JSON field (client-side only — saved with form)
                    set_item_params(frm, locals[cdt][cdn], new_params);

                    // Update badge display inline
                    update_param_button($btn, new_params.length);
                    render_params_badges($wrapper, new_params);

                    frappe.show_alert({
                        message: __('Parameters updated — will be saved with the order'),
                        indicator: 'blue'
                    });
                    dialog.hide();
                }
            });

            dialog.show();
        });
    }
});

// ── Subcontract PO Dialog (existing) ──
function open_subcontract_po_dialog(frm) {
    frappe.call({
        method: "kniterp.api.subcontracting.get_subcontract_po_items",
        args: { sales_order: frm.doc.name },
        freeze: true,
        callback(r) { open_subcontract_po_dialog_ui(frm, r.message); }
    });
}

function open_subcontract_po_dialog_ui(frm, items) {
    const dialog = new frappe.ui.Dialog({
        title: __("Create Subcontracted Purchase Order"),
        size: "large",
        fields: [
            { fieldtype: "Link", fieldname: "supplier", label: __("Supplier"), options: "Supplier", reqd: 1 },
            {
                fieldtype: "Table", fieldname: "items", label: __("Items"),
                cannot_add_rows: true, in_place_edit: false, data: items,
                fields: [
                    { fieldtype: "Check", fieldname: "select", label: __("Select"), in_list_view: 1 },
                    { fieldtype: "Data", fieldname: "service_item", label: "Service Item", read_only: 1, in_list_view: 1 },
                    { fieldtype: "Data", fieldname: "service_item_name", label: "Service Name", read_only: 1, in_list_view: 1 },
                    { fieldtype: "Data", fieldname: "fg_item", label: "Finished Good", read_only: 1, in_list_view: 1 },
                    { fieldtype: "Float", fieldname: "fg_qty", label: "FG Qty", read_only: 1, in_list_view: 1 },
                    { fieldtype: "Float", fieldname: "service_qty", label: "Service Qty", read_only: 1, in_list_view: 1 },
                    { fieldtype: "Date", fieldname: "delivery_date", label: "Delivery Date", read_only: 1, in_list_view: 1 }
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
    if (!selected.length) { frappe.throw("Select at least one service item"); }
    frappe.call({
        method: "kniterp.api.subcontracting.make_subcontract_purchase_order",
        args: { sales_order: frm.doc.name, supplier: values.supplier, items: selected },
        freeze: true
    }).then(r => { frappe.set_route("Form", "Purchase Order", r.message); });
}
