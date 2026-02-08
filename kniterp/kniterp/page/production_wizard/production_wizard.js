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
            this.status_filter.set_value(this.filters.invoice_status);
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

        // Party Name filter (Select)
        this.customer_filter = this.page.add_field({
            fieldname: 'customer',
            label: __('Party Name'),
            fieldtype: 'Select',
            options: [{ 'label': __('All Parties'), 'value': '' }],
            change: () => {
                this.filters.customer = this.customer_filter.get_value();
                this.refresh_pending_items();
            }
        });

        // Load parties initial - moved to end


        // From Date filter
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

        // To Date filter
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

        // Urgent filter
        this.urgent_filter = this.page.add_field({
            fieldname: 'urgent',
            label: __('Urgent Only'),
            fieldtype: 'Check',
            change: () => {
                this.filters.urgent = this.urgent_filter.get_value();
                this.load_party_options();
                this.refresh_pending_items();
            }
        });

        // Invoice Status filter
        this.status_filter = this.page.add_field({
            fieldname: 'status_filter',
            label: __('View Items'),
            fieldtype: 'Select',
            options: [
                { 'label': __('Pending Production'), 'value': 'Pending Production' },
                { 'label': __('Ready to Deliver'), 'value': 'Ready to Deliver' },
                { 'label': __('Ready to Invoice'), 'value': 'Ready to Invoice' },
                { 'label': __('All Active'), 'value': 'All' }
            ],
            default: 'Pending Production',
            change: () => {
                this.filters.invoice_status = this.status_filter.get_value();
                this.load_party_options();
                this.refresh_pending_items();
            }
        });

        // Materials Status filter (Action Center support)
        this.materials_filter = this.page.add_field({
            fieldname: 'materials_status',
            label: __('Materials'),
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

        // Type filter (Inward/Outward/Standard)
        this.type_filter = this.page.add_field({
            fieldname: 'job_work',
            label: __('Type'),
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

        // Set default filter if not present
        if (!this.filters.invoice_status) {
            this.filters.invoice_status = 'Pending Production';
        }

        // Ensure the fields are styled correctly for the top bar
        this.page.page_form.css({
            'padding': '10px 15px',
            'background': 'var(--subtle-fg)',
            'border-bottom': '1px solid var(--border-color)',
            'margin-bottom': '10px'
        });

        // Load parties initial (after fields are created)
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
						<h4>${details.production_item || details.item_name}</h4>
						<span class="text-muted">
                            ${details.production_item ? details.production_item : details.item_code}
                            ${details.is_subcontracted ? `<br><small class="text-muted">${__('Service')}: ${details.item_name}</small>` : ''}
                        </span>
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
                `<div>
                     <a href="/app/bom/${details.bom_no}">${details.bom_no}</a>
                     <button class="btn btn-xs btn-link text-muted btn-edit-bom ml-1" title="${__('Edit BOM')}" style="padding: 0 4px;">
                        <i class="fa fa-pencil"></i>
                     </button>
                 </div>` :
                `<button class="btn btn-xs btn-primary btn-create-bom-designer" data-item="${details.production_item || details.item_code}">
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
					${details.bom_no ? this.get_primary_action_buttons(details) : ''}
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

				<!-- Operations Section -->
				<div class="section-header">
					<h5><i class="fa fa-tasks"></i> ${__('Operations')}</h5>
				</div>
				<div class="operations-list">
					${details.bom_no ? this.render_operations(details) : `<div class="text-muted p-3">${__('Please create a BOM to view operations')}</div>`}
				</div>
			</div>
		`;

        this.$details_content.html(html);
        this.render_notes_section(details);
        this.bind_action_events(details);
        this.bind_note_events(details);
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
            // Check if we can deliver (produced > delivered)
            // Or just show the button if WO exists
            if (details.work_order && (details.work_order.produced_qty > 0)) {
                buttons.push(`
				<button class="btn btn-success btn-send-delivery mr-2" data-sio="${details.subcontracting_inward_order}">
					<i class="fa fa-truck"></i> ${__('Send Delivery')}
				</button>
			`);
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
        } else if (details.work_order.status === 'In Process') {
            // Allow delivery if we have formatted goods ready (produced > delivered)
            // This handles partial deliveries and over-production scenarios
            const produced = details.work_order.produced_qty || 0;
            const delivered = details.delivered_qty || 0;

            if (produced > delivered) {
                buttons.push(`
				<button class="btn btn-success btn-create-delivery">
					<i class="fa fa-truck"></i> ${__('Create Delivery Note')}
				</button>
			`);
            }
        } else if (details.work_order.status === 'Completed') {
            if (details.pending_qty > 0) {
                buttons.push(`
				<button class="btn btn-success btn-create-delivery">
					<i class="fa fa-truck"></i> ${__('Create Delivery Note')}
				</button>
			`);
            } else {
                if (details.draft_sales_invoice) {
                    buttons.push(`
                    <button class="btn btn-warning btn-create-invoice">
                        <i class="fa fa-file-text-o"></i> ${__('View Draft Invoice')}
                    </button>
                `);
                } else {
                    buttons.push(`
                    <button class="btn btn-success btn-create-invoice">
                        <i class="fa fa-file-text"></i> ${__('Create Sales Invoice')}
                    </button>
                `);
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
            frappe.set_route('bom_designer', {
                item_code: item_code,
                sales_order_item: details.sales_order_item,
                return_to: 'production_wizard'
            });
        });

        // Edit BOM (New)
        this.$details_content.find('.btn-edit-bom').on('click', function (e) {
            e.preventDefault(); // Prevent default link behavior if any
            frappe.set_route('bom_designer', {
                bom_no: details.bom_no,
                item_code: details.item_code, // Ensure item_code is available in details
                sales_order_item: details.sales_order_item,
                return_to: 'production_wizard'
            });
        });
    }

    receive_customer_rm(sio_name) {
        frappe.model.open_mapped_doc({
            method: "erpnext.subcontracting.doctype.subcontracting_inward_order.subcontracting_inward_order.make_rm_stock_entry_inward",
            frm: { doc: { name: sio_name, doctype: 'Subcontracting Inward Order' } } // Mocking frm somewhat
        });
        // The open_mapped_doc implementation usually expects frm.doc.name. 
        // If frm is passed, it uses frm.doc.name as source_name.
        // Let's check if we can pass source_name directly in args if we call make_mapped_doc manually.
        /* 
           Actually, the standard way in a page is to call frappe.model.mapper.make_mapped_doc directly.
        */
        return frappe.call({
            type: "POST",
            method: "frappe.model.mapper.make_mapped_doc",
            args: {
                method: "erpnext.subcontracting.doctype.subcontracting_inward_order.subcontracting_inward_order.make_rm_stock_entry_inward",
                source_name: sio_name,
            },
            freeze: true,
            callback: function (r) {
                if (!r.exc) {
                    var doc = frappe.model.sync(r.message);
                    frappe.set_route("Form", doc[0].doctype, doc[0].name);
                }
            }
        });
    }

    send_subcontracting_delivery(sio_name) {
        return frappe.call({
            type: "POST",
            method: "frappe.model.mapper.make_mapped_doc",
            args: {
                method: "erpnext.subcontracting.doctype.subcontracting_inward_order.subcontracting_inward_order.make_subcontracting_delivery",
                source_name: sio_name,
            },
            freeze: true,
            callback: function (r) {
                if (!r.exc) {
                    var doc = frappe.model.sync(r.message);
                    frappe.set_route("Form", doc[0].doctype, doc[0].name);
                }
            }
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

        // Find the operation to get job card
        const op = details.operations.find(o => o.operation === operation);
        if (!op || !op.job_card) {
            frappe.throw(__('No Job Card found for operation {0}', [operation]));
            return;
        }

        const job_card = op.job_card;

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
                // Default to remaining_qty if positive, else 0. 
                // Don't fallback to total quantity if remaining is 0 or negative (over-production logic)
                const default_qty = (remaining_qty > 0) ? remaining_qty : 0;

                const d = new frappe.ui.Dialog({
                    title: __('Update Manufactured Quantity: {0}', [operation]),
                    fields: [
                        {
                            fieldname: 'sb_progress',
                            fieldtype: 'Section Break',
                            label: __('Production Progress')
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
                            description: __('Person performing the operation')
                        },
                        {
                            fieldname: 'cb_qty',
                            fieldtype: 'Column Break'
                        },
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
                                qty: values.qty,
                                workstation: values.workstation,
                                employee: values.employee
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
            }
        });
    }

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
        // Prepare items with sales_order for linking
        const shortage_items = details.raw_materials.filter(m => m.shortage > 0).map(m => {
            m.sales_order = details.sales_order;
            m.sales_order_item = details.sales_order_item;
            return m;
        });

        if (!shortage_items.length) {
            frappe.msgprint(__('No shortages to order'));
            return;
        }

        this.__show_po_dialog(details, shortage_items, __('Create Purchase Order for Shortages'));
    }

    __show_po_dialog(details, shortage_items, title) {
        const self = this;
        const default_warehouse = details.work_order?.source_warehouse || 'Stores - O';

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
