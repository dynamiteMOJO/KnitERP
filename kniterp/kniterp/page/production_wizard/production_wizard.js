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
            single_column: true
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
        if (this.filters.customer !== undefined) {
            this.customer_filter.set_value(this.filters.customer);
        }
        if (this.filters.from_date !== undefined) {
            this.from_date_filter.set_value(this.filters.from_date);
        }
        if (this.filters.to_date !== undefined) {
            this.to_date_filter.set_value(this.filters.to_date);
        }
        if (this.filters.urgent !== undefined) {
            this.urgent_filter.set_value(this.filters.urgent);
        }
        if (this.filters.invoice_status !== undefined) {
            this.set_active_tab(this.filters.invoice_status);
        }
        if (this.filters.materials_status !== undefined) {
            this.materials_filter.set_value(this.filters.materials_status);
        }
        if (this.filters.job_work !== undefined) {
            this.type_filter.set_value(this.filters.job_work);
        }
    }

    setup_page() {
        this.page.set_primary_action(__('Refresh'), () => this.refresh(), 'refresh');

        this.page.add_menu_item(__('Dashboard'), () => {
            this.show_dashboard();
        });

        this.page.add_inner_button(__('Consolidated Procurement'), () => {
            this.show_consolidated_wizard();
        });
    }

    make_filters() {
        // Clear anything in sidebar just in case
        this.page.sidebar.empty();

        // ── SCOPE ───────────────────────────────────────────────────────
        this.page.page_form.append('<div class="filter-section-header">Scope</div>');

        this.customer_filter = this.page.add_field({
            fieldname: 'customer',
            label: __('Customer'),
            fieldtype: 'Select',
            options: [{ 'label': __('All Parties'), 'value': '' }],
            change: () => {
                this.filters.customer = this.customer_filter.get_value();
                this.refresh_pending_items();
            }
        });

        this.type_filter = this.page.add_field({
            fieldname: 'job_work',
            label: __('Work Type'),
            fieldtype: 'Select',
            options: [
                { 'label': __('All Types'), 'value': '' },
                { 'label': __('In-House'), 'value': 'Standard' },
                { 'label': __('Job Work In'), 'value': 'Inward' },
                { 'label': __('Job Work Out'), 'value': 'Outward' }
            ],
            change: () => {
                this.filters.job_work = this.type_filter.get_value();
                this.load_party_options();
                this.refresh_pending_items();
            }
        });

        // ── ORDER DATE ──────────────────────────────────────────────────
        this.page.page_form.append('<div class="filter-section-header">Order Date</div>');

        this.from_date_filter = this.page.add_field({
            fieldname: 'from_date',
            label: __('From Date'),
            fieldtype: 'Date',
            default: frappe.datetime.add_months(frappe.datetime.nowdate(), -1),
            change: () => {
                this.filters.from_date = this.from_date_filter.get_value();
                this.load_party_options();
                this.refresh_pending_items();
            }
        });

        this.to_date_filter = this.page.add_field({
            fieldname: 'to_date',
            label: __('To Date'),
            fieldtype: 'Date',
            default: frappe.datetime.add_months(frappe.datetime.nowdate(), 1),
            change: () => {
                this.filters.to_date = this.to_date_filter.get_value();
                this.load_party_options();
                this.refresh_pending_items();
            }
        });

        // ── STATUS ──────────────────────────────────────────────────────
        this.page.page_form.append('<div class="filter-section-header">Status</div>');

        this.materials_filter = this.page.add_field({
            fieldname: 'materials_status',
            label: __('Material Status'),
            fieldtype: 'Select',
            options: [
                { 'label': __('All'), 'value': '' },
                { 'label': __('Ready for Production'), 'value': 'Ready' },
                { 'label': __('Material Shortage'), 'value': 'Shortage' }
            ],
            change: () => {
                this.filters.materials_status = this.materials_filter.get_value();
                this.refresh_pending_items();
            }
        });

        this.urgent_filter = this.page.add_field({
            fieldname: 'urgent',
            label: __('Urgent'),
            fieldtype: 'Check',
            change: () => {
                this.filters.urgent = this.urgent_filter.get_value();
                this.load_party_options();
                this.refresh_pending_items();
            }
        });

        // Set default invoice_status if not passed via route_options
        if (!this.filters.invoice_status) {
            this.filters.invoice_status = 'Pending Production';
        }

        // Style the filter bar
        this.page.page_form.css({
            'padding': '10px 15px',
            'background': 'var(--subtle-fg)',
            'border-bottom': '1px solid var(--border-color)',
            'margin-bottom': '10px'
        });

        // Load initial party options (after fields are created)
        this.load_party_options();
    }

    load_party_options() {
        // Synchronize filters with UI fields if not already set (handles initialization)
        if (this.from_date_filter && !this.filters.from_date) {
            this.filters.from_date = this.from_date_filter.get_value();
        }
        if (this.to_date_filter && !this.filters.to_date) {
            this.filters.to_date = this.to_date_filter.get_value();
        }
        if (this.urgent_filter && this.filters.urgent === undefined) {
            this.filters.urgent = this.urgent_filter.get_value();
        }

        // Create a copy of filters but exclude the customer filter itself
        // We want to see ALL parties that match the DATE/STATUS criteria, 
        // not just the one currently selected (if any)
        const query_filters = Object.assign({}, this.filters);
        delete query_filters.customer;

        frappe.call({
            method: 'kniterp.api.production_wizard.get_unique_parties',
            args: {
                filters: query_filters
            },
            callback: (r) => {
                if (r.message) {
                    const options = [{ 'label': __('All Parties'), 'value': '' }]
                        .concat(r.message.map(p => ({
                            'label': p.customer_name,
                            'value': p.customer
                        })));

                    const current_selection = this.filters.customer;

                    // Update options
                    this.customer_filter.df.options = options;
                    this.customer_filter.refresh();

                    // Restore or Reset Logic
                    if (current_selection) {
                        const still_valid = options.find(o => o.value === current_selection);
                        if (still_valid) {
                            this.customer_filter.set_value(current_selection);
                        } else {
                            // Invalid, reset
                            this.customer_filter.set_value('');
                            this.filters.customer = '';
                            this.refresh_pending_items();
                        }
                    }
                }
            }
        });
    }

    make_layout() {
        if (this.page.main.find('.production-wizard-container').length) return;

        this.page.main.append(`
			<div class="production-wizard-container">
				<div class="row">
					<div class="col-md-5">
						<div class="pending-items-panel">
							<div class="panel-header d-flex justify-content-between align-items-center pr-2">
                                <div class="d-flex align-items-center">
								    <h5 class="mb-0 mr-2">${__('Pending Production Items')}</h5>
								    <span class="item-count badge badge-secondary">0</span>
                                </div>
                                <div class="dropdown">
                                    <button class="btn btn-xs btn-default dropdown-toggle" type="button" data-toggle="dropdown">
                                        ${__('Sort')}
                                    </button>
                                    <div class="dropdown-menu dropdown-menu-right">
                                        <a class="dropdown-item sort-action" data-sort="customer_name" href="#">${__('Party')}</a>
                                        <a class="dropdown-item sort-action" data-sort="delivery_date" href="#">${__('Delivery Date')}</a>
                                        <a class="dropdown-item sort-action" data-sort="sales_order" href="#">${__('Sales Order')}</a>
                                    </div>
                                </div>
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

        // Sort Listener
        this.page.main.on('click', '.sort-action', (e) => {
            e.preventDefault();
            const field = $(e.currentTarget).data('sort');
            const label = $(e.currentTarget).text();
            this.page.main.find('.dropdown-toggle').text(`${__('Sort')}: ${label}`);
            this.sort_pending_items(field);
        });

        this.render_stage_tabs();
    }

    set_active_tab(value) {
        if (!this.$stage_tabs) return;
        this.$stage_tabs.find('.stage-tab').removeClass('active');
        this.$stage_tabs.find(`.stage-tab[data-value="${value}"]`).addClass('active');
    }

    render_stage_tabs() {
        const tabs = [
            { label: __('Pending Production'), value: 'Pending Production' },
            { label: __('Ready to Deliver'), value: 'Ready to Deliver' },
            { label: __('Ready to Invoice'), value: 'Ready to Invoice' },
            { label: __('All Active'), value: 'All' }
        ];

        const active = this.filters.invoice_status || 'Pending Production';

        this.$stage_tabs = $('<div class="stage-tabs"></div>');
        tabs.forEach(tab => {
            const $tab = $(`<button class="stage-tab${tab.value === active ? ' active' : ''}" data-value="${tab.value}">${tab.label}</button>`);
            $tab.on('click', () => {
                this.filters.invoice_status = tab.value;
                this.set_active_tab(tab.value);
                this.load_party_options();
                this.refresh_pending_items();
            });
            this.$stage_tabs.append($tab);
        });

        // Prepend tab strip above the panels row inside the main container
        this.page.main.find('.production-wizard-container').prepend(this.$stage_tabs);
    }

    sort_pending_items(field) {
        if (!this.pending_items || !this.pending_items.length) return;
        this.current_sort_field = field;

        this.pending_items.sort((a, b) => {
            const valA = a[field] || '';
            const valB = b[field] || '';
            if (valA < valB) return -1;
            if (valA > valB) return 1;
            return 0;
        });

        this.render_pending_items();
    }

    refresh() {
        let selected_item = null;

        // Check for new route options (from deep linking)
        if (frappe.route_options) {
            // Extract selected_item target specifically BEFORE merging
            if (frappe.route_options.selected_item) {
                selected_item = frappe.route_options.selected_item;
                delete frappe.route_options.selected_item; // Remove before merge
            }

            // First, reset all mutable filters to defaults to avoid carry-over from previous navigation
            this.filters = {
                'invoice_status': 'Pending Production', // Reset view filter
                'materials_status': '',                 // Reset materials filter
                'customer': '',                         // Reset customer
                'urgent': 0                             // Reset urgent
            };

            // Preserve current date filters if they exist (usually we want to keep date range or use defaults from UI)
            if (this.from_date_filter) this.filters.from_date = this.from_date_filter.get_value();
            if (this.to_date_filter) this.filters.to_date = this.to_date_filter.get_value();

            // Merge other filters (selected_item already removed)
            this.filters = Object.assign(this.filters, frappe.route_options);

            frappe.route_options = null;

            // Update UI without triggering another refresh call
            this.suppress_refresh = true;
            this.apply_filters();
            this.suppress_refresh = false;
        }

        // If we have a specific target from navigation, clear any old selection state
        if (selected_item) {
            this.selected_item = null;
            this.$details_content.empty();
            // Refresh list with the new target
            this.refresh_pending_items(selected_item);
        } else {
            // No new target - just refresh the list
            this.refresh_pending_items();
            // Reload existing selection if any
            if (this.selected_item) {
                this.load_production_details(this.selected_item);
            }
        }
    }

    refresh_pending_items(item_to_select = null) {
        if (this.suppress_refresh) return;

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
                if (this.current_sort_field) {
                    this.sort_pending_items(this.current_sort_field);
                } else {
                    this.render_pending_items();
                }

                // Auto-select item if passed in route options (Action Center deep link)
                const target = item_to_select || this.filters.selected_item;
                if (target) {
                    // Check if item exists in the list
                    const exists = this.pending_items.find(i => i.sales_order_item === target);
                    if (exists) {
                        this.select_item(target);

                        // Scroll to item
                        setTimeout(() => {
                            const $item = this.$pending_list.find(`[data-item="${target}"]`);
                            if ($item.length) {
                                $item[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
                            }
                        }, 500); // Small delay to render
                    }
                    if (this.filters.selected_item) delete this.filters.selected_item; // Clear to avoid re-selecting on manual refresh
                }
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

            // Subcontracting UX
            const is_subcontracted = item.is_subcontracted;
            const display_item_code = is_subcontracted ? (item.fg_item || item.item_code) : item.item_code;
            const display_item_name = is_subcontracted ? (item.fg_item || item.item_name) : item.item_name;
            const service_name = is_subcontracted ? item.item_name : '';

            const badge_html = is_subcontracted ?
                `<span class="badge badge-warning ml-1" style="font-size: 10px;">${__('Subcontract')}</span>` : '';

            html += `
				<div class="pending-item-card ${this.selected_item === item.sales_order_item ? 'selected' : ''}"
					 data-item="${item.sales_order_item}">
					<div class="d-flex justify-content-between align-items-start mb-1">
						<span class="font-weight-bold text-truncate" style="font-size: 14px; max-width: 65%; color: var(--text-color);" title="${item.customer_name}">
                            ${item.customer_name}
                        </span>
						<span class="status-badge ${status_class}">${status_label}</span>
					</div>
					<div class="item-details mb-1">
						<div class="item-name text-truncate" title="${display_item_name}" style="font-size: 13px; margin-bottom: 2px;">
                            ${is_subcontracted ? `<i class="fa fa-industry text-muted mr-1"></i>` : ''} 
                            ${display_item_name} ${badge_html}
                        </div>
                        ${is_subcontracted ? `<div class="text-muted small text-truncate" title="${service_name}"><i class="fa fa-wrench mr-1"></i> ${service_name}</div>` : ''}
                        <div class="d-flex justify-content-between align-items-center mt-1">
                            <span class="text-muted small">${item.sales_order}</span>
                             ${item.fg_item_qty && is_subcontracted ? `<span class="badge badge-light" title="${__('FG Qty')}">${frappe.format(item.fg_item_qty, { fieldtype: 'Float', precision: 2 })}</span>` : ''}
                        </div>
					</div>
					<div class="item-footer mt-2 pt-2 border-top">
						<span class="delivery-date small text-muted">
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
                        ${details.is_subcontracted ? `<div class="mb-1"><span class="badge badge-warning">${__('Subcontracting Inward')}</span></div>` : ''}
						<h4><a href="/app/item/${encodeURIComponent(details.production_item || details.item_code)}" target="_blank">${details.production_item_name || details.item_name || details.production_item}</a></h4>
						<span class="text-muted">
                            ${details.production_item || details.item_code}
                            ${details.is_subcontracted ? `<br><small class="text-muted">${__('Service')}: ${details.item_name}</small>` : ''}
                        </span>
					</div>
					<div class="d-flex align-items-start">
					<button class="btn btn-sm btn-default btn-view-activity-log mr-3" title="${__('View Activity Log')}">
						<i class="fa fa-history"></i> ${__('Activity Log')}
					</button>
					<div class="qty-info">
						<div class="big-number">${frappe.format(details.projected_qty, { fieldtype: 'Float', precision: 2 })}</div>
						<div class="text-muted">${__('Projected FG Qty')}</div>
					</div>
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
							${(details.bom_no && (!details.is_subcontracted || details.bom_scio_compatible)) ?
                `<div>
                     <a href="/app/bom/${details.bom_no}">${details.bom_no}</a>
                     <button class="btn btn-xs btn-link text-muted btn-edit-bom ml-1" title="${__('Edit BOM')}" style="padding: 0 4px;">
                        <i class="fa fa-pencil"></i>
                     </button>
                 </div>` :
                `<button class="btn btn-xs btn-primary btn-create-bom-designer" data-item="${details.production_item || details.item_code}" data-bom="${details.bom_no || ''}">
									<i class="fa fa-plus"></i> ${__('Create BOM')}
								</button>
								${(details.is_subcontracted && details.bom_no && !details.bom_scio_compatible) ?
                    `<div class="text-danger small mt-1">${__('BOM has no customer-provided materials')}</div>` : ''}`
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
                    ${details.subcontracting_inward_order ? `
					<div class="info-card">
						<i class="fa fa-share-square-o"></i>
						<div>
							<div class="label">${__('Inward Order')}</div>
							<a href="/app/subcontracting-inward-order/${details.subcontracting_inward_order}">${details.subcontracting_inward_order}</a>
							<span class="badge badge-info ml-1">${details.sio_status}</span>
						</div>
					</div>
					` : ''}
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
					${(details.bom_no && (!details.is_subcontracted || details.bom_scio_compatible)) ? this.get_primary_action_buttons(details) : ''}
				</div>

				<!-- Raw Materials Section -->
				<div class="section-header">
					<h5><i class="fa fa-cube"></i> ${__('Raw Materials')}</h5>
					<div>
						${this.has_rm_orders(details.raw_materials) ? `<button class="btn btn-sm btn-default btn-view-rm-orders mr-1"><i class="fa fa-list"></i> ${__('View Orders')}</button>` : ''}
						<button class="btn btn-sm ${this.has_shortages(details.raw_materials) ? 'btn-warning' : 'btn-default'} create-shortage-po">
							<i class="fa fa-shopping-cart"></i> ${this.has_shortages(details.raw_materials) ? __('Create PO for Shortages') : __('Create PO')}
						</button>
					</div>
				</div>
				<div class="materials-list">
					${this.render_raw_materials(details.raw_materials, details)}
				</div>

				<!-- Operations Section -->
				<div class="section-header">
					<h5><i class="fa fa-tasks"></i> ${__('Operations')}</h5>
				</div>
				<div class="operations-list">
					${(details.bom_no && (!details.is_subcontracted || details.bom_scio_compatible)) ? this.render_operations(details) : `<div class="text-muted p-3">${(details.is_subcontracted && details.bom_no && !details.bom_scio_compatible) ? __('Current BOM is not compatible with Subcontracting Inward. Please create a valid BOM.') : __('Please create a BOM to view operations')}</div>`}
				</div>
			</div>
		`;

        this.$details_content.html(html);
        this.render_transaction_parameters_section(details);
        this.render_notes_section(details);
        this.bind_action_events(details);
        this.bind_note_events(details);
    }

    render_transaction_parameters_section(details) {
        const params = details.transaction_parameters || [];
        if (!params.length) return;

        const badges_html = params.map(p =>
            `<span class="badge mr-1 mb-1" style="background:#e6f7f5;color:#0d7377;border:1px solid #b2e0db;font-size:12px;font-weight:500;padding:4px 9px;border-radius:12px;">
                <span style="opacity:0.7;">${frappe.utils.escape_html(p.parameter)}:</span>&nbsp;<strong>${frappe.utils.escape_html(p.value)}</strong>
            </span>`
        ).join('');

        const section_html = `
            <div class="tx-params-bar mt-2 mb-1 pb-2 border-bottom" style="padding:0 2px;">
                <div class="d-flex flex-wrap align-items-center">
                    <span class="text-muted mr-2" style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;white-space:nowrap;">
                        <i class="fa fa-sliders mr-1"></i>${__('Process Params')}:
                    </span>
                    ${badges_html}
                </div>
            </div>
        `;

        // Insert after .info-cards, before .primary-actions
        this.$details_content.find('.info-cards').after(section_html);
    }

    render_notes_section(details) {
        const notes = details.notes || [];

        let notes_html = '';
        if (notes.length === 0) {
            notes_html = `
                <div class="text-center text-muted p-4 no-notes-message">
                    <div class="mb-2"><i class="fa fa-comment-o fa-2x" style="opacity: 0.3;"></i></div>
                    <small>${__('No notes yet.')}</small>
                </div>
            `;
        } else {
            notes_html = notes.map(note => {
                const is_owner = note.owner === frappe.session.user;
                const time_ago = frappe.datetime.comment_when(note.creation);
                return `
                    <div class="note-item py-3 border-bottom">
                        <div class="d-flex justify-content-between align-items-start">
                            <div class="d-flex align-items-center mb-2">
                                <span class="avatar avatar-xs mr-2" title="${note.user_fullname}">
                                    ${frappe.avatar(note.owner, 'avatar-xs')}
                                </span>
                                <div>
                                    <div class="font-weight-bold" style="font-size: 12px;">${note.user_fullname}</div>
                                    <div class="text-muted" style="font-size: 10px;">${time_ago}</div>
                                </div>
                            </div>
                            ${is_owner || frappe.user.has_role('System Manager') ?
                        `<button class="btn btn-xs btn-link text-muted btn-delete-note p-0" data-note="${note.name}" title="${__('Delete')}">
                                    <i class="fa fa-times"></i>
                                </button>` : ''}
                        </div>
                        <div class="note-content pl-1" style="white-space: pre-wrap; font-size: 13px; color: var(--text-color); padding-left: 28px;">${frappe.utils.escape_html(note.note)}</div>
                    </div>
                `;
            }).join('');
        }

        const section_html = `
            <div class="section-header mt-4 mb-3 border-top pt-4">
                <h5 class="mb-3"><i class="fa fa-comments-o text-muted mr-1"></i> ${__('Notes')} <span class="badge badge-pill badge-light text-muted ml-1" style="font-size: 10px;">${notes.length}</span></h5>
            </div>
            <div class="notes-section">
                 <!-- Input Area -->
                <div class="comment-input-box mb-4">
                    <div class="input-wrapper p-2 border rounded" style="background-color: var(--control-bg);">
                        <textarea class="form-control border-0 bg-transparent" rows="2" placeholder="${__('Write a note...')}" style="resize: none; font-size: 13px; box-shadow: none;"></textarea>
                        <div class="d-flex justify-content-between align-items-center mt-2 px-1">
                             <div class="text-muted" style="font-size: 10px;">${__('Ctrl+Enter to post')}</div>
                             <button class="btn btn-xs btn-primary btn-add-note px-3">
                                ${__('Comment')}
                            </button>
                        </div>
                    </div>
                </div>

                <!-- List Area -->
                <div class="notes-list" style="max-height: 400px; overflow-y: auto;">
                    ${notes_html}
                </div>
            </div>
        `;

        this.$details_content.append(section_html);
    }

    bind_note_events(details) {
        const $section = this.$details_content.find('.notes-section');
        const $textarea = $section.find('textarea');
        const $btn = $section.find('.btn-add-note');

        const post_note = () => {
            const note_content = $textarea.val().trim();

            if (!note_content) {
                frappe.msgprint(__('Please enter a note'));
                return;
            }

            frappe.call({
                method: 'kniterp.api.production_wizard.add_production_note',
                args: {
                    sales_order_item: details.sales_order_item,
                    note: note_content
                },
                freeze: true,
                callback: (r) => {
                    if (r.message) {
                        frappe.show_alert({ message: __('Note added'), indicator: 'green' });
                        // Refresh details to show new note
                        this.load_production_details(details.sales_order_item);
                    }
                }
            });
        };

        // Click event
        $btn.on('click', () => post_note());

        // Keyboard Shortcut (Ctrl+Enter)
        $textarea.on('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                post_note();
            }
        });

        // Delete Note
        $section.on('click', '.btn-delete-note', (e) => {
            const note_name = $(e.currentTarget).data('note');

            frappe.confirm(__('Are you sure you want to delete this note?'), () => {
                frappe.call({
                    method: 'kniterp.api.production_wizard.delete_production_note',
                    args: {
                        note_name: note_name
                    },
                    freeze: true,
                    callback: (r) => {
                        if (r.message) {
                            frappe.show_alert({ message: __('Note deleted'), indicator: 'green' });
                            // Refresh details
                            this.load_production_details(details.sales_order_item);
                        }
                    }
                });
            });
        });
    }

    get_primary_action_buttons(details) {
        let buttons = [];

        const all_rm_available = !details.raw_materials || details.raw_materials.length === 0 || details.raw_materials.every(m => (m.available_qty || 0) > 0);

        if (details.is_subcontracted && !details.subcontracting_inward_order) {
            buttons.push(`
				<button class="btn btn-primary btn-create-sio mr-2">
					<i class="fa fa-file-text-o"></i> ${__('Create Inward Order')}
				</button>
			`);
        } else if (details.is_subcontracted && details.subcontracting_inward_order) {
            // For SCIO, delivery is tracked on the SIO Item, not the SO Item
            const sio_delivered = details.sio_delivered_qty || 0;
            const sio_qty = details.sio_qty || 0;
            const produced = (details.work_order && details.work_order.produced_qty) || 0;

            // Send Delivery button: only when there's produced-but-undelivered FG qty
            if (produced > sio_delivered && (sio_qty > sio_delivered)) {
                buttons.push(`
				<button class="btn btn-success btn-send-delivery mr-2" data-sio="${details.subcontracting_inward_order}">
					<i class="fa fa-truck"></i> ${__('Send Delivery')}
				</button>
			`);
            }

            // Partial Invoice button: when SIO has delivered qty that hasn't been billed yet
            if (sio_delivered > 0 && flt(details.billed_amt || 0) < flt(details.amount || 0)) {
                if (details.draft_sales_invoice) {
                    buttons.push(`
                    <button class="btn btn-warning btn-create-scio-invoice mr-2">
                        <i class="fa fa-file-text-o"></i> ${__('View Draft Invoice')}
                    </button>
                    `);
                } else {
                    buttons.push(`
                    <button class="btn btn-primary btn-create-scio-invoice mr-2">
                        <i class="fa fa-file-text"></i> ${__('Create Sales Invoice')}
                    </button>
                    `);
                }
            }
        }

        if (!details.work_order) {
            if (all_rm_available) {
                buttons.push(`
				<button class="btn btn-primary btn-create-wo">
					<i class="fa fa-plus"></i> ${__('Create Work Order')}
				</button>
			`);
            }
        } else if (details.work_order.status === 'Draft') {
            buttons.push(`
				<button class="btn btn-primary btn-start-wo">
					<i class="fa fa-play"></i> ${__('Start Production')}
				</button>
			`);
        } else if (details.work_order.status === 'In Process' || details.work_order.status === 'Not Started') {
            // Allow delivery if we have formatted goods ready (produced > delivered)
            // Skip for SCIO — delivery is via Send Delivery (subcontracting delivery)
            // Note: WO can stay "Not Started" in subcontracting flows since
            // material_transferred_for_manufacturing is never updated by SCR path
            if (!details.is_subcontracted) {
                const produced = details.work_order.produced_qty || 0;
                const delivered = details.delivered_qty || 0;

                if (produced > delivered) {
                    buttons.push(`
					<button class="btn btn-success btn-create-delivery">
						<i class="fa fa-truck"></i> ${__('Create Delivery Note')}
					</button>
				`);
                }

                // Show SI button if there's delivered-but-unbilled qty
                const delivered_value = flt(delivered * flt(details.rate || 0));
                if (delivered > 0 && flt(details.billed_amt || 0) < delivered_value) {
                    if (details.draft_sales_invoice) {
                        buttons.push(`
                        <button class="btn btn-warning btn-create-invoice">
                            <i class="fa fa-file-text-o"></i> ${__('View Draft Invoice')}
                        </button>
                        `);
                    } else {
                        buttons.push(`
                        <button class="btn btn-primary btn-create-invoice">
                            <i class="fa fa-file-text"></i> ${__('Create Sales Invoice')}
                        </button>
                        `);
                    }
                }
            }
        } else if (details.work_order.status === 'Completed') {
            if (details.is_subcontracted) {
                // SCIO: No delivery note needed, invoice button is in the SCIO block above
            } else {
                // Show Delivery Note button if there's still qty to deliver
                if ((details.pending_qty > 0) || (details.work_order && (details.work_order.produced_qty || 0) > (details.delivered_qty || 0)) || (details.projected_qty > details.delivered_qty)) {
                    buttons.push(`
				<button class="btn btn-success btn-create-delivery">
					<i class="fa fa-truck"></i> ${__('Create Delivery Note')}
				</button>
			`);
                }

                // Show SI button if there's delivered-but-unbilled qty
                const delivered_value = flt((details.delivered_qty || 0) * flt(details.rate || 0));
                if ((details.delivered_qty || 0) > 0 && flt(details.billed_amt || 0) < delivered_value) {
                    if (details.draft_sales_invoice) {
                        buttons.push(`
                        <button class="btn btn-warning btn-create-invoice">
                            <i class="fa fa-file-text-o"></i> ${__('View Draft Invoice')}
                        </button>
                        `);
                    } else {
                        buttons.push(`
                        <button class="btn btn-primary btn-create-invoice">
                            <i class="fa fa-file-text"></i> ${__('Create Sales Invoice')}
                        </button>
                        `);
                    }
                }
            }
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
                // For Sent: Denominator is Required Material = Ordered FG * Conversion Factor
                const conversion_factor = op.conversion_factor || 1;
                const sent_denom = po_qty_raw * conversion_factor;

                // For Received: Denominator is Ordered FG (PO Qty)
                const recvd_denom = po_qty_raw;

                const sent = frappe.format(sent_raw, { fieldtype: 'Float', precision: 3 });
                const recvd = frappe.format(recvd_raw, { fieldtype: 'Float', precision: 3 });
                const sent_denom_fmt = frappe.format(sent_denom, { fieldtype: 'Float', precision: 3 });
                const recvd_denom_fmt = frappe.format(recvd_denom, { fieldtype: 'Float', precision: 3 });

                const sent_pct = sent_denom ? Math.min(100, (sent_raw / sent_denom) * 100) : 0;
                const recd_pct = recvd_denom ? Math.min(100, (recvd_raw / recvd_denom) * 100) : 0;

                let send_btn = '';
                // Removed ambiguous 'Send Raw Material' button from aggregate progress bar.
                // We show individual buttons per SCO in the actions list.

                let recd_btn = '';
                // Removed old ambiguous 'Receive Goods' button.
                // We show individual buttons per SCO in the actions list.

                progress_html = `
                    <div class="op-progress-container">
                        <!-- Sent Section -->
                        <div class="op-progress-row mb-3">
                            <div class="op-progress-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                                <span class="op-progress-label" style="font-size: 11px; font-weight: 600; color: var(--text-muted);">${__('Sent')}</span>
                                <span class="op-progress-summary" style="font-size: 13px; font-weight: 700; white-space: nowrap !important; display: flex; align-items: center;">
                                    ${sent}&nbsp;/&nbsp;${sent_denom_fmt}
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
                                    ${recvd}&nbsp;/&nbsp;${recvd_denom_fmt}
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
                const completed = op.completed_qty || 0;
                const total = op.for_quantity || details.pending_qty;
                const completed_fmt = format_number(completed, null, 2);
                const total_fmt = format_number(total, null, 2);

                let progress_bars_html = '';
                let overproduced_badge = '';

                if (completed > total) {
                    // Stacked bar logic: Container represents 'completed' qty
                    // Standard bar = (total / completed) * 100
                    // Red bar = (excess / completed) * 100
                    const planned_pct = (total / completed) * 100;
                    const over_pct = 100 - planned_pct; // fill the rest

                    const over_qty = completed - total;
                    // Use toFixed to avoid frappe.format returning a div
                    const over_qty_fmt = parseFloat(over_qty).toFixed(2);

                    progress_bars_html = `
                        <div class="progress-bar" style="width: ${planned_pct}%"></div>
                        <div class="progress-bar bg-danger" style="width: ${over_pct}%"></div>
                     `;

                    overproduced_badge = `<div class="clearfix">
                        <span class="badge badge-danger float-right mt-1" style="font-size: 10px;">+ ${over_qty_fmt} ${details.uom || ''}</span>
                     </div>`;
                } else {
                    // Standard logic
                    const pct = total ? Math.min(100, (completed / total) * 100) : 0;
                    progress_bars_html = `
                        <div class="progress-bar" style="width: ${pct}%"></div>
                    `;
                }

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
                                ${progress_bars_html}
                            </div>
                        </div>
                        ${overproduced_badge}
                    </div>
                `;
            }

            const links_html = `
                ${op.job_card ? `<div class="op-link mt-1"><i class="fa fa-link mr-1"></i><a href="/app/job-card/${op.job_card}" class="small">${op.job_card}</a></div>` : ''}
                ${op.purchase_order ? `<div class="op-link mt-1"><i class="fa fa-shopping-cart mr-1"></i><a href="/app/purchase-order/${op.purchase_order}" class="small">${op.purchase_order}</a></div>` : ''}
            `;

            const meta_parts = [];
            if (op.workstation) meta_parts.push(`<span class="text-muted small"><i class="fa fa-cog mr-1"></i>${op.workstation}</span>`);
            if (op.finished_good) meta_parts.push(`<span class="text-muted small"><i class="fa fa-arrow-right mr-1"></i>${__('Produces')}: <a href="/app/item/${encodeURIComponent(op.finished_good)}" target="_blank">${op.finished_good_name || op.finished_good}</a></span>`);
            const meta_html = meta_parts.length ? `<div class="d-flex flex-wrap gap-2 mt-1">${meta_parts.join('')}</div>` : '';

            html += `
				<div class="operation-card ${status_class}">
					<div class="op-header">
						<span class="op-number">${op.idx}</span>
						<div class="flex-fill">
						    <div class="d-flex align-items-center">
                                <span class="op-name">${op.operation}</span>
                                ${type_badge}
                            </div>
                            ${meta_html}
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

        // Check if there's still material to subcontract
        // qty_ready_from_prev from backend is Net Remaining (Total Available - Already Processed/Ordered)
        // so we just need to check if it's > 0 (using a small epsilon for float precision)
        const has_more_to_subcontract = op.is_subcontracted &&
            ((op.available_to_process || 0) > 0.001 || (op.qty_ready_from_prev || 0) > 0.001);

        if (op.status === 'Completed' && !has_more_to_subcontract) {
            let done_html = `<span class="text-success"><i class="fa fa-check"></i> ${__('Done')}</span>`;
            // Show View Logs for completed in-house ops with production history
            if (!op.is_subcontracted && op.job_card && (op.completed_qty || 0) > 0) {
                done_html += `
                    <button class="btn btn-xs btn-default btn-view-logs ml-2"
                            data-job-card="${op.job_card}"
                            data-operation="${op.operation}">
                        <i class="fa fa-list-alt"></i> ${__('View Logs')}
                    </button>`;
            }
            return done_html;
        }

        // Check if previous operation is complete (sequence enforcement)
        if (!op.previous_complete) {
            return `<span class="text-muted"><i class="fa fa-lock"></i> ${__('Waiting for previous operation')}</span>`;
        }

        if (op.is_subcontracted) {
            // Wrap everything in a full-width column container so items stack vertically
            let subcontractedHtml = '<div style="width: 100%; display: flex; flex-direction: column; gap: 8px;">';

            // Show existing SCO info first
            if (op.subcontracting_orders && op.subcontracting_orders.length > 0) {
                subcontractedHtml += `<div class="small">`;
                for (const sco of op.subcontracting_orders) {
                    const statusIcon = sco.received_qty >= sco.qty ? 'check-circle text-success' : 'clock-o text-warning';

                    const required_rm = sco.required_rm_qty || 0;
                    const sent_rm = sco.sent_qty || 0;
                    const showSend = (sco.received_qty < sco.qty) && (sent_rm < (required_rm - 0.001));
                    const showReceive = (sco.sent_qty || 0) > 0 && sco.received_qty < sco.qty;

                    subcontractedHtml += `
                        <div class="mb-2 p-2 rounded" style="background-color: var(--control-bg); border: 1px solid var(--border-color);">
                            <div class="d-flex justify-content-between align-items-center">
                                <div>
                                    <div class="d-flex align-items-center mb-1">
                                        <i class="fa fa-${statusIcon} mr-2"></i>
                                        <a href="/app/subcontracting-order/${sco.sco_name}" class="font-weight-bold" style="color: var(--text-color);">${sco.sco_name}</a>
                                    </div>
                                    <div class="small" style="color: var(--text-muted); margin-left: 20px;">
                                        ${sco.supplier} &bull; ${sco.received_qty}/${sco.qty} ${details.uom || 'Units'}
                                        ${(sco.sent_qty || 0) > 0 ? `&bull; Sent: ${sco.sent_qty}` : ''}
                                    </div>
                                </div>
                                <div class="text-right">
                                    ${showSend ? `
                                    <button class="btn btn-xs btn-default btn-send-sco-material mb-1 ml-1" 
                                        data-sco="${sco.sco_name}" data-po="${sco.po_name}"
                                        data-pending-fg="${flt(sco.qty - (sco.received_qty || 0), 3)}"
                                        data-sent-rm="${sent_rm}" data-required-rm="${required_rm}">
                                        <i class="fa fa-truck text-warning"></i> ${__('Send Material')}
                                    </button>` : ''}
                                    
                                    ${showReceive ? `
                                    <button class="btn btn-xs btn-default btn-receive-sco-goods mb-1 ml-1" 
                                        data-sco="${sco.sco_name}" data-po="${sco.po_name}">
                                        <i class="fa fa-download text-success"></i> ${__('Receive Goods')}
                                    </button>` : ''}

                                    ${(sco.received_qty >= sco.qty && flt(sco.billed_amt || 0) < flt(sco.po_amount || 0)) ? (
                            sco.submitted_pi
                                ? `<a href="/app/purchase-invoice/${sco.submitted_pi}" class="btn btn-xs btn-success mb-1 ml-1">
                                            <i class="fa fa-check"></i> ${__('View Invoice')}
                                           </a>`
                                : sco.draft_pi
                                    ? `<button class="btn btn-xs btn-warning btn-create-sco-pi mb-1 ml-1"
                                            data-po="${sco.po_name}" data-draft-pi="${sco.draft_pi}">
                                            <i class="fa fa-file-text-o"></i> ${__('View Draft PI')}
                                          </button>`
                                    : `<button class="btn btn-xs btn-primary btn-create-sco-pi mb-1 ml-1"
                                            data-po="${sco.po_name}" data-supplier="${sco.supplier}"
                                            data-amount="${sco.po_amount || 0}">
                                            <i class="fa fa-file-text"></i> ${__('Create PI')}
                                          </button>`
                        ) : ''}
                                </div>
                            </div>
                        </div>`;
                }
                subcontractedHtml += `</div>`;
            }

            // Action buttons below SCO list
            const remaining_to_subcontract = op.qty_ready_from_prev || 0;
            let bottomButtons = '';

            if (remaining_to_subcontract > 0) {
                const btnLabel = op.purchase_order
                    ? __('Create Additional SCO')
                    : __('Create Subcontracting Order');
                bottomButtons += `
					<button class="btn btn-sm btn-primary btn-create-sco"
							data-operation="${op.operation}"
							data-remaining="${remaining_to_subcontract}">
						<i class="fa fa-file-text-o"></i> ${btnLabel}
					</button>`;
            }

            if (op.job_card && op.received_qty > 0 && op.status !== 'Completed') {
                bottomButtons += `
                    <button class="btn btn-sm btn-success btn-complete-jc"
                            data-job-card="${op.job_card}"
                            data-operation="${op.operation}"
                            data-received="${op.received_qty}">
                        <i class="fa fa-check"></i> ${__('Complete Job Card')}
                    </button>`;
            }

            if (bottomButtons) {
                subcontractedHtml += `<div style="display: flex; gap: 8px; flex-wrap: wrap;">${bottomButtons}</div>`;
            }

            subcontractedHtml += '</div>';
            actions.push(subcontractedHtml);
        } else {
            // In-house operation
            const remaining_qty = (op.for_quantity || details.pending_qty) - (op.completed_qty || 0);
            if (op.status !== 'Completed' && op.job_card) {
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
            // View Logs button - shown when there's production history
            if (op.job_card && (op.completed_qty || 0) > 0) {
                actions.push(`
                    <button class="btn btn-sm btn-default btn-view-logs ml-1"
                            data-job-card="${op.job_card}"
                            data-operation="${op.operation}">
                        <i class="fa fa-list-alt"></i> ${__('View Logs')}
                    </button>
                    `);
            }
        }

        return actions.join('');
    }

    render_raw_materials(materials, details) {
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
            // If consumed, show consumed qty; otherwise show shortage
            const consumed_display = (m.consumed_qty && m.consumed_qty > 0)
                ? parseFloat(m.consumed_qty).toFixed(3)
                : '-';

            const shortage_display = (m.shortage && m.shortage > 0)
                ? parseFloat(m.shortage).toFixed(3)
                : '-';

            let shortage_class = (m.shortage > 0) ? 'text-danger font-weight-bold' : '';
            const consumed_class = (m.consumed_qty > 0) ? 'text-info font-weight-bold' : '';

            // Adjust status/class for customer provided items
            if (m.is_customer_provided) {
                if (m.status === 'available_cust') {
                    shortage_class = 'text-success'; // Available
                } else if (m.status === 'shortage_cust') {
                    shortage_class = 'text-danger font-weight-bold';
                }
            }

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

            // Subcontracting Inward Logic
            if (m.is_customer_provided) {
                if (m.sio_received_qty < m.sio_required_qty) {
                    actions_html = `<button class="btn btn-xs btn-warning btn-receive-customer-rm" 
                        data-sio="${details.subcontracting_inward_order}" 
                        data-item="${m.item_code}">
                        <i class="fa fa-download"></i> ${__('Receive RM')}
                    </button>`;
                } else {
                    actions_html = `<span class="text-success"><i class="fa fa-check-circle"></i> ${__('Received')}</span>`;
                }
            }
            // Standard PO Logic
            else if (m.linked_pos && m.linked_pos.length > 0) {
                const first_po = m.linked_pos[0];
                if (first_po.status === 'To Receive and Bill' || first_po.status === 'To Receive') {
                    actions_html = `<button class="btn btn-xs btn-success create-pr-btn" data-po="${first_po.po_name}">
                        <i class="fa fa-download"></i> ${__('Create PR')}
                    </button>`;
                }
            } else if (m.shortage > 0) {
                actions_html = `<button class="btn btn-xs btn-primary create-item-po-btn" data-item="${m.item_code}">
                    <i class="fa fa-shopping-cart"></i> ${__('Create PO')}
                </button>`;
            }

            const customer_badge = m.is_customer_provided ?
                `<span class="badge badge-warning ml-1" style="font-size: 9px;">${__('Customer Provided')}</span>` : '';

            // Update ordered html for customer provided
            if (m.is_customer_provided) {
                ordered_html = `<div>
                    <span class="font-weight-bold">${parseFloat(m.sio_received_qty || 0).toFixed(3)}</span> 
                    <span class="text-muted">/ ${parseFloat(m.sio_required_qty || 0).toFixed(3)}</span>
                 </div>`;
            }

            html += `
				<tr class="material-row ${m.status}">
					<td>
						<a href="/app/item/${m.item_code}">${m.item_code}</a>
						<div class="text-muted small">${m.item_name}</div>
                        ${customer_badge}
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

    get_material_status_badge(m) {
        if (m.is_customer_provided) {
            if (m.status === 'pending_receipt') {
                return `<span class="badge badge-warning">${__('Pending Receipt')}</span>`;
            } else if (m.status === 'available_cust') {
                return `<span class="badge badge-success">${__('Available')}</span>`;
            } else if (m.status === 'shortage_cust') {
                return `<span class="badge badge-danger">${__('Shortage')}</span>`;
            } else if (m.status === 'partial_cust') {
                return `<span class="badge badge-warning">${__('Partial')}</span>`;
            }
            return `<span class="badge badge-success">${__('Received')}</span>`;
        }

        if (m.status === 'consumed') {
            return `<span class="badge badge-info">${__('Consumed')}</span>`;
        } else if (m.status === 'shortage') {
            return `<span class="badge badge-danger">${__('Shortage')}</span>`;
        } else if (m.status === 'low') {
            return `<span class="badge badge-warning">${__('Low Stock')}</span>`;
        }
        return `<span class="badge badge-success">${__('Available')}</span>`;
    }

    has_shortages(materials) {
        // Only return true if there are purchasable items with shortage
        return materials && materials.some(m => !m.is_customer_provided && m.shortage > 0);
    }

    has_rm_orders(materials) {
        return materials && materials.some(m => m.linked_pos && m.linked_pos.length > 0);
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
        // Create Delivery Note
        this.$details_content.find('.btn-create-delivery').on('click', () => {
            this.create_delivery_note(details);
        });

        // Create Sales Invoice
        this.$details_content.find('.btn-create-invoice').on('click', () => {
            this.create_sales_invoice(details);
        });

        // Create SCIO Sales Invoice (partial, ratio-based)
        this.$details_content.find('.btn-create-scio-invoice').on('click', () => {
            if (details.draft_sales_invoice) {
                frappe.set_route('Form', 'Sales Invoice', details.draft_sales_invoice);
            } else {
                this.create_scio_sales_invoice(details);
            }
        });

        // Create Subcontracting Order
        this.$details_content.find('.btn-create-sco').on('click', function () {
            const operation = $(this).data('operation');
            self.create_subcontracting_order(details, operation);
        });

        // Send Raw Material to Supplier (New per-SCO button)
        this.$details_content.find('.btn-send-sco-material').on('click', function () {
            const sco = $(this).data('sco');
            const pending_fg = flt($(this).data('pending-fg'));
            const sent_rm = flt($(this).data('sent-rm'));
            const required_rm = flt($(this).data('required-rm'));
            self.send_raw_material_to_supplier(null, sco, { pending_fg, sent_rm, required_rm });
        });

        // Receive Goods (New per-SCO button)
        this.$details_content.find('.btn-receive-sco-goods').on('click', function () {
            const sco_name = $(this).data('sco');
            const po_name = $(this).data('po');
            // Find the matching SCO object so we can pass rich context to the dialog
            let sco_ctx = null;
            for (const op of (details.operations || [])) {
                if (op.subcontracting_orders) {
                    sco_ctx = op.subcontracting_orders.find(s => s.sco_name === sco_name) || null;
                    if (sco_ctx) {
                        sco_ctx = Object.assign({}, sco_ctx, {
                            operation: op.operation,
                            item_name: details.item_name || details.item_code || '',
                            sales_order: details.sales_order || '',
                            uom: details.uom || 'Units'
                        });
                        break;
                    }
                }
            }
            self.receive_subcontracted_goods(po_name, sco_name, sco_ctx);
        });

        // Create Purchase Invoice for SCO PO
        this.$details_content.find('.btn-create-sco-pi').on('click', function () {
            const po_name = $(this).data('po');
            const draft_pi = $(this).data('draft-pi');
            if (draft_pi) {
                frappe.set_route('Form', 'Purchase Invoice', draft_pi);
            } else {
                const supplier = $(this).data('supplier');
                const amount = $(this).data('amount');
                self.create_sco_purchase_invoice(po_name, supplier, amount);
            }
        });

        // Update Manufactured Qty
        this.$details_content.find('.btn-complete-op').on('click', function () {
            const operation = $(this).data('operation');
            const remaining = $(this).data('remaining');
            self.complete_operation(details, operation, remaining);
        });

        // Complete Job Card (in-house)
        this.$details_content.find('.btn-finish-jc').on('click', function () {
            const operation = $(this).data('operation');
            const job_card = $(this).data('job-card');
            self.complete_job_card(details, operation, job_card);
        });

        // Complete Job Card (subcontracted) - manual completion
        this.$details_content.find('.btn-complete-jc').on('click', function () {
            const job_card = $(this).data('job-card');
            const operation = $(this).data('operation');
            const received = $(this).data('received');

            frappe.confirm(
                __('Complete Job Card {0} with {1} qty received? No additional subcontracting orders can be created after this.', [job_card, received]),
                () => {
                    frappe.call({
                        method: 'kniterp.api.production_wizard.complete_subcontracted_job_card',
                        args: { job_card: job_card },
                        freeze: true,
                        freeze_message: __('Completing Job Card...'),
                        callback: (r) => {
                            if (r.message && r.message.success) {
                                frappe.show_alert({
                                    message: r.message.message,
                                    indicator: 'green'
                                });
                                // Reload details
                                self.load_production_details(self.selected_item);
                            }
                        }
                    });
                }
            );
        });

        // View Production Logs (inline on operation card)
        this.$details_content.find('.btn-view-logs').on('click', function () {
            const job_card = $(this).data('job-card');
            self.show_production_logs(job_card);
        });

        // Create SIO
        this.$details_content.find('.btn-create-sio').on('click', () => {
            frappe.confirm(__('Create Subcontracting Inward Order for {0}?', [details.production_item || details.item_code]), () => {
                frappe.call({
                    method: 'kniterp.api.production_wizard.create_subcontracting_inward_order',
                    args: {
                        sales_order: details.sales_order,
                        sales_order_item: details.sales_order_item
                    },
                    freeze: true,
                    callback: (r) => {
                        if (r.message) {
                            frappe.show_alert({ message: __('Subcontracting Inward Order Created'), indicator: 'green' });
                            // Reload details
                            this.load_production_details(this.selected_item);
                        }
                    }
                });
            });
        });

        // Create PO for Shortages
        this.$details_content.find('.create-shortage-po').on('click', () => {
            this.create_shortage_po(details);
        });

        // View RM Orders dialog
        this.$details_content.find('.btn-view-rm-orders').on('click', () => {
            this.show_rm_orders_dialog(details);
        });

        // Create Purchase Receipt from PO
        this.$details_content.find('.create-pr-btn').on('click', function () {
            const po_name = $(this).data('po');
            self.create_purchase_receipt(po_name);
        });

        // Create PO for individual item
        this.$details_content.find('.create-item-po-btn').on('click', function () {
            const item_code = $(this).data('item');
            self.create_po_for_item(details, item_code);
        });

        // Receive Customer RM
        this.$details_content.find('.btn-receive-customer-rm').on('click', function () {
            const sio_name = $(this).data('sio');
            self.receive_customer_rm(sio_name);
        });

        // Send Delivery
        this.$details_content.find('.btn-send-delivery').on('click', function () {
            const sio_name = $(this).data('sio');
            self.send_subcontracting_delivery(sio_name);
        });

        // Create BOM Designer (New)
        this.$details_content.find('.btn-create-bom-designer').on('click', function () {
            const item_code = $(this).data('item');
            const bom_no = $(this).data('bom');
            const route_args = {
                item_code: item_code,
                sales_order_item: details.sales_order_item,
                return_to: 'production-wizard'
            };
            if (bom_no) route_args.bom_no = bom_no;
            frappe.set_route('bom_designer', route_args);
        });

        // Edit BOM (New)
        this.$details_content.find('.btn-edit-bom').on('click', function (e) {
            e.preventDefault(); // Prevent default link behavior if any
            frappe.set_route('bom_designer', {
                bom_no: details.bom_no,
                item_code: details.item_code, // Ensure item_code is available in details
                sales_order_item: details.sales_order_item,
                return_to: 'production-wizard'
            });
        });

        // View Activity Log
        this.$details_content.find('.btn-view-activity-log').on('click', () => {
            this.show_order_activity_log(details);
        });
    }

    receive_customer_rm(sio_name) {
        frappe.call({
            method: "run_doc_method",
            args: {
                dt: "Subcontracting Inward Order",
                dn: sio_name,
                method: "make_rm_stock_entry_inward"
            },
            freeze: true,
            callback: function (r) {
                if (r.message) {
                    var doc = frappe.model.sync(r.message);
                    frappe.set_route("Form", doc[0].doctype, doc[0].name);
                }
            }
        });
    }

    send_subcontracting_delivery(sio_name) {
        frappe.call({
            method: "run_doc_method",
            args: {
                dt: "Subcontracting Inward Order",
                dn: sio_name,
                method: "make_subcontracting_delivery"
            },
            freeze: true,
            callback: function (r) {
                if (r.message) {
                    var doc = frappe.model.sync(r.message);
                    frappe.set_route("Form", doc[0].doctype, doc[0].name);
                }
            }
        });
    }

    show_rm_orders_dialog(details) {
        const self = this;
        const materials = details.raw_materials || [];

        // Collect all items that have linked POs
        const items_with_pos = materials.filter(m => m.linked_pos && m.linked_pos.length > 0);

        if (!items_with_pos.length) {
            frappe.msgprint(__('No purchase orders found for raw materials.'));
            return;
        }

        let html = '';
        for (const m of items_with_pos) {
            html += `
                <div style="margin-bottom:16px;">
                    <div style="font-weight:600; font-size:13px; margin-bottom:6px;">
                        <a href="/app/item/${m.item_code}" target="_blank">${m.item_code}</a>
                        <span class="text-muted" style="font-weight:400;"> — ${m.item_name}</span>
                    </div>`;

            for (const po of m.linked_pos) {
                let status_color = 'var(--text-muted)';
                if (po.status === 'Completed') status_color = 'var(--green-600, #16a34a)';
                else if (po.status === 'To Receive and Bill' || po.status === 'To Receive') status_color = 'var(--orange-600, #ea580c)';
                else if (po.status === 'To Bill') status_color = 'var(--blue-600, #2563eb)';

                html += `
                    <div style="background:var(--control-bg); border:1px solid var(--border-color); border-radius:6px; padding:10px 12px; margin-bottom:6px;">
                        <div class="d-flex justify-content-between align-items-center mb-1">
                            <div>
                                <a href="/app/purchase-order/${po.po_name}" target="_blank" style="font-weight:500;">${po.po_name}</a>
                                <span class="badge ml-1" style="background:${status_color}; color:#fff; font-size:10px;">${po.status}</span>
                            </div>
                            <span style="font-size:12px; color:var(--text-muted);">
                                ${flt(po.received_qty, 3)} / ${flt(po.ordered_qty, 3)} ${m.uom}
                            </span>
                        </div>`;

                // PRs
                if (po.purchase_receipts && po.purchase_receipts.length > 0) {
                    for (const pr of po.purchase_receipts) {
                        html += `
                            <div style="font-size:12px; margin-left:8px; padding:2px 0;">
                                <i class="fa fa-download" style="color:var(--green-600); width:14px;"></i>
                                <a href="/app/purchase-receipt/${pr.name}" target="_blank">${pr.name}</a>
                                <span class="text-muted">(${flt(pr.qty, 3)} ${m.uom})</span>
                            </div>`;
                    }
                } else if (po.pending_qty > 0) {
                    html += `<div style="font-size:12px; margin-left:8px; padding:2px 0; color:var(--text-muted);"><i class="fa fa-exclamation-circle" style="width:14px; color:var(--orange-600);"></i> ${__('No Purchase Receipt yet')}</div>`;
                }

                // PIs
                if (po.purchase_invoices && po.purchase_invoices.length > 0) {
                    for (const pi of po.purchase_invoices) {
                        const pi_color = pi.status === 'Paid' ? 'var(--green-600, #16a34a)' : 'var(--blue-600, #2563eb)';
                        html += `
                            <div style="font-size:12px; margin-left:8px; padding:2px 0;">
                                <i class="fa fa-file-text-o" style="color:${pi_color}; width:14px;"></i>
                                <a href="/app/purchase-invoice/${pi.name}" target="_blank">${pi.name}</a>
                                <span style="color:${pi_color}; font-size:11px;">${pi.status}</span>
                            </div>`;
                    }
                } else if (po.received_qty > 0) {
                    html += `<div style="font-size:12px; margin-left:8px; padding:2px 0; color:var(--text-muted);"><i class="fa fa-exclamation-circle" style="width:14px; color:var(--blue-600);"></i> ${__('No Purchase Invoice yet')}</div>`;
                }

                // Action buttons
                const action_btns = [];
                if (po.pending_qty > 0 && (po.status === 'To Receive and Bill' || po.status === 'To Receive')) {
                    action_btns.push(`<button class="btn btn-xs btn-success rm-orders-create-pr" data-po="${po.po_name}">
                        <i class="fa fa-download"></i> ${__('Create PR')}
                    </button>`);
                }
                if ((!po.purchase_invoices || !po.purchase_invoices.length) && po.received_qty > 0) {
                    action_btns.push(`<button class="btn btn-xs btn-primary rm-orders-create-pi" data-po="${po.po_name}">
                        <i class="fa fa-file-text-o"></i> ${__('Create PI')}
                    </button>`);
                }
                if (action_btns.length) {
                    html += `<div style="margin-top:6px; display:flex; gap:6px;">${action_btns.join('')}</div>`;
                }

                html += `</div>`;
            }

            html += `</div>`;
        }

        const d = new frappe.ui.Dialog({
            title: __('Raw Material Orders'),
            size: 'large',
            fields: [{
                fieldname: 'orders_html',
                fieldtype: 'HTML',
                options: html
            }]
        });

        d.show();

        // Bind Create PR buttons inside the dialog
        d.$wrapper.find('.rm-orders-create-pr').on('click', function () {
            const po_name = $(this).data('po');
            d.hide();
            self.create_purchase_receipt(po_name);
        });

        // Bind Create PI buttons inside the dialog
        d.$wrapper.find('.rm-orders-create-pi').on('click', function () {
            const po_name = $(this).data('po');
            d.hide();
            frappe.call({
                method: 'erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_invoice',
                args: { source_name: po_name },
                freeze: true,
                freeze_message: __('Creating Purchase Invoice...'),
                callback: (r) => {
                    if (r.message) {
                        const doc = frappe.model.sync(r.message)[0];
                        frappe.set_route('Form', doc.doctype, doc.name);
                    }
                }
            });
        });
    }

    create_purchase_receipt(po_name) {
        const self = this;

        frappe.call({
            method: 'kniterp.api.production_wizard.get_po_items_for_receipt',
            args: { purchase_order: po_name },
            freeze: true,
            freeze_message: __('Fetching PO details...'),
            callback: (r) => {
                if (!r.message || !r.message.items || !r.message.items.length) {
                    frappe.msgprint(__('No pending items to receive on this Purchase Order.'));
                    return;
                }

                const po_data = r.message;
                const po_items = po_data.items;

                // Build context panel
                let context_html = `
                    <div class="mb-3" style="background:var(--control-bg); border:1px solid var(--border-color); border-radius:6px; padding:10px 14px; color:var(--text-color);">
                        <div style="font-size:13px; line-height:1.8;">
                            <div><strong>${__('Purchase Order')}:</strong>
                                <a href="/app/purchase-order/${po_name}" target="_blank">${po_name}</a>
                            </div>
                            <div><strong>${__('Supplier')}:</strong> ${po_data.supplier_name || po_data.supplier}</div>
                        </div>
                    </div>
                `;

                // Build per-item sections with batch tables
                let items_html = '';
                po_items.forEach((item, idx) => {
                    const badge_color = item.has_batch_no ? 'orange' : 'blue';
                    const badge_text = item.has_batch_no ? __('Batch Tracked') : __('No Batch');
                    items_html += `
                        <div class="pr-item-section mb-3" data-item-code="${item.item_code}" data-idx="${idx}"
                             style="border:1px solid var(--border-color); border-radius:6px; padding:12px;">
                            <div class="d-flex justify-content-between align-items-start mb-2">
                                <div>
                                    <strong>${item.item_code}</strong>
                                    <div class="text-muted small">${item.item_name}</div>
                                </div>
                                <span class="badge" style="background:var(--${badge_color}-100, #fff7ed); color:var(--${badge_color}-600, #ea580c); font-size:10px;">${badge_text}</span>
                            </div>
                            <div class="d-flex justify-content-between flex-wrap mb-2" style="font-size:12px; color:var(--text-muted);">
                                <span><strong>${__('Ordered')}:</strong> ${item.ordered_qty} ${item.uom}</span>
                                <span><strong>${__('Received')}:</strong> ${item.received_qty} ${item.uom}</span>
                                <span><strong>${__('Pending')}:</strong>
                                    <span style="color:var(--orange-600, #ea580c); font-weight:600;">${item.pending_qty} ${item.uom}</span>
                                </span>
                            </div>`;

                    if (item.has_batch_no) {
                        items_html += `
                            <div class="d-flex align-items-center mb-2">
                                <label class="mb-0 mr-2" style="font-size:12px; white-space:nowrap;">${__('No. of Lots')}:</label>
                                <input type="number" class="form-control form-control-sm pr-num-batches" data-idx="${idx}"
                                       min="1" value="1" style="width:70px;">
                            </div>
                            <div class="pr-batch-table-wrapper" data-idx="${idx}"></div>
                            <div class="pr-item-total text-right text-muted small" data-idx="${idx}">
                                ${__('Total')}: <strong class="pr-item-total-qty">0</strong> ${item.uom}
                            </div>`;
                    } else {
                        items_html += `
                            <div class="d-flex align-items-center">
                                <label class="mb-0 mr-2" style="font-size:12px; white-space:nowrap;">${__('Qty to Receive')}:</label>
                                <input type="number" class="form-control form-control-sm pr-item-qty" data-idx="${idx}"
                                       min="0" step="any" value="${item.pending_qty}" style="width:120px;">
                            </div>`;
                    }

                    items_html += `</div>`;
                });

                const d = new frappe.ui.Dialog({
                    title: __('Receive Raw Materials — {0}', [po_data.supplier_name || po_data.supplier]),
                    fields: [
                        {
                            fieldname: 'context_html',
                            fieldtype: 'HTML',
                            options: context_html
                        },
                        {
                            fieldname: 'items_html',
                            fieldtype: 'HTML',
                            options: items_html
                        }
                    ],
                    size: 'large',
                    primary_action_label: __('Create & Submit Receipt'),
                    primary_action: () => {
                        const result_items = [];
                        let has_error = false;

                        po_items.forEach((item, idx) => {
                            const $section = d.$wrapper.find(`.pr-item-section[data-idx="${idx}"]`);
                            const entry = { item_code: item.item_code, batches: [] };

                            if (item.has_batch_no) {
                                let item_total = 0;
                                $section.find('.pr-batch-row').each(function () {
                                    const row_qty = flt($(this).find('.pr-batch-qty').val());
                                    const row_lot = $(this).find('.pr-batch-lot').val().trim();

                                    if (!row_qty || row_qty <= 0) {
                                        frappe.msgprint(__('Enter a valid quantity for all lots of {0}.', [item.item_code]));
                                        has_error = true;
                                        return false;
                                    }
                                    if (!row_lot) {
                                        frappe.msgprint(__('Enter a Lot No for all lots of {0}.', [item.item_code]));
                                        has_error = true;
                                        return false;
                                    }

                                    entry.batches.push({ batch_no: row_lot, qty: row_qty });
                                    item_total += row_qty;
                                });

                                if (has_error) return;

                                if (item_total > item.pending_qty + 0.001) {
                                    frappe.msgprint(__('Total lot qty ({0}) for {1} exceeds pending qty ({2}).', [item_total, item.item_code, item.pending_qty]));
                                    has_error = true;
                                    return;
                                }
                            } else {
                                const qty = flt($section.find('.pr-item-qty').val());
                                if (qty <= 0) {
                                    frappe.msgprint(__('Enter a valid quantity for {0}.', [item.item_code]));
                                    has_error = true;
                                    return;
                                }
                                if (qty > item.pending_qty + 0.001) {
                                    frappe.msgprint(__('Qty ({0}) for {1} exceeds pending qty ({2}).', [qty, item.item_code, item.pending_qty]));
                                    has_error = true;
                                    return;
                                }
                                entry.qty = qty;
                            }

                            result_items.push(entry);
                        });

                        if (has_error) return;

                        frappe.call({
                            method: 'kniterp.api.production_wizard.create_rm_purchase_receipt',
                            args: {
                                purchase_order: po_name,
                                items: JSON.stringify(result_items)
                            },
                            freeze: true,
                            freeze_message: __('Creating Purchase Receipt...'),
                            callback: (r) => {
                                if (r.message) {
                                    d.hide();
                                    frappe.show_alert({
                                        message: __('Purchase Receipt {0} created and submitted',
                                            [`<a href="/app/purchase-receipt/${r.message.name}">${r.message.name}</a>`]),
                                        indicator: 'green'
                                    }, 7);
                                    self.load_production_details(self.selected_item);
                                }
                            }
                        });
                    }
                });

                d.show();

                // Render batch tables and bind events
                const render_batch_table = ($wrapper, idx, num_batches, prefill_qty) => {
                    const item = po_items[idx];
                    let html = '<table class="table table-bordered table-condensed mb-0"><thead><tr>'
                        + '<th>' + __('Quantity') + '</th><th>' + __('Lot No / Batch No') + '</th>'
                        + '</tr></thead><tbody>';
                    for (let i = 0; i < num_batches; i++) {
                        const qty_val = (num_batches === 1 && prefill_qty) ? prefill_qty : '';
                        html += `
                            <tr class="pr-batch-row">
                                <td><input type="number" class="form-control form-control-sm pr-batch-qty" min="0" step="any" placeholder="${__('Qty')}" value="${qty_val}"></td>
                                <td><input type="text" class="form-control form-control-sm pr-batch-lot" placeholder="${__('Lot No')}"></td>
                            </tr>`;
                    }
                    html += '</tbody></table>';
                    $wrapper.html(html);

                    // Auto-update total when batch qty changes
                    $wrapper.find('.pr-batch-qty').on('input', function () {
                        let total = 0;
                        $wrapper.find('.pr-batch-qty').each(function () {
                            total += flt($(this).val());
                        });
                        d.$wrapper.find(`.pr-item-total[data-idx="${idx}"] .pr-item-total-qty`).text(flt(total, 3));
                    });
                };

                // Initialize batch tables for all batch-tracked items
                po_items.forEach((item, idx) => {
                    if (!item.has_batch_no) return;
                    const $wrapper = d.$wrapper.find(`.pr-batch-table-wrapper[data-idx="${idx}"]`);
                    render_batch_table($wrapper, idx, 1, item.pending_qty);
                    // Show initial total
                    d.$wrapper.find(`.pr-item-total[data-idx="${idx}"] .pr-item-total-qty`).text(flt(item.pending_qty, 3));
                });

                // Bind "Number of Lots" change
                d.$wrapper.find('.pr-num-batches').on('change', function () {
                    const idx = cint($(this).data('idx'));
                    const num = cint($(this).val()) || 1;
                    const $wrapper = d.$wrapper.find(`.pr-batch-table-wrapper[data-idx="${idx}"]`);
                    render_batch_table($wrapper, idx, num, null);
                    // Reset total display
                    d.$wrapper.find(`.pr-item-total[data-idx="${idx}"] .pr-item-total-qty`).text('0');
                });
            }
        });
    }

    create_po_for_item(details, item_code) {
        const item = details.raw_materials.find(m => m.item_code === item_code);
        if (!item) return;

        // Pass sales_order and sales_order_item from details to item for linking
        item.sales_order = details.sales_order;
        item.sales_order_item = details.sales_order_item;

        // Reuse the logic from create_shortage_po but for a single item
        this.__show_po_dialog(details, [item], __('Create PO for {0}', [item_code]));
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
        const operations_data = (details.operations || []).map(op => {
            let skip = 0;
            let wh = details.work_order?.wip_warehouse || '';

            // Defaults based on user request
            if (op.operation.toLowerCase().includes('knitting') && !op.is_subcontracted) {
                skip = 1;
            }

            if (op.operation.toLowerCase().includes('dyeing')) {
                wh = 'Job Work Outward - O';
            }

            return {
                operation: op.operation,
                workstation: op.workstation || '',
                skip_material_transfer: skip,
                wip_warehouse: wh
            };
        });

        const d = new frappe.ui.Dialog({
            title: __('Start Production: {0}', [details.work_order.name]),
            size: 'large',
            fields: [
                {
                    fieldname: 'info',
                    fieldtype: 'HTML',
                    options: `<div class="alert alert-info">${__('Define settings for each operation. These will be applied to the generated Job Cards.')}</div>`
                },
                {
                    fieldname: 'operation_settings',
                    fieldtype: 'Table',
                    label: __('Operation Settings'),
                    fields: [
                        {
                            fieldname: 'operation',
                            fieldtype: 'Data',
                            label: __('Operation'),
                            read_only: 1,
                            in_list_view: 1,
                            columns: 3
                        },
                        {
                            fieldname: 'workstation',
                            fieldtype: 'Link',
                            options: 'Workstation',
                            label: __('Initial Machine'),
                            in_list_view: 1,
                            columns: 3,
                            reqd: 1
                        },
                        {
                            fieldname: 'skip_material_transfer',
                            fieldtype: 'Check',
                            label: __('Skip'),
                            in_list_view: 1,
                            columns: 2
                        },
                        {
                            fieldname: 'wip_warehouse',
                            fieldtype: 'Link',
                            options: 'Warehouse',
                            label: __('WIP Wh'),
                            in_list_view: 1,
                            columns: 3
                        }
                    ],
                    data: operations_data
                }
            ],
            primary_action_label: __('Start Production'),
            primary_action: (values) => {
                frappe.call({
                    method: 'kniterp.api.production_wizard.start_work_order',
                    args: {
                        work_order: details.work_order.name,
                        operation_settings: values.operation_settings
                    },
                    freeze: true,
                    freeze_message: __('Starting Production...'),
                    callback: (r) => {
                        if (r.message) {
                            d.hide();
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
        });

        d.show();
    }

    create_subcontracting_order(details, operation) {
        const self = this;

        // Find the operation details
        const op = details.operations.find(o => o.operation === operation);
        const total_qty = op?.for_quantity || details.pending_qty;
        const already_ordered = op?.po_qty || 0;
        const remaining_required = op?.remaining_to_subcontract || (total_qty - already_ordered);

        // Get availability from previous operation (batch flow)
        // If undefined (e.g. first op), assume full pending qty is available
        const available_from_prev = op.qty_ready_from_prev !== undefined ? op.qty_ready_from_prev : details.pending_qty;

        // The default qty should be what's available to process NOW
        // (limited by both remaining requirement and previous op output)
        const default_qty = op.available_to_process !== undefined ? op.available_to_process : remaining_required;

        // Build info section
        let info_html = `
            <div class="alert alert-info">
                <div class="d-flex justify-content-between flex-wrap">
                    <span><strong>${__('Total Required')}:</strong> ${total_qty}</span>
                    <span><strong>${__('Already Ordered')}:</strong> ${already_ordered}</span>
                    <span><strong>${__('Remaining Needed')}:</strong> ${remaining_required}</span>
                </div>
            </div>
        `;

        // Show availability context if relevant (i.e. not first op or if flow restricted)
        if (op.qty_ready_from_prev !== undefined) {
            const can_proceed = default_qty > 0;
            const alert_class = can_proceed ? 'alert-success' : 'alert-warning';
            const is_first_op = details.operations[0].operation === operation;
            const default_icon = can_proceed ? 'check-circle' : 'exclamation-circle';
            const icon = is_first_op && default_icon !== 'exclamation-circle' ? 'cubes' : default_icon;
            const title = is_first_op ? __('Max Available RM Limit') : __('Ready to Process');
            const note = is_first_op ? __('Maximum you can process based on raw material stock') : __('Based on output from previous operation');

            info_html += `
                <div class="alert ${alert_class}">
                    <i class="fa fa-${icon}"></i>
                    <strong>${title}:</strong> ${flt(available_from_prev, 3)} ${details.uom || 'Units'}
                    <br><small class="text-muted">${note}</small>
                </div>
             `;
        }

        // Show supplier selection dialog
        const d = new frappe.ui.Dialog({
            title: already_ordered > 0
                ? __('Create Additional Subcontracting Order')
                : __('Create Subcontracting Order'),
            fields: [
                {
                    fieldname: 'info_section',
                    fieldtype: 'HTML',
                    options: info_html
                },
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
                    fieldname: 'rate',
                    fieldtype: 'Currency',
                    label: __('Rate'),
                    reqd: 0,
                    description: __('Rate per Unit')
                },
                {
                    fieldname: 'qty',
                    fieldtype: 'Float',
                    label: __('Quantity for this Batch'),
                    default: default_qty,
                    reqd: 1,
                    description: __('Limit: {0} (Available from previous op)', [flt(available_from_prev, 3)])
                }
            ],
            primary_action_label: __('Create & Submit'),
            primary_action(values) {
                // Validation: Warn but don't strictly block if they really want to proceed (unless 0)
                // Use a small epsilon for float comparison to avoid 245 > 244.99999 issues

                if (values.qty <= 0) {
                    frappe.msgprint({
                        title: __('Invalid Quantity'),
                        message: __('Quantity must be greater than 0'),
                        indicator: 'red'
                    });
                    return;
                }

                // Round available to 3 decimal places for comparison strictness
                const rounded_available = flt(available_from_prev, 3);

                // Strict validation: Block if quantity exceeds available (with epsilon tolerance)
                if (values.qty > rounded_available + 0.001) {
                    const is_first_op = details.operations[0].operation === operation;
                    const err_msg = is_first_op
                        ? __('You are ordering <b>{0}</b>, but you only have Raw Materials to process <b>{1}</b>.', [values.qty, rounded_available])
                        : __('You are ordering <b>{0}</b>, but only <b>{1}</b> is available to process from the previous operation.', [values.qty, rounded_available]);

                    frappe.msgprint({
                        title: __('Limit Exceeded'),
                        message: err_msg,
                        indicator: 'red'
                    });
                    return;
                } else if (values.qty > remaining_required + 0.001) {
                    frappe.confirm(
                        __('You are ordering <b>{0}</b>, which is more than the remaining required quantity <b>{1}</b>. Continue?', [values.qty, remaining_required]),
                        () => {
                            self._submit_sco(details, operation, values, d);
                        }
                    );
                } else {
                    self._submit_sco(details, operation, values, d);
                }
            }
        });

        d.show();
    }

    _submit_sco(details, operation, values, d) {
        const self = this;
        frappe.call({
            method: 'kniterp.api.production_wizard.create_subcontracting_order',
            args: {
                work_order: details.work_order.name,
                operation: operation,
                supplier: values.supplier,
                qty: values.qty,
                rate: values.rate
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

    send_raw_material_to_supplier(purchase_order, sco_name, ctx) {
        const create_ste = (sco, fg_qty) => {
            const args = { sco_name: sco };
            if (fg_qty) args.fg_qty = fg_qty;

            frappe.call({
                method: 'kniterp.api.production_wizard.auto_split_subcontract_stock_entry',
                args: args,
                freeze: true,
                freeze_message: __('Drafting Stock Entry and allocating batches...'),
                callback: (r) => {
                    if (r.message) {
                        frappe.set_route('Form', 'Stock Entry', r.message);
                    }
                }
            });
        };

        if (sco_name) {
            // Show qty prompt for partial sends
            const pending_fg = ctx ? flt(ctx.pending_fg) : 0;
            const pending_rm = ctx ? flt(ctx.required_rm - ctx.sent_rm, 3) : 0;

            if (pending_fg > 0) {
                const rm_per_fg = pending_fg > 0 ? pending_rm / pending_fg : 0;
                let _updating = false;

                const d = new frappe.ui.Dialog({
                    title: __('Send Raw Material'),
                    fields: [
                        {
                            fieldname: 'info_html',
                            fieldtype: 'HTML',
                            options: `<div class="mb-3" style="background:var(--control-bg); border:1px solid var(--border-color); border-radius:6px; padding:10px 14px; font-size:13px;">
                                <div><strong>${__('SCO')}:</strong> ${sco_name}</div>
                                <div><strong>${__('Pending FG Qty')}:</strong> ${pending_fg}</div>
                                <div><strong>${__('Pending RM Qty')}:</strong> ${pending_rm}</div>
                            </div>`
                        },
                        {
                            fieldname: 'fg_qty',
                            fieldtype: 'Float',
                            label: __('FG Qty'),
                            default: pending_fg,
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
                            default: pending_rm,
                            reqd: 1,
                            change: () => {
                                if (_updating) return;
                                _updating = true;
                                const v = flt(d.get_value('rm_qty'), 3);
                                d.set_value('fg_qty', rm_per_fg > 0 ? flt(v / rm_per_fg, 3) : 0).then(() => _updating = false);
                            }
                        }
                    ],
                    primary_action_label: __('Create Stock Entry'),
                    primary_action: (values) => {
                        const qty = flt(values.fg_qty);
                        if (qty <= 0) {
                            frappe.msgprint(__('Quantity must be greater than 0'));
                            return;
                        }
                        if (qty > pending_fg) {
                            frappe.msgprint(__('Quantity cannot exceed pending FG qty ({0})', [pending_fg]));
                            return;
                        }
                        d.hide();
                        create_ste(sco_name, qty < pending_fg ? qty : null);
                    }
                });
                d.show();
            } else {
                create_ste(sco_name);
            }
            return;
        }

        frappe.call({
            method: 'frappe.client.get_value',
            args: {
                doctype: 'Subcontracting Order',
                filters: { 'purchase_order': purchase_order, 'docstatus': 1 },
                fieldname: 'name'
            },
            callback: (r) => {
                if (r.message && r.message.name) {
                    create_ste(r.message.name);
                } else {
                    frappe.msgprint(__('No submitted Subcontracting Order found for this Purchase Order'));
                }
            }
        });
    }

    receive_subcontracted_goods(po_name, sco_name, ctx) {
        const self = this;

        // Build order context panel from ctx (passed by the click handler)
        let context_html = '';
        if (ctx) {
            const pending = flt(ctx.qty - (ctx.received_qty || 0), 3);
            const sent = flt(ctx.sent_qty || 0, 3);
            const received = flt(ctx.received_qty || 0, 3);
            const total = flt(ctx.qty || 0, 3);
            const uom = ctx.uom || 'Units';
            context_html = `
                <div class="mb-3" style="background:var(--control-bg); border:1px solid var(--border-color); border-radius:6px; padding:10px 14px; color:var(--text-color);">
                    <div style="font-size:13px; line-height:1.8;">
                        <div><strong>${__('Supplier')}:</strong> ${ctx.supplier || '—'}</div>
                        <div><strong>${__('Item')}:</strong> ${ctx.item_name || '—'}</div>
                        <div><strong>${__('Operation')}:</strong> ${ctx.operation || '—'}</div>
                        <div><strong>${__('Order')}:</strong>
                            <a href="/app/purchase-order/${ctx.po_name}" target="_blank">${ctx.po_name}</a>
                            &nbsp;/&nbsp;
                            <a href="/app/subcontracting-order/${ctx.sco_name}" target="_blank">${ctx.sco_name}</a>
                        </div>
                    </div>
                    <hr style="margin:8px 0; border-color:var(--border-color);">
                    <div class="d-flex justify-content-between flex-wrap" style="font-size:12px; color:var(--text-muted);">
                        <span><strong>${__('Ordered')}:</strong> ${total} ${uom}</span>
                        <span><strong>${__('Sent')}:</strong> ${sent} ${uom}</span>
                        <span><strong>${__('Already Received')}:</strong> ${received} ${uom}</span>
                        <span><strong>${__('Pending')}:</strong> <span style="color:#fff; background:${pending > 0 ? 'var(--yellow-500, #d97706)' : 'var(--green-500, #16a34a)'}; border-radius:4px; padding:1px 6px;">${pending} ${uom}</span></span>
                    </div>
                </div>
            `;
        }

        // Prompt for details
        const d = new frappe.ui.Dialog({
            title: ctx ? __('Receive Goods — {0}', [ctx.supplier || po_name]) : __('Receive Subcontracted Goods'),
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
                    fieldname: 'sb_lot',
                    fieldtype: 'Section Break',
                    label: __('Lot Traceability')
                },
                {
                    fieldname: 'num_batches',
                    fieldtype: 'Int',
                    label: __('Number of Output Batches Received'),
                    description: __('How many different dyeing batches did you receive for this quantity?'),
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

                    received_batches.push({
                        qty: row_qty,
                        batch_no: row_lot
                    });
                    total_batch_qty += row_qty;
                });

                if (has_error) return;

                if (Math.abs(total_batch_qty - flt(values.qty)) > 0.001) {
                    frappe.msgprint(__('Total batch quantities ({0}) must equal the Quantity to Receive ({1})', [total_batch_qty, values.qty]));
                    return;
                }

                if (d.max_receivable_qty && total_batch_qty > d.max_receivable_qty) {
                    frappe.msgprint(__('Total batch quantities ({0}) exceed the maximum receivable quantity ({1})', [total_batch_qty, d.max_receivable_qty]));
                    return;
                }

                frappe.call({
                    method: 'kniterp.api.production_wizard.receive_subcontracted_goods',
                    args: {
                        purchase_order: po_name,
                        subcontracting_order: sco_name,
                        rate: values.rate,
                        supplier_delivery_note: values.supplier_delivery_note,
                        received_batches: JSON.stringify(received_batches)
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
                            self.load_production_details(self.selected_item);
                        }
                    }
                });
            }
        });

        // Helper: build and inject batch table HTML for the given number of batches
        const render_batch_table = (num_batches, prefill_qty) => {
            let html = '<table class="table table-bordered table-condensed"><thead><tr><th>' + __('Quantity') + '</th><th>' + __('Output Dyeing Lot No') + '</th></tr></thead><tbody>';
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

            // Auto-calculate total qty when batch-qty changes
            d.$wrapper.find('.batch-qty').on('input', function () {
                let total = 0;
                d.$wrapper.find('.batch-qty').each(function () {
                    total += flt($(this).val());
                });
                d.set_value('qty', total);
            });
        };

        // Fetch PO details to set defaults
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
                            // If the item has a specific fg_item_qty compared to the PO service qty, convert the ratio.
                            if (item.fg_item_qty && item.qty) {
                                fg_received = (item.received_qty || 0) * (item.fg_item_qty / item.qty);
                            }
                            const item_pending = (item.fg_item_qty || item.qty) - fg_received;
                            pending += Math.max(0, item_pending);
                            rate = item.rate;
                        });
                    }

                    // Cap receivable to FG equivalent of RM actually sent
                    if (ctx && ctx.required_rm_qty && ctx.sent_qty && ctx.qty) {
                        const fg_for_sent_rm = flt((ctx.sent_qty / ctx.required_rm_qty) * ctx.qty, 3);
                        const already_received = flt(ctx.received_qty || 0, 3);
                        const receivable_from_sent = flt(fg_for_sent_rm - already_received, 3);
                        pending = Math.min(pending, Math.max(0, receivable_from_sent));
                    }

                    d.max_receivable_qty = pending;
                    d.set_value('qty', pending);
                    d.set_df_property('qty', 'description', __('Maximum receivable quantity: {0}', [pending]));
                    d.set_value('rate', rate);
                    d.show();
                    // Render the default 1-batch table with qty pre-filled
                    render_batch_table(1, pending);
                } else {
                    d.show();
                    render_batch_table(1);
                }
            }
        });
    }

    complete_operation(details, operation, remaining_qty) {
        const self = this;

        // Find the operation to get job card
        const op = details.operations.find(o => o.operation === operation);
        if (!op || !op.job_card) {
            frappe.throw(__('No Job Card found for operation {0}', [operation]));
            return;
        }

        const job_card = op.job_card;
        // batch_map will be populated after fetching availability: { item_code: [{batch_no, qty}] }
        let _batch_map = {};

        // Fetch Job Card details to pre-populate dialog
        frappe.call({
            method: 'frappe.client.get',
            args: {
                doctype: 'Job Card',
                name: job_card
            },
            callback: (r) => {
                if (!r.message) {
                    frappe.msgprint(__('Could not load Job Card details'));
                    return;
                }

                const jc = r.message;
                const work_order_skip = details.work_order?.skip_transfer || false;
                const jc_skip = jc.skip_material_transfer || false;
                const current_skip = work_order_skip || jc_skip;

                // Calculate batch context
                const total_qty = op.for_quantity || jc.for_quantity || 0;
                const completed_qty = op.completed_qty || jc.total_completed_qty || 0;
                const remaining = total_qty - completed_qty;

                // Get max producible based on available RM (from backend calculation)
                const raw_max_producible = details.max_producible_qty || 0;
                const conversion_factor = op.conversion_factor || 1.0;
                const max_producible = raw_max_producible / conversion_factor;
                const bottleneck = details.bottleneck_item || '';

                // Get available from previous operation (batch flow)
                const available_from_prev = op.qty_ready_from_prev !== undefined ? op.qty_ready_from_prev : details.pending_qty;

                // Default qty logic:
                // 1. Start with available to process (min of remaining and prev_op_output)
                let default_qty = op.available_to_process !== undefined ? op.available_to_process : remaining;

                // 2. Limit by raw materials if first operation or if significant RM constraint
                if (max_producible > 0 && max_producible < default_qty) {
                    default_qty = max_producible;
                }

                // 3. Ensure positive and round to standard precision
                default_qty = Math.max(0, flt(default_qty, 3));

                // Build info section for batch context
                let info_html = `
                    <div class="alert alert-light border">
                        <div class="d-flex justify-content-between flex-wrap">
                            <span><strong>${__('Total Required')}:</strong> ${total_qty} ${details.uom || 'Units'}</span>
                            <span><strong>${__('Completed')}:</strong> ${completed_qty} ${details.uom || 'Units'}</span>
                            <span><strong>${__('Remaining')}:</strong> ${parseFloat(remaining > 0 ? remaining : 0).toFixed(3)} ${details.uom || 'Units'}</span>
                        </div>
                    </div>
                `;

                // Show availability from previous op
                if (op.qty_ready_from_prev !== undefined) {
                    const is_first_op = details.operations[0].operation === operation;
                    let title = is_first_op ? __('Max Available RM Limit') : __('Ready to Process');
                    let notes = is_first_op ? __('Based on Raw Material stock in warehouse') : __('Based on output from previous operation');
                    let alert_class = 'alert-info';
                    let icon = is_first_op ? 'cubes' : 'arrow-right';

                    // Check if limited by Raw Material (values are close)
                    // If available_from_prev is approx equal to max_producible, it means RM is the constraint
                    const is_rm_limited = max_producible > 0 && Math.abs(available_from_prev - max_producible) < 0.01;

                    if (is_rm_limited) {
                        notes = __('Limited by Raw Material availability');
                        if (bottleneck) {
                            notes += `: <strong>${bottleneck}</strong>`;
                        }
                        alert_class = 'alert-warning';
                        icon = 'exclamation-triangle';
                    }

                    info_html += `
                        <div class="alert ${alert_class}">
                            <i class="fa fa-${icon}"></i>
                            <strong>${title}:</strong> ${flt(available_from_prev, 3)} ${details.uom || 'Units'}
                            <br><small class="text-muted">${notes}</small>
                        </div>
                     `;
                }

                // Show max producible based on available RM (ONLY if not already covered above)
                // If is_rm_limited is true, we already showed the bottleneck info in the first alert.
                // We only show this secondary alert if max_producible is DIFFERENT (usually higher) than available_from_prev
                // but still lower than remaining (indicating a future ceiling), or if we have overproduced (remaining <= 0).
                if (max_producible > 0 && (max_producible < remaining || remaining <= 0)) {
                    const is_rm_limited = op.qty_ready_from_prev !== undefined && Math.abs(available_from_prev - max_producible) < 0.01;

                    if (!is_rm_limited) {
                        info_html += `
                            <div class="alert alert-warning">
                                <i class="fa fa-exclamation-triangle"></i>
                                <strong>${__('Max Producible with Available RM')}:</strong> ${flt(max_producible, 3)} ${details.uom || 'Units'}
                                ${bottleneck ? `<br><small class="text-muted">${__('Limited by')}: ${bottleneck}</small>` : ''}
                            </div>
                        `;
                    }
                } else if (max_producible === 0 && remaining > 0) {
                    // Only show red alert if RM is strictly required (usually first op)
                    // For subsequent ops, previous op output is the main constraint
                    info_html += `
                        <div class="alert alert-danger">
                            <i class="fa fa-times-circle"></i>
                            ${__('No raw materials available')}
                            ${bottleneck ? `<br><small>${__('Missing')}: ${bottleneck}</small>` : ''}
                        </div>
                    `;
                }

                if (completed_qty > 0) {
                    info_html += `<p class="text-muted small">${__('This will add to the existing completed quantity (batch production).')}</p>`;
                }

                // Mutable map of item_code → required qty for this production batch.
                // Updated whenever the user changes the 'qty' field.
                const rm_items_for_lots = (jc.items && jc.items.length > 0) ? jc.items : [];
                const _need_qtys = {};
                // _lot_allocations[item_code] = [{batch_no, available, use_qty, ...provenance}]
                const _lot_allocations = {};
                let _check_submit_eligibility = null;
                let d = null; // dialog reference, assigned in _show_dialog

                // FIFO allocation: distribute needed_qty across sorted batches (oldest first).
                // ALL batches with available stock are included in the table so the user can
                // freely swap to a different lot. FIFO pre-fills the optimal selection; the
                // rest appear with use_qty = 0 and are fully editable.
                const _fifo_allocate = (item_code) => {
                    const batches = _batch_map[item_code] || [];
                    const needed = _need_qtys[item_code] || 0;
                    let remaining = needed;
                    const FIFO_MIN_QTY = 0.005; // matches backend fractional tolerance
                    const allocs = [];
                    batches.forEach(b => {
                        const avail = flt(b.qty, 3);
                        if (avail <= 0) return; // skip zero-stock lots entirely

                        // FIFO: fill as much as needed, then 0 for the rest.
                        // Always include in the table so the user can pick any lot.
                        const use_qty = (remaining >= FIFO_MIN_QTY)
                            ? flt(Math.min(remaining, avail), 3)
                            : 0;

                        allocs.push({
                            batch_no: b.batch_no,
                            available: avail,
                            use_qty: use_qty,
                            warehouse: b.warehouse || '',
                            source_doc_type: b.source_doc_type || '',
                            source_doc_name: b.source_doc_name || '',
                            entry_date: b.entry_date || '',
                            supplier_name: b.supplier_name || '',
                            purchase_order: b.purchase_order || '',
                        });
                        remaining = flt(Math.max(0, remaining - use_qty), 3);
                    });
                    _lot_allocations[item_code] = allocs;
                };

                // Build provenance display string for a batch
                const _provenance_html = (alloc) => {
                    let parts = [];
                    if (alloc.source_doc_type === 'Purchase Receipt') {
                        if (alloc.purchase_order) parts.push(`📦 ${alloc.purchase_order}`);
                        if (alloc.supplier_name) parts.push(alloc.supplier_name);
                        if (alloc.entry_date) parts.push(__('Rcvd {0}', [frappe.datetime.str_to_user(alloc.entry_date)]));
                    } else if (alloc.source_doc_type) {
                        parts.push(alloc.source_doc_type);
                        if (alloc.source_doc_name) parts.push(alloc.source_doc_name);
                        if (alloc.entry_date) parts.push(frappe.datetime.str_to_user(alloc.entry_date));
                    }
                    return parts.length > 0
                        ? `<span class="text-muted" style="font-size:11px;">${parts.join(' • ')}</span>`
                        : '';
                };

                // Render the multi-lot allocation table for a single RM item
                const _render_lot_table = (item_code, item_name) => {
                    const allocs = _lot_allocations[item_code] || [];
                    const needed = _need_qtys[item_code] || 0;
                    let total_allocated = 0;
                    allocs.forEach(a => { total_allocated += flt(a.use_qty, 3); });

                    const safe_ic = item_code.replace(/[^a-zA-Z0-9]/g, '_');

                    if (allocs.length === 0) {
                        return `<div class="lot-table-wrapper" data-item="${safe_ic}">
                            <div class="alert alert-warning py-2 px-3 mb-2" style="font-size:12px;">
                                <i class="fa fa-exclamation-triangle"></i>
                                ${__('No batches with available stock for {0}', [item_name || item_code])}
                            </div>
                        </div>`;
                    }

                    // Progress bar
                    let pct = needed > 0 ? Math.min(100, (total_allocated / needed) * 100) : 100;
                    let bar_class = 'bg-success';
                    let status_icon = '✅';
                    if (needed > 0 && total_allocated < needed - 0.001) {
                        bar_class = pct > 50 ? 'bg-warning' : 'bg-danger';
                        status_icon = pct > 50 ? '⚠' : '❌';
                    } else if (total_allocated > needed + 0.001) {
                        bar_class = 'bg-danger';
                        status_icon = '❌';
                    }

                    let html = `<div class="lot-table-wrapper" data-item="${safe_ic}">
                        <div style="font-weight:600; margin-bottom:4px; font-size:13px;">
                            ${item_name || item_code}
                            <span class="text-muted" style="font-weight:normal; font-size:12px;"> — ${__('Need')}: ${needed.toFixed(3)}</span>
                        </div>
                        <table class="table table-bordered table-sm lot-alloc-table" style="margin-bottom:4px; font-size:12px;">
                            <thead style="background:#f8f9fa; color:#212529;">
                                <tr>
                                    <th style="width:28%;">${__('Lot')}</th>
                                    <th style="width:22%;">${__('Warehouse')}</th>
                                    <th style="width:12%; text-align:right;">${__('Avail')}</th>
                                    <th style="width:14%; text-align:right;">${__('Use')}</th>
                                    <th>${__('Source')}</th>
                                </tr>
                            </thead>
                            <tbody>`;

                    allocs.forEach((a, idx) => {
                        html += `
                            <tr>
                                <td><strong>${a.batch_no}</strong></td>
                                <td style="font-size:11px; color:#6c757d;">${a.warehouse}</td>
                                <td style="text-align:right;">${a.available.toFixed(3)}</td>
                                <td style="text-align:right;">
                                    <input type="number" class="form-control form-control-sm lot-use-qty"
                                           data-item="${safe_ic}" data-idx="${idx}"
                                           value="${a.use_qty.toFixed(3)}"
                                           min="0" max="${a.available.toFixed(3)}" step="any"
                                           style="text-align:right; padding:2px 6px; height:28px; font-size:12px;">
                                </td>
                                <td>${_provenance_html(a)}</td>
                            </tr>`;
                    });

                    html += `</tbody></table>
                        <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
                            <div style="flex:1; background:#e9ecef; border-radius:4px; height:8px; overflow:hidden;">
                                <div class="lot-progress-bar ${bar_class}" style="width:${pct}%; height:100%; transition:width 0.3s;"></div>
                            </div>
                            <span class="lot-status-text" style="font-size:11px; white-space:nowrap;">
                                ${status_icon} ${total_allocated.toFixed(3)} / ${needed.toFixed(3)}
                            </span>
                        </div>
                    </div>`;
                    return html;
                };

                // Refresh lot tables in the dialog
                const _refresh_all_lot_tables = () => {
                    if (!d) return;
                    const $wrapper = d.fields_dict.lot_tables_html?.$wrapper;
                    if (!$wrapper) return;

                    let combined_html = '';
                    rm_items_for_lots.forEach(item => {
                        combined_html += _render_lot_table(item.item_code, item.item_name || '');
                    });

                    if (rm_items_for_lots.length === 0) {
                        combined_html = `<div class="text-muted small">${__('No raw material items found on Job Card.')}</div>`;
                    }

                    $wrapper.html(combined_html);

                    // Bind input events for use_qty editing
                    $wrapper.find('.lot-use-qty').off('input').on('input', function () {
                        const $input = $(this);
                        const safe_ic = $input.data('item');
                        const idx = parseInt($input.data('idx'));
                        const new_val = flt($input.val(), 3);

                        // Find the matching item_code from safe_ic
                        const item = rm_items_for_lots.find(i => i.item_code.replace(/[^a-zA-Z0-9]/g, '_') === safe_ic);
                        if (!item) return;

                        const allocs = _lot_allocations[item.item_code] || [];
                        if (allocs[idx] !== undefined) {
                            allocs[idx].use_qty = Math.min(flt(new_val, 3), allocs[idx].available);
                        }

                        // Refresh just the progress bar for this item (not full re-render to avoid blur)
                        const needed = _need_qtys[item.item_code] || 0;
                        let total_alloc = 0;
                        allocs.forEach(a => { total_alloc += flt(a.use_qty, 3); });

                        let pct = needed > 0 ? Math.min(100, (total_alloc / needed) * 100) : 100;
                        let bar_class = 'bg-success';
                        let status_icon = '✅';
                        if (needed > 0 && total_alloc < needed - 0.001) {
                            bar_class = pct > 50 ? 'bg-warning' : 'bg-danger';
                            status_icon = pct > 50 ? '⚠' : '❌';
                        } else if (total_alloc > needed + 0.001) {
                            bar_class = 'bg-danger';
                            status_icon = '❌';
                        }

                        const $table_wrapper = $input.closest('.lot-table-wrapper');
                        $table_wrapper.find('.lot-progress-bar').removeClass('bg-success bg-warning bg-danger').addClass(bar_class).css('width', pct + '%');
                        $table_wrapper.find('.lot-status-text').html(`${status_icon} ${total_alloc.toFixed(3)} / ${needed.toFixed(3)}`);

                        if (_check_submit_eligibility) _check_submit_eligibility();
                        _update_output_batch_field();
                    });

                    if (_check_submit_eligibility) _check_submit_eligibility();
                };

                // Run FIFO allocation for all RM items and refresh tables
                const _run_fifo_and_refresh = () => {
                    rm_items_for_lots.forEach(item => {
                        _fifo_allocate(item.item_code);
                    });
                    _refresh_all_lot_tables();
                };

                // Derive a deterministic output batch name from the sorted set of
                // input RM lot numbers chosen by FIFO allocation.
                // Same input lots → same batch name; different lots → different name.
                // Prefixed with "FAB-" so the output fabric lot is clearly distinct from
                // the input RM (yarn/greige) lot numbers.
                // Returns empty string if no lots are allocated yet.
                const _derive_output_batch = () => {
                    const all_batch_nos = new Set();
                    rm_items_for_lots.forEach(item => {
                        const allocs = _lot_allocations[item.item_code] || [];
                        allocs.forEach(a => {
                            if (flt(a.use_qty, 3) > 0) {
                                all_batch_nos.add(a.batch_no);
                            }
                        });
                    });
                    if (all_batch_nos.size === 0) return '';
                    return 'FAB-' + Array.from(all_batch_nos).sort().join('+');
                };

                // Track the last auto-derived value so we can detect manual overrides
                let _last_auto_batch = '';

                // Update the output_batch_no field only when it hasn't been manually overridden
                const _update_output_batch_field = () => {
                    if (!d) return;
                    const derived = _derive_output_batch();
                    const current_val = (d.get_value('output_batch_no') || '').trim();
                    // Only update if the field still shows the previous auto value (or is empty)
                    if (current_val === '' || current_val === _last_auto_batch) {
                        if (derived !== _last_auto_batch) {
                            _last_auto_batch = derived;
                            d.set_value('output_batch_no', derived);
                        }
                    }
                };

                const _show_dialog = () => {
                    // Compute initial need_qtys
                    const ratio = flt(default_qty, 3) / flt(jc.for_quantity || 1);
                    rm_items_for_lots.forEach(item => {
                        _need_qtys[item.item_code] = flt((item.required_qty || 0) * ratio, 3);
                    });

                    // Run initial FIFO allocation
                    rm_items_for_lots.forEach(item => {
                        _fifo_allocate(item.item_code);
                    });

                    d = new frappe.ui.Dialog({
                        title: __('Update Manufactured Quantity: {0}', [operation]),
                        fields: [
                            {
                                fieldname: 'info_section',
                                fieldtype: 'HTML',
                                options: info_html
                            },
                            {
                                fieldname: 'sb_progress',
                                fieldtype: 'Section Break',
                                label: __('Production Details')
                            },
                            {
                                fieldname: 'workstation',
                                fieldtype: 'Link',
                                options: 'Workstation',
                                label: __('Machine / Workstation'),
                                default: jc.workstation || op.workstation || '',
                                reqd: 1
                            },
                            {
                                fieldname: 'employee',
                                fieldtype: 'Link',
                                options: 'Employee',
                                label: __('Employee'),
                                description: __('Person performing the operation'),
                                reqd: operation.toLowerCase().includes('knitting') ? 1 : 0
                            },
                            // Conditionally add fields for Knitting Machine Attendance
                            ...(operation.toLowerCase().includes('knitting') ? [
                                {
                                    fieldname: 'attendance_date',
                                    fieldtype: 'Date',
                                    label: __('Date'),
                                    default: frappe.datetime.get_today(),
                                    reqd: 1
                                },
                                {
                                    fieldname: 'shift',
                                    fieldtype: 'Link',
                                    options: 'Shift Type',
                                    label: __('Shift'),
                                    reqd: 1
                                }
                            ] : []),
                            {
                                fieldname: 'cb_qty',
                                fieldtype: 'Column Break'
                            },
                            {
                                fieldname: 'qty',
                                fieldtype: 'Float',
                                label: __('Quantity to Manufacture in this Batch'),
                                default: default_qty,
                                reqd: 1,
                                description: __('Enter the quantity you produced in this batch. You can produce more batches later.'),
                                onchange: function () {
                                    // Recalculate required qty per RM item and re-run FIFO
                                    const new_qty = flt(this.value) || 0;
                                    const jc_qty = flt(jc.for_quantity) || 1;
                                    rm_items_for_lots.forEach(item => {
                                        _need_qtys[item.item_code] = flt((item.required_qty || 0) * new_qty / jc_qty, 3);
                                    });
                                    _run_fifo_and_refresh();
                                    _update_output_batch_field();
                                }
                            },
                            {
                                fieldname: 'sb_lot_tracking',
                                fieldtype: 'Section Break',
                                label: __('Lot Traceability')
                            },
                            {
                                fieldname: 'lot_tables_html',
                                fieldtype: 'HTML',
                                options: ''
                            },
                            {
                                fieldname: 'output_batch_no',
                                fieldtype: 'Data',
                                label: __('Output Batch No'),
                                description: __('Auto-derived from input RM lots (edit to override). Same input lots always produce the same batch name.')
                            }
                        ],
                        primary_action_label: __('Update'),
                        primary_action(values) {
                            // Build consumed_lots map in multi-batch format:
                            // {item_code: [{batch_no, qty}]}
                            let consumed_lots_map = {};

                            rm_items_for_lots.forEach(item => {
                                const allocs = _lot_allocations[item.item_code] || [];
                                const entries = [];
                                allocs.forEach(a => {
                                    if (flt(a.use_qty, 3) > 0) {
                                        entries.push({
                                            batch_no: a.batch_no,
                                            qty: flt(a.use_qty, 3)
                                        });
                                    }
                                });
                                if (entries.length > 0) {
                                    consumed_lots_map[item.item_code] = entries;
                                }
                            });

                            frappe.call({
                                method: 'kniterp.api.production_wizard.complete_operation',
                                args: {
                                    work_order: details.work_order.name,
                                    operation: operation,
                                    qty: values.qty,
                                    workstation: values.workstation,
                                    employee: values.employee,
                                    attendance_date: values.attendance_date,
                                    shift: values.shift,
                                    consumed_lots: JSON.stringify(consumed_lots_map),
                                    output_batch_no: values.output_batch_no || null
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
                        },
                        secondary_action_label: __('View Logs'),
                        secondary_action() {
                            self.show_production_logs(op.job_card);
                        }
                    });

                    d.show();

                    // Render the lot tables into the HTML field
                    _refresh_all_lot_tables();

                    // Set the initial derived output batch (after FIFO has run)
                    _last_auto_batch = _derive_output_batch();
                    d.set_value('output_batch_no', _last_auto_batch);

                    // Wire up submit eligibility checking
                    _check_submit_eligibility = () => {
                        let any_under = false;
                        rm_items_for_lots.forEach(item => {
                            const allocs = _lot_allocations[item.item_code] || [];
                            const needed = _need_qtys[item.item_code] || 0;
                            let total_alloc = 0;
                            allocs.forEach(a => { total_alloc += flt(a.use_qty, 3); });
                            // Block if total stock across all lots is less than needed
                            // and user hasn't allocated enough
                            let total_avail = 0;
                            allocs.forEach(a => { total_avail += a.available; });
                            if (needed > 0 && total_alloc < needed - 0.001 && total_avail >= needed) {
                                any_under = true;
                            }
                        });
                        const $btn = d.get_primary_btn();
                        if (any_under) {
                            $btn.prop('disabled', true).attr('title', __('Please allocate sufficient lot quantity for all raw materials'));
                        } else {
                            $btn.prop('disabled', false).removeAttr('title');
                        }
                    };
                    _check_submit_eligibility(); // initial state
                }; // end _show_dialog

                // Fetch batch availability with provenance context (FIFO sorted)
                if (rm_items_for_lots.length > 0) {
                    let pending_calls = rm_items_for_lots.length;
                    rm_items_for_lots.forEach(item => {
                        frappe.call({
                            method: 'kniterp.api.production_wizard.get_available_batches_with_context',
                            args: { item_code: item.item_code },
                            callback: (br) => {
                                _batch_map[item.item_code] = br.message || [];
                                pending_calls--;
                                if (pending_calls === 0) _show_dialog();
                            }
                        });
                    });
                } else {
                    _show_dialog();
                }
            } // end JC callback
        }); // end frappe.call for Job Card
    } // end complete_operation

    show_production_logs(job_card) {
        const self = this;
        frappe.call({
            method: 'kniterp.api.production_wizard.get_production_logs',
            args: { job_card: job_card },
            callback: (r) => {
                const logs = r.message || [];

                const d = new frappe.ui.Dialog({
                    title: __('Production Logs: {0}', [job_card]),
                    size: 'large',
                    fields: [
                        {
                            fieldname: 'logs_html',
                            fieldtype: 'HTML'
                        }
                    ]
                });

                const render_table = () => {
                    let html = `
                        <table class="table table-bordered table-sm" style="margin-top: 10px;">
                            <thead>
                                <tr>
                                    <th style="width: 140px;">${__('Date & Time')}</th>
                                    <th>${__('Stock Entry')}</th>
                                    <th>${__('Employee')}</th>
                                    <th>${__('Machine')}</th>
                                    <th class="text-right" style="width: 80px;">${__('Qty')}</th>
                                    <th class="text-center" style="width: 110px;">${__('Action')}</th>
                                </tr>
                            </thead>
                            <tbody>
                    `;

                    if (logs.length === 0) {
                        html += `<tr><td colspan="6" class="text-center text-muted" style="padding: 20px;">${__('No production logs found.')}</td></tr>`;
                    } else {
                        logs.forEach(log => {
                            // Format date time slightly nicer
                            const posting_datetime = frappe.datetime.str_to_user(log.posting_date) + ' ' + (log.posting_time ? log.posting_time.substring(0, 5) : '');

                            html += `
                                <tr>
                                    <td>${posting_datetime}</td>
                                    <td><a href="/app/stock-entry/${log.name}" target="_blank" style="font-weight: bold;">${log.name}</a></td>
                                    <td>${log.employee_name || log.employee || '-'}</td>
                                    <td>${log.workstation || '-'}</td>
                                    <td class="text-right"><strong>${parseFloat(log.fg_completed_qty).toFixed(3)}</strong></td>
                                    <td class="text-center">
                                        <div class="btn-group btn-group-xs">
                                            <button class="btn btn-default btn-edit" data-name="${log.name}" data-qty="${log.fg_completed_qty}" data-employee="${log.employee || ''}" data-workstation="${log.workstation || ''}" title="${__('Edit Entry')}">
                                                ${frappe.utils.icon('edit', 'xs')}
                                            </button>
                                            <button class="btn btn-danger btn-revert" data-name="${log.name}" title="${__('Revert Entry')}">
                                                ${frappe.utils.icon('undo', 'xs')}
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            `;
                        });
                    }

                    html += `</tbody></table>`;

                    const $wrapper = d.fields_dict.logs_html.$wrapper;
                    $wrapper.html(html);

                    // Bind events
                    $wrapper.find('.btn-revert').off('click').on('click', function () {
                        const stock_entry = $(this).data('name');

                        frappe.confirm(
                            __('Are you sure you want to revert Stock Entry <b>{0}</b>?<br><br>This will:<br>1. Cancel the Stock Entry.<br>2. Remove the corresponding Time Log from the Job Card.', [stock_entry]),
                            () => {
                                frappe.call({
                                    method: 'kniterp.api.production_wizard.revert_production_entry',
                                    args: { stock_entry: stock_entry },
                                    freeze: true,
                                    freeze_message: __('Reverting Production Entry...'),
                                    callback: (res) => {
                                        if (!res.exc) {
                                            frappe.show_alert({ message: __('Entry reverted successfully'), indicator: 'green' });
                                            refresh_view(stock_entry);
                                        }
                                    }
                                });
                            }
                        );
                    });

                    // Bind Edit
                    $wrapper.find('.btn-edit').off('click').on('click', function () {
                        const btn = $(this);
                        const stock_entry = btn.data('name');
                        const current_qty = btn.data('qty');
                        const current_employee = btn.data('employee');
                        const current_workstation = btn.data('workstation');

                        const d_edit = new frappe.ui.Dialog({
                            title: __('Update Entry: {0}', [stock_entry]),
                            fields: [
                                {
                                    fieldname: 'employee',
                                    fieldtype: 'Link',
                                    label: __('Employee'),
                                    options: 'Employee',
                                    default: current_employee
                                },
                                {
                                    fieldname: 'workstation',
                                    fieldtype: 'Link',
                                    label: __('Workstation'),
                                    options: 'Workstation',
                                    default: current_workstation,
                                    reqd: 1
                                },
                                {
                                    fieldname: 'qty',
                                    fieldtype: 'Float',
                                    label: __('Quantity'),
                                    default: current_qty,
                                    reqd: 1
                                }
                            ],
                            primary_action_label: __('Update'),
                            primary_action(values) {
                                frappe.call({
                                    method: 'kniterp.api.production_wizard.update_production_entry',
                                    args: {
                                        stock_entry: stock_entry,
                                        qty: values.qty,
                                        employee: values.employee,
                                        workstation: values.workstation
                                    },
                                    freeze: true,
                                    freeze_message: __('Updating Production Entry...'),
                                    callback: (res) => {
                                        if (!res.exc) {
                                            d_edit.hide();
                                            frappe.show_alert({ message: __('Entry updated successfully'), indicator: 'green' });
                                            refresh_view(stock_entry);
                                        }
                                    }
                                });
                            }
                        });
                        d_edit.show();
                    });
                };

                const refresh_view = (removed_stock_entry) => {
                    frappe.call({
                        method: 'kniterp.api.production_wizard.get_production_logs',
                        args: { job_card: job_card },
                        callback: (r) => {
                            if (r.message) {
                                logs.length = 0;
                                logs.push(...r.message);
                                render_table();

                                // Refresh main UI (parent)
                                self.refresh_pending_items();
                                if (self.selected_item) {
                                    self.load_production_details(self.selected_item);
                                }
                            }
                        }
                    });
                };

                render_table();
                d.show();
            }
        });
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
                const summary_fields = [];

                // --- SUMMARY SECTION ---
                const produced_qty = parseFloat(jc.manufactured_qty || 0);
                const planned_qty = parseFloat(jc.for_quantity || 0);
                const pending_qty = Math.max(0, planned_qty - produced_qty);
                const is_over = produced_qty > planned_qty;
                const status_color = is_over ? "var(--red-500)" : (produced_qty >= planned_qty ? "var(--green-500)" : "var(--orange-500)");
                const status_text = is_over ? `Over-Produced (+${(produced_qty - planned_qty).toFixed(2)})` : (produced_qty >= planned_qty ? "Fully Produced" : "In Progress");

                summary_fields.push({
                    fieldname: 'summary_section',
                    fieldtype: 'Section Break',
                    label: __('Job Card Summary')
                });

                summary_fields.push({
                    fieldname: 'summary_html',
                    fieldtype: 'HTML',
                    options: `
                        <div style="padding: 12px; background-color: var(--fill-color); border: 1px solid var(--border-color); border-radius: var(--border-radius); margin-bottom: 15px;">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                                <span class="text-muted">${__('Planned Quantity')}:</span>
                                <strong>${planned_qty}</strong>
                            </div>
                            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                                <span class="text-muted">${__('Already Produced')}:</span>
                                <strong>${produced_qty}</strong>
                            </div>
                            <div style="display: flex; justify-content: space-between; margin-bottom: 8px; border-bottom: 1px dashed var(--border-color); padding-bottom: 8px;">
                                <span class="text-muted">${__('Balance Pending')}:</span>
                                <strong>${pending_qty}</strong>
                            </div>
                             <div style="display: flex; justify-content: space-between; align-items: center;">
                                <span class="text-muted">${__('Status')}:</span>
                                <span class="badge" style="background-color: ${status_color}; color: white; padding: 4px 8px;">${status_text}</span>
                            </div>
                            
                            <div style="margin-top: 12px; font-size: 11px; color: var(--text-muted); line-height: 1.4;">
                                ${pending_qty > 0
                            ? `Could trigger a final <b>Stock Entry</b> for the remaining <b>${pending_qty}</b> units (and associated RM consumption).`
                            : `Production is complete. This action will <b>close the Job Card</b> without creating further stock entries.`}
                            </div>
                        </div>
                    `
                });
                // ---------------------------
                // Item and Settings fields removed as per request.
                // We now rely on Job Card / Work Order defaults.
                /* if (jc.items && jc.items.length > 0) { ... } */

                const d = new frappe.ui.Dialog({
                    title: __('Complete Job Card: {0}', [job_card]),
                    size: 'large',
                    fields: [
                        ...summary_fields
                    ],
                    primary_action_label: __('Complete Job Card'),
                    primary_action(values) {
                        frappe.call({
                            method: 'kniterp.api.production_wizard.complete_job_card',
                            args: {
                                job_card: job_card,
                                additional_qty: 0,
                                process_loss_qty: 0
                            },
                            freeze: true,
                            freeze_message: __('Completing Job Card...'),
                            callback: (r) => {
                                if (r.message) {
                                    d.hide();
                                    frappe.show_alert({
                                        message: __('Job Card {0} completed successfully.',
                                            [`<a href="/app/job-card/${job_card}">${job_card}</a>`]),
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
        if (!details.raw_materials) return;

        // Prepare items with sales_order for linking
        let items_source = details.raw_materials.filter(m => m.shortage > 0);
        let title = __('Create Purchase Order for Shortages');

        // If no shortages, select all valid raw materials (for overproduction/stocking up)
        if (items_source.length === 0) {
            items_source = details.raw_materials.filter(m => !m.is_customer_provided);
            title = __('Create Purchase Order');
        }

        const shortage_items = items_source.map(m => {
            // Clone to avoid mutating original
            let m_copy = Object.assign({}, m);
            m_copy.sales_order = details.sales_order;
            m_copy.sales_order_item = details.sales_order_item;
            return m_copy;
        });

        if (!shortage_items.length) {
            frappe.msgprint(__('No items to order.'));
            return;
        }

        this.__show_po_dialog(details, shortage_items, title);
    }

    __show_po_dialog(details, shortage_items, title) {
        const self = this;
        const default_warehouse = details.work_order?.source_warehouse || 'Stores - O';
        const base_parent_qty = details.pending_qty || 1; // Avoid div by zero

        // Calculate initial plan quantity based on min producible from shortages
        // We use the "Net" required qty here because we want to know how much *more* we can make given current shortages
        let initial_plan_qty = base_parent_qty;
        let min_producible = -1;


        shortage_items.forEach(item => {
            // Use the true BOM ratio pre-calculated by the backend
            const ratio = item.qty_per_unit || 0;

            if (ratio > 0 && item.shortage > 0) {
                const producible = item.shortage / ratio;
                if (min_producible === -1 || producible < min_producible) {
                    min_producible = producible;
                }
            }
        });

        if (min_producible !== -1) {
            initial_plan_qty = min_producible;
        }

        // Round to 3 decimals
        initial_plan_qty = parseFloat(initial_plan_qty.toFixed(3));

        // Calculate remaining to produce for Total Planning Mode
        const produced = details.work_order?.produced_qty || 0;
        const remaining_to_produce = Math.max(0, base_parent_qty - produced);

        const d = new frappe.ui.Dialog({
            title: title,
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
                    fieldname: 'bom_info',
                    fieldtype: 'Data',
                    label: __('Based on BOM'),
                    default: details.bom_no || __('Default BOM'),
                    read_only: 1,
                    description: __('The logic uses this BOM for ratio calculations.')
                },
                {
                    fieldname: 'sb_calc',
                    fieldtype: 'Section Break',
                    label: __('Calculator')
                },
                {
                    fieldname: 'include_available_stock',
                    fieldtype: 'Check',
                    label: __('Consider Available Stock for Planning'),
                    default: 1,
                    description: __('If checked, the calculator will deduct available raw material stock from the required quantity. Default plan quantity will be set to remaining production (Pending - Produced).'),
                    onchange: function () {
                        const checked = this.get_value();
                        if (checked) {
                            // Switch to Total Planning Mode

                            // Default to Remaining Production: Total Pending (Sales) - Already Produced
                            const produced = details.work_order?.produced_qty || 0;
                            const remaining_to_produce = Math.max(0, base_parent_qty - produced);
                            d.set_value('parent_qty', remaining_to_produce);
                        } else {
                            // Switch to Shortage Planning Mode (Default: Min Producible Shortage)
                            d.set_value('parent_qty', initial_plan_qty);
                        }
                        // Trigger recalculation
                        d.fields_dict.parent_qty.df.onchange.call(d.fields_dict.parent_qty);
                    }
                },
                {
                    fieldname: 'parent_qty',
                    fieldtype: 'Float',
                    label: __('Plan for Quantity of ' + (details.production_item || details.item_code)),
                    default: remaining_to_produce,
                    onchange: function () {
                        const new_parent_qty = this.get_value() || 0;
                        const include_stock = d.get_value('include_available_stock');
                        let all_stock_available = true;

                        // Update item quantities based on BOM ratios
                        shortage_items.forEach((item, i) => {
                            // Use true BOM ratio pre-calculated by backend
                            const ratio = item.qty_per_unit || 0;

                            // Calc Required based on Plan Qty
                            let new_qty = new_parent_qty * ratio;

                            if (include_stock) {
                                // Deduct available stock (actual - reserved)
                                const available = parseFloat(item.available_qty || 0); // available_qty is ALREADY actual - reserved
                                new_qty = Math.max(0, new_qty - available);
                            }

                            if (new_qty > 0.0001) {
                                all_stock_available = false;
                            }

                            // Update input
                            const $input = d.$wrapper.find(`.item-qty[data-idx="${i}"]`);
                            if ($input.length) {
                                if (include_stock && new_qty === 0) {
                                    $input.val(0);
                                    $input.attr('placeholder', __('Stock Available'));
                                } else {
                                    $input.val(parseFloat(new_qty).toFixed(3));
                                    $input.attr('placeholder', '');
                                }
                            }
                        });

                        // Show notification if all stock is available
                        const $calc_info = d.fields_dict.calc_info.$wrapper;
                        if (include_stock && all_stock_available && new_parent_qty > 0) {
                            $calc_info.html(`<div class="alert alert-center alert-success mt-3 mb-0">
                                <i class="fa fa-check-circle"></i> ${__('Raw material is already available to produce this quantity.')}
                             </div>`);
                        } else {
                            $calc_info.html(`<p class="text-muted small mt-4">${__('Changing the planned quantity will auto-adjust the required shortage quantities below based on BOM ratios.')}</p>`);
                        }
                    }
                },
                {
                    fieldname: 'col_break_calc',
                    fieldtype: 'Column Break'
                },
                {
                    fieldname: 'calc_info',
                    fieldtype: 'HTML',
                    options: `<p class="text-muted small mt-4">${__('Changing the planned quantity will auto-adjust the required shortage quantities below based on BOM ratios.')}</p>`
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
            <table class="table table-sm table-bordered">
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
            const rate = parseFloat(item.last_purchase_rate || item.valuation_rate || 0).toFixed(2);
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
                            data-idx="${i}" value="${rate}" step="0.01" placeholder="Auto">
                    </td>
                    <td>${item.uom || item.stock_uom || ''}</td>
                </tr>
            `;
        }
        items_html += '</tbody></table > ';

        d.fields_dict.items_html.$wrapper.html(items_html);
        d.show();

        // Bind manual editing events to inputs
        d.$wrapper.find('.item-qty').on('input', function () {
            self._recalculate_manual_qty(d, shortage_items, base_parent_qty);
        });

        // Trigger initial calculation to ensure the dialog state matches the checked option
        setTimeout(() => {
            if (d && d.fields_dict && d.fields_dict.parent_qty) {
                d.fields_dict.parent_qty.df.onchange.call(d.fields_dict.parent_qty);
            }
        }, 100);
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
                    warehouse: values.warehouse || shortage_items[idx].warehouse,
                    sales_order: shortage_items[idx].sales_order || null,
                    sales_order_item: shortage_items[idx].sales_order_item || null
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

    _recalculate_manual_qty(d, shortage_items, base_parent_qty) {
        const include_stock = d.get_value('include_available_stock');

        let min_producible_fg = Infinity;
        let limiting_item = null;

        const manual_quantities = [];

        // 1. First Pass: Find the Limiting RM and Max Producible FG
        shortage_items.forEach((item, i) => {
            const $input = d.$wrapper.find(`.item-qty[data-idx="${i}"]`);
            const order_qty = parseFloat($input.val()) || 0;
            manual_quantities.push(order_qty);

            const ratio = item.qty_per_unit || 0;
            if (ratio <= 0) return;

            let total_available_for_production = order_qty;
            if (include_stock) {
                total_available_for_production += Math.max(0, parseFloat(item.available_qty || 0));
            }

            const producible_fg = total_available_for_production / ratio;
            if (producible_fg < min_producible_fg) {
                min_producible_fg = producible_fg;
                limiting_item = item;
            }
        });

        if (min_producible_fg === Infinity || !limiting_item) return;

        // 2. Second Pass: Calculate differences
        let info_html = `<div class="mt-4 p-3 mb-0" style="background-color: var(--control-bg); border-radius: 4px; border: 1px solid var(--border-color);">`;
        info_html += `<div class="font-weight-bold mb-2"><i class="fa fa-info-circle text-info"></i> ${__('Manual Input Analysis')}</div>`;
        info_html += `<div class="small mb-2">${__('Based on the quantities entered below, you can produce a maximum of')} <strong class="text-success">${parseFloat(min_producible_fg).toFixed(3)}</strong> ${__('units of Finished Goods.')}</div>`;
        let excess_html = '';

        // Find max FG possible if limiting_item wasn't limiting (to find how much limiting item is needed to balance)
        let max_producible_fg_without_limit = 0;

        shortage_items.forEach((item, i) => {
            if (item.item_code === limiting_item.item_code) return;

            const ratio = item.qty_per_unit || 0;

            let actual_available = manual_quantities[i];
            if (include_stock) {
                actual_available += Math.max(0, parseFloat(item.available_qty || 0));
            }

            const fg_possible = actual_available / ratio;
            if (fg_possible > max_producible_fg_without_limit) {
                max_producible_fg_without_limit = fg_possible;
            }

            const required_for_fg = min_producible_fg * ratio;
            const excess = actual_available - required_for_fg;

            if (excess > 0.001) {
                excess_html += `<li class="mt-1 border-bottom pb-1"><strong>${item.item_code}</strong>: ${__('Excess of')} <span class="text-warning font-weight-bold">${parseFloat(excess).toFixed(3)}</span> ${item.uom || ''}</li>`;
            }
        });

        info_html += `<div class="small mb-2 pt-1">`;
        info_html += `<div>${__('Limiting Raw Material:')} <strong class="text-danger">${limiting_item.item_code}</strong></div>`;

        if (excess_html) {
            // Calculate how much limiting item is needed to balance the highest excess
            const limit_ratio = limiting_item.qty_per_unit || 0;
            const limiting_item_qty_needed = max_producible_fg_without_limit * limit_ratio;

            let current_limit_qty = parseFloat(d.$wrapper.find(`.item-qty[data-idx="${shortage_items.findIndex(m => m.item_code === limiting_item.item_code)}"]`).val()) || 0;
            if (include_stock) {
                current_limit_qty += Math.max(0, parseFloat(limiting_item.available_qty || 0));
            }

            const limiting_shortage = limiting_item_qty_needed - current_limit_qty;

            if (limiting_shortage > 0.001) {
                info_html += `<div class="text-danger mt-1 pl-2 mb-2" style="border-left: 2px solid #ff5858; opacity: 0.9;">
                     <i class="fa fa-exclamation-triangle"></i> 
                     ${__('Short by <strong>{0}</strong> {1}',
                    [parseFloat(limiting_shortage).toFixed(3), limiting_item.uom || ''])}
                 </div>`;
            }
        }
        info_html += `</div>`;

        if (excess_html) {
            info_html += `<div class="small mt-2 pt-2 border-top"><strong>${__('Excess Materials Ordered:')}</strong><ul class="mb-0 pl-3 list-unstyled">` + excess_html + '</ul></div>';
            info_html += `<div class="mt-2 text-muted small"><i class="fa fa-lightbulb-o text-warning"></i> ${__('Tip: To balance this order, either add the exact short amount to your limit material, or reduce the excess amounts.')}</div>`;
        } else {
            info_html += `<div class="small mt-2 pt-2 border-top text-success"><i class="fa fa-check"></i> ${__('Materials are perfectly balanced.')}</div>`;
        }

        info_html += `</div>`;

        d.fields_dict.calc_info.$wrapper.html(info_html);
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

    create_sales_invoice(details) {
        frappe.call({
            method: 'kniterp.api.production_wizard.create_sales_invoice',
            args: {
                sales_order: details.sales_order
            },
            freeze: true,
            freeze_message: __('Creating Sales Invoice...'),
            callback: (r) => {
                if (r.message) {
                    frappe.set_route('Form', 'Sales Invoice', r.message);
                }
            }
        });
    }

    create_sco_purchase_invoice(po_name, supplier, amount) {
        const self = this;
        const d = new frappe.ui.Dialog({
            title: __('Create Purchase Invoice'),
            fields: [
                {
                    fieldtype: 'HTML',
                    fieldname: 'context_info',
                    options: `<div class="mb-3 p-2 rounded" style="background: var(--control-bg); border: 1px solid var(--border-color);">
                        <div class="small">
                            <strong>${__('Purchase Order')}:</strong> <a href="/app/purchase-order/${po_name}">${po_name}</a><br>
                            <strong>${__('Supplier')}:</strong> ${supplier}<br>
                            <strong>${__('Amount')}:</strong> ${frappe.format(amount, { fieldtype: 'Currency' })}
                        </div>
                    </div>`
                },
                {
                    label: __('Bill No (Supplier Invoice)'),
                    fieldname: 'bill_no',
                    fieldtype: 'Data',
                    description: __('Supplier invoice number')
                },
                {
                    label: __('Bill Date'),
                    fieldname: 'bill_date',
                    fieldtype: 'Date',
                    default: frappe.datetime.nowdate()
                },
                {
                    fieldtype: 'Column Break'
                },
                {
                    label: __('Posting Date'),
                    fieldname: 'posting_date',
                    fieldtype: 'Date',
                    default: frappe.datetime.nowdate()
                }
            ],
            primary_action_label: __('Submit'),
            primary_action: (values) => {
                self._call_create_pi(d, po_name, values, true);
            },
            secondary_action_label: __('Save as Draft'),
            secondary_action: () => {
                const values = d.get_values();
                self._call_create_pi(d, po_name, values, false);
            }
        });
        d.show();
    }

    _call_create_pi(dialog, po_name, values, submit) {
        frappe.call({
            method: 'kniterp.api.production_wizard.create_purchase_invoice_from_po',
            args: {
                purchase_order: po_name,
                bill_no: values.bill_no || '',
                bill_date: values.bill_date || '',
                posting_date: values.posting_date || '',
                submit: submit
            },
            freeze: true,
            freeze_message: submit ? __('Creating and Submitting Purchase Invoice...') : __('Creating Purchase Invoice...'),
            callback: (r) => {
                if (r.message && r.message.success) {
                    dialog.hide();
                    if (r.message.existing) {
                        frappe.show_alert({
                            message: __('Draft Purchase Invoice {0} already exists', [r.message.purchase_invoice]),
                            indicator: 'orange'
                        });
                        frappe.set_route('Form', 'Purchase Invoice', r.message.purchase_invoice);
                    } else {
                        frappe.show_alert({
                            message: r.message.submitted
                                ? __('Purchase Invoice {0} created and submitted', [r.message.purchase_invoice])
                                : __('Purchase Invoice {0} created as draft', [r.message.purchase_invoice]),
                            indicator: 'green'
                        });
                        this.load_production_details(this.selected_item);
                    }
                }
            }
        });
    }


    create_scio_sales_invoice(details) {
        frappe.call({
            method: 'kniterp.api.production_wizard.create_scio_sales_invoice',
            args: {
                sales_order_item: details.sales_order_item
            },
            freeze: true,
            freeze_message: __('Creating Sales Invoice...'),
            callback: (r) => {
                if (r.message) {
                    frappe.set_route('Form', 'Sales Invoice', r.message);
                }
            }
        });
    }

    show_order_activity_log(details) {
        frappe.call({
            method: 'kniterp.api.production_wizard.get_order_activity_log',
            args: { sales_order_item: details.sales_order_item },
            freeze: true,
            freeze_message: __('Loading Activity Log...'),
            callback: (r) => {
                if (!r.message) return;
                const data = r.message;
                const events = data.events || [];

                // Build filter tabs
                const event_types = [...new Set(events.map(e => e.event_type))];
                const type_labels = {
                    order: __('Orders'),
                    work_order: __('Work Order'),
                    job_card: __('Job Cards'),
                    stock_entry: __('Production'),
                    subcontracting: __('Subcontracting'),
                    delivery: __('Delivery'),
                    invoice: __('Invoice'),
                    audit: __('Audit'),
                    comment: __('Comments'),
                    note: __('Notes')
                };

                let filter_html = `<div class="activity-log-filters mb-3">
                    <button class="btn btn-xs btn-primary activity-filter active" data-type="all">${__('All')} (${events.length})</button>`;
                for (const t of event_types) {
                    const count = events.filter(e => e.event_type === t).length;
                    filter_html += `<button class="btn btn-xs btn-default activity-filter" data-type="${t}">${type_labels[t] || t} (${count})</button>`;
                }
                filter_html += '</div>';

                // Build timeline HTML
                let timeline_html = '<div class="activity-log-timeline">';
                for (const evt of events) {
                    const time_ago = frappe.datetime.prettyDate(evt.timestamp);
                    const full_time = frappe.datetime.str_to_user(evt.timestamp);
                    const link_html = evt.linked_name
                        ? `<a href="/app/${frappe.router.slug(evt.linked_doctype)}/${evt.linked_name}" class="activity-log-link">${evt.linked_doctype}: ${evt.linked_name}</a>`
                        : '';

                    // Escape and format description (preserve newlines for audit logs)
                    let desc = (evt.description || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                    desc = desc.replace(/\n/g, '<br>');

                    timeline_html += `
                        <div class="activity-log-item" data-event-type="${evt.event_type}">
                            <div class="activity-log-node" style="background-color: ${evt.color};">
                                <i class="fa ${evt.icon}"></i>
                            </div>
                            <div class="activity-log-content">
                                <div class="activity-log-header">
                                    <span class="activity-log-title">${evt.title}</span>
                                    <span class="activity-log-time" title="${full_time}">${time_ago}</span>
                                </div>
                                ${desc ? `<div class="activity-log-desc">${desc}</div>` : ''}
                                <div class="activity-log-footer">
                                    ${evt.actor_name ? `<span class="activity-log-actor"><i class="fa fa-user"></i> ${evt.actor_name}</span>` : ''}
                                    ${link_html}
                                </div>
                            </div>
                        </div>`;
                }
                timeline_html += '</div>';

                if (events.length === 0) {
                    timeline_html = `<div class="text-muted text-center p-5">
                        <i class="fa fa-info-circle fa-2x mb-2"></i>
                        <div>${__('No activity recorded for this order yet.')}</div>
                    </div>`;
                }

                const d = new frappe.ui.Dialog({
                    title: __('Activity Log \u2014 {0}', [data.item_code]),
                    size: 'extra-large',
                    fields: [
                        {
                            fieldname: 'log_html',
                            fieldtype: 'HTML',
                            options: `
                                <div class="activity-log-container">
                                    <div class="activity-log-summary mb-3">
                                        <span class="badge badge-info">${data.total_events} ${__('events')}</span>
                                        <span class="text-muted ml-2">${data.item_name}</span>
                                    </div>
                                    ${filter_html}
                                    ${timeline_html}
                                </div>
                            `
                        }
                    ]
                });

                d.show();

                // Bind filter click events
                d.$wrapper.find('.activity-filter').on('click', function () {
                    d.$wrapper.find('.activity-filter').removeClass('btn-primary active').addClass('btn-default');
                    $(this).removeClass('btn-default').addClass('btn-primary active');

                    const type = $(this).data('type');
                    if (type === 'all') {
                        d.$wrapper.find('.activity-log-item').show();
                    } else {
                        d.$wrapper.find('.activity-log-item').hide();
                        d.$wrapper.find(`.activity-log-item[data-event-type="${type}"]`).show();
                    }
                });
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

    show_consolidated_wizard() {
        const d = new frappe.ui.Dialog({
            title: __('Consolidated Procurement Wizard'),
            size: 'extra-large',
            fields: [
                {
                    fieldname: 'customer',
                    fieldtype: 'Link',
                    options: 'Customer',
                    label: __('Filter by Customer'),
                    description: __('Select customer to aggregate shortages for')
                },
                {
                    fieldname: 'col_break_1',
                    fieldtype: 'Column Break'
                },
                {
                    fieldname: 'item_group',
                    fieldtype: 'Link',
                    options: 'Item Group',
                    label: __('Filter by Item Group'),
                    description: __('e.g., Yarn, Buttons')
                },
                {
                    fieldname: 'sec_dates',
                    fieldtype: 'Section Break',
                    label: __('Date Range')
                },
                {
                    fieldname: 'from_date',
                    fieldtype: 'Date',
                    label: __('From Delivery Date'),
                    default: frappe.datetime.add_months(frappe.datetime.nowdate(), -1)
                },
                {
                    fieldname: 'col_break_2',
                    fieldtype: 'Column Break'
                },
                {
                    fieldname: 'to_date',
                    fieldtype: 'Date',
                    label: __('To Delivery Date'),
                    default: frappe.datetime.add_months(frappe.datetime.nowdate(), 1)
                },
                {
                    fieldname: 'sec_action',
                    fieldtype: 'Section Break'
                },
                {
                    fieldname: 'get_btn',
                    fieldtype: 'Button',
                    label: __('Get Shortages'),
                    click: () => {
                        this.get_consolidated_shortages(d);
                    }
                },
                {
                    fieldname: 'results_section',
                    fieldtype: 'Section Break',
                    label: __('Shortage Summary'),
                    hidden: 1
                },
                {
                    fieldname: 'shortages_html',
                    fieldtype: 'HTML'
                }
            ]
        });

        d.show();
    }

    get_consolidated_shortages(dialog) {
        const values = dialog.get_values();
        if (!values) return;

        dialog.get_field('shortages_html').$wrapper.html(`
            <div class="text-center p-4">
                <div class="spinner-border text-primary" role="status">
                    <span class="sr-only">${__('Loading...')}</span>
                </div>
            </div>
        `);
        dialog.set_df_property('results_section', 'hidden', 0);

        frappe.call({
            method: 'kniterp.api.production_wizard.get_consolidated_shortages',
            args: {
                filters: values
            },
            callback: (r) => {
                const shortages = r.message || {};
                this.render_consolidated_shortages(dialog, shortages);
            }
        });
    }

    render_consolidated_shortages(dialog, shortages) {
        if (Object.keys(shortages).length === 0) {
            dialog.get_field('shortages_html').$wrapper.html(`
                <div class="text-muted text-center p-4">${__('No shortages found based on current filters.')}</div>
            `);
            return;
        }

        let html = `
            <div class="consolidated-table-wrapper" style="max-height: 400px; overflow-y: auto;">
                <table class="table table-bordered table-sm">
                    <thead>
                        <tr class="thead-light">
                            <th style="width: 40px"><input type="checkbox" class="select-all-shortages"></th>
                            <th>${__('Item')}</th>
                            <th class="text-right">${__('Total Required')}</th>
                            <th class="text-right">${__('Total Shortage')}</th>
                            <th class="text-right" style="width: 120px">${__('Order Qty')}</th>
                            <th>${__('Details')}</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        for (const [item_code, data] of Object.entries(shortages)) {
            // Build tooltip or expand/collapse details
            const breakdown_info = data.breakdown.map(b =>
                `<div>${b.sales_order}: ${parseFloat(b.shortage).toFixed(3)}</div>`
            ).join('');

            html += `
                <tr data-item-code="${item_code}">
                    <td><input type="checkbox" class="select-shortage" checked></td>
                    <td>
                        <strong>${item_code}</strong>
                        <div class="small text-muted">${data.item_name || ''}</div>
                    </td>
                    <td class="text-right">${parseFloat(data.total_required).toFixed(3)} ${data.uom}</td>
                    <td class="text-right text-danger font-weight-bold">${parseFloat(data.total_shortage).toFixed(3)} ${data.uom}</td>
                    <td>
                        <input type="number" class="form-control form-control-sm text-right order-qty" 
                            value="${parseFloat(data.total_shortage).toFixed(3)}" step="0.001">
                    </td>
                    <td>
                         <button class="btn btn-xs btn-default btn-view-breakdown" data-toggle="popover" title="${__('Demand Breakdown')}" data-content="${breakdown_info}" data-html="true" data-trigger="focus">
                            <i class="fa fa-list"></i> ${data.breakdown.length} ${__('Orders')}
                         </button>
                    </td>
                </tr>
            `;
        }

        html += `</tbody></table></div>`;

        // Add Create PO Button at the bottom
        html += `
            <div class="mt-3 text-right">
                <button class="btn btn-primary btn-create-consolidated-po">
                    <i class="fa fa-shopping-cart"></i> ${__('Create Consolidated PO')}
                </button>
            </div>
        `;

        const wrapper = dialog.get_field('shortages_html').$wrapper;
        wrapper.html(html);

        // Initialize popovers
        wrapper.find('[data-toggle="popover"]').popover();

        // Bind Select All
        wrapper.find('.select-all-shortages').on('change', function () {
            wrapper.find('.select-shortage').prop('checked', $(this).is(':checked'));
        });

        // Bind Create PO
        wrapper.find('.btn-create-consolidated-po').on('click', () => {
            this.create_consolidated_po(dialog, shortages);
        });
    }

    create_consolidated_po(dialog, shortages) {
        const wrapper = dialog.get_field('shortages_html').$wrapper;
        const selected_items = [];

        wrapper.find('.select-shortage:checked').each(function () {
            const row = $(this).closest('tr');
            const item_code = row.data('item-code');
            const custom_qty = parseFloat(row.find('.order-qty').val()) || 0;

            if (custom_qty > 0 && shortages[item_code]) {
                const data = shortages[item_code];
                // Logic to distribute custom_qty among the breakdown
                // If custom_qty == total_shortage, we take everything.
                // If custom_qty != total_shortage, we assume proportional or FIFO?
                // For simplicity, let's assume we fulfill shortages in order until qty runs out.

                let remaining_to_order = custom_qty;

                for (let b of data.breakdown) {
                    if (remaining_to_order <= 0) break;

                    const needed = flt(b.shortage);
                    const take = Math.min(remaining_to_order, needed);

                    selected_items.push({
                        item_code: item_code,
                        qty: take,
                        sales_order: b.sales_order,
                        sales_order_item: b.sales_order_item,
                        warehouse: b.warehouse
                    });

                    remaining_to_order -= take;
                }

                // If there is still remaining qty (user ordered EXTRA), add a line without SO
                if (remaining_to_order > 0.001) {
                    selected_items.push({
                        item_code: item_code,
                        qty: remaining_to_order,
                        sales_order: null, // Extra stock
                        warehouse: data.breakdown[0].warehouse // Default to first warehouse
                    });
                }
            }
        });

        if (selected_items.length === 0) {
            frappe.msgprint(__('Please select items to order'));
            return;
        }

        // Now prompt for Supplier
        const d = new frappe.ui.Dialog({
            title: __('Select Supplier'),
            fields: [
                {
                    fieldname: 'supplier',
                    fieldtype: 'Link',
                    options: 'Supplier',
                    label: __('Supplier'),
                    reqd: 1
                }
            ],
            primary_action_label: __('Create Sales Orders'),
            primary_action: (values) => {
                frappe.call({
                    method: 'kniterp.api.production_wizard.create_purchase_orders_for_shortage',
                    args: {
                        items: JSON.stringify(selected_items),
                        supplier: values.supplier,
                        submit: 0 // Draft mode
                    },
                    freeze: true,
                    callback: (r) => {
                        if (r.message) {
                            d.hide();
                            dialog.hide();
                            frappe.show_alert({
                                message: __('Purchase Order created successfully: <a href="/app/purchase-order/{0}">{0}</a>', [r.message.name]),
                                indicator: 'green'
                            }, 5);
                            this.refresh_pending_items();
                            if (this.selected_item) this.load_production_details(this.selected_item);
                        }
                    }
                });
            }
        });

        // Only change label if we are creating PO
        d.set_primary_action(__('Create Purchase Order'), d.primary_action);
        d.show();
    }
}
