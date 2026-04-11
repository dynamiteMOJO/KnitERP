// Client script for Subcontracting Inward Order — SCIO Delivery Dialog
// Intercepts the "Create Delivery" button to show a batch/package selection
// dialog before creating the Delivery Note.

frappe.ui.form.on('Subcontracting Inward Order', {
    refresh(frm) {
        if (frm.doc.docstatus !== 1) return;

        // Remove the standard delivery button and re-add ours
        // The standard button calls make_subcontracting_delivery directly
        setTimeout(() => {
            // Check if there's a "Delivery Note" or "Subcontracting Delivery" button
            const $btn = frm.page.inner_toolbar
                .find('.btn-default:contains("Subcontracting Delivery"), .btn-default:contains("Delivery Note")');

            if (!$btn.length) {
                // Check if any items have pending delivery
                const has_pending = (frm.doc.items || []).some(
                    item => flt(item.produced_qty) > flt(item.delivered_qty)
                );
                if (has_pending) {
                    frm.add_custom_button(__('Create Delivery'), () => {
                        kniterp_scio_delivery_dialog(frm);
                    }, __('Actions'));
                }
                return;
            }

            // Replace existing button handler
            $btn.off('click').on('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                kniterp_scio_delivery_dialog(frm);
            });
        }, 500);
    }
});


function kniterp_scio_delivery_dialog(frm) {
    frappe.call({
        method: 'kniterp.api.production_wizard.get_scio_delivery_preview',
        args: { scio_name: frm.doc.name },
        freeze: true,
        freeze_message: __('Loading delivery details…'),
        callback: (r) => {
            if (!r.message) return;
            const preview = r.message;

            if (preview.has_batch_items) {
                _show_scio_form_delivery_dialog(frm, preview);
            } else {
                // Non-batch items — create directly
                frappe.call({
                    method: 'kniterp.api.production_wizard.create_scio_delivery_note',
                    args: { scio_name: frm.doc.name },
                    freeze: true,
                    freeze_message: __('Creating Delivery Note…'),
                    callback: (r2) => {
                        if (r2.message) {
                            frappe.set_route('Form', 'Delivery Note', r2.message);
                        }
                    }
                });
            }
        }
    });
}


