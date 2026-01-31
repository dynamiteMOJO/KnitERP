frappe.pages['production-wizard'].on_page_load = function (wrapper) {
    frappe.production_wizard = new ProductionWizard(wrapper);
};

frappe.pages['production-wizard'].refresh = function (wrapper) {
    if (frappe.production_wizard) {
        frappe.production_wizard.refresh();
    }
};

class ProductionWizard {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.page = frappe.ui.make_app_page({
            parent: wrapper,
            title: __('Production Wizard'),
            single_column: false
        });

        this.selected_item = null;
        this.filters = frappe.route_options || {};
        frappe.route_options = null; // Clear after reading

        this.setup_page();
        this.make_filters();
        this.apply_filters();
        this.make_layout();
        this.refresh();
    }

    apply_filters() {
        if (this.filters.customer) {
            this.customer_filter.set_value(this.filters.customer);
        }
        if (this.filters.from_date) {
            this.from_date_filter.set_value(this.filters.from_date);
        }
        if (this.filters.to_date) {
            this.to_date_filter.set_value(this.filters.to_date);
        }
        if (this.filters.urgent) {
            this.urgent_filter.set_value(this.filters.urgent);
        }
    }

    setup_page() {
        this.page.set_primary_action(__('Refresh'), () => this.refresh(), 'refresh');

        this.page.add_menu_item(__('Dashboard'), () => {
            this.show_dashboard();
        });
    }

    make_filters() {
        // Clear anything in sidebar just in case
        this.page.sidebar.empty();

        // Customer filter
        this.customer_filter = this.page.add_field({
            fieldname: 'customer',
            label: __('Customer'),
            fieldtype: 'Link',
            options: 'Customer',
            change: () => {
                this.filters.customer = this.customer_filter.get_value();
                this.refresh_pending_items();
            }
        });

        // From Date filter
        this.from_date_filter = this.page.add_field({
            fieldname: 'from_date',
            label: __('From Date'),
            fieldtype: 'Date',
            default: frappe.datetime.add_months(frappe.datetime.nowdate(), -1),
            change: () => {
                this.filters.from_date = this.from_date_filter.get_value();
                this.refresh_pending_items();
            }
        });

        // To Date filter
        this.to_date_filter = this.page.add_field({
            fieldname: 'to_date',
            label: __('To Date'),
            fieldtype: 'Date',
            default: frappe.datetime.add_months(frappe.datetime.nowdate(), 1),
            change: () => {
                this.filters.to_date = this.to_date_filter.get_value();
                this.refresh_pending_items();
            }
        });

        // Urgent filter
        this.urgent_filter = this.page.add_field({
            fieldname: 'urgent',
            label: __('Urgent Only'),
            fieldtype: 'Check',
            change: () => {
                this.filters.urgent = this.urgent_filter.get_value();
                this.refresh_pending_items();
            }
        });

        // Ensure the fields are styled correctly for the top bar
        this.page.page_form.css({
            'padding': '10px 15px',
            'background': 'var(--subtle-fg)',
            'border-bottom': '1px solid var(--border-color)',
            'margin-bottom': '10px'
        });
    }

    make_layout() {
        if (this.page.main.find('.production-wizard-container').length) return;

        this.page.main.append(`
			<div class="production-wizard-container">
				<div class="row">
					<div class="col-md-5">
						<div class="pending-items-panel">
							<div class="panel-header">
								<h5>${__('Pending Production Items')}</h5>
								<span class="item-count badge badge-secondary">0</span>
							</div>
							<div class="pending-items-list"></div>
						</div>
					</div>
					<div class="col-md-7">
						<div class="production-details-panel">
							<div class="panel-header">
								<h5>${__('Production Details')}</h5>
							</div>
							<div class="details-content">
								<div class="no-selection-message text-muted text-center p-5">
									<i class="fa fa-hand-pointer-o fa-3x mb-3"></i>
									<p>${__('Select an item from the left panel to view production details')}</p>
								</div>
							</div>
						</div>
					</div>
				</div>
			</div>
		`);

        this.$pending_list = this.page.main.find('.pending-items-list');
        this.$details_content = this.page.main.find('.details-content');
        this.$item_count = this.page.main.find('.item-count');
    }

    refresh() {
        // Refresh both panels
        this.refresh_pending_items();
        if (this.selected_item) {
            this.load_production_details(this.selected_item);
        }
    }

    refresh_pending_items() {
        this.$pending_list.html(`
			<div class="text-center p-4">
				<div class="spinner-border text-primary" role="status">
					<span class="sr-only">${__('Loading...')}</span>
				</div>
			</div>
		`);

        frappe.call({
            method: 'kniterp.api.production_wizard.get_pending_production_items',
            args: {
                filters: this.filters
            },
            callback: (r) => {
                this.pending_items = r.message || [];
                this.render_pending_items();
            }
        });
    }

    render_pending_items() {
        this.$item_count.text(this.pending_items.length);

        if (!this.pending_items.length) {
            this.$pending_list.html(`
				<div class="text-center text-muted p-4">
					<i class="fa fa-check-circle fa-3x mb-3 text-success"></i>
					<p>${__('No pending production items')}</p>
				</div>
			`);
            return;
        }

        let html = '';
        for (let item of this.pending_items) {
            const status_class = this.get_status_class(item);
            const status_label = this.get_status_label(item);

            html += `
				<div class="pending-item-card ${this.selected_item === item.sales_order_item ? 'selected' : ''}"
					 data-item="${item.sales_order_item}">
					<div class="item-header">
						<span class="so-number">${item.sales_order}</span>
						<span class="status-badge ${status_class}">${status_label}</span>
					</div>
					<div class="item-details">
						<div class="item-name">${item.item_name}</div>
						<div class="item-qty">
							<strong>${item.pending_qty}</strong> ${__('pending')}
							<span class="text-muted">/ ${item.qty} ${__('total')}</span>
						</div>
					</div>
					<div class="item-footer">
						<span class="customer-name">
							<i class="fa fa-user"></i> ${item.customer_name}
						</span>
						<span class="delivery-date">
							<i class="fa fa-calendar"></i> ${frappe.datetime.str_to_user(item.delivery_date)}
						</span>
					</div>
				</div>
			`;
        }

        this.$pending_list.html(html);

        // Bind click events
        this.$pending_list.find('.pending-item-card').on('click', (e) => {
            const item_id = $(e.currentTarget).data('item');
            this.select_item(item_id);
        });
    }

    get_status_class(item) {
        if (item.work_order_status === 'Completed') return 'status-completed';
        if (item.work_order_status) return 'status-in-progress';
        return 'status-pending';
    }

    get_status_label(item) {
        // Map internal states to business-friendly labels
        const status = item.work_order_status;
        if (!status) return __('Pending');
        if (status === 'Completed') return __('Completed');
        if (status === 'Draft') return __('Work Order Draft');
        if (status === 'Not Started') return __('Ready to Produce');
        if (status === 'In Process') return __('In Production');
        if (status === 'Stopped') return __('Production Stopped');
        return status;
    }

    select_item(sales_order_item) {
        this.selected_item = sales_order_item;

        // Update UI selection
        this.$pending_list.find('.pending-item-card').removeClass('selected');
        this.$pending_list.find(`[data-item="${sales_order_item}"]`).addClass('selected');

        // Load details
        this.load_production_details(sales_order_item);
    }

    load_production_details(sales_order_item) {
        this.$details_content.html(`
			<div class="text-center p-4">
				<div class="spinner-border text-primary" role="status">
					<span class="sr-only">${__('Loading...')}</span>
				</div>
			</div>
		`);

        frappe.call({
            method: 'kniterp.api.production_wizard.get_production_details',
            args: {
                sales_order_item: sales_order_item
            },
            callback: (r) => {
                if (r.message) {
                    this.current_details = r.message;
                    this.render_production_details(r.message);
                }
            }
        });
    }

    render_production_details(details) {
        let html = `
			<div class="production-details">
				<!-- Header -->
				<div class="details-header">
					<div class="item-info">
						<h4>${details.item_name}</h4>
						<span class="text-muted">${details.item_code}</span>
					</div>
					<div class="qty-info">
						<div class="big-number">${frappe.format(details.projected_qty, { fieldtype: 'Float', precision: 2 })}</div>
						<div class="text-muted">${__('Projected FG Qty')}</div>
					</div>
				</div>

				<!-- Info Cards -->
				<div class="info-cards">
					<div class="info-card">
						<i class="fa fa-file-text-o"></i>
						<div>
							<div class="label">${__('Sales Order')}</div>
							<a href="/app/sales-order/${details.sales_order}">${details.sales_order}</a>
						</div>
					</div>
					<div class="info-card">
						<i class="fa fa-sitemap"></i>
						<div>
							<div class="label">${__('BOM')}</div>
							${details.bom_no ?
                `<a href="/app/bom/${details.bom_no}">${details.bom_no}</a>` :
                `<button class="btn btn-xs btn-primary btn-create-bom-designer" data-item="${details.item_code}">
									<i class="fa fa-plus"></i> ${__('Create BOM')}
								</button>`
            }
						</div>
					</div>
					<div class="info-card">
						<i class="fa fa-calendar"></i>
						<div>
							<div class="label">${__('Delivery Date')}</div>
							<span>${frappe.datetime.str_to_user(details.delivery_date)}</span>
						</div>
					</div>
					${details.work_order ? `
					<div class="info-card">
						<i class="fa fa-cogs"></i>
						<div>
							<div class="label">${__('Work Order')}</div>
							<a href="/app/work-order/${details.work_order.name}">${details.work_order.name}</a>
							<span class="badge badge-info ml-1">${details.work_order.status}</span>
						</div>
					</div>
					` : ''}
				</div>

				<!-- Primary Actions -->
				<div class="primary-actions">
					${details.bom_no ? this.get_primary_action_buttons(details) : ''}
				</div>

				<!-- Operations Section -->
				<div class="section-header">
					<h5><i class="fa fa-tasks"></i> ${__('Operations')}</h5>
				</div>
				<div class="operations-list">
					${details.bom_no ? this.render_operations(details) : `<div class="text-muted p-3">${__('Please create a BOM to view operations')}</div>`}
				</div>

				<!-- Raw Materials Section -->
				<div class="section-header">
					<h5><i class="fa fa-cube"></i> ${__('Raw Materials')}</h5>
					${this.has_shortages(details.raw_materials) ? `
						<button class="btn btn-sm btn-warning create-shortage-po">
							<i class="fa fa-shopping-cart"></i> ${__('Create PO for Shortages')}
						</button>
					` : ''}
				</div>
				<div class="materials-list">
					${this.render_raw_materials(details.raw_materials)}
				</div>
			</div>
		`;

        this.$details_content.html(html);
        this.bind_action_events(details);
    }

    get_primary_action_buttons(details) {
        let buttons = [];

        if (!details.work_order) {
            buttons.push(`
				<button class="btn btn-primary btn-create-wo">
					<i class="fa fa-plus"></i> ${__('Create Work Order')}
				</button>
			`);
        } else if (details.work_order.status === 'Draft') {
            buttons.push(`
				<button class="btn btn-primary btn-start-wo">
					<i class="fa fa-play"></i> ${__('Start Production')}
				</button>
			`);
        } else if (details.work_order.status === 'Completed') {
            buttons.push(`
				<button class="btn btn-success btn-create-delivery">
					<i class="fa fa-truck"></i> ${__('Create Delivery Note')}
				</button>
			`);
        }

        return buttons.join('');
    }

    render_operations(details) {
        if (!details.operations || !details.operations.length) {
            return `<div class="text-muted p-3">${__('No operations defined in BOM')}</div>`;
        }

        let html = '';
        for (let op of details.operations) {
            const status_class = this.get_operation_status_class(op);
            const status_icon = this.get_operation_status_icon(op);
            const type_badge = op.is_subcontracted ?
                `<span class="badge badge-warning"><i class="fa fa-external-link"></i> ${__('Subcontracted')}</span>` :
                `<span class="badge badge-info"><i class="fa fa-home"></i> ${__('In-house')}</span>`;

            let progress_html = '';

            if (op.is_subcontracted && op.purchase_order) {
                const sent_raw = op.sent_qty || 0;
                const recvd_raw = op.received_qty || 0;
                const po_qty_raw = op.po_qty || 0;

                const sent = frappe.format(sent_raw, { fieldtype: 'Float', precision: 2 });
                const recvd = frappe.format(recvd_raw, { fieldtype: 'Float', precision: 2 });
                const po_qty_fmt = frappe.format(po_qty_raw, { fieldtype: 'Float', precision: 2 });

                const sent_pct = po_qty_raw ? Math.min(100, (sent_raw / po_qty_raw) * 100) : 0;
                const recd_pct = this.get_operation_progress(op, details);

                let send_btn = '';
                if (recvd_raw < po_qty_raw) {
                    send_btn = `<button class="btn btn-xs btn-warning btn-send-material" data-operation="${op.operation}" data-po="${op.purchase_order}" title="${__('Send Raw Material')}">
                        <i class="fa fa-truck"></i> ${__('Send Raw Material')}
                    </button>`;
                }

                let recd_btn = '';
                if (sent_raw > 0 && recvd_raw < po_qty_raw) {
                    recd_btn = `<button class="btn btn-xs btn-success btn-receive-goods" data-operation="${op.operation}" data-po="${op.purchase_order}" title="${__('Receive Goods')}">
                        <i class="fa fa-download"></i> ${__('Receive Goods')}
                    </button>`;
                }

                progress_html = `
                    <div class="op-progress-container">
                        <!-- Sent Section -->
                        <div class="op-progress-row mb-3">
                            <div class="op-progress-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                                <span class="op-progress-label" style="font-size: 11px; font-weight: 600; color: var(--text-muted);">${__('Sent')}</span>
                                <span class="op-progress-summary" style="font-size: 13px; font-weight: 700; white-space: nowrap !important; display: flex; align-items: center;">
                                    ${sent}&nbsp;/&nbsp;${po_qty_fmt}
                                </span>
                            </div>
                            <div class="op-progress-bar-container" style="margin-bottom: 8px;">
                                <div class="progress" style="height: 8px; background: var(--control-bg); border-radius: 4px; overflow: hidden;">
                                    <div class="progress-bar bg-warning" style="width: ${sent_pct}%"></div>
                                </div>
                            </div>
                            ${send_btn ? `<div class="op-btn-container" style="text-align: left;">${send_btn}</div>` : ''}
                        </div>

                        <!-- Received Section -->
                        <div class="op-progress-row">
                            <div class="op-progress-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                                <span class="op-progress-label" style="font-size: 11px; font-weight: 600; color: var(--text-muted);">${__('Received')}</span>
                                <span class="op-progress-summary" style="font-size: 13px; font-weight: 700; white-space: nowrap !important; display: flex; align-items: center;">
                                    ${recvd}&nbsp;/&nbsp;${po_qty_fmt}
                                </span>
                            </div>
                            <div class="op-progress-bar-container" style="margin-bottom: 8px;">
                                <div class="progress" style="height: 8px; background: var(--control-bg); border-radius: 4px; overflow: hidden;">
                                    <div class="progress-bar bg-success" style="width: ${recd_pct}%"></div>
                                </div>
                            </div>
                            ${recd_btn ? `<div class="op-btn-container" style="text-align: left;">${recd_btn}</div>` : ''}
                        </div>
                    </div>
                `;
            } else {
                const completed_fmt = frappe.format(op.completed_qty || 0, { fieldtype: 'Float', precision: 2 });
                const total_fmt = frappe.format(op.for_quantity || details.pending_qty, { fieldtype: 'Float', precision: 2 });
                const pct = this.get_operation_progress(op, details);

                progress_html = `
                    <div class="op-progress-row">
                        <div class="op-progress-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                            <span></span>
                             <span class="op-progress-summary" style="font-size: 13px; font-weight: 700; white-space: nowrap !important; display: flex; align-items: center;">
                                ${completed_fmt}&nbsp;/&nbsp;${total_fmt}
                             </span>
                        </div>
                        <div class="op-progress-bar-container">
                            <div class="progress" style="height: 10px; background: var(--control-bg); border-radius: 4px; overflow: hidden;">
                                <div class="progress-bar" style="width: ${pct}%"></div>
                            </div>
                        </div>
                    </div>
                `;
            }

            const links_html = `
                ${op.job_card ? `<div class="op-link mt-1"><i class="fa fa-link mr-1"></i><a href="/app/job-card/${op.job_card}" class="small">${op.job_card}</a></div>` : ''}
                ${op.purchase_order ? `<div class="op-link mt-1"><i class="fa fa-shopping-cart mr-1"></i><a href="/app/purchase-order/${op.purchase_order}" class="small">${op.purchase_order}</a></div>` : ''}
            `;

            html += `
				<div class="operation-card ${status_class}">
					<div class="op-header">
						<span class="op-number">${op.idx}</span>
						<div class="flex-fill">
						    <div class="d-flex align-items-center">
                                <span class="op-name">${op.operation}</span>
                                ${type_badge}
                            </div>
                            ${links_html}
						</div>
						<span class="op-status">${status_icon} ${op.status}</span>
					</div>
					<div class="op-details" style="display: flex; flex-direction: column; gap: 10px; margin-top: 10px;">
						${progress_html}
					</div>
					<div class="op-actions" style="margin-top: 10px;">
						${this.get_operation_actions(op, details)}
					</div>
				</div>
                    `;
        }

        return html;
    }

    get_operation_status_class(op) {
        if (op.status === 'Completed') return 'completed';
        if (op.status === 'Work In Progress') return 'in-progress';
        if (op.status === 'Material Transferred') return 'in-progress';
        return 'pending';
    }

    get_operation_status_icon(op) {
        if (op.status === 'Completed') return '✅';
        if (op.status === 'Work In Progress') return '🔄';
        if (op.status === 'Material Transferred') return '📦';
        if (op.is_subcontracted) return '🏭';
        return '⏳';
    }

    get_operation_progress(op, details) {
        const total_qty = op.for_quantity || details.pending_qty;
        if (!total_qty) return 0;
        return Math.min(100, ((op.completed_qty || 0) / total_qty) * 100);
    }

    get_operation_actions(op, details) {
        let actions = [];

        if (!details.work_order || details.work_order.status === 'Draft') {
            return ''; // No actions until work order is started
        }

        if (op.status === 'Completed') {
            return `<span class="text-success"><i class="fa fa-check"></i> ${__('Done')}</span>`;
        }

        // Check if previous operation is complete (sequence enforcement)
        if (!op.previous_complete) {
            return `<span class="text-muted"><i class="fa fa-lock"></i> ${__('Waiting for previous operation')}</span>`;
        }

        if (op.is_subcontracted) {
            if (!op.purchase_order) {
                actions.push(`
					<button class="btn btn-sm btn-primary btn-create-sco"
							data-operation="${op.operation}">
						<i class="fa fa-file-text-o"></i> ${__('Create Subcontracting Order')}
					</button>
                    `);
            } else {
                // PO exists - show progress and buttons based on state
                const sent_qty = op.sent_qty || 0;
                const received_qty = op.received_qty || 0;
                const po_qty = op.po_qty || 0;

                // Show subcontracting progress
                // Moved to main progress bar


                // Action buttons are now inline with progress bars
                /*
                // Send Material button - always show if not fully received
                if (received_qty < po_qty) {
                    actions.push(`...`);
                }
                // Receive Goods button - only show if some material has been sent
                if (sent_qty > 0 && received_qty < po_qty) {
                    actions.push(`...`);
                }
                */
            }
        } else {
            // In-house operation
            const remaining_qty = (op.for_quantity || details.pending_qty) - (op.completed_qty || 0);
            if (op.status !== 'Completed' && remaining_qty > 0) {
                actions.push(`
					<button class="btn btn-sm btn-primary btn-complete-op"
							data-operation="${op.operation}"
							data-remaining="${remaining_qty}">
						<i class="fa fa-plus-circle"></i> ${__('Update Manufactured Qty')}
					</button>
                    `);
            }
            if (op.job_card && op.completed_qty >= (op.for_quantity || details.pending_qty) && op.status !== 'Completed') {
                actions.push(`
					<button class="btn btn-sm btn-success btn-finish-jc"
							data-operation="${op.operation}"
							data-job-card="${op.job_card}">
						<i class="fa fa-check-circle"></i> ${__('Complete Job Card')}
					</button>
                    `);
            }
        }

        return actions.join('');
    }

    render_raw_materials(materials) {
        if (!materials || !materials.length) {
            return `<div class="text-muted p-3">${__('No raw materials required')}</div>`;
        }

        let html = '<table class="table table-sm materials-table"><thead><tr>';
        html += `<th>${__('Item')}</th>`;
        html += `<th class="text-right">${__('Required')}</th>`;
        html += `<th class="text-right">${__('Available')}</th>`;
        html += `<th class="text-right">${__('Ordered')}</th>`;
        html += `<th class="text-right">${__('Consumed')}</th>`;
        html += `<th class="text-right">${__('Shortage')}</th>`;
        html += `<th>${__('Status')}</th>`;
        html += `<th>${__('Actions')}</th>`;
        html += '</tr></thead><tbody>';

        for (let m of materials) {
            const status_badge = this.get_material_status_badge(m);

            // If consumed, show consumed qty; otherwise show shortage
            const consumed_display = m.status === 'consumed' && m.consumed_qty > 0
                ? parseFloat(m.consumed_qty || 0).toFixed(3)
                : '-';
            const shortage_display = m.status === 'consumed'
                ? '-'
                : parseFloat(m.shortage || 0).toFixed(3);
            const shortage_class = (m.status !== 'consumed' && m.shortage > 0) ? 'text-danger font-weight-bold' : '';
            const consumed_class = m.status === 'consumed' ? 'text-info font-weight-bold' : '';

            // Ordered column with PO links
            let ordered_html = '-';
            if (m.linked_pos && m.linked_pos.length > 0) {
                const po_links = m.linked_pos.map(po =>
                    `<a href="/app/purchase-order/${po.po_name}" style="color: var(--text-color);">${po.po_name}</a>`
                ).join(', ');
                ordered_html = `<div class="font-weight-bold" style="color: var(--text-color);">${parseFloat(m.ordered_qty || 0).toFixed(3)}</div>
                    <div class="small" style="color: var(--text-muted);">${po_links}</div>`;
            }

            // Actions column
            let actions_html = '';
            if (m.linked_pos && m.linked_pos.length > 0) {
                const first_po = m.linked_pos[0];
                if (first_po.status === 'To Receive and Bill' || first_po.status === 'To Receive') {
                    actions_html = `<button class="btn btn-xs btn-success create-pr-btn" data-po="${first_po.po_name}">
                        <i class="fa fa-download"></i> ${__('Create PR')}
                    </button>`;
                }
            }

            html += `
				<tr class="material-row ${m.status}">
					<td>
						<a href="/app/item/${m.item_code}">${m.item_code}</a>
						<div class="text-muted small">${m.item_name}</div>
					</td>
					<td class="text-right">${parseFloat(m.required_qty || 0).toFixed(3)} ${m.uom}</td>
					<td class="text-right">${parseFloat(m.available_qty || 0).toFixed(3)} ${m.uom}</td>
					<td class="text-right">${ordered_html}</td>
					<td class="text-right ${consumed_class}">${consumed_display}</td>
					<td class="text-right ${shortage_class}">${shortage_display}</td>
					<td>${status_badge}</td>
					<td>${actions_html}</td>
				</tr>
                    `;
        }

        html += '</tbody></table>';
        return html;
    }

    get_material_status_badge(material) {
        if (material.status === 'consumed') {
            return `<span class="badge badge-info">✓ ${__('Consumed')}</span>`;
        } else if (material.status === 'available') {
            return `<span class="badge badge-success">✓ ${__('Available')}</span>`;
        } else if (material.linked_pos && material.linked_pos.length > 0) {
            // Has pending POs
            const first_po = material.linked_pos[0];
            if (first_po.status === 'To Receive and Bill' || first_po.status === 'To Receive') {
                return `<span class="badge badge-primary">📦 ${__('Awaiting PR')}</span>`;
            } else {
                return `<span class="badge badge-info">📋 ${__('PO Created')}</span>`;
            }
        } else if (material.status === 'low') {
            return `<span class="badge badge-warning">⚠ ${__('Low Stock')}</span>`;
        } else {
            return `<span class="badge badge-danger">✗ ${__('Shortage')}</span>`;
        }
    }

    has_shortages(materials) {
        return materials && materials.some(m => m.shortage > 0);
    }

    bind_action_events(details) {
        const self = this;

        // Create Work Order
        this.$details_content.find('.btn-create-wo').on('click', () => {
            this.create_work_order(details);
        });

        // Start Work Order
        this.$details_content.find('.btn-start-wo').on('click', () => {
            this.start_work_order(details);
        });

        // Create Delivery Note
        this.$details_content.find('.btn-create-delivery').on('click', () => {
            this.create_delivery_note(details);
        });

        // Create Subcontracting Order
        this.$details_content.find('.btn-create-sco').on('click', function () {
            const operation = $(this).data('operation');
            self.create_subcontracting_order(details, operation);
        });

        // Send Raw Material to Supplier
        this.$details_content.find('.btn-send-material').on('click', function () {
            const po = $(this).data('po');
            self.send_raw_material_to_supplier(po);
        });

        // Receive Goods
        this.$details_content.find('.btn-receive-goods').on('click', function () {
            const po = $(this).data('po');
            self.receive_subcontracted_goods(po);
        });

        // Update Manufactured Qty
        this.$details_content.find('.btn-complete-op').on('click', function () {
            const operation = $(this).data('operation');
            const remaining = $(this).data('remaining');
            self.complete_operation(details, operation, remaining);
        });

        // Complete Job Card
        this.$details_content.find('.btn-finish-jc').on('click', function () {
            const operation = $(this).data('operation');
            const job_card = $(this).data('job-card');
            self.complete_job_card(details, operation, job_card);
        });

        // Create PO for Shortages
        this.$details_content.find('.create-shortage-po').on('click', () => {
            this.create_shortage_po(details);
        });

        // Create Purchase Receipt from PO
        this.$details_content.find('.create-pr-btn').on('click', function () {
            const po_name = $(this).data('po');
            self.create_purchase_receipt(po_name);
        });

        // Create BOM Designer
        this.$details_content.find('.btn-create-bom-designer').on('click', function () {
            const item_code = $(this).data('item');
            window.open(`/app/bom_designer?item_code=${encodeURIComponent(item_code)}`, '_blank');
        });
    }

    create_purchase_receipt(po_name) {
        const self = this;
        frappe.call({
            method: 'erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_receipt',
            args: {
                source_name: po_name
            },
            freeze: true,
            freeze_message: __('Creating Purchase Receipt...'),
            callback: (r) => {
                if (r.message) {
                    // The method returns a doc object, sync it and open in form
                    const doc = frappe.model.sync(r.message)[0];
                    frappe.set_route('Form', doc.doctype, doc.name);
                }
            }
        });
    }

    create_work_order(details) {
        frappe.call({
            method: 'kniterp.api.production_wizard.create_work_order',
            args: {
                sales_order: details.sales_order,
                sales_order_item: details.sales_order_item
            },
            freeze: true,
            freeze_message: __('Creating Work Order...'),
            callback: (r) => {
                if (r.message) {
                    frappe.show_alert({
                        message: __('Work Order {0} created successfully',
                            [`<a href="/app/work-order/${r.message}">${r.message}</a>`]),
                        indicator: 'green'
                    }, 5);
                    this.refresh_pending_items();
                    this.load_production_details(this.selected_item);
                }
            }
        });
    }

    start_work_order(details) {
        frappe.confirm(
            __('This will submit the Work Order and create Job Cards. Continue?'),
            () => {
                frappe.call({
                    method: 'kniterp.api.production_wizard.start_work_order',
                    args: {
                        work_order: details.work_order.name
                    },
                    freeze: true,
                    freeze_message: __('Starting Production...'),
                    callback: (r) => {
                        if (r.message) {
                            frappe.show_alert({
                                message: __('Work Order {0} started. Job Cards created.',
                                    [`<a href="/app/work-order/${r.message.work_order}">${r.message.work_order}</a>`]),
                                indicator: 'green'
                            }, 5);
                            // Refresh both panels
                            this.refresh_pending_items();
                            this.load_production_details(this.selected_item);
                        }
                    }
                });
            }
        );
    }

    create_subcontracting_order(details, operation) {
        const self = this;

        // Find the operation to get for_quantity
        const op = details.operations.find(o => o.operation === operation);
        const default_qty = op?.for_quantity || details.pending_qty;

        // Show supplier selection dialog
        const d = new frappe.ui.Dialog({
            title: __('Create Subcontracting Order'),
            fields: [
                {
                    fieldname: 'supplier',
                    fieldtype: 'Link',
                    options: 'Supplier',
                    label: __('Supplier'),
                    reqd: 1,
                    get_query: () => {
                        return {
                            filters: {
                                'disabled': 0
                            }
                        };
                    }
                },
                {
                    fieldname: 'qty',
                    fieldtype: 'Float',
                    label: __('Quantity'),
                    default: default_qty,
                    description: __('Quantity to be processed by subcontractor')
                }
            ],
            primary_action_label: __('Create & Submit'),
            primary_action(values) {
                frappe.call({
                    method: 'kniterp.api.production_wizard.create_subcontracting_order',
                    args: {
                        work_order: details.work_order.name,
                        operation: operation,
                        supplier: values.supplier,
                        qty: values.qty
                    },
                    freeze: true,
                    freeze_message: __('Creating and Submitting Subcontracting Order...'),
                    callback: (r) => {
                        if (r.message) {
                            d.hide();
                            frappe.show_alert({
                                message: __('PO {0} and SCO {1} created and submitted',
                                    [`<a href="/app/purchase-order/${r.message.purchase_order}">${r.message.purchase_order}</a>`,
                                    `<a href="/app/subcontracting-order/${r.message.subcontracting_order}">${r.message.subcontracting_order}</a>`]),
                                indicator: 'green'
                            }, 7);
                            self.refresh_pending_items();
                            self.load_production_details(self.selected_item);
                        }
                    }
                });
            }
        });

        d.show();
    }

    send_raw_material_to_supplier(purchase_order) {
        // Open the Stock Entry form with Send to Subcontractor purpose
        frappe.call({
            method: 'frappe.client.get_value',
            args: {
                doctype: 'Subcontracting Order',
                filters: { 'purchase_order': purchase_order, 'docstatus': 1 },
                fieldname: 'name'
            },
            callback: (r) => {
                if (r.message && r.message.name) {
                    frappe.new_doc('Stock Entry', {
                        'purpose': 'Send to Subcontractor',
                        'subcontracting_order': r.message.name
                    });
                } else {
                    frappe.msgprint(__('No submitted Subcontracting Order found for this Purchase Order'));
                }
            }
        });
    }

    receive_subcontracted_goods(purchase_order) {
        frappe.call({
            method: 'kniterp.api.production_wizard.receive_subcontracted_goods',
            args: {
                purchase_order: purchase_order
            },
            freeze: true,
            freeze_message: __('Creating Subcontracting Receipt...'),
            callback: (r) => {
                if (r.message) {
                    frappe.set_route('Form', 'Subcontracting Receipt', r.message);
                }
            }
        });
    }

    complete_operation(details, operation, remaining_qty) {
        const self = this;

        // Find the operation to get for_quantity
        const op = details.operations.find(o => o.operation === operation);
        const default_qty = remaining_qty || op?.for_quantity || details.pending_qty;

        const d = new frappe.ui.Dialog({
            title: __('Update Manufactured Quantity'),
            fields: [
                {
                    fieldname: 'qty',
                    fieldtype: 'Float',
                    label: __('Quantity Manufactured'),
                    default: default_qty,
                    reqd: 1
                }
            ],
            primary_action_label: __('Update'),
            primary_action(values) {
                frappe.call({
                    method: 'kniterp.api.production_wizard.complete_operation',
                    args: {
                        work_order: details.work_order.name,
                        operation: operation,
                        qty: values.qty
                    },
                    freeze: true,
                    freeze_message: __('Updating Manufactured Quantity...'),
                    callback: (r) => {
                        if (r.message) {
                            d.hide();
                            frappe.show_alert({
                                message: __('Operation {0} updated with qty {1}', [operation, values.qty]),
                                indicator: 'green'
                            }, 3);
                            self.refresh_pending_items();
                            self.load_production_details(self.selected_item);
                        }
                    }
                });
            }
        });

        d.show();
    }

    complete_job_card(details, operation, job_card) {
        const self = this;

        // Find the operation
        const op = details.operations.find(o => o.operation === operation);
        const remaining_qty = (op?.for_quantity || details.pending_qty) - (op?.completed_qty || 0);

        // Fetch Job Card details to pre-populate dialog
        frappe.call({
            method: 'frappe.client.get',
            args: {
                doctype: 'Job Card',
                name: job_card
            },
            async: false,
            callback: (r) => {
                if (!r.message) {
                    frappe.msgprint(__('Could not load Job Card details'));
                    return;
                }

                const jc = r.message;
                const work_order_skip = details.work_order?.skip_transfer || false;
                const jc_skip = jc.skip_material_transfer || false;
                const current_skip = work_order_skip || jc_skip;

                // Build items table fields
                const item_fields = [];
                if (jc.items && jc.items.length > 0) {
                    item_fields.push({
                        fieldname: 'section_items',
                        fieldtype: 'Section Break',
                        label: __('Raw Materials - Source Warehouses')
                    });

                    for (let i = 0; i < jc.items.length; i++) {
                        const item = jc.items[i];
                        item_fields.push({
                            fieldname: 'item_info_' + i,
                            fieldtype: 'HTML',
                            options: `
                    <div style="margin-top: 10px; margin-bottom: 5px;">
                                    <span style="font-weight: bold; color: var(--text-color); font-size: 13px;">${item.item_code}</span>
                                    <span style="color: var(--text-muted); font-size: 12px; margin-left: 8px;">(Req: <strong style="color: var(--text-color);">${parseFloat(item.required_qty || 0).toFixed(3)} ${item.uom || ''}</strong>)</span>
                                </div>
                    <div style="color: var(--text-muted); font-size: 11px; margin-bottom: 5px;">${item.item_name || ''}</div>
                `
                        });
                        item_fields.push({
                            fieldname: 'source_warehouse_' + item.item_code,
                            fieldtype: 'Link',
                            options: 'Warehouse',
                            label: __('Source Warehouse'),
                            default: item.source_warehouse || '',
                            reqd: 1
                        });
                    }
                }

                const d = new frappe.ui.Dialog({
                    title: __('Complete Job Card: {0}', [job_card]),
                    size: 'large',
                    fields: [
                        {
                            fieldname: 'section_settings',
                            fieldtype: 'Section Break',
                            label: __('Material Transfer Settings')
                        },
                        {
                            fieldname: 'skip_material_transfer',
                            fieldtype: 'Check',
                            label: __('Skip Material Transfer to WIP Warehouse'),
                            default: current_skip ? 1 : 0,
                            description: __('If checked, materials will be consumed directly from source warehouse'),
                            onchange: function () {
                                const skip = d.get_value('skip_material_transfer');
                                d.set_df_property('wip_warehouse', 'hidden', skip);
                                d.set_df_property('wip_warehouse', 'reqd', !skip);
                            }
                        },
                        {
                            fieldname: 'wip_warehouse',
                            fieldtype: 'Link',
                            options: 'Warehouse',
                            label: __('WIP Warehouse'),
                            default: jc.wip_warehouse || details.work_order?.wip_warehouse || '',
                            hidden: current_skip,
                            reqd: !current_skip,
                            description: __('Work In Progress warehouse for material transfer')
                        },
                        ...item_fields,
                        {
                            fieldname: 'section_qty',
                            fieldtype: 'Section Break',
                            label: __('Quantity')
                        },
                        {
                            fieldname: 'pending_qty',
                            fieldtype: 'Float',
                            label: __('Additional Quantity (if any)'),
                            default: remaining_qty > 0 ? remaining_qty : 0,
                            description: __('Enter any remaining quantity to manufacture')
                        },
                        {
                            fieldname: 'col_break',
                            fieldtype: 'Column Break'
                        },
                        {
                            fieldname: 'process_loss_qty',
                            fieldtype: 'Float',
                            label: __('Process Loss Quantity'),
                            default: 0,
                            description: __('Enter process loss quantity if applicable')
                        }
                    ],
                    primary_action_label: __('Complete Job Card'),
                    primary_action(values) {
                        // Collect source warehouses
                        const source_warehouses = {};
                        for (let item of jc.items) {
                            const wh = values['source_warehouse_' + item.item_code];
                            if (wh) {
                                source_warehouses[item.item_code] = wh;
                            }
                        }

                        frappe.call({
                            method: 'kniterp.api.production_wizard.complete_job_card',
                            args: {
                                job_card: job_card,
                                additional_qty: values.pending_qty || 0,
                                process_loss_qty: values.process_loss_qty || 0,
                                wip_warehouse: values.wip_warehouse || '',
                                skip_material_transfer: values.skip_material_transfer ? 1 : 0,
                                source_warehouses: JSON.stringify(source_warehouses)
                            },
                            freeze: true,
                            freeze_message: __('Completing Job Card...'),
                            callback: (r) => {
                                if (r.message) {
                                    d.hide();
                                    frappe.show_alert({
                                        message: __('Job Card {0} completed. Stock Entry {1} created.',
                                            [`<a href="/app/job-card/${job_card}">${job_card}</a>`,
                                            `<a href="/app/stock-entry/${r.message}">${r.message}</a>`]),
                                        indicator: 'green'
                                    }, 5);
                                    self.refresh_pending_items();
                                    self.load_production_details(self.selected_item);
                                }
                            }
                        });
                    }
                });

                d.show();
            }
        });
    }

    create_shortage_po(details) {
        const shortage_items = details.raw_materials.filter(m => m.shortage > 0);

        if (!shortage_items.length) {
            frappe.msgprint(__('No shortages to order'));
            return;
        }

        const self = this;
        const default_warehouse = details.work_order?.source_warehouse || 'Stores - O';

        const d = new frappe.ui.Dialog({
            title: __('Create Purchase Order for Shortages'),
            size: 'large',
            fields: [
                {
                    fieldname: 'supplier',
                    fieldtype: 'Link',
                    options: 'Supplier',
                    label: __('Supplier'),
                    reqd: 1
                },
                {
                    fieldname: 'col_break_1',
                    fieldtype: 'Column Break'
                },
                {
                    fieldname: 'schedule_date',
                    fieldtype: 'Date',
                    label: __('Required By Date'),
                    default: frappe.datetime.add_days(frappe.datetime.nowdate(), 7),
                    reqd: 1
                },
                {
                    fieldname: 'warehouse',
                    fieldtype: 'Link',
                    options: 'Warehouse',
                    label: __('Target Warehouse'),
                    default: default_warehouse
                },
                {
                    fieldname: 'items_section',
                    fieldtype: 'Section Break',
                    label: __('Items')
                },
                {
                    fieldname: 'items_html',
                    fieldtype: 'HTML'
                }
            ],
            primary_action_label: __('Create PO'),
            primary_action(values) {
                self._create_po_from_dialog(d, values, shortage_items, false);
            },
            secondary_action_label: __('Edit in Full Form'),
            secondary_action() {
                const values = d.get_values();
                if (!values) return;
                self._create_po_from_dialog(d, values, shortage_items, true);
            }
        });

        // Render editable items table
        let items_html = `
                    < table class="table table-sm table-bordered" >
                <thead>
                    <tr>
                        <th>${__('Item')}</th>
                        <th class="text-right" style="width: 100px;">${__('Qty')}</th>
                        <th class="text-right" style="width: 100px;">${__('Rate')}</th>
                        <th>${__('UOM')}</th>
                    </tr>
                </thead>
                <tbody>
        `;

        for (let i = 0; i < shortage_items.length; i++) {
            const item = shortage_items[i];
            items_html += `
                <tr>
                    <td>
                        <strong>${item.item_code}</strong>
                        <br><small class="text-muted">${item.item_name || ''}</small>
                    </td>
                    <td>
                        <input type="number" class="form-control form-control-sm text-right item-qty" 
                            data-idx="${i}" value="${parseFloat(item.shortage || 0).toFixed(3)}" step="0.001">
                    </td>
                    <td>
                        <input type="number" class="form-control form-control-sm text-right item-rate" 
                            data-idx="${i}" value="0" step="0.01" placeholder="Auto">
                    </td>
                    <td>${item.uom || item.stock_uom || ''}</td>
                </tr>
            `;
        }
        items_html += '</tbody></table > ';

        d.fields_dict.items_html.$wrapper.html(items_html);
        d.show();
    }

    _create_po_from_dialog(dialog, values, shortage_items, open_form) {
        const self = this;

        // Collect item data from inputs
        const items = [];
        dialog.$wrapper.find('.item-qty').each(function () {
            const idx = $(this).data('idx');
            const qty = parseFloat($(this).val()) || 0;
            const rate_input = dialog.$wrapper.find(`.item-rate[data-idx="${idx}"]`);
            const rate = parseFloat(rate_input.val()) || 0;

            if (qty > 0) {
                items.push({
                    item_code: shortage_items[idx].item_code,
                    qty: qty,
                    rate: rate > 0 ? rate : null,
                    warehouse: values.warehouse || shortage_items[idx].warehouse
                });
            }
        });

        if (!items.length) {
            frappe.msgprint(__('No items with quantity to order'));
            return;
        }

        frappe.call({
            method: 'kniterp.api.production_wizard.create_purchase_orders_for_shortage',
            args: {
                items: JSON.stringify(items),
                supplier: values.supplier,
                schedule_date: values.schedule_date,
                warehouse: values.warehouse,
                submit: open_form ? 0 : 1  // Submit only if not opening form
            },
            freeze: true,
            freeze_message: __('Creating Purchase Order...'),
            callback: (r) => {
                if (r.message) {
                    dialog.hide();
                    if (open_form) {
                        frappe.set_route('Form', 'Purchase Order', r.message.name);
                    } else {
                        frappe.show_alert({
                            message: __('Purchase Order <a href="/app/purchase-order/{0}">{0}</a> created', [r.message.name]),
                            indicator: 'green'
                        }, 5);
                        self.refresh_pending_items();
                        self.load_production_details(self.selected_item);
                    }
                }
            }
        });
    }

    create_delivery_note(details) {
        frappe.call({
            method: 'kniterp.api.production_wizard.create_delivery_note',
            args: {
                sales_order: details.sales_order
            },
            freeze: true,
            freeze_message: __('Creating Delivery Note...'),
            callback: (r) => {
                if (r.message) {
                    frappe.set_route('Form', 'Delivery Note', r.message);
                }
            }
        });
    }

    show_dashboard() {
        frappe.call({
            method: 'kniterp.api.production_wizard.get_status_summary',
            callback: (r) => {
                if (r.message) {
                    frappe.msgprint({
                        title: __('Production Dashboard'),
                        message: `
							<div class="dashboard-summary">
								<p><strong>${__('Pending Items')}:</strong> ${r.message.pending_items}</p>
								<p><strong>${__('Pending Receipts')}:</strong> ${r.message.pending_receipts}</p>
								<p><strong>${__('Work Orders')}:</strong></p>
								<ul>
									${Object.entries(r.message.work_order_status || {}).map(([status, count]) =>
                            `<li>${status}: ${count}</li>`
                        ).join('')}
								</ul>
							</div>
						`,
                        indicator: 'blue'
                    });
                }
            }
        });
    }
}
