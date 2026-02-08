frappe.pages['action-center'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Action Center',
        single_column: true
    });

    frappe.action_center = new ActionCenter(wrapper);
};

class ActionCenter {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.body = $(wrapper).find('.layout-main-section');
        this.setup_page();
    }

    setup_page() {
        this.body.html(frappe.render_template('action_center', {}));

        // Load CSS
        frappe.require('/assets/kniterp/js/page/action_center/action_center.css');

        // Bind events
        this.body.on('click', '#refresh-actions', () => this.refresh());
        this.body.on('click', '.action-item', (e) => {
            const link = $(e.currentTarget).data('link');
            const options = $(e.currentTarget).data('options');
            if (link) {
                if (options) {
                    frappe.route_options = JSON.parse(JSON.stringify(options));
                }
                frappe.set_route(link);
            }
        });

        this.body.on('click', '.btn-view-all', (e) => {
            const link = $(e.currentTarget).data('link');
            const options = $(e.currentTarget).data('options');
            if (link) {
                if (options) {
                    frappe.route_options = JSON.parse(JSON.stringify(options));
                }
                frappe.set_route(link);
            }
        });

        this.body.on('click', '.btn-fix', (e) => {
            const key = $(e.currentTarget).data('key');
            if (key) {
                this.show_fix_dialog(key);
            }
        });

        this.refresh();
    }

    refresh() {
        const $dashboard = this.body.find('.action-dashboard');
        $dashboard.html(`
            <div class="text-center p-5 text-muted">
                <div class="spinner-border text-primary"></div>
                <p class="mt-2">Loading actions...</p>
            </div>
        `);

        frappe.call({
            method: 'kniterp.api.action_center.get_action_items',
            callback: (r) => {
                if (r.message) {
                    this.render(r.message);
                }
            }
        });
    }

    render(actions) {
        const $dashboard = this.body.find('.action-dashboard');
        $dashboard.empty();

        const order = [
            'rm_shortage',
            'knitting_pending',
            'send_to_job_worker',
            'receive_from_job_worker',
            'receive_rm_from_customer',
            'pending_purchase_receipt',
            'pending_purchase_invoice',
            'pending_delivery',
            'pending_invoice'
        ];

        order.forEach(key => {
            const data = actions[key];
            if (data && data.count > 0) {
                data.key = key;  // Pass the key to make_card
                $dashboard.append(this.make_card(data));
            }
        });
    }

    make_card(data) {
        let items_html = '';
        if (data.items.length === 0) {
            items_html = `
                <div class="p-4 text-center text-muted">
                    <i class="fa fa-check-circle text-success mb-2"></i>
                    <div>All caught up!</div>
                </div>
            `;
        } else {
            data.items.forEach(item => {
                const route_options_attr = item.route_options ? `data-options='${JSON.stringify(item.route_options)}'` : '';
                items_html += `
                    <div class="action-item" data-link="${item.link}" ${route_options_attr}>
                        <div class="item-main">
                            <div class="item-title" title="${item.title}">${item.title}</div>
                            ${item.date ? `<div class="item-meta">${frappe.datetime.str_to_user(item.date)}</div>` : ''}
                        </div>
                        <div class="item-sub">
                            <div>${item.description}</div>
                            <i class="fa fa-chevron-right text-muted"></i>
                        </div>
                    </div>
                `;
            });
        }

        const badge_class = `badge-${data.color || 'secondary'}`;
        const status_class = `status-${data.color || 'secondary'}`;

        let view_all_link = '';
        let view_all_options = '';

        if (data.label === 'Raw Material Shortage') {
            view_all_link = 'production-wizard';
            view_all_options = JSON.stringify({ 'materials_status': 'Shortage' });
        } else if (data.label === 'Ready for Knitting') {
            view_all_link = 'production-wizard';
            view_all_options = JSON.stringify({ 'materials_status': 'Ready' });
        } else if (data.label === 'Pending Delivery to Customer') {
            view_all_link = 'production-wizard';
            view_all_options = JSON.stringify({ 'invoice_status': 'Ready to Deliver' });
        } else if (data.label === 'Pending Sales Invoices') {
            view_all_link = 'production-wizard';
            view_all_options = JSON.stringify({ 'invoice_status': 'Ready to Invoice' });
        } else if (data.label === 'Pending Purchase Receipt') {
            view_all_link = 'List/Purchase Order';
            view_all_options = JSON.stringify({
                'docstatus': 1,
                'is_subcontracted': 0,
                'per_received': ['<', 100],
                'status': ['not in', ['Closed', 'Completed', 'Cancelled']]
            });
        } else if (data.label === 'Pending Purchase Invoice') {
            view_all_link = 'List/Purchase Order';
            view_all_options = JSON.stringify({
                'docstatus': 1,
                'per_billed': ['<', 100],
                'status': ['not in', ['Closed', 'Cancelled']]
            });
        }

        // Get contextual button label based on card type
        const button_labels = {
            'rm_shortage': __('Resolve'),
            'knitting_pending': __('Produce'),
            'send_to_job_worker': __('Send'),
            'receive_from_job_worker': __('Receive'),
            'receive_rm_from_customer': __('Receive'),
            'pending_purchase_receipt': __('Receive'),
            'pending_purchase_invoice': __('Invoice'),
            'pending_delivery': __('Deliver'),
            'pending_invoice': __('Invoice')
        };
        const btn_label = button_labels[data.key] || __('Actions');

        const fix_btn_html = data.key && data.count > 0 ? `
            <button class="btn btn-xs btn-primary btn-fix ml-2" data-key="${data.key}">
                ${btn_label} <i class="fa fa-wrench ml-1"></i>
            </button>
        ` : '';

        return `
            <div class="action-card ${status_class}">
                <div class="card-header">
                    <div class="card-title">
                        <div>
                             ${data.label}
                            <span class="card-badge ${badge_class}">${data.count}</span>
                        </div>
                        ${fix_btn_html}
                    </div>
                </div>
                <div class="card-body">
                    ${items_html}
                </div>
                ${data.count > 0 ? `
                <div class="card-footer">
                    <button class="btn btn-xs btn-default btn-view-all" 
                            data-link="${view_all_link || data.items[0].link}"
                            ${view_all_options ? `data-options='${view_all_options}'` : ''}>
                        View All
                    </button>
                </div>
                ` : ''}
            </div>
        `;
    }

    show_fix_dialog(action_key) {
        frappe.call({
            method: 'kniterp.api.action_center.get_fix_details',
            args: { action_key: action_key },
            callback: (r) => {
                if (r.message && r.message.data) {
                    this.render_fix_dialog(r.message);
                } else {
                    frappe.msgprint('No details available');
                }
            }
        });
    }

    render_fix_dialog(details) {
        const d = new frappe.ui.Dialog({
            title: details.title,
            size: 'extra-large',
            fields: []
        });

        d.show();

        const $body = d.$wrapper.find('.modal-body');

        // Bulk actions bar
        let bulk_actions_html = '';
        if (details.bulk_actions && details.bulk_actions.length > 0) {
            bulk_actions_html = `
                <div class="bulk-actions-bar" style="padding: 10px 0; border-bottom: 1px solid var(--border-color); margin-bottom: 10px; display: flex; align-items: center; gap: 15px;">
                    <label style="margin: 0; display: flex; align-items: center; cursor: pointer;">
                        <input type="checkbox" class="select-all" style="margin-right: 8px;">
                        <span>${__('Select All')}</span>
                    </label>
                    <span class="selected-count text-muted" style="font-size: 12px;">0 ${__('selected')}</span>
                    <div style="margin-left: auto;">
                        ${details.bulk_actions.map(action => `
                            <button class="btn btn-sm btn-primary btn-bulk-action" data-action="${action.action}" disabled>
                                ${action.icon ? `<i class="${action.icon}"></i>` : ''} ${action.label}
                            </button>
                        `).join('')}
                    </div>
                </div>
            `;
        }

        // Build HTML table
        let table_html = `
            <div class="fix-table-wrapper" style="overflow-x: auto; max-height: 500px;">
                <table class="table table-bordered table-hover table-sm" style="width: 100%;">
                    <thead class="thead-light">
                        <tr>
                            ${details.columns.map(col => {
            if (col.fieldname === 'select') {
                return `<th style="width: 40px;"></th>`;
            }
            return `<th style="white-space: nowrap;">${col.label}</th>`;
        }).join('')}
                        </tr>
                    </thead>
                    <tbody>
        `;

        details.data.forEach((row, idx) => {
            let action_buttons = '';
            if (details.row_actions) {
                details.row_actions.forEach(action => {
                    let label = action.label;
                    let icon = action.icon;
                    let btnClass = 'btn-secondary';

                    if (action.action === 'create_invoice' && row.draft_invoice) {
                        label = __('View Draft');
                        icon = 'fa fa-file-text-o';
                        btnClass = 'btn-warning';
                    }

                    action_buttons += `
                        <button class="btn btn-xs ${btnClass} btn-row-action mr-1" 
                            data-action="${action.action}"
                            data-row-idx="${idx}"
                            title="${label}">
                            ${icon ? `<i class="${icon}"></i>` : label}
                        </button>
                     `;
                });
            }

            table_html += `<tr data-row-idx="${idx}">`;
            details.columns.forEach(col => {
                if (col.fieldname === 'select') {
                    table_html += `<td><input type="checkbox" class="row-select" data-idx="${idx}"></td>`;
                } else if (col.fieldname === 'action_btn') {
                    table_html += `<td style="white-space: nowrap;">${action_buttons}</td>`;
                } else if (col.fieldname === 'delivery_date' || col.fieldname === 'posting_date' || col.fieldname === 'po_date') {
                    table_html += `<td>${row[col.fieldname] ? frappe.datetime.str_to_user(row[col.fieldname]) : ''}</td>`;
                } else if (col.fieldname === 'amount' || col.fieldname === 'total_amount' || col.fieldname === 'pending_amount') {
                    table_html += `<td class="text-right">${frappe.format(row[col.fieldname], { fieldtype: 'Currency' })}</td>`;
                } else if (col.fieldname === 'billed_percent') {
                    table_html += `<td class="text-right">${row[col.fieldname] || 0}%</td>`;
                } else if (['required_qty', 'available_qty', 'shortage', 'qty', 'pending_qty', 'ordered_qty', 'delivered_qty', 'received_qty'].includes(col.fieldname)) {
                    table_html += `<td class="text-right">${row[col.fieldname] || 0}</td>`;
                } else {
                    table_html += `<td>${row[col.fieldname] || ''}</td>`;
                }
            });
            table_html += `</tr>`;
        });

        table_html += `
                    </tbody>
                </table>
            </div>
        `;

        $body.html(bulk_actions_html + table_html);

        // Store data for action handling
        const data = details.data;

        // Update selection count
        const updateSelectionCount = () => {
            const count = $body.find('.row-select:checked').length;
            $body.find('.selected-count').text(`${count} ${__('selected')}`);
            $body.find('.btn-bulk-action').prop('disabled', count === 0);
        };

        // Select All checkbox
        $body.on('change', '.select-all', (e) => {
            const isChecked = $(e.target).is(':checked');
            $body.find('.row-select').prop('checked', isChecked);
            updateSelectionCount();
        });

        // Individual checkbox
        $body.on('change', '.row-select', () => {
            updateSelectionCount();
            const total = $body.find('.row-select').length;
            const checked = $body.find('.row-select:checked').length;
            $body.find('.select-all').prop('checked', total === checked);
        });

        // Bulk action button
        $body.on('click', '.btn-bulk-action', (e) => {
            const action = $(e.currentTarget).data('action');
            const selectedRows = [];
            $body.find('.row-select:checked').each(function () {
                const idx = $(this).data('idx');
                selectedRows.push(data[idx]);
            });
            this.handle_bulk_action(action, selectedRows, d, details);
        });

        // Event Delegation for Row Actions
        $body.on('click', '.btn-row-action', (e) => {
            const action = $(e.currentTarget).data('action');
            const rowIdx = $(e.currentTarget).data('row-idx');
            const rowData = data[rowIdx];

            this.handle_row_action(action, rowData, d);
        });
    }

    handle_row_action(action, rowData, dialog) {
        if (action === 'view_order') {
            if (rowData.sales_order_item) {
                frappe.route_options = {
                    'selected_item': rowData.sales_order_item
                };
                frappe.set_route('production-wizard');
            } else if (rowData.sales_order) {
                frappe.set_route('Form', 'Sales Order', rowData.sales_order);
            }
            dialog.hide();
        } else if (action === 'view_po') {
            frappe.set_route('Form', 'Purchase Order', rowData.po_name);
            dialog.hide();
        } else if (action === 'view_dn') {
            frappe.set_route('Form', 'Delivery Note', rowData.dn_name);
            dialog.hide();
        } else if (action === 'create_po') {
            frappe.model.with_doctype('Purchase Order', () => {
                frappe.new_doc('Purchase Order', {
                    'supplier': '',
                    'items': [{
                        'item_code': rowData.rm_item,
                        'qty': rowData._raw_shortage,
                        'schedule_date': frappe.datetime.now_date(),
                        'sales_order': rowData.sales_order,
                        'sales_order_item': rowData.sales_order_item
                    }]
                });
                dialog.hide();
            });
        } else if (action === 'create_wo') {
            frappe.call({
                method: 'kniterp.api.production_wizard.create_work_order',
                args: {
                    sales_order: rowData.sales_order,
                    sales_order_item: rowData.sales_order_item
                },
                freeze: true,
                callback: (r) => {
                    if (r.message) {
                        frappe.show_alert({
                            message: __('Work Order created: {0}', [r.message]),
                            indicator: 'green'
                        }, 5);
                        this.refresh();
                        dialog.hide();
                    }
                }
            });
        } else if (action === 'create_dn') {
            frappe.model.with_doctype('Delivery Note', () => {
                frappe.new_doc('Delivery Note', {
                    'customer': rowData.customer,
                });
                dialog.hide();
            });
        } else if (action === 'create_invoice') {
            if (rowData.draft_invoice) {
                frappe.set_route('Form', 'Sales Invoice', rowData.draft_invoice);
                dialog.hide();
            } else {
                frappe.call({
                    method: 'erpnext.stock.doctype.delivery_note.delivery_note.make_sales_invoice',
                    args: {
                        source_name: rowData.dn_name
                    },
                    freeze: true,
                    callback: (r) => {
                        if (r.message) {
                            const doclist = frappe.model.sync(r.message);
                            frappe.set_route('Form', 'Sales Invoice', doclist[0].name);
                            dialog.hide();
                        }
                    }
                });
            }
        } else if (action === 'send_material') {
            frappe.route_options = {
                'selected_item': rowData.sales_order_item
            };
            frappe.set_route('production-wizard');
            dialog.hide();
        } else if (action === 'receive_goods') {
            frappe.route_options = {
                'selected_item': rowData.sales_order_item
            };
            frappe.set_route('production-wizard');
            dialog.hide();
        } else if (action === 'receive_rm') {
            frappe.set_route('Form', 'Subcontracting Inward Order', rowData.order_name);
            dialog.hide();
        } else if (action === 'create_pr') {
            // Create Purchase Receipt from Purchase Order
            frappe.call({
                method: 'erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_receipt',
                args: {
                    source_name: rowData.po_name
                },
                freeze: true,
                callback: (r) => {
                    if (r.message) {
                        const doclist = frappe.model.sync(r.message);
                        frappe.set_route('Form', 'Purchase Receipt', doclist[0].name);
                        dialog.hide();
                    }
                }
            });
        } else if (action === 'create_pi') {
            // Create Purchase Invoice from Purchase Order
            frappe.call({
                method: 'erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_invoice',
                args: {
                    source_name: rowData.po_name
                },
                freeze: true,
                callback: (r) => {
                    if (r.message) {
                        const doclist = frappe.model.sync(r.message);
                        frappe.set_route('Form', 'Purchase Invoice', doclist[0].name);
                        dialog.hide();
                    }
                }
            });
        }
    }

    handle_bulk_action(action, selectedRows, dialog, details) {
        if (selectedRows.length === 0) {
            frappe.msgprint(__('Please select at least one row'));
            return;
        }

        if (action === 'consolidated_po') {
            // Aggregate shortages by RM item
            const consolidated = {};
            selectedRows.forEach(row => {
                const key = row.rm_item;
                if (!consolidated[key]) {
                    consolidated[key] = {
                        item_code: row.rm_item,
                        item_name: row.rm_name,
                        total_shortage: 0,
                        uom: row.uom,
                        breakdown: []
                    };
                }
                consolidated[key].total_shortage += row._raw_shortage || 0;
                consolidated[key].breakdown.push({
                    sales_order: row.sales_order,
                    sales_order_item: row.sales_order_item,
                    shortage: row._raw_shortage || row.shortage,
                    warehouse: row.warehouse
                });
            });

            // Show supplier selection dialog
            const d = new frappe.ui.Dialog({
                title: __('Create Consolidated Purchase Order'),
                fields: [
                    {
                        fieldname: 'supplier',
                        fieldtype: 'Link',
                        options: 'Supplier',
                        label: __('Supplier'),
                        reqd: 1
                    },
                    {
                        fieldname: 'summary_section',
                        fieldtype: 'Section Break',
                        label: __('Items to Order')
                    },
                    {
                        fieldname: 'summary_html',
                        fieldtype: 'HTML'
                    }
                ],
                primary_action_label: __('Create Purchase Order'),
                primary_action: (values) => {
                    // Build items array like production wizard
                    const items = [];
                    Object.values(consolidated).forEach(data => {
                        data.breakdown.forEach(b => {
                            items.push({
                                item_code: data.item_code,
                                qty: b.shortage,
                                sales_order: b.sales_order,
                                sales_order_item: b.sales_order_item,
                                warehouse: b.warehouse
                            });
                        });
                    });

                    frappe.call({
                        method: 'kniterp.api.production_wizard.create_purchase_orders_for_shortage',
                        args: {
                            items: JSON.stringify(items),
                            supplier: values.supplier,
                            submit: 0
                        },
                        freeze: true,
                        callback: (r) => {
                            if (r.message) {
                                d.hide();
                                dialog.hide();
                                frappe.show_alert({
                                    message: __('Purchase Order created: <a href="/app/purchase-order/{0}">{0}</a>', [r.message.name]),
                                    indicator: 'green'
                                }, 5);
                                this.refresh();
                            }
                        }
                    });
                }
            });

            // Render summary
            let summary_html = '<table class="table table-sm"><thead><tr><th>Item</th><th class="text-right">Qty</th></tr></thead><tbody>';
            Object.values(consolidated).forEach(data => {
                summary_html += `<tr><td>${data.item_name} (${data.item_code})</td><td class="text-right">${data.total_shortage.toFixed(3)} ${data.uom}</td></tr>`;
            });
            summary_html += '</tbody></table>';
            d.fields_dict.summary_html.$wrapper.html(summary_html);

            d.show();
        } else if (action === 'bulk_create_wo') {
            frappe.confirm(
                __('Create Work Orders for {0} items?', [selectedRows.length]),
                () => {
                    let completed = 0;
                    selectedRows.forEach(row => {
                        frappe.call({
                            method: 'kniterp.api.production_wizard.create_work_order',
                            args: {
                                sales_order: row.sales_order,
                                sales_order_item: row.sales_order_item
                            },
                            async: false,
                            callback: () => {
                                completed++;
                            }
                        });
                    });
                    frappe.show_alert({
                        message: __('Created {0} Work Orders', [completed]),
                        indicator: 'green'
                    }, 5);
                    dialog.hide();
                    this.refresh();
                }
            );
        } else if (action === 'bulk_create_dn') {
            frappe.msgprint(__('Please create Delivery Notes individually via the Production Wizard for better control.'));
        } else if (action === 'bulk_create_invoice') {
            frappe.confirm(
                __('Create Sales Invoices for {0} Delivery Notes?', [selectedRows.length]),
                () => {
                    let created = [];
                    selectedRows.forEach(row => {
                        frappe.call({
                            method: 'erpnext.stock.doctype.delivery_note.delivery_note.make_sales_invoice',
                            args: {
                                source_name: row.dn_name
                            },
                            async: false,
                            callback: (r) => {
                                if (r.message) {
                                    const doc = frappe.model.sync(r.message)[0];
                                    created.push(doc.name);
                                }
                            }
                        });
                    });
                    if (created.length > 0) {
                        frappe.show_alert({
                            message: __('Created {0} Sales Invoices', [created.length]),
                            indicator: 'green'
                        }, 5);
                    }
                    dialog.hide();
                    this.refresh();
                }
            );
        }
    }
}
