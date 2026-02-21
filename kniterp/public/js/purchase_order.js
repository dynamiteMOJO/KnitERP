// ── Helpers to read/write params from the hidden JSON field ──
function get_po_item_params(row) {
    try {
        return JSON.parse(row.custom_transaction_params_json || '[]');
    } catch (e) {
        return [];
    }
}

function set_po_item_params(frm, row, params) {
    frappe.model.set_value(row.doctype, row.name, 'custom_transaction_params_json',
        JSON.stringify(params));
    frm.dirty();
}

function render_po_params_badges($wrapper, params) {
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

function update_po_param_button($btn, count) {
    if (count > 0) {
        $btn.html(`<i class="fa fa-sliders"></i> ${__('Parameters')} <span class="badge" style="background:#0d7377;color:#fff;margin-left:4px;">${count}</span>`);
        $btn.removeClass('btn-default').addClass('btn-primary');
    } else {
        $btn.html(`<i class="fa fa-sliders"></i> ${__('Set Parameters')}`);
        $btn.removeClass('btn-primary').addClass('btn-default');
    }
}

// ── Per-row Transaction Parameters button for PO Items ──
frappe.ui.form.on("Purchase Order Item", {
    form_render(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        const grid_row = frm.fields_dict.items.grid.grid_rows_by_docname[cdn];
        if (!grid_row || !grid_row.grid_form) return;

        const $wrapper = grid_row.grid_form.wrapper;

        $wrapper.find('.btn-set-tx-params').remove();
        $wrapper.find('.tx-params-display').remove();

        const params = get_po_item_params(row);

        const $btn = $(`<button class="btn btn-xs btn-default btn-set-tx-params"
            style="margin-left:8px; border-radius:4px;">
            <i class="fa fa-sliders"></i> ${__('Set Parameters')}
        </button>`);

        $wrapper.find('.grid-form-heading .toolbar .panel-title').after($btn);
        update_po_param_button($btn, params.length);
        render_po_params_badges($wrapper, params);

        $btn.on('click', (e) => {
            e.stopPropagation();

            const current_params = get_po_item_params(locals[cdt][cdn]);
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
                        data: current_params.map(p => ({ parameter: p.parameter, value: p.value })),
                        fields: [
                            {
                                fieldtype: 'Link', fieldname: 'parameter',
                                label: __('Parameter'), options: 'Transaction Parameter',
                                in_list_view: 1, reqd: 1, columns: 4
                            },
                            {
                                fieldtype: 'Data', fieldname: 'value',
                                label: __('Value'), in_list_view: 1, reqd: 1, columns: 6
                            }
                        ]
                    }
                ],
                primary_action_label: __('Done'),
                primary_action(values) {
                    const new_params = (values.params || [])
                        .filter(p => p.parameter && p.value)
                        .map(p => ({ parameter: p.parameter, value: p.value }));

                    set_po_item_params(frm, locals[cdt][cdn], new_params);
                    update_po_param_button($btn, new_params.length);
                    render_po_params_badges($wrapper, new_params);

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
