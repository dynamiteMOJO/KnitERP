frappe.pages['outsourcing-desk'].on_page_load = function (wrapper) {
    frappe.outsourcing_desk = new OutsourcingDesk(wrapper);
};

frappe.pages['outsourcing-desk'].refresh = function () {
    if (frappe.outsourcing_desk) {
        frappe.outsourcing_desk.refresh();
    }
};

class OutsourcingDesk {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.page = frappe.ui.make_app_page({
            parent: wrapper,
            title: __('Outsourcing Desk'),
            single_column: true
        });

        this.selected_po = null;
        this.orders = [];
        this.filters = frappe.route_options || {};
        frappe.route_options = null;

        this.setup_page();
        this.make_filters();
        this.make_layout();
        this.apply_filters();
        this.refresh();
    }

    apply_filters() {
        if (this.filters.supplier !== undefined) {
            this.supplier_filter.set_value(this.filters.supplier);
        }
        if (this.filters.from_date !== undefined) {
            this.from_date_filter.set_value(this.filters.from_date);
        }
        if (this.filters.to_date !== undefined) {
            this.to_date_filter.set_value(this.filters.to_date);
        }
    }

    setup_page() {
        this.page.set_primary_action(__('Refresh'), () => this.refresh(), 'refresh');

        this.page.add_inner_button(__('New Job Work Out'), () => {
            frappe.route_options = { voucher_type: 'job-work-out' };
            frappe.set_route('transaction-desk');
        });
    }

    // ── Transport field definitions (shared with PW) ────────────────────
    _get_transport_field_definitions() {
        return [
            {
                fieldname: 'transporter',
                fieldtype: 'Link',
                options: 'Supplier',
                label: __('Transporter'),
                get_query: () => ({ filters: { disabled: 0, is_transporter: 1 } }),
                change: function () {
                    const val = this.get_value();
                    const d = this.layout && this.layout.dialog;
                    if (!d) return;
                    if (val) {
                        frappe.db.get_value('Supplier', val,
                            ['supplier_name', 'gst_transporter_id'], (r) => {
                                if (r) {
                                    d.set_value('transporter_name', r.supplier_name || '');
                                    d.set_value('gst_transporter_id', r.gst_transporter_id || '');
                                }
                            });
                    } else {
                        d.set_value('transporter_name', '');
                        d.set_value('gst_transporter_id', '');
                    }
                }
            },
            { fieldname: 'vehicle_no', fieldtype: 'Data', label: __('Vehicle No'), length: 15 },
            { fieldname: 'lr_no', fieldtype: 'Data', label: __('Transport Receipt No'), length: 30 },
            { fieldtype: 'Column Break' },
            { fieldname: 'transporter_name', fieldtype: 'Data', label: __('Transporter Name'), read_only: 1 },
            { fieldname: 'gst_transporter_id', fieldtype: 'Data', label: __('GST Transporter ID'), read_only: 1, hidden: 1 },
            { fieldname: 'lr_date', fieldtype: 'Date', label: __('Transport Receipt Date'), default: frappe.datetime.nowdate() },
            { fieldname: 'distance', fieldtype: 'Int', label: __('Distance (km)') }
        ];
    }

    // ── Filters ─────────────────────────────────────────────────────────
    make_filters() {
        this.page.page_form.append(`<div class="od-filter-section-header">${__('Scope')}</div>`);

        this.supplier_filter = this.page.add_field({
            fieldname: 'supplier',
            label: __('Supplier'),
            fieldtype: 'Select',
            options: [{ label: __('All Suppliers'), value: '' }],
            change: () => {
                this.filters.supplier = this.supplier_filter.get_value();
                this.refresh_list();
            }
        });

        this.page.page_form.append(`<div class="od-filter-section-header">${__('Order Date')}</div>`);

        this.from_date_filter = this.page.add_field({
            fieldname: 'from_date',
            label: __('From Date'),
            fieldtype: 'Date',
            default: frappe.datetime.add_months(frappe.datetime.nowdate(), -3),
            change: () => {
                this.filters.from_date = this.from_date_filter.get_value();
                this.load_supplier_options();
                this.refresh_list();
            }
        });

        this.to_date_filter = this.page.add_field({
            fieldname: 'to_date',
            label: __('To Date'),
            fieldtype: 'Date',
            default: frappe.datetime.add_months(frappe.datetime.nowdate(), 1),
            change: () => {
                this.filters.to_date = this.to_date_filter.get_value();
                this.load_supplier_options();
                this.refresh_list();
            }
        });

        this.page.page_form.css({
            'padding': '10px 15px',
            'background': 'var(--subtle-fg)',
            'border-bottom': '1px solid var(--border-color)',
            'margin-bottom': '10px'
        });

        this.load_supplier_options();
    }

    load_supplier_options() {
        frappe.call({
            method: 'kniterp.api.outsourcing_desk.get_standalone_jwo_suppliers',
            callback: (r) => {
                if (r.message) {
                    const options = [{ label: __('All Suppliers'), value: '' }]
                        .concat(r.message.map(s => ({
                            label: s.supplier_name,
                            value: s.supplier
                        })));
                    const current = this.filters.supplier;
                    this.supplier_filter.df.options = options;
                    this.supplier_filter.refresh();
                    if (current) {
                        const still_valid = options.find(o => o.value === current);
                        if (still_valid) {
                            this.supplier_filter.set_value(current);
                        } else {
                            this.supplier_filter.set_value('');
                            this.filters.supplier = '';
                        }
                    }
                }
            }
        });
    }

    // ── Layout ──────────────────────────────────────────────────────────
    make_layout() {
        if (this.page.main.find('.od-container').length) return;

        this.page.main.append(`
            <div class="od-container">
                <div class="row">
                    <div class="col-md-5">
                        <div class="od-list-panel">
                            <div class="panel-header d-flex justify-content-between align-items-center pr-2">
                                <div class="d-flex align-items-center">
                                    <h5 class="mb-0 mr-2">${__('Job Work Orders')}</h5>
                                    <span class="od-item-count badge badge-secondary">0</span>
                                </div>
                            </div>
                            <div class="od-status-tabs"></div>
                            <div class="od-list"></div>
                        </div>
                    </div>
                    <div class="col-md-7">
                        <div class="od-detail-panel">
                            <div class="panel-header">
                                <h5>${__('Order Details')}</h5>
                            </div>
                            <div class="od-detail-content">
                                <div class="od-no-selection text-muted text-center p-5">
                                    <i class="fa fa-hand-pointer-o fa-3x mb-3"></i>
                                    <p>${__('Select an order from the left panel to view details')}</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `);

        this.$list = this.page.main.find('.od-list');
        this.$detail = this.page.main.find('.od-detail-content');
        this.$item_count = this.page.main.find('.od-item-count');
        this.$status_tabs = this.page.main.find('.od-status-tabs');

        this.render_status_tabs();
    }

    render_status_tabs() {
        const tabs = [
            { label: __('All'), value: '' },
            { label: __('Pending Material'), value: 'Pending Material' },
            { label: __('Material Sent'), value: 'Material Sent' },
            { label: __('Partially Received'), value: 'Partially Received' },
            { label: __('Completed'), value: 'Completed' },
        ];
        this.active_status = this.filters.status || '';
        let html = '<div class="od-tabs">';
        tabs.forEach(t => {
            const active = t.value === this.active_status ? 'active' : '';
            html += `<button class="od-tab ${active}" data-status="${t.value}">${t.label}</button>`;
        });
        html += '</div>';
        this.$status_tabs.html(html);

        this.$status_tabs.find('.od-tab').on('click', (e) => {
            const val = $(e.currentTarget).data('status');
            this.active_status = val;
            this.$status_tabs.find('.od-tab').removeClass('active');
            $(e.currentTarget).addClass('active');
            this.render_list();
        });
    }

    // ── Refresh / Data Loading ──────────────────────────────────────────
    refresh() {
        // Read route_options on each refresh (supports deep-link from PW)
        if (frappe.route_options) {
            Object.assign(this.filters, frappe.route_options);
            frappe.route_options = null;
        }
        this.load_supplier_options();
        this.refresh_list();
    }

    refresh_list() {
        if (!this.from_date_filter) return;

        const filters = {
            supplier: this.supplier_filter.get_value(),
            from_date: this.from_date_filter.get_value(),
            to_date: this.to_date_filter.get_value(),
        };

        frappe.call({
            method: 'kniterp.api.outsourcing_desk.get_standalone_jwo_list',
            args: { filters: JSON.stringify(filters) },
            callback: (r) => {
                this.orders = r.message || [];
                this.render_list();

                // Auto-select from route_options
                if (this.filters.selected_po) {
                    const po_name = this.filters.selected_po;
                    delete this.filters.selected_po;
                    this.select_order(po_name);
                }
            }
        });
    }

    // ── Left Panel: Order List ──────────────────────────────────────────
    render_list() {
        let filtered = this.orders;
        if (this.active_status) {
            filtered = filtered.filter(o => o.computed_status === this.active_status);
        }

        this.$item_count.text(filtered.length);

        if (!filtered.length) {
            this.$list.html(`
                <div class="text-muted text-center p-4">
                    <i class="fa fa-inbox fa-2x mb-2"></i>
                    <p>${__('No standalone job work orders found')}</p>
                </div>
            `);
            return;
        }

        let html = '';
        filtered.forEach(order => {
            const selected = this.selected_po === order.name ? 'selected' : '';
            const status_class = this._status_class(order.computed_status);
            const pct = order.fg_item_qty ? Math.min(100, Math.round((order.service_received_qty / order.service_qty) * 100)) : 0;
            const fg_display = order.fg_item_name || order.fg_item || order.service_item_name || order.service_item;

            html += `
                <div class="od-order-card ${selected}" data-po="${order.name}">
                    <div class="od-card-header">
                        <span class="od-supplier-name">${frappe.utils.escape_html(order.supplier_name)}</span>
                        <span class="status-badge ${status_class}">${order.computed_status}</span>
                    </div>
                    <div class="od-card-item">${frappe.utils.escape_html(fg_display)}</div>
                    <div class="od-card-qty">
                        ${__('Ordered')}: ${order.fg_item_qty || order.service_qty}
                        &nbsp;|&nbsp;
                        ${__('Received')}: ${flt(order.service_received_qty * (order.fg_item_qty / order.service_qty), 3) || 0}
                    </div>
                    <div class="od-card-progress">
                        <div class="progress" style="height:6px;">
                            <div class="progress-bar bg-primary" style="width:${pct}%"></div>
                        </div>
                    </div>
                    <div class="od-card-footer">
                        <span><i class="fa fa-file-text-o"></i> ${order.name}</span>
                        <span><i class="fa fa-calendar"></i> ${frappe.datetime.str_to_user(order.transaction_date)}</span>
                    </div>
                </div>
            `;
        });
        this.$list.html(html);

        this.$list.find('.od-order-card').on('click', (e) => {
            const po_name = $(e.currentTarget).data('po');
            this.select_order(po_name);
        });
    }

    select_order(po_name) {
        this.selected_po = po_name;
        this.$list.find('.od-order-card').removeClass('selected');
        this.$list.find(`.od-order-card[data-po="${po_name}"]`).addClass('selected');
        this.load_details(po_name);
    }

    _status_class(status) {
        const map = {
            'Pending Material': 'status-pending',
            'Material Sent': 'status-in-progress',
            'Partially Received': 'status-in-progress',
            'Completed': 'status-completed',
        };
        return map[status] || 'status-pending';
    }

    // ── Right Panel: Order Details ──────────────────────────────────────
    load_details(po_name) {
        this.$detail.html(`
            <div class="text-center p-5 text-muted">
                <i class="fa fa-spinner fa-spin fa-2x"></i>
            </div>
        `);

        frappe.call({
            method: 'kniterp.api.outsourcing_desk.get_standalone_jwo_details',
            args: { purchase_order: po_name },
            callback: (r) => {
                if (r.message) {
                    this.current_details = r.message;
                    this.render_details(r.message);
                }
            }
        });
    }

    render_details(data) {
        const po = data.purchase_order;
        const summary = data.summary;
        const actions = data.actions;

        let html = '';

        // ── Header ──────────────────────────────────────────────────
        html += `
            <div class="od-details-header">
                <div>
                    <h4>${frappe.utils.escape_html(po.supplier_name)}</h4>
                    <div class="text-muted" style="font-size:13px;">
                        <a href="/app/purchase-order/${po.name}" target="_blank">${po.name}</a>
                        ${data.sco_name ? `&nbsp;/&nbsp;<a href="/app/subcontracting-order/${data.sco_name}" target="_blank">${data.sco_name}</a>` : ''}
                    </div>
                    <div class="text-muted" style="font-size:12px; margin-top:4px;">
                        ${__('Order Date')}: ${frappe.datetime.str_to_user(po.transaction_date)}
                        &nbsp;|&nbsp;${__('Due')}: ${frappe.datetime.str_to_user(po.schedule_date)}
                        &nbsp;|&nbsp;${__('Status')}: <strong>${po.status}</strong>
                    </div>
                </div>
                <div class="od-qty-info">
                    <div class="od-big-number">${summary.total_fg_received}/${summary.total_fg_ordered}</div>
                    <div class="text-muted" style="font-size:12px;">${__('FG Received / Ordered')}</div>
                </div>
            </div>
        `;

        // ── Primary Actions ─────────────────────────────────────────
        html += '<div class="od-primary-actions">';
        if (actions.can_send_material) {
            html += `<button class="btn btn-sm btn-primary btn-send-material">
                <i class="fa fa-truck"></i> ${__('Send Material')}
            </button>`;
        }
        if (actions.can_receive_goods) {
            html += `<button class="btn btn-sm btn-success btn-receive-goods">
                <i class="fa fa-download"></i> ${__('Receive Goods')}
            </button>`;
        }
        if (actions.can_create_invoice) {
            html += `<button class="btn btn-sm btn-default btn-create-pi">
                <i class="fa fa-file-text"></i> ${__('Create Invoice')}
            </button>`;
        }
        html += '</div>';

        // ── Items Summary ───────────────────────────────────────────
        html += `
            <div class="od-section-header">
                <h5><i class="fa fa-cube"></i> ${__('Items')}</h5>
            </div>
            <table class="table table-bordered table-sm od-table">
                <thead>
                    <tr>
                        <th>${__('FG Item')}</th>
                        <th class="text-right">${__('Ordered')}</th>
                        <th class="text-right">${__('Received')}</th>
                        <th class="text-right">${__('Pending')}</th>
                    </tr>
                </thead>
                <tbody>
        `;
        data.items.forEach(item => {
            html += `
                <tr>
                    <td>
                        <div style="font-weight:500;">${frappe.utils.escape_html(item.fg_item_name || item.fg_item)}</div>
                        <div class="text-muted" style="font-size:11px;">${__('Service')}: ${frappe.utils.escape_html(item.item_name || item.item_code)}</div>
                    </td>
                    <td class="text-right">${item.fg_item_qty}</td>
                    <td class="text-right">${item.fg_received_qty}</td>
                    <td class="text-right ${item.fg_pending_qty > 0 ? 'text-warning font-weight-bold' : 'text-success'}">${item.fg_pending_qty}</td>
                </tr>
            `;
        });
        html += '</tbody></table>';

        // ── Raw Materials Status ────────────────────────────────────
        if (data.supplied_items.length) {
            const has_shortage = data.supplied_items.some(si => si.shortage > 0);
            html += `
                <div class="od-section-header">
                    <h5><i class="fa fa-cubes"></i> ${__('Raw Materials')}</h5>
                </div>
                <table class="table table-bordered table-sm od-table">
                    <thead>
                        <tr>
                            <th>${__('Item')}</th>
                            <th class="text-right">${__('Required')}</th>
                            <th class="text-right">${__('Available')}</th>
                            <th class="text-right">${__('Pending')}</th>
                            <th class="text-center">${__('Status')}</th>
                            <th class="text-center">${__('Action')}</th>
                        </tr>
                    </thead>
                    <tbody>
            `;
            data.supplied_items.forEach((si, idx) => {
                const row_class = si.shortage > 0 ? 'od-rm-pending' : '';
                const status_badge = si.shortage > 0
                    ? `<span class="badge od-badge-shortage"><i class="fa fa-exclamation-triangle mr-1"></i>${__('Shortage')}: ${si.shortage}</span>`
                    : `<span class="badge od-badge-available"><i class="fa fa-check mr-1"></i>${__('In Stock')}</span>`;

                // Existing POs/WOs summary
                let existing_html = '';
                if (si.existing_pos && si.existing_pos.length) {
                    existing_html += si.existing_pos.map(po =>
                        `<div class="od-existing-link"><i class="fa fa-shopping-cart text-muted mr-1"></i><a href="/app/purchase-order/${po.name}" target="_blank">${po.name}</a> <span class="text-muted small">(${flt(po.qty - po.received_qty, 3)} pending)</span></div>`
                    ).join('');
                }
                if (si.existing_wos && si.existing_wos.length) {
                    existing_html += si.existing_wos.map(wo =>
                        `<div class="od-existing-link"><i class="fa fa-cogs text-muted mr-1"></i><a href="/app/work-order/${wo.name}" target="_blank">${wo.name}</a> <span class="text-muted small">(${wo.status})</span></div>`
                    ).join('');
                }

                // Action buttons
                let action_html = '';
                if (si.shortage > 0) {
                    action_html = `<div class="od-rm-actions">
                        <div class="btn-group btn-group-sm">
                            <button class="btn btn-xs btn-primary btn-rm-purchase" data-idx="${idx}" title="${__('Purchase this RM')}">
                                <i class="fa fa-shopping-cart"></i> ${__('Buy')}
                            </button>
                            ${si.has_bom ? `<button class="btn btn-xs btn-info btn-rm-manufacture" data-idx="${idx}" title="${__('Manufacture this RM')}">
                                <i class="fa fa-industry"></i> ${__('Make')}
                            </button>` : ''}
                        </div>
                    </div>`;
                } else if (si.pending_qty > 0) {
                    action_html = `<span class="text-success small"><i class="fa fa-check-circle"></i> ${__('Ready')}</span>`;
                }

                // Check for receivable POs (submitted POs with pending qty)
                const receivable_pos = (si.existing_pos || []).filter(po => flt(po.qty - po.received_qty, 3) > 0);
                if (receivable_pos.length) {
                    action_html += `<div class="mt-1">
                        <button class="btn btn-xs btn-outline-success btn-rm-receive" data-idx="${idx}" data-po="${receivable_pos[0].name}">
                            <i class="fa fa-download"></i> ${__('Receive RM')}
                        </button>
                    </div>`;
                }

                html += `
                    <tr class="${row_class}">
                        <td>
                            <div style="font-weight:500;">${frappe.utils.escape_html(si.rm_item_name || si.rm_item_code)}</div>
                            <div class="text-muted" style="font-size:11px;">${si.rm_item_code}</div>
                            ${existing_html ? `<div class="od-existing-links mt-1">${existing_html}</div>` : ''}
                        </td>
                        <td class="text-right">${si.required_qty}</td>
                        <td class="text-right">${si.available_qty}</td>
                        <td class="text-right ${si.pending_qty > 0 ? 'text-warning font-weight-bold' : 'text-success'}">${si.pending_qty}</td>
                        <td class="text-center">${status_badge}</td>
                        <td class="text-center">${action_html}</td>
                    </tr>
                `;
            });
            html += '</tbody></table>';
        }

        // ── Transaction History ─────────────────────────────────────
        const has_history = data.stock_entries.length || data.receipts.length || data.invoices.length;
        if (has_history) {
            html += `
                <div class="od-section-header">
                    <h5><i class="fa fa-history"></i> ${__('Transaction History')}</h5>
                </div>
                <div class="od-timeline">
            `;

            // Stock Entries
            data.stock_entries.forEach(se => {
                const status_label = se.docstatus === 1 ? __('Submitted') : __('Draft');
                const status_color = se.docstatus === 1 ? 'green' : 'orange';
                const items_summary = se.items.map(i => `${i.item_code}: ${i.qty}`).join(', ');
                html += `
                    <div class="od-timeline-item">
                        <div class="od-timeline-node" style="background:var(--${status_color}-500);">
                            <i class="fa fa-truck"></i>
                        </div>
                        <div class="od-timeline-content">
                            <div class="od-timeline-header">
                                <span class="od-timeline-title">${__('Material Sent')}</span>
                                <span class="od-timeline-date">${frappe.datetime.str_to_user(se.posting_date)}</span>
                            </div>
                            <div class="od-timeline-desc">
                                <a href="/app/stock-entry/${se.name}" target="_blank">${se.name}</a>
                                <span class="badge badge-${status_color === 'green' ? 'success' : 'warning'} ml-1">${status_label}</span>
                            </div>
                            <div class="od-timeline-desc text-muted">${items_summary}</div>
                        </div>
                    </div>
                `;
            });

            // Receipts
            data.receipts.forEach(scr => {
                const status_label = scr.docstatus === 1 ? __('Submitted') : __('Draft');
                html += `
                    <div class="od-timeline-item">
                        <div class="od-timeline-node" style="background:var(--green-500);">
                            <i class="fa fa-download"></i>
                        </div>
                        <div class="od-timeline-content">
                            <div class="od-timeline-header">
                                <span class="od-timeline-title">${__('Goods Received')}</span>
                                <span class="od-timeline-date">${frappe.datetime.str_to_user(scr.posting_date)}</span>
                            </div>
                            <div class="od-timeline-desc">
                                <a href="/app/subcontracting-receipt/${scr.name}" target="_blank">${scr.name}</a>
                                <span class="badge badge-success ml-1">${status_label}</span>
                                &nbsp;${__('Qty')}: ${scr.total_qty}
                            </div>
                        </div>
                    </div>
                `;
            });

            // Invoices
            data.invoices.forEach(pi => {
                html += `
                    <div class="od-timeline-item">
                        <div class="od-timeline-node" style="background:var(--blue-500);">
                            <i class="fa fa-file-text"></i>
                        </div>
                        <div class="od-timeline-content">
                            <div class="od-timeline-header">
                                <span class="od-timeline-title">${__('Purchase Invoice')}</span>
                                <span class="od-timeline-date">${frappe.datetime.str_to_user(pi.posting_date)}</span>
                            </div>
                            <div class="od-timeline-desc">
                                <a href="/app/purchase-invoice/${pi.name}" target="_blank">${pi.name}</a>
                                &nbsp;${pi.status} &nbsp;${format_currency(pi.grand_total)}
                            </div>
                        </div>
                    </div>
                `;
            });

            html += '</div>';
        }

        this.$detail.html(html);
        this._bind_detail_actions(data);
    }

    _bind_detail_actions(data) {
        const self = this;

        this.$detail.find('.btn-send-material').on('click', () => {
            self.show_send_material_dialog(data);
        });

        this.$detail.find('.btn-receive-goods').on('click', () => {
            self.show_receive_goods_dialog(data);
        });

        this.$detail.find('.btn-create-pi').on('click', () => {
            frappe.call({
                method: 'erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_invoice',
                args: { source_name: data.purchase_order.name },
                freeze: true,
                callback: (r) => {
                    if (r.message) {
                        const doclist = frappe.model.sync(r.message);
                        frappe.set_route('Form', 'Purchase Invoice', doclist[0].name);
                    }
                }
            });
        });

        // RM procurement buttons
        this.$detail.find('.btn-rm-purchase').on('click', (e) => {
            const idx = $(e.currentTarget).data('idx');
            self.show_rm_purchase_dialog(data, data.supplied_items[idx]);
        });

        this.$detail.find('.btn-rm-manufacture').on('click', (e) => {
            const idx = $(e.currentTarget).data('idx');
            self.show_rm_manufacture_dialog(data, data.supplied_items[idx]);
        });

        this.$detail.find('.btn-rm-receive').on('click', (e) => {
            const idx = $(e.currentTarget).data('idx');
            const po_name = $(e.currentTarget).data('po');
            self.show_rm_receive_dialog(data, data.supplied_items[idx], po_name);
        });
    }

    // ── RM Purchase Dialog ──────────────────────────────────────────────
    show_rm_purchase_dialog(data, rm_item) {
        const self = this;
        const sco_name = data.sco_name;
        const rate = rm_item.last_purchase_rate || rm_item.valuation_rate || 0;

        const d = new frappe.ui.Dialog({
            title: __('Purchase Raw Material — {0}', [rm_item.rm_item_name || rm_item.rm_item_code]),
            fields: [
                {
                    fieldname: 'info_html',
                    fieldtype: 'HTML',
                    options: `<div class="mb-3 od-dialog-info">
                        <div><strong>${__('Item')}:</strong> ${frappe.utils.escape_html(rm_item.rm_item_name)} <span class="text-muted">(${rm_item.rm_item_code})</span></div>
                        <div><strong>${__('Shortage')}:</strong> <span class="text-danger font-weight-bold">${rm_item.shortage} ${rm_item.stock_uom}</span></div>
                        <div><strong>${__('Available')}:</strong> ${rm_item.available_qty} ${rm_item.stock_uom} in ${rm_item.reserve_warehouse}</div>
                    </div>`
                },
                {
                    fieldname: 'supplier',
                    fieldtype: 'Link',
                    options: 'Supplier',
                    label: __('Supplier'),
                    reqd: 1
                },
                { fieldtype: 'Column Break' },
                {
                    fieldname: 'schedule_date',
                    fieldtype: 'Date',
                    label: __('Required By Date'),
                    default: frappe.datetime.add_days(frappe.datetime.nowdate(), 7),
                    reqd: 1
                },
                { fieldtype: 'Section Break' },
                {
                    fieldname: 'qty',
                    fieldtype: 'Float',
                    label: __('Quantity'),
                    default: rm_item.shortage,
                    reqd: 1
                },
                { fieldtype: 'Column Break' },
                {
                    fieldname: 'rate',
                    fieldtype: 'Currency',
                    label: __('Rate'),
                    default: rate
                }
            ],
            primary_action_label: __('Create PO & Submit'),
            primary_action: (values) => {
                d.hide();
                frappe.call({
                    method: 'kniterp.api.outsourcing_desk.create_rm_purchase_order',
                    args: {
                        subcontracting_order: sco_name,
                        items: JSON.stringify([{
                            item_code: rm_item.rm_item_code,
                            qty: values.qty,
                            rate: values.rate || null,
                            warehouse: rm_item.reserve_warehouse,
                        }]),
                        supplier: values.supplier,
                        schedule_date: values.schedule_date,
                        warehouse: rm_item.reserve_warehouse,
                        submit: 1,
                    },
                    freeze: true,
                    freeze_message: __('Creating Purchase Order...'),
                    callback: (r) => {
                        if (r.message) {
                            frappe.show_alert({ message: __('PO {0} created', [r.message.name]), indicator: 'green' }, 5);
                            self.load_details(data.purchase_order.name);
                        }
                    }
                });
            },
            secondary_action_label: __('Create Draft'),
            secondary_action: () => {
                const values = d.get_values();
                if (!values) return;
                d.hide();
                frappe.call({
                    method: 'kniterp.api.outsourcing_desk.create_rm_purchase_order',
                    args: {
                        subcontracting_order: sco_name,
                        items: JSON.stringify([{
                            item_code: rm_item.rm_item_code,
                            qty: values.qty,
                            rate: values.rate || null,
                            warehouse: rm_item.reserve_warehouse,
                        }]),
                        supplier: values.supplier,
                        schedule_date: values.schedule_date,
                        warehouse: rm_item.reserve_warehouse,
                        submit: 0,
                    },
                    freeze: true,
                    callback: (r) => {
                        if (r.message) {
                            frappe.set_route('Form', 'Purchase Order', r.message.name);
                        }
                    }
                });
            }
        });
        d.show();
    }

    // ── RM Manufacture Dialog ───────────────────────────────────────────
    show_rm_manufacture_dialog(data, rm_item) {
        const self = this;
        const po_name = data.purchase_order.name;

        const d = new frappe.ui.Dialog({
            title: __('Manufacture Raw Material — {0}', [rm_item.rm_item_name || rm_item.rm_item_code]),
            fields: [
                {
                    fieldname: 'info_html',
                    fieldtype: 'HTML',
                    options: `<div class="mb-3 od-dialog-info">
                        <div><strong>${__('Item')}:</strong> ${frappe.utils.escape_html(rm_item.rm_item_name)} <span class="text-muted">(${rm_item.rm_item_code})</span></div>
                        <div><strong>${__('Shortage')}:</strong> <span class="text-danger font-weight-bold">${rm_item.shortage} ${rm_item.stock_uom}</span></div>
                        <div><strong>${__('BOM')}:</strong> <a href="/app/bom/${rm_item.default_bom}" target="_blank">${rm_item.default_bom}</a></div>
                    </div>`
                },
                {
                    fieldname: 'qty',
                    fieldtype: 'Float',
                    label: __('Quantity to Manufacture'),
                    default: rm_item.shortage,
                    reqd: 1
                },
                { fieldtype: 'Column Break' },
                {
                    fieldname: 'bom_no',
                    fieldtype: 'Link',
                    options: 'BOM',
                    label: __('BOM'),
                    default: rm_item.default_bom,
                    get_query: () => ({
                        filters: { item: rm_item.rm_item_code, is_active: 1, docstatus: 1 }
                    })
                },
                {
                    fieldname: 'fg_warehouse',
                    fieldtype: 'Link',
                    options: 'Warehouse',
                    label: __('Target Warehouse'),
                    default: rm_item.reserve_warehouse
                }
            ],
            primary_action_label: __('Create Work Order'),
            primary_action: (values) => {
                d.hide();
                frappe.call({
                    method: 'kniterp.api.outsourcing_desk.create_rm_work_order',
                    args: {
                        item_code: rm_item.rm_item_code,
                        qty: values.qty,
                        bom_no: values.bom_no,
                        fg_warehouse: values.fg_warehouse,
                    },
                    freeze: true,
                    freeze_message: __('Creating Work Order...'),
                    callback: (r) => {
                        if (r.message) {
                            // Show success dialog with navigation options
                            const wo_name = r.message.name;
                            frappe.confirm(
                                __('Work Order <strong>{0}</strong> created.<br><br>Would you like to open it in <strong>Production Wizard</strong> to start manufacturing?', [wo_name]),
                                () => {
                                    frappe.route_options = {
                                        invoice_status: 'Standalone',
                                        selected_item: wo_name,
                                        _od_return: po_name,
                                    };
                                    frappe.set_route('production-wizard');
                                },
                                () => {
                                    // Stay here, just refresh
                                    self.load_details(po_name);
                                }
                            );
                        }
                    }
                });
            }
        });
        d.show();
    }

    // ── RM Receive Dialog (Purchase Receipt) ────────────────────────────
    show_rm_receive_dialog(data, rm_item, po_name) {
        const self = this;
        const item_code = rm_item.rm_item_code;

        // Parallel fetch: PO pending qty + item batch setting
        let pending_qty = 0;
        let has_batch = false;
        let fetches_remaining = 2;

        const on_data_ready = () => {
            fetches_remaining--;
            if (fetches_remaining > 0) return;
            build_and_show();
        };

        frappe.db.get_value('Item', item_code, 'has_batch_no', (r) => {
            has_batch = !!(r && cint(r.has_batch_no));
            on_data_ready();
        });

        frappe.call({
            method: 'frappe.client.get',
            args: { doctype: 'Purchase Order', name: po_name },
            callback: (r) => {
                if (r.message) {
                    r.message.items.forEach(item => {
                        if (item.item_code === item_code) {
                            pending_qty += flt(item.qty - item.received_qty, 3);
                        }
                    });
                }
                on_data_ready();
            }
        });

        const build_and_show = () => {
            const fields = [
                {
                    fieldname: 'info_html',
                    fieldtype: 'HTML',
                    options: `<div class="mb-3 od-dialog-info">
                        <div><strong>${__('RM Item')}:</strong> ${frappe.utils.escape_html(rm_item.rm_item_name)}</div>
                        <div><strong>${__('Purchase Order')}:</strong> <a href="/app/purchase-order/${po_name}" target="_blank">${po_name}</a></div>
                    </div>`
                },
                {
                    fieldname: 'qty',
                    fieldtype: 'Float',
                    label: __('Quantity to Receive'),
                    reqd: 1,
                    read_only: has_batch ? 1 : 0,
                }
            ];

            if (has_batch) {
                fields.push(
                    { fieldtype: 'Section Break', label: __('Batch Details') },
                    {
                        fieldname: 'num_batches',
                        fieldtype: 'Int',
                        label: __('Number of Batches'),
                        description: __('How many different batches are you receiving?'),
                        default: 1,
                        onchange: function () {
                            render_batch_table(cint(this.value) || 1);
                        }
                    },
                    { fieldname: 'batch_table_html', fieldtype: 'HTML' }
                );
            }

            const d = new frappe.ui.Dialog({
                title: __('Receive Raw Material — {0}', [rm_item.rm_item_name || item_code]),
                fields,
                primary_action_label: __('Create & Submit'),
                primary_action: () => on_submit(d),
                secondary_action_label: __('Save as Draft'),
                secondary_action: () => on_draft(d),
            });

            const render_batch_table = (num_batches) => {
                let html = '<table class="table table-bordered table-condensed"><thead><tr>'
                    + `<th>${__('Quantity')}</th><th>${__('Batch No')}</th></tr></thead><tbody>`;
                for (let i = 0; i < num_batches; i++) {
                    const qty_val = (num_batches === 1 && pending_qty) ? pending_qty : '';
                    html += `<tr class="rm-batch-row">
                        <td><input type="number" class="form-control batch-qty" min="0" step="any" placeholder="${__('Qty')}" value="${qty_val}"></td>
                        <td><input type="text" class="form-control batch-lot" placeholder="${__('Batch No')}"></td>
                    </tr>`;
                }
                html += '</tbody></table>';
                d.fields_dict.batch_table_html.$wrapper.html(html);
                d.$wrapper.find('.batch-qty').on('input', () => {
                    let total = 0;
                    d.$wrapper.find('.batch-qty').each(function () { total += flt($(this).val()); });
                    d.set_value('qty', total);
                });
            };

            const on_submit = (dlg) => {
                const values = dlg.get_values();
                if (!values) return;

                let received_batches = null;

                if (has_batch) {
                    received_batches = [];
                    let total_batch_qty = 0;
                    let has_error = false;

                    dlg.$wrapper.find('.rm-batch-row').each(function () {
                        const row_qty = flt($(this).find('.batch-qty').val());
                        const row_lot = $(this).find('.batch-lot').val().trim();
                        if (!row_qty || row_qty <= 0) {
                            frappe.msgprint(__('Please enter a valid quantity for all batch rows.'));
                            has_error = true;
                            return false;
                        }
                        if (!row_lot) {
                            frappe.msgprint(__('Please enter a Batch No for all batch rows.'));
                            has_error = true;
                            return false;
                        }
                        received_batches.push({ qty: row_qty, batch_no: row_lot });
                        total_batch_qty += row_qty;
                    });

                    if (has_error) return;

                    if (Math.abs(total_batch_qty - flt(values.qty)) > 0.001) {
                        frappe.msgprint(__('Total batch quantities ({0}) must equal Quantity to Receive ({1})',
                            [total_batch_qty, values.qty]));
                        return;
                    }
                }

                dlg.hide();
                const args = {
                    purchase_order: po_name,
                    items: JSON.stringify([{ item_code, qty: values.qty }]),
                    submit: 1,
                };
                if (received_batches) args.received_batches = JSON.stringify(received_batches);

                frappe.call({
                    method: 'kniterp.api.outsourcing_desk.create_rm_purchase_receipt',
                    args,
                    freeze: true,
                    freeze_message: __('Creating and submitting Purchase Receipt...'),
                    callback: (r) => {
                        if (r.message) {
                            frappe.show_alert({ message: __('Purchase Receipt submitted'), indicator: 'green' });
                            frappe.set_route('Form', 'Purchase Receipt', r.message.name);
                            self.load_details(po_name);
                        }
                    }
                });
            };

            const on_draft = (dlg) => {
                dlg.hide();
                frappe.call({
                    method: 'kniterp.api.outsourcing_desk.create_rm_purchase_receipt',
                    args: {
                        purchase_order: po_name,
                        items: JSON.stringify([{ item_code, qty: dlg.get_value('qty') || pending_qty }]),
                    },
                    freeze: true,
                    freeze_message: __('Creating Purchase Receipt...'),
                    callback: (r) => {
                        if (r.message) {
                            frappe.set_route('Form', 'Purchase Receipt', r.message.name);
                        }
                    }
                });
            };

            if (pending_qty) d.set_value('qty', pending_qty);
            if (has_batch) render_batch_table(1);
            d.show();
        };
    }

    // ── Send Material Dialog ────────────────────────────────────────────
    show_send_material_dialog(data) {
        const self = this;
        const sco_name = data.sco_name;
        if (!sco_name) {
            frappe.msgprint(__('No Subcontracting Order found for this Purchase Order'));
            return;
        }

        const total_rm_pending = data.summary.total_rm_required - data.summary.total_rm_supplied;
        const total_fg_pending = data.summary.total_fg_ordered - data.summary.total_fg_received;
        const rm_per_fg = total_fg_pending > 0 ? total_rm_pending / total_fg_pending : 0;
        let _updating = false;

        const d = new frappe.ui.Dialog({
            title: __('Send Raw Material'),
            fields: [
                {
                    fieldname: 'info_html',
                    fieldtype: 'HTML',
                    options: (() => {
                        const rm_rows = (data.supplied_items || [])
                            .filter(si => si.pending_qty > 0)
                            .map(si => `<div style="display:flex;justify-content:space-between;padding:2px 0 2px 8px;">
                                <span>${frappe.utils.escape_html(si.rm_item_name || si.rm_item_code)}</span>
                                <span class="text-muted">${flt(si.pending_qty, 3)} ${frappe.utils.escape_html(si.stock_uom || '')}</span>
                            </div>`).join('');
                        return `<div class="mb-3" style="background:var(--control-bg); border:1px solid var(--border-color); border-radius:6px; padding:10px 14px; font-size:13px;">
                            <div><strong>${__('SCO')}:</strong> ${sco_name}</div>
                            <div><strong>${__('Pending FG Qty')}:</strong> ${total_fg_pending}</div>
                            <div style="margin-top:6px;"><strong>${__('Materials to Send')}:</strong></div>
                            ${rm_rows || `<div class="text-muted" style="padding-left:8px;">${__('No pending RM items')}</div>`}
                        </div>`;
                    })()
                },
                {
                    fieldname: 'fg_qty',
                    fieldtype: 'Float',
                    label: __('FG Qty'),
                    default: total_fg_pending,
                    reqd: 1,
                    change: () => {
                        if (_updating) return;
                        _updating = true;
                        const v = flt(d.get_value('fg_qty'), 3);
                        d.set_value('rm_qty', flt(v * rm_per_fg, 3)).then(() => _updating = false);
                    }
                },
                {
                    fieldname: 'rm_qty',
                    fieldtype: 'Float',
                    label: __('RM Qty'),
                    default: flt(total_rm_pending, 3),
                    reqd: 1,
                    change: () => {
                        if (_updating) return;
                        _updating = true;
                        const v = flt(d.get_value('rm_qty'), 3);
                        d.set_value('fg_qty', rm_per_fg > 0 ? flt(v / rm_per_fg, 3) : 0).then(() => _updating = false);
                    }
                },
                {
                    fieldtype: 'Section Break',
                    label: __('Transport Details'),
                    collapsible: 1
                },
                ...this._get_transport_field_definitions(),
                {
                    fieldtype: 'Section Break',
                    label: __('Package Details'),
                    collapsible: 1
                },
                {
                    fieldname: 'no_of_pkgs',
                    fieldtype: 'Int',
                    label: __('No. of Pkgs'),
                },
                {
                    fieldname: 'kind_of_pkgs',
                    fieldtype: 'Select',
                    label: __('Kind of Pkgs'),
                    options: '\nRolls\nBags\nBoxes\nOther',
                },
                {
                    fieldname: 'kind_of_pkgs_other',
                    fieldtype: 'Data',
                    label: __('Specify Kind'),
                    depends_on: "eval:doc.kind_of_pkgs=='Other'",
                    mandatory_depends_on: "eval:doc.kind_of_pkgs=='Other'",
                }
            ],
            primary_action_label: __('Create Stock Entry'),
            primary_action: (values) => {
                const qty = flt(values.fg_qty);
                if (qty <= 0) {
                    frappe.msgprint(__('Quantity must be greater than 0'));
                    return;
                }
                if (qty > total_fg_pending) {
                    frappe.msgprint(__('Quantity cannot exceed pending FG qty ({0})', [total_fg_pending]));
                    return;
                }
                d.hide();

                const extra_args = {};
                for (const f of ['transporter', 'transporter_name', 'gst_transporter_id',
                    'vehicle_no', 'lr_no', 'lr_date', 'distance',
                    'no_of_pkgs', 'kind_of_pkgs', 'kind_of_pkgs_other']) {
                    if (values[f]) extra_args[f] = values[f];
                }

                frappe.call({
                    method: 'kniterp.api.production_wizard.auto_split_subcontract_stock_entry',
                    args: {
                        sco_name: sco_name,
                        fg_qty: qty < total_fg_pending ? qty : null,
                        extra_args: Object.keys(extra_args).length ? JSON.stringify(extra_args) : null
                    },
                    freeze: true,
                    freeze_message: __('Drafting Stock Entry and allocating batches...'),
                    callback: (r) => {
                        if (r.message) {
                            frappe.set_route('Form', 'Stock Entry', r.message);
                        }
                    }
                });
            }
        });
        d.show();
    }

    // ── Receive Goods Dialog ────────────────────────────────────────────
    show_receive_goods_dialog(data) {
        const self = this;
        const po_name = data.purchase_order.name;
        const sco_name = data.sco_name;

        const pending_fg = data.summary.total_fg_ordered - data.summary.total_fg_received;
        const supplier = data.purchase_order.supplier_name;

        const context_html = `
            <div class="mb-3" style="background:var(--control-bg); border:1px solid var(--border-color); border-radius:6px; padding:10px 14px; color:var(--text-color);">
                <div style="font-size:13px; line-height:1.8;">
                    <div><strong>${__('Supplier')}:</strong> ${frappe.utils.escape_html(supplier)}</div>
                    <div><strong>${__('Order')}:</strong>
                        <a href="/app/purchase-order/${po_name}" target="_blank">${po_name}</a>
                        ${sco_name ? `&nbsp;/&nbsp;<a href="/app/subcontracting-order/${sco_name}" target="_blank">${sco_name}</a>` : ''}
                    </div>
                </div>
                <hr style="margin:8px 0; border-color:var(--border-color);">
                <div class="d-flex justify-content-between flex-wrap" style="font-size:12px; color:var(--text-muted);">
                    <span><strong>${__('Ordered')}:</strong> ${data.summary.total_fg_ordered}</span>
                    <span><strong>${__('Received')}:</strong> ${data.summary.total_fg_received}</span>
                    <span><strong>${__('Pending')}:</strong>
                        <span style="color:#fff; background:${pending_fg > 0 ? 'var(--yellow-500, #d97706)' : 'var(--green-500, #16a34a)'}; border-radius:4px; padding:1px 6px;">
                            ${pending_fg}
                        </span>
                    </span>
                </div>
            </div>
        `;

        const d = new frappe.ui.Dialog({
            title: __('Receive Goods — {0}', [supplier]),
            fields: [
                {
                    fieldname: 'order_context',
                    fieldtype: 'HTML',
                    options: context_html
                },
                {
                    fieldname: 'supplier_delivery_note',
                    fieldtype: 'Data',
                    label: __('Supplier Delivery Note'),
                    reqd: 1
                },
                {
                    fieldname: 'qty',
                    fieldtype: 'Float',
                    label: __('Quantity to Receive'),
                    reqd: 1,
                    default: 0
                },
                {
                    fieldname: 'rate',
                    fieldtype: 'Currency',
                    label: __('Rate (Final)'),
                    reqd: 0
                },
                {
                    fieldname: 'sb_pkgs',
                    fieldtype: 'Section Break',
                    label: __('Package Details')
                },
                {
                    fieldname: 'no_of_pkgs',
                    fieldtype: 'Int',
                    label: __('No. of Pkgs'),
                },
                {
                    fieldname: 'kind_of_pkgs',
                    fieldtype: 'Select',
                    label: __('Kind of Pkgs'),
                    options: '\nRolls\nBags\nBoxes\nOther',
                },
                {
                    fieldname: 'kind_of_pkgs_other',
                    fieldtype: 'Data',
                    label: __('Specify Kind'),
                    depends_on: "eval:doc.kind_of_pkgs=='Other'",
                    mandatory_depends_on: "eval:doc.kind_of_pkgs=='Other'",
                },
                {
                    fieldname: 'sb_lot',
                    fieldtype: 'Section Break',
                    label: __('Lot Traceability')
                },
                {
                    fieldname: 'num_batches',
                    fieldtype: 'Int',
                    label: __('Number of Output Batches Received'),
                    description: __('How many different batches did you receive for this quantity?'),
                    default: 1,
                    onchange: function () {
                        render_batch_table(cint(this.value) || 1);
                    }
                },
                {
                    fieldname: 'batch_table_html',
                    fieldtype: 'HTML'
                }
            ],
            primary_action_label: __('Create & Submit Receipt'),
            primary_action: (values) => {
                const received_batches = [];
                let total_batch_qty = 0;
                let has_error = false;

                d.$wrapper.find('.scr-batch-row').each(function () {
                    const row_qty = flt($(this).find('.batch-qty').val());
                    const row_lot = $(this).find('.batch-lot').val().trim();

                    if (!row_qty || row_qty <= 0) {
                        frappe.msgprint(__('Please enter a valid quantity for all batches.'));
                        has_error = true;
                        return false;
                    }
                    if (!row_lot) {
                        frappe.msgprint(__('Please enter a Lot No / Batch No for all batches.'));
                        has_error = true;
                        return false;
                    }

                    received_batches.push({ qty: row_qty, batch_no: row_lot });
                    total_batch_qty += row_qty;
                });

                if (has_error) return;

                if (Math.abs(total_batch_qty - flt(values.qty)) > 0.001) {
                    frappe.msgprint(__('Total batch quantities ({0}) must equal the Quantity to Receive ({1})',
                        [total_batch_qty, values.qty]));
                    return;
                }

                frappe.call({
                    method: 'kniterp.api.production_wizard.receive_subcontracted_goods',
                    args: {
                        purchase_order: po_name,
                        subcontracting_order: sco_name,
                        rate: values.rate,
                        supplier_delivery_note: values.supplier_delivery_note,
                        received_batches: JSON.stringify(received_batches),
                        no_of_pkgs: cint(values.no_of_pkgs) || 0,
                        kind_of_pkgs: values.kind_of_pkgs || '',
                        kind_of_pkgs_other: values.kind_of_pkgs_other || '',
                    },
                    freeze: true,
                    freeze_message: __('Creating Subcontracting Receipt...'),
                    callback: (r) => {
                        if (r.message) {
                            d.hide();
                            frappe.show_alert({
                                message: __('Subcontracting Receipt Created and Submitted'),
                                indicator: 'green'
                            });
                            self.load_details(po_name);
                            self.refresh_list();
                        }
                    }
                });
            }
        });

        const render_batch_table = (num_batches, prefill_qty) => {
            let html = '<table class="table table-bordered table-condensed"><thead><tr><th>'
                + __('Quantity') + '</th><th>' + __('Output Lot / Batch No') + '</th></tr></thead><tbody>';
            for (let i = 0; i < num_batches; i++) {
                const qty_val = (num_batches === 1 && prefill_qty) ? prefill_qty : '';
                html += `
                    <tr class="scr-batch-row">
                        <td><input type="number" class="form-control batch-qty" min="0" step="any" placeholder="${__('Qty')}" value="${qty_val}"></td>
                        <td><input type="text" class="form-control batch-lot" placeholder="${__('Lot No / Batch No')}"></td>
                    </tr>
                `;
            }
            html += '</tbody></table>';
            d.fields_dict.batch_table_html.$wrapper.html(html);

            d.$wrapper.find('.batch-qty').on('input', function () {
                let total = 0;
                d.$wrapper.find('.batch-qty').each(function () {
                    total += flt($(this).val());
                });
                d.set_value('qty', total);
            });
        };

        // Pre-populate with PO details
        frappe.call({
            method: 'frappe.client.get',
            args: { doctype: 'Purchase Order', name: po_name },
            callback: (po_res) => {
                if (po_res.message) {
                    const po = po_res.message;
                    let pending = 0;
                    let rate = 0;
                    if (po.items) {
                        po.items.forEach(item => {
                            let fg_received = item.received_qty || 0;
                            if (item.fg_item_qty && item.qty) {
                                fg_received = (item.received_qty || 0) * (item.fg_item_qty / item.qty);
                            }
                            const item_pending = (item.fg_item_qty || item.qty) - fg_received;
                            pending += Math.max(0, item_pending);
                            rate = item.rate;
                        });
                    }

                    d.set_value('qty', pending);
                    d.set_df_property('qty', 'description', __('Maximum receivable quantity: {0}', [pending]));
                    d.set_value('rate', rate);
                    d.show();
                    render_batch_table(1, pending);
                } else {
                    d.show();
                    render_batch_table(1);
                }
            }
        });
    }
}