function _show_scio_form_delivery_dialog(frm, preview) {
    let items_html = '';
    preview.items.forEach((item, idx) => {
        items_html += `
            <div class="mb-3" data-idx="${idx}"
                 style="border:1px solid var(--border-color); border-radius:6px; padding:12px;">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <div>
                        <strong>${frappe.utils.escape_html(item.item_code)}</strong>
                        <div class="text-muted small">${frappe.utils.escape_html(item.item_name)}</div>
                    </div>
                </div>
                <div class="d-flex flex-wrap mb-2" style="gap:12px; font-size:12px; color:var(--text-muted);">
                    <span><strong>${__('Produced')}:</strong> ${flt(item.produced_qty, 3)} ${item.uom}</span>
                    <span><strong>${__('Delivered')}:</strong> ${flt(item.delivered_qty, 3)} ${item.uom}</span>
                    <span style="color:var(--green-600); font-weight:600;">
                        <strong>${__('To Deliver')}:</strong> ${flt(item.qty, 3)} ${item.uom}
                    </span>
                </div>`;

        if (item.has_batch_no && item.batches && item.batches.length) {
            items_html += `
                <table class="table table-bordered table-sm mb-2">
                    <thead class="thead-light">
                        <tr>
                            <th>${__('Batch')}</th>
                            <th style="width:100px">${__('Available')}</th>
                            <th style="width:120px">${__('Deliver Qty')}</th>
                        </tr>
                    </thead>
                    <tbody>`;
            let remaining_to_fill = flt(item.qty, 3);
            let initial_total = 0;
            item.batches.forEach((b, bidx) => {
                let prefill_qty = 0;
                if (remaining_to_fill > 0) {
                    prefill_qty = Math.min(remaining_to_fill, flt(b.qty, 3));
                    remaining_to_fill -= prefill_qty;
                    initial_total += prefill_qty;
                }
                items_html += `
                        <tr>
                            <td><strong>${frappe.utils.escape_html(b.batch_no)}</strong></td>
                            <td class="text-muted">${flt(b.qty, 3)} ${item.uom}</td>
                            <td><input type="number" class="form-control form-control-sm scio-form-batch-qty"
                                data-idx="${idx}" data-bidx="${bidx}"
                                min="0" max="${flt(b.qty, 3)}" step="any" value="${prefill_qty}"></td>
                        </tr>`;
            });
            items_html += `
                    </tbody>
                </table>
                <div class="scio-form-batch-total text-right text-muted small" data-idx="${idx}">
                    ${__('Selected')}: <strong class="scio-form-batch-total-qty">${flt(initial_total, 3)}</strong> / ${flt(item.qty, 3)} ${item.uom}
                </div>`;
        }

        // Package fields
        items_html += `
                <hr class="my-2">
                <div class="d-flex align-items-center flex-wrap" style="gap:10px;">
                    <div>
                        <label class="small mb-0">${__('No. of Pkgs')}</label>
                        <input type="number" class="form-control form-control-sm scio-form-pkgs-no" data-idx="${idx}"
                            min="0" step="1" style="width:80px;">
                    </div>
                    <div>
                        <label class="small mb-0">${__('Kind')}</label>
                        <select class="form-control form-control-sm scio-form-pkgs-kind" data-idx="${idx}" style="width:110px;">
                            <option value=""></option>
                            <option value="Rolls">${__('Rolls')}</option>
                            <option value="Bags">${__('Bags')}</option>
                            <option value="Boxes">${__('Boxes')}</option>
                            <option value="Other">${__('Other')}</option>
                        </select>
                    </div>
                    <div class="scio-form-pkgs-other-wrap" data-idx="${idx}" style="display:none;">
                        <label class="small mb-0">${__('Other Kind')}</label>
                        <input type="text" class="form-control form-control-sm scio-form-pkgs-other" data-idx="${idx}" style="width:120px;">
                    </div>
                </div>`;

        items_html += `</div>`;
    });

    const context_html = `
        <div class="mb-3" style="background:var(--control-bg); border:1px solid var(--border-color); border-radius:6px; padding:10px 14px;">
            <div style="font-size:14px; font-weight:600;">${frappe.utils.escape_html(preview.customer_name)}</div>
            <div class="text-muted small">
                <strong>${__('SCIO')}:</strong> ${preview.scio_name}&emsp;
                <strong>${__('SO')}:</strong> <a href="/app/sales-order/${preview.sales_order}">${preview.sales_order}</a>
            </div>
            ${preview.shipping_address_name
                ? `<div class="text-muted small mt-1"><strong>${__('Ship To')}:</strong> ${frappe.utils.escape_html(preview.shipping_address_name)}</div>`
                : ''}
        </div>`;

    const d = new frappe.ui.Dialog({
        title: __('SCIO Delivery — {0}', [preview.scio_name]),
        size: 'large',
        fields: [
            { fieldtype: 'HTML', fieldname: 'context_html', options: context_html },
            { fieldtype: 'Section Break', label: __('Items & Batches') },
            { fieldtype: 'HTML', fieldname: 'items_html', options: items_html },
            {
                fieldtype: 'Section Break',
                label: __('Transport Details'),
                collapsible: 1
            },
            {
                fieldname: 'transporter', fieldtype: 'Link', options: 'Supplier',
                label: __('Transporter'),
                get_query: () => ({ filters: { disabled: 0, is_transporter: 1 } }),
                change: function () {
                    const val = d.get_value('transporter');
                    if (val) {
                        frappe.db.get_value('Supplier', val,
                            ['supplier_name', 'gst_transporter_id'], (r) => {
                                if (r) {
                                    d.set_value('transporter_name', r.supplier_name || '');
                                    d.set_value('gst_transporter_id', r.gst_transporter_id || '');
                                }
                            });
                    }
                }
            },
            { fieldname: 'vehicle_no', fieldtype: 'Data', label: __('Vehicle No'), length: 15 },
            { fieldname: 'lr_no', fieldtype: 'Data', label: __('Transport Receipt No'), length: 30 },
            { fieldtype: 'Column Break' },
            { fieldname: 'transporter_name', fieldtype: 'Data', label: __('Transporter Name'), read_only: 1 },
            { fieldname: 'gst_transporter_id', fieldtype: 'Data', label: __('GST Transporter ID'), read_only: 1, hidden: 1 },
            { fieldname: 'lr_date', fieldtype: 'Date', label: __('Transport Receipt Date'), default: frappe.datetime.nowdate() },
            { fieldname: 'distance', fieldtype: 'Int', label: __('Distance (km)') },
        ],
        primary_action_label: __('Create Delivery Note'),
        primary_action: () => {
            const delivery_items = [];
            let has_error = false;

            preview.items.forEach((item, idx) => {
                const entry = {
                    scio_detail: item.scio_detail,
                    item_code: item.item_code,
                    batches: [],
                    no_of_pkgs: cint(d.$wrapper.find(`.scio-form-pkgs-no[data-idx="${idx}"]`).val()),
                    kind_of_pkgs: d.$wrapper.find(`.scio-form-pkgs-kind[data-idx="${idx}"]`).val() || '',
                    kind_of_pkgs_other: d.$wrapper.find(`.scio-form-pkgs-other[data-idx="${idx}"]`).val() || '',
                };

                if (item.has_batch_no && item.batches && item.batches.length) {
                    let total = 0;
                    item.batches.forEach((b, bidx) => {
                        const qty = flt(d.$wrapper.find(`.scio-form-batch-qty[data-idx="${idx}"][data-bidx="${bidx}"]`).val());
                        if (qty > 0) {
                            if (qty > flt(b.qty, 3) + 0.001) {
                                frappe.msgprint(__('Batch {0}: qty {1} exceeds available {2}', [b.batch_no, qty, flt(b.qty, 3)]));
                                has_error = true;
                            }
                            entry.batches.push({ batch_no: b.batch_no, qty: qty });
                            total += qty;
                        }
                    });
                    if (total <= 0 && !has_error) {
                        frappe.msgprint(__('Please select at least one batch for {0}', [item.item_code]));
                        has_error = true;
                    }
                    if (total > flt(item.qty, 3) + 0.001 && !has_error) {
                        frappe.msgprint(__('Item {0}: total batch qty {1} exceeds deliverable {2}', [item.item_code, total, item.qty]));
                        has_error = true;
                    }
                }

                delivery_items.push(entry);
            });

            if (has_error) return;

            // Collect transport args
            const transport_args = {};
            for (const f of ['transporter', 'transporter_name', 'gst_transporter_id',
                'vehicle_no', 'lr_no', 'lr_date', 'distance']) {
                const val = d.get_value(f);
                if (val) transport_args[f] = val;
            }

            d.hide();

            frappe.call({
                method: 'kniterp.api.production_wizard.create_scio_delivery_note',
                args: {
                    scio_name: preview.scio_name,
                    delivery_items: JSON.stringify(delivery_items),
                    transport_args: Object.keys(transport_args).length
                        ? JSON.stringify(transport_args) : null,
                },
                freeze: true,
                freeze_message: __('Creating Delivery Note…'),
                callback: (r) => {
                    if (r.message) {
                        frappe.set_route('Form', 'Delivery Note', r.message);
                    }
                }
            });
        }
    });

    d.show();

    // Live total update
    d.$wrapper.on('input', '.scio-form-batch-qty', function () {
        const idx = $(this).data('idx');
        let total = 0;
        d.$wrapper.find(`.scio-form-batch-qty[data-idx="${idx}"]`).each(function () {
            total += flt($(this).val());
        });
        d.$wrapper.find(`.scio-form-batch-total[data-idx="${idx}"] .scio-form-batch-total-qty`).text(flt(total, 3));
    });

    d.$wrapper.on('change', '.scio-form-pkgs-kind', function () {
        const idx = $(this).data('idx');
        d.$wrapper.find(`.scio-form-pkgs-other-wrap[data-idx="${idx}"]`)
            .toggle($(this).val() === 'Other');
    });
}
