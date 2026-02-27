frappe.pages['transaction-desk'].on_page_load = function (wrapper) {
    frappe.transaction_desk = new TransactionDesk(wrapper);
};

frappe.pages['transaction-desk'].refresh = function (wrapper) {
    if (frappe.transaction_desk) {
        frappe.transaction_desk.on_refresh();
    }
};

class TransactionDesk {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.page = frappe.ui.make_app_page({
            parent: wrapper,
            title: __('Transaction Desk'),
            single_column: true
        });

        this.defaults = {};
        this.form_controls = {};
        this.item_rows = [];
        this.account_rows = [];

        // Read type from route options
        const route_type = (frappe.route_options || {}).type || null;
        frappe.route_options = null;

        if (route_type) {
            this.init_form(route_type);
        } else {
            this.render_type_selector();
        }
    }

    on_refresh() {
        const route_type = (frappe.route_options || {}).type || null;
        frappe.route_options = null;
        if (route_type && route_type !== this.current_type) {
            this.init_form(route_type);
        }
    }

    // ─── Type Registry ──────────────────────────────────────
    get_type_registry() {
        return {
            'sales-order': {
                label: __('Sales Order'),
                icon: 'fa-file-text',
                color: '#2490ef',
                doctype: 'Sales Order',
                party_field: 'customer',
                party_label: __('Customer'),
                party_doctype: 'Customer',
                date_field: 'delivery_date',
                date_label: __('Delivery Date'),
                date_default_days: 7,
                has_items: true,
                has_tax: true,
                tax_type: 'sales',
            },
            'purchase-order': {
                label: __('Purchase Order'),
                icon: 'fa-shopping-cart',
                color: '#ff5858',
                doctype: 'Purchase Order',
                party_field: 'supplier',
                party_label: __('Supplier'),
                party_doctype: 'Supplier',
                date_field: 'required_date',
                date_label: __('Required By'),
                date_default_days: 14,
                has_items: true,
                has_tax: true,
                tax_type: 'purchase',
            },
            'payment-receive': {
                label: __('Payment Received'),
                icon: 'fa-arrow-down',
                color: '#28a745',
                doctype: 'Payment Entry',
                party_field: 'customer',
                party_label: __('Customer'),
                party_doctype: 'Customer',
                has_items: false,
                has_tax: false,
                is_payment: true,
                payment_type: 'Receive',
            },
            'payment-pay': {
                label: __('Payment Made'),
                icon: 'fa-arrow-up',
                color: '#dc3545',
                doctype: 'Payment Entry',
                party_field: 'supplier',
                party_label: __('Supplier'),
                party_doctype: 'Supplier',
                has_items: false,
                has_tax: false,
                is_payment: true,
                payment_type: 'Pay',
            },
            'journal-entry': {
                label: __('Journal Entry'),
                icon: 'fa-book',
                color: '#6c5ce7',
                doctype: 'Journal Entry',
                has_items: false,
                has_tax: false,
                is_journal: true,
            },
        };
    }

    // ─── Type Selector ──────────────────────────────────────
    render_type_selector() {
        this.current_type = null;
        this.page.set_title(__('Transaction Desk'));
        this.page.clear_actions();
        this.page.main.empty();

        const registry = this.get_type_registry();
        let cards_html = '';
        for (const [key, cfg] of Object.entries(registry)) {
            cards_html += `
                <div class="td-type-card" data-type="${key}">
                    <div class="td-type-icon" style="background: ${cfg.color}15; color: ${cfg.color};">
                        <i class="fa ${cfg.icon} fa-2x"></i>
                    </div>
                    <div class="td-type-label">${cfg.label}</div>
                    <div class="td-type-doctype text-muted">${cfg.doctype}</div>
                </div>
            `;
        }

        this.page.main.html(`
            <div class="td-container">
                <div class="td-welcome text-center mb-5">
                    <h3 class="mb-2">${__('Create a Transaction')}</h3>
                    <p class="text-muted">${__('Select a voucher type to begin')}</p>
                </div>
                <div class="td-type-grid">${cards_html}</div>
            </div>
        `);

        this.page.main.find('.td-type-card').on('click', (e) => {
            const type = $(e.currentTarget).data('type');
            this.init_form(type);
        });
    }

    // ─── Form Initialization ────────────────────────────────
    async init_form(type) {
        const registry = this.get_type_registry();
        const cfg = registry[type];
        if (!cfg) {
            frappe.msgprint(__('Unknown voucher type'));
            return;
        }

        this.current_type = type;
        this.current_config = cfg;
        this.form_controls = {};
        this.item_rows = [];
        this.account_rows = [];

        this.page.set_title(cfg.label);
        this.page.clear_actions();
        this.page.main.empty();

        // Show loading
        this.page.main.html(`
            <div class="text-center p-5">
                <div class="spinner-border text-primary" role="status"></div>
                <p class="mt-3 text-muted">${__('Loading defaults...')}</p>
            </div>
        `);

        // Fetch defaults
        try {
            const r = await frappe.xcall('kniterp.api.transaction_desk.get_defaults', {
                voucher_type: type
            });
            this.defaults = r;
        } catch (e) {
            frappe.msgprint(__('Failed to load defaults: ') + e.message);
            return;
        }

        this.page.main.empty();
        this.render_form();
        this.setup_page_actions();
        this.setup_keyboard_shortcuts();
        this.load_recent_entries();
    }

    // ─── Page Actions ───────────────────────────────────────
    setup_page_actions() {
        const cfg = this.current_config;

        this.page.set_primary_action(__('Create'), () => this.submit_form(), 'check');

        this.page.add_menu_item(__('Open Full Form'), () => {
            frappe.set_route('Form', cfg.doctype, 'new');
        });

        this.page.add_menu_item(__('Back to Type Selection'), () => {
            this.render_type_selector();
        });
    }

    // ─── Form Renderer ──────────────────────────────────────
    render_form() {
        const cfg = this.current_config;

        let html = `<div class="td-container">`;

        // Form header
        html += `
            <div class="td-form-header">
                <div class="d-flex align-items-center mb-3">
                    <div class="td-form-icon mr-3" style="background: ${cfg.color}15; color: ${cfg.color};">
                        <i class="fa ${cfg.icon} fa-lg"></i>
                    </div>
                    <div>
                        <h4 class="mb-0">${cfg.label}</h4>
                        <span class="text-muted small">${cfg.doctype}</span>
                    </div>
                </div>
            </div>
        `;

        // Main form area + sidebar
        html += `<div class="row"><div class="col-md-9">`;
        html += `<div class="td-form-body frappe-control" id="td-form-fields"></div>`;

        if (cfg.has_items) {
            html += this.render_item_table_html();
        }

        if (cfg.is_journal) {
            html += this.render_accounts_table_html();
        }

        if (cfg.has_tax) {
            html += `<div class="td-tax-section mt-4" id="td-tax-section"></div>`;
        }

        // Totals
        html += `<div class="td-totals-bar mt-4" id="td-totals-bar"></div>`;

        html += `</div>`;  // col-md-9

        // Sidebar — recent entries
        html += `
            <div class="col-md-3">
                <div class="td-recent-panel" id="td-recent-panel">
                    <h6 class="text-muted mb-3"><i class="fa fa-history mr-1"></i>${__('Recent Entries')}</h6>
                    <div class="td-recent-list"></div>
                </div>
            </div>
        `;

        html += `</div></div>`;  // row + container

        this.page.main.html(html);

        // Now render Frappe controls into #td-form-fields
        this.render_form_controls();

        if (cfg.has_items) {
            this.add_item_row();
        }
        if (cfg.is_journal) {
            this.add_account_row();
            this.add_account_row();
        }

        // Auto-load tax details if a default template was pre-filled
        if (cfg.has_tax && this.defaults.default_tax_template) {
            this.load_tax_details();
        }
    }

    // ─── Form Controls ──────────────────────────────────────
    render_form_controls() {
        const cfg = this.current_config;
        const $container = this.page.main.find('#td-form-fields');
        const fields = this.get_form_fields();

        $container.html('<div class="td-fields-grid"></div>');
        const $grid = $container.find('.td-fields-grid');

        fields.forEach(f => {
            const $wrapper = $(`<div class="td-field-wrapper ${f.fieldtype === 'Section Break' ? 'td-section-break' : ''}" data-fieldname="${f.fieldname || ''}"></div>`);
            $grid.append($wrapper);

            if (f.fieldtype === 'Section Break') {
                $wrapper.html(`<hr class="mt-3 mb-2"><h6 class="text-muted mb-2">${f.label || ''}</h6>`);
                return;
            }

            // For Link fields outside a form, skip async validation
            // and manually track selected values
            if (f.fieldtype === 'Link') {
                f.ignore_link_validation = 1;
            }

            const control = frappe.ui.form.make_control({
                df: f,
                parent: $wrapper,
                render_input: true,
            });

            if (f.default !== undefined) {
                control.set_value(f.default);
            }

            // For Link controls, manually track selected value
            if (f.fieldtype === 'Link' && control.$input) {
                control._selected_value = f.default || '';
                const orig_get = control.get_value.bind(control);
                control.get_value = function () {
                    return this._selected_value || orig_get() || '';
                };
                control.$input.on('awesomplete-selectcomplete', function () {
                    control._selected_value = control.get_input_value();
                });
                control.$input.on('blur', function () {
                    const val = control.get_input_value();
                    if (val) control._selected_value = val;
                });
            }

            this.form_controls[f.fieldname] = control;

            // Live tax update on template change
            if (f.fieldname === 'tax_template') {
                control.$input && control.$input.on('awesomplete-selectcomplete', () => {
                    this.load_tax_details();
                });
            }

            // Auto-fill Tax Template when Company is selected/changed
            if (f.fieldname === 'company') {
                control.$input && control.$input.on('awesomplete-selectcomplete', () => {
                    setTimeout(async () => {
                        const company = control.get_value();
                        if (!company || !cfg.has_tax) return;

                        try {
                            const tax_template = await frappe.xcall('kniterp.api.transaction_desk.get_default_tax_template', {
                                voucher_type: this.current_type,
                                company: company
                            });

                            if (this.form_controls.tax_template) {
                                this.form_controls.tax_template.set_value(tax_template || '');
                                this.form_controls.tax_template._selected_value = tax_template || '';
                                this.load_tax_details();
                            }
                        } catch (e) {
                            console.error('Company tax template error:', e);
                        }
                    }, 50);
                });
            }

            // Auto-fill Tax Template when Customer/Supplier is selected
            if (f.fieldname === cfg.party_field) {
                control.$input && control.$input.on('awesomplete-selectcomplete', () => {
                    setTimeout(async () => {
                        const party = control.get_value();
                        if (!party || !cfg.has_tax) return;

                        try {
                            const tax_template = await frappe.xcall('kniterp.api.transaction_desk.get_party_tax_template', {
                                voucher_type: this.current_type,
                                party: party,
                                company: this.get_field_value('company') || this.defaults.company
                            });

                            if (tax_template && this.form_controls.tax_template) {
                                this.form_controls.tax_template.set_value(tax_template);
                                this.form_controls.tax_template._selected_value = tax_template;
                                this.load_tax_details();
                            }
                        } catch (e) {
                            console.error('Party tax template error:', e);
                        }
                    }, 50);
                });
            }
        });
    }

    get_form_fields() {
        const cfg = this.current_config;
        const d = this.defaults;
        const fields = [];

        // Common: Company + Date (one row)
        fields.push({
            fieldname: 'company',
            fieldtype: 'Link',
            options: 'Company',
            label: __('Company'),
            default: d.company,
            reqd: 1,
        });

        fields.push({
            fieldname: 'posting_date',
            fieldtype: 'Date',
            label: __('Date'),
            default: d.posting_date,
            reqd: 1,
        });

        // Type-specific fields
        if (cfg.party_field) {
            fields.push({
                fieldname: cfg.party_field,
                fieldtype: 'Link',
                options: cfg.party_doctype,
                label: cfg.party_label,
                reqd: 1,
            });
        }

        if (cfg.date_field) {
            fields.push({
                fieldname: cfg.date_field,
                fieldtype: 'Date',
                label: cfg.date_label,
                default: frappe.datetime.add_days(frappe.datetime.nowdate(), cfg.date_default_days),
            });
        }

        if (cfg.has_items) {
            fields.push({
                fieldname: 'warehouse',
                fieldtype: 'Link',
                options: 'Warehouse',
                label: __('Default Warehouse'),
                default: d.warehouse || '',
            });
        }

        if (cfg.has_tax) {
            const template_doctype = cfg.tax_type === 'sales'
                ? 'Sales Taxes and Charges Template'
                : 'Purchase Taxes and Charges Template';

            fields.push({
                fieldname: 'tax_template',
                fieldtype: 'Link',
                options: template_doctype,
                label: __('Tax Template'),
                default: d.default_tax_template || '',
                get_query: () => ({
                    filters: { company: this.get_field_value('company') || d.company }
                }),
            });
        }

        // Payment-specific
        if (cfg.is_payment) {
            fields.push({
                fieldname: 'amount',
                fieldtype: 'Currency',
                label: __('Amount'),
                reqd: 1,
                options: 'currency',
            });

            fields.push({
                fieldname: 'mode_of_payment',
                fieldtype: 'Link',
                options: 'Mode of Payment',
                label: __('Mode of Payment'),
            });

            fields.push({ fieldtype: 'Section Break', label: __('Reference Details') });

            fields.push({
                fieldname: 'reference_no',
                fieldtype: 'Data',
                label: __('Reference No (Cheque/UTR)'),
            });

            fields.push({
                fieldname: 'reference_date',
                fieldtype: 'Date',
                label: __('Reference Date'),
            });
        }

        // Journal Entry-specific
        if (cfg.is_journal) {
            fields.push({
                fieldname: 'entry_type',
                fieldtype: 'Select',
                label: __('Entry Type'),
                options: 'Journal Entry\nContra Entry\nBank Entry\nCash Entry',
                default: 'Journal Entry',
            });

            fields.push({
                fieldname: 'cheque_no',
                fieldtype: 'Data',
                label: __('Reference No'),
            });

            fields.push({
                fieldname: 'cheque_date',
                fieldtype: 'Date',
                label: __('Reference Date'),
            });

            fields.push({
                fieldname: 'user_remark',
                fieldtype: 'Small Text',
                label: __('Remark'),
            });
        }

        return fields;
    }

    get_field_value(fieldname) {
        const ctrl = this.form_controls[fieldname];
        return ctrl ? ctrl.get_value() : null;
    }

    // ─── Item Table ─────────────────────────────────────────
    render_item_table_html() {
        return `
            <div class="td-item-table mt-4">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <h6 class="mb-0"><i class="fa fa-list mr-1"></i>${__('Items')}</h6>
                    <button class="btn btn-xs btn-primary btn-add-item">
                        <i class="fa fa-plus mr-1"></i>${__('Add Row')}
                    </button>
                </div>
                <table class="table table-bordered td-items-table">
                    <thead>
                        <tr>
                            <th style="width: 4%">#</th>
                            <th style="width: 30%">${__('Item')}</th>
                            <th style="width: 10%">${__('Qty')}</th>
                            <th style="width: 12%">${__('UOM')}</th>
                            <th style="width: 14%">${__('Rate')}</th>
                            <th style="width: 18%">${__('Amount')}</th>
                            <th style="width: 12%"></th>
                        </tr>
                    </thead>
                    <tbody id="td-item-rows"></tbody>
                    <tfoot>
                        <tr class="td-items-total-row">
                            <td colspan="5" class="text-right font-weight-bold">${__('Net Total')}</td>
                            <td class="font-weight-bold" id="td-net-total">0.00</td>
                            <td></td>
                        </tr>
                    </tfoot>
                </table>
            </div>
        `;
    }

    add_item_row(data = {}) {
        const self = this;
        const idx = this.item_rows.length;
        const row_id = `item-row-${idx}`;

        // Row data object (declared early for closures and to hold all controls)
        const row_data = {
            id: row_id, idx,
            $row: null, $detail_row: null, // Will be assigned after creation
            item_ctrl: null, qty_ctrl: null, uom_ctrl: null, rate_ctrl: null, desc_ctrl: null, // Will be assigned after creation
            item_name: '',
            description: '',
            uom: data.uom || '',
            transaction_params: data.transaction_params || [],
        };

        const $tbody = this.page.main.find('#td-item-rows');

        // ── Main row ──
        const $row = $(`
            <tr data-row-id="${row_id}" data-idx="${idx}">
                <td class="text-center align-middle">${idx + 1}</td>
                <td class="td-cell-item">
                    <div class="td-item-name-stack">
                        <div class="td-item-link-wrap"></div>
                        <div class="td-item-name-sub"></div>
                    </div>
                </td>
                <td class="td-cell-qty"></td>
                <td class="td-cell-uom"></td>
                <td class="td-cell-rate"></td>
                <td class="td-cell-amount text-right align-middle">
                    <div class="td-amount-value">0.00</div>
                    <div class="td-item-tax-info text-muted small"></div>
                </td>
                <td class="text-center align-middle" style="white-space:nowrap;">
                    <button class="td-btn-expand" title="${__('Details')}">
                        <i class="fa fa-chevron-down"></i>
                    </button>
                    <button class="btn btn-xs btn-link text-danger btn-remove-item" data-idx="${idx}">
                        <i class="fa fa-times"></i>
                    </button>
                </td>
            </tr>
        `);
        row_data.$row = $row;

        // ── Detail row (expandable, hidden by default) ──
        const $detail_row = $(`
            <tr class="td-detail-row" data-detail-for="${row_id}">
                <td colspan="7">
                    <div class="td-detail-panel">
                        <div class="td-item-description-wrap"></div>
                        <div class="td-params-section">
                            <span class="td-params-label"><i class="fa fa-sliders"></i> ${__('Parameters')}:</span>
                            <span class="td-params-badges"></span>
                            <button class="td-btn-add-param">
                                <i class="fa fa-plus"></i> ${__('Add')}
                            </button>
                        </div>
                    </div>
                </td>
            </tr>
        `);

        $tbody.append($row);
        $tbody.append($detail_row);
        row_data.$detail_row = $detail_row;

        // Start hidden
        $detail_row.hide();

        // ── Description control (editable, inside detail panel) ──
        const desc_ctrl = frappe.ui.form.make_control({
            df: {
                fieldname: `desc_${idx}`,
                fieldtype: 'Small Text',
                label: __('Description'),
                placeholder: __('Item description...'),
            },
            parent: $detail_row.find('.td-item-description-wrap'),
            render_input: true,
        });
        row_data.desc_ctrl = desc_ctrl;

        // ── Item Link control (with smart/convoluted search) ──
        const item_ctrl = frappe.ui.form.make_control({
            df: {
                fieldname: `item_${idx}`,
                fieldtype: 'Link',
                options: 'Item',
                placeholder: __('Type to search item...'),
                ignore_link_validation: 1,
            },
            parent: $row.find('.td-item-link-wrap'),
            only_input: true,
            render_input: true,
        });
        row_data.item_ctrl = item_ctrl;

        // Wire up the convoluted/smart item search
        item_ctrl.get_query = () => ({
            query: 'kniterp.api.item_search.smart_search',
        });

        item_ctrl._selected_value = '';
        const orig_get_value = item_ctrl.get_value.bind(item_ctrl);
        item_ctrl.get_value = function () {
            return this._selected_value || orig_get_value() || '';
        };

        // On item selection: fetch details via dedicated API
        item_ctrl.$input.on('awesomplete-selectcomplete', async function () {
            const selected = item_ctrl.get_input_value();
            item_ctrl._selected_value = selected;

            if (selected) {
                try {
                    const details = await frappe.xcall(
                        'kniterp.api.transaction_desk.get_item_details',
                        { item_code: selected }
                    );
                    if (details) {
                        // Item name subtitle
                        row_data.item_name = details.item_name || '';
                        $row.find('.td-item-name-sub').text(details.item_name || '');

                        // Description (editable)
                        const desc_text = (details.description || '').replace(/<[^>]*>/g, '').trim();
                        row_data.description = desc_text;
                        desc_ctrl.set_value(desc_text);

                        // UOM
                        if (details.stock_uom) {
                            uom_ctrl.set_value(details.stock_uom);
                            uom_ctrl._selected_value = details.stock_uom;
                            row_data.uom = details.stock_uom;
                        }

                        // Price
                        if (details.price_list_rate) {
                            rate_ctrl.set_value(details.price_list_rate);
                        }
                    }
                    // Update the amount AFTER the rate has been fetched and set
                    self.update_row_amount(row_data);
                } catch (e) {
                    // silently ignore
                }
            }
        });

        item_ctrl.$input.on('blur', function () {
            const val = item_ctrl.get_input_value();
            if (val) item_ctrl._selected_value = val;
        });

        // ── Qty control ──
        const qty_ctrl = frappe.ui.form.make_control({
            df: {
                fieldname: `qty_${idx}`,
                fieldtype: 'Float',
                default: data.qty || 1,
                placeholder: '1',
            },
            parent: $row.find('.td-cell-qty'),
            only_input: true,
            render_input: true,
        });
        qty_ctrl.set_value(data.qty || 1);
        row_data.qty_ctrl = qty_ctrl;

        if (qty_ctrl.$input) {
            qty_ctrl.$input.on('change input', () => {
                setTimeout(() => self.update_row_amount(row_data), 50);
            });
        }

        // ── UOM control ──
        const uom_ctrl = frappe.ui.form.make_control({
            df: {
                fieldname: `uom_${idx}`,
                fieldtype: 'Link',
                options: 'UOM',
                placeholder: __('UOM'),
                ignore_link_validation: 1,
            },
            parent: $row.find('.td-cell-uom'),
            only_input: true,
            render_input: true,
        });
        uom_ctrl._selected_value = data.uom || '';
        row_data.uom_ctrl = uom_ctrl;

        const orig_uom_get = uom_ctrl.get_value.bind(uom_ctrl);
        uom_ctrl.get_value = function () {
            return this._selected_value || orig_uom_get() || '';
        };
        uom_ctrl.$input.on('awesomplete-selectcomplete', function () {
            uom_ctrl._selected_value = uom_ctrl.get_input_value();
        });
        uom_ctrl.$input.on('blur', function () {
            const val = uom_ctrl.get_input_value();
            if (val) uom_ctrl._selected_value = val;
        });
        if (data.uom) uom_ctrl.set_value(data.uom);

        // ── Rate control ──
        const rate_ctrl = frappe.ui.form.make_control({
            df: {
                fieldname: `rate_${idx}`,
                fieldtype: 'Currency',
                default: data.rate || 0,
                placeholder: '0.00',
            },
            parent: $row.find('.td-cell-rate'),
            only_input: true,
            render_input: true,
        });
        rate_ctrl.set_value(data.rate || 0);
        row_data.rate_ctrl = rate_ctrl;

        if (rate_ctrl.$input) {
            rate_ctrl.$input.on('change input', () => {
                setTimeout(() => self.update_row_amount(row_data), 50);
            });
        }

        // Initial registration
        this.item_rows.push(row_data);

        // ── Expand/collapse toggle ──
        const $expand_btn = $row.find('.td-btn-expand');
        $expand_btn.on('click', (e) => {
            e.stopPropagation();
            $detail_row.slideToggle(200);
            $expand_btn.toggleClass('expanded');
        });

        // ── Parameter badge click → expand panel ──
        $row.find('.td-param-count-badge').on('click', () => {
            $expand_btn.trigger('click');
        });

        // ── Add Parameter button ──
        $detail_row.find('.td-btn-add-param').on('click', () => {
            self.open_param_dialog(row_data);
        });

        // ── Render existing param badges ──
        this.render_row_param_badges(row_data);

        // Remove row button
        $row.find('.btn-remove-item').on('click', () => {
            this.remove_item_row(idx);
        });

        // Bind add-row button (once)
        if (idx === 0) {
            this.page.main.find('.btn-add-item').off('click').on('click', () => {
                this.add_item_row();
            });
        }

        // Focus the new item control
        setTimeout(() => item_ctrl.$input && item_ctrl.$input.focus(), 100);
    }

    remove_item_row(idx) {
        if (this.item_rows.length <= 1) {
            frappe.show_alert({ message: __('At least one item row is required'), indicator: 'orange' });
            return;
        }
        const row = this.item_rows[idx];
        if (row) {
            row.$row.remove();
            row.$detail_row.remove();
            this.item_rows[idx] = null;
            this.reindex_items();
            this.update_totals();
        }
    }

    reindex_items() {
        this.item_rows = this.item_rows.filter(r => r !== null);
        this.item_rows.forEach((row, i) => {
            row.idx = i;
            row.$row.find('td:first').text(i + 1);
        });
    }

    _get_raw_value(ctrl) {
        if (!ctrl || !ctrl.$input) return 0;

        try {
            const raw = ctrl.$input.val();
            if (raw === '' || raw === undefined || raw === null) return 0;

            // Clean up common intermediate typing artifacts
            const clean = raw.replace(/[^\d.-]/g, '');
            const parsed = parseFloat(clean);
            return isNaN(parsed) ? 0 : parsed;
        } catch (e) {
            return 0;
        }
    }

    update_row_amount(row_data) {
        if (!row_data || !row_data.qty_ctrl || !row_data.rate_ctrl) return;

        const qty = this._get_raw_value(row_data.qty_ctrl);
        const rate = this._get_raw_value(row_data.rate_ctrl);
        const amount = qty * rate;

        // Direct DOM update via the row ID to be absolutely sure
        this.page.main.find(`tr[data-row-id="${row_data.id}"] .td-amount-value`)
            .text(format_currency(amount, this.defaults.currency));

        this.update_totals();
    }

    // ─── Transaction Parameters Helpers ──────────────────────
    render_row_param_badges(row_data) {
        const params = row_data.transaction_params || [];
        const $badges = row_data.$detail_row.find('.td-params-badges');
        const $name_sub = row_data.$row.find('.td-item-name-sub');

        // Remove old count badge
        $name_sub.find('.td-param-count-badge').remove();

        if (!params.length) {
            $badges.html('');
            return;
        }

        // Teal badges in detail panel
        const badge_html = params.map(p =>
            `<span class="td-param-badge">
                <span class="td-param-key">${frappe.utils.escape_html(p.parameter)}:</span>
                <span class="td-param-val">${frappe.utils.escape_html(p.value)}</span>
            </span>`
        ).join('');
        $badges.html(badge_html);

        // Small count badge next to item name
        $name_sub.append(
            `<span class="td-param-count-badge" title="${__('Click to view parameters')}">${params.length} ${params.length === 1 ? 'param' : 'params'}</span>`
        );
    }

    open_param_dialog(row_data) {
        const self = this;
        const current_params = row_data.transaction_params || [];
        const item_name = row_data.item_name || row_data.item_ctrl.get_value() || '';

        const dialog = new frappe.ui.Dialog({
            title: __('Transaction Parameters') + (item_name ? ` — ${item_name}` : ''),
            size: 'large',
            fields: [
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

                row_data.transaction_params = new_params;
                self.render_row_param_badges(row_data);

                frappe.show_alert({
                    message: __('Parameters updated'),
                    indicator: 'blue'
                });
                dialog.hide();
            }
        });
        dialog.show();
    }

    // ─── Accounts Table (Journal Entry) ─────────────────────
    render_accounts_table_html() {
        return `
            <div class="td-accounts-table mt-4">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <h6 class="mb-0"><i class="fa fa-list-alt mr-1"></i>${__('Accounts')}</h6>
                    <button class="btn btn-xs btn-primary btn-add-account">
                        <i class="fa fa-plus mr-1"></i>${__('Add Row')}
                    </button>
                </div>
                <table class="table table-bordered td-accounts-tbl">
                    <thead>
                        <tr>
                            <th style="width: 5%">#</th>
                            <th style="width: 45%">${__('Account')}</th>
                            <th style="width: 20%">${__('Debit')}</th>
                            <th style="width: 20%">${__('Credit')}</th>
                            <th style="width: 10%"></th>
                        </tr>
                    </thead>
                    <tbody id="td-account-rows"></tbody>
                    <tfoot>
                        <tr class="td-account-total-row">
                            <td colspan="2" class="text-right font-weight-bold">${__('Total')}</td>
                            <td class="font-weight-bold" id="td-total-debit">0.00</td>
                            <td class="font-weight-bold" id="td-total-credit">0.00</td>
                            <td></td>
                        </tr>
                        <tr id="td-difference-row" class="d-none">
                            <td colspan="2" class="text-right text-danger font-weight-bold">${__('Difference')}</td>
                            <td colspan="2" class="text-danger font-weight-bold" id="td-difference-amount">0.00</td>
                            <td></td>
                        </tr>
                    </tfoot>
                </table>
            </div>
        `;
    }

    add_account_row(data = {}) {
        const idx = this.account_rows.length;
        const $tbody = this.page.main.find('#td-account-rows');

        const $row = $(`
            <tr data-aidx="${idx}">
                <td class="text-center align-middle">${idx + 1}</td>
                <td class="td-cell-account"></td>
                <td class="td-cell-debit"></td>
                <td class="td-cell-credit"></td>
                <td class="text-center align-middle">
                    <button class="btn btn-xs btn-link text-danger btn-remove-account" data-aidx="${idx}">
                        <i class="fa fa-times"></i>
                    </button>
                </td>
            </tr>
        `);

        $tbody.append($row);

        const self = this;

        const account_ctrl = frappe.ui.form.make_control({
            df: {
                fieldname: `account_${idx}`,
                fieldtype: 'Link',
                options: 'Account',
                placeholder: __('Select Account'),
                ignore_link_validation: 1,
                get_query: () => ({
                    filters: { company: self.get_field_value('company') || self.defaults.company, is_group: 0 }
                }),
            },
            parent: $row.find('.td-cell-account'),
            only_input: true,
            render_input: true,
        });

        // Manually track account value
        account_ctrl._selected_value = '';
        const orig_acct_get = account_ctrl.get_value.bind(account_ctrl);
        account_ctrl.get_value = function () {
            return this._selected_value || orig_acct_get() || '';
        };
        account_ctrl.$input.on('awesomplete-selectcomplete', function () {
            account_ctrl._selected_value = account_ctrl.get_input_value();
        });
        account_ctrl.$input.on('blur', function () {
            const val = account_ctrl.get_input_value();
            if (val) account_ctrl._selected_value = val;
        });

        const debit_ctrl = frappe.ui.form.make_control({
            df: {
                fieldname: `debit_${idx}`,
                fieldtype: 'Currency',
                placeholder: '0.00',
                change: () => self.update_totals(),
            },
            parent: $row.find('.td-cell-debit'),
            only_input: true,
            render_input: true,
        });
        debit_ctrl.set_value(data.debit || 0);

        const credit_ctrl = frappe.ui.form.make_control({
            df: {
                fieldname: `credit_${idx}`,
                fieldtype: 'Currency',
                placeholder: '0.00',
                change: () => self.update_totals(),
            },
            parent: $row.find('.td-cell-credit'),
            only_input: true,
            render_input: true,
        });
        credit_ctrl.set_value(data.credit || 0);

        const row_data = { idx, $row, account_ctrl, debit_ctrl, credit_ctrl };
        this.account_rows.push(row_data);

        $row.find('.btn-remove-account').on('click', () => {
            if (this.account_rows.length <= 2) {
                frappe.show_alert({ message: __('At least two account rows are required'), indicator: 'orange' });
                return;
            }
            this.account_rows[idx] = null;
            $row.remove();
            this.account_rows = this.account_rows.filter(r => r !== null);
            this.account_rows.forEach((r, i) => {
                r.idx = i;
                r.$row.find('td:first').text(i + 1);
            });
            this.update_totals();
        });

        // Bind add-account button (once)
        if (idx === 0) {
            this.page.main.find('.btn-add-account').off('click').on('click', () => {
                this.add_account_row();
            });
        }

        setTimeout(() => account_ctrl.$input && account_ctrl.$input.focus(), 100);
    }

    // ─── Tax Details ────────────────────────────────────────
    async load_tax_details() {
        let template = this.get_field_value('tax_template');
        const $section = this.page.main.find('#td-tax-section');

        // Fallback: read directly from the input if get_value returned empty
        if (!template && this.form_controls.tax_template) {
            template = this.form_controls.tax_template._selected_value
                || (this.form_controls.tax_template.$input && this.form_controls.tax_template.$input.val())
                || '';
        }

        if (!template) {
            $section.html('');
            this.tax_rows = [];
            this.update_totals();
            return;
        }

        $section.html(`<div class="text-muted small p-2"><i class="fa fa-spinner fa-spin"></i> ${__('Loading tax details...')}</div>`);

        try {
            const rows = await frappe.xcall('kniterp.api.transaction_desk.get_tax_details', {
                voucher_type: this.current_type,
                template_name: template,
            });
            this.tax_rows = rows || [];
            this.render_tax_details(rows);
            this.update_totals();
        } catch (e) {
            console.error('load_tax_details error:', e, 'template:', template);
            $section.html(`<div class="text-danger small p-2">${__('Failed to load tax details')}: ${e.message || e}</div>`);
        }
    }

    render_tax_details(rows) {
        const $section = this.page.main.find('#td-tax-section');
        if (!rows || !rows.length) {
            $section.html('');
            return;
        }

        let html = `
            <h6 class="text-muted mb-2"><i class="fa fa-percent mr-1"></i>${__('Taxes & Charges')}</h6>
            <table class="table table-sm table-bordered td-tax-table">
                <thead>
                    <tr>
                        <th>${__('Type')}</th>
                        <th>${__('Account')}</th>
                        <th>${__('Rate')}</th>
                        <th>${__('Amount')}</th>
                    </tr>
                </thead>
                <tbody>
        `;

        rows.forEach((row, i) => {
            html += `
                <tr>
                    <td>${frappe.utils.escape_html(row.charge_type || '')}</td>
                    <td>${frappe.utils.escape_html(row.account_head || '')}</td>
                    <td class="text-right">${row.rate ? row.rate + '%' : '-'}</td>
                    <td class="text-right td-tax-amount"
                        data-rate="${row.rate || 0}"
                        data-charge-type="${row.charge_type || ''}"
                        data-row-id="${row.row_id || 0}"
                        data-tax-amount="${row.tax_amount || 0}"
                        data-tax-idx="${i}"
                    >0.00</td>
                </tr>
            `;
        });

        html += `</tbody></table>`;
        $section.html(html);
    }

    // ─── Totals ─────────────────────────────────────────────
    update_totals() {
        const cfg = this.current_config;
        if (!cfg) return;

        const $bar = this.page.main.find('#td-totals-bar');

        if (cfg.has_items) {
            let net_total = 0;
            this.item_rows.forEach(row => {
                if (!row) return;
                const qty = this._get_raw_value(row.qty_ctrl);
                const rate = this._get_raw_value(row.rate_ctrl);
                net_total += qty * rate;
            });

            this.page.main.find('#td-net-total').text(format_currency(net_total, this.defaults.currency));

            // Calculate tax — ERPNext-accurate per charge_type logic
            let tax_total = 0;
            const tax_amounts = [];    // tax_amount per row
            const tax_totals = [];     // cumulative total per row (net_total + sum of taxes up to this row)

            if (this.tax_rows && this.tax_rows.length) {
                const $tax_cells = this.page.main.find('.td-tax-amount');
                $tax_cells.each((i, el) => {
                    const $el = $(el);
                    const rate = flt($el.data('rate'));
                    const charge_type = String($el.data('charge-type'));
                    const row_id = parseInt($el.data('row-id')) || 0;
                    const actual_amount = flt($el.data('tax-amount'));
                    let current_tax = 0;

                    if (charge_type === 'On Net Total') {
                        current_tax = net_total * rate / 100;
                    } else if (charge_type === 'On Previous Row Amount') {
                        // row_id is 1-based idx; tax_amounts is 0-based
                        const ref_idx = row_id - 1;
                        const prev_amount = (ref_idx >= 0 && ref_idx < tax_amounts.length)
                            ? tax_amounts[ref_idx] : 0;
                        current_tax = prev_amount * rate / 100;
                    } else if (charge_type === 'On Previous Row Total') {
                        const ref_idx = row_id - 1;
                        const prev_total = (ref_idx >= 0 && ref_idx < tax_totals.length)
                            ? tax_totals[ref_idx] : net_total;
                        current_tax = prev_total * rate / 100;
                    } else if (charge_type === 'On Item Quantity') {
                        // rate × total qty across all items
                        let total_qty = 0;
                        this.item_rows.forEach(r => {
                            if (r) total_qty += this._get_raw_value(r.qty_ctrl);
                        });
                        current_tax = rate * total_qty;
                    } else if (charge_type === 'Actual') {
                        current_tax = actual_amount;
                    }

                    current_tax = flt(current_tax, 2);
                    tax_amounts.push(current_tax);
                    // cumulative total = net_total + all taxes up to and including this row
                    tax_totals.push(net_total + tax_total + current_tax);
                    tax_total += current_tax;

                    $el.text(format_currency(current_tax, this.defaults.currency));
                });
            }

            // ── Item-wise tax distribution ──
            if (net_total > 0 && tax_total > 0) {
                this.item_rows.forEach(r => {
                    if (!r) return;
                    const item_amount = this._get_raw_value(r.qty_ctrl) * this._get_raw_value(r.rate_ctrl);
                    const item_tax = flt(item_amount / net_total * tax_total, 2);
                    r.$row.find('.td-item-tax-info')
                        .html(`<span class="text-muted" style="font-size:11px;">+ ${format_currency(item_tax, this.defaults.currency)} tax</span>`);
                });
            } else {
                this.item_rows.forEach(r => {
                    if (!r) return;
                    r.$row.find('.td-item-tax-info').html('');
                });
            }

            const grand_total = net_total + tax_total;

            $bar.html(`
                <div class="td-totals-card">
                    <div class="td-total-row">
                        <span>${__('Net Total')}</span>
                        <span class="font-weight-bold">${format_currency(net_total, this.defaults.currency)}</span>
                    </div>
                    ${tax_total ? `
                    <div class="td-total-row">
                        <span>${__('Tax')}</span>
                        <span>${format_currency(tax_total, this.defaults.currency)}</span>
                    </div>` : ''}
                    <div class="td-total-row td-grand-total">
                        <span>${__('Grand Total')}</span>
                        <span>${format_currency(grand_total, this.defaults.currency)}</span>
                    </div>
                </div>
            `);
        } else if (cfg.is_journal) {
            let total_debit = 0, total_credit = 0;
            this.account_rows.forEach(row => {
                if (!row) return;
                total_debit += flt(row.debit_ctrl.get_value());
                total_credit += flt(row.credit_ctrl.get_value());
            });

            this.page.main.find('#td-total-debit').text(format_currency(total_debit, this.defaults.currency));
            this.page.main.find('#td-total-credit').text(format_currency(total_credit, this.defaults.currency));

            const diff = Math.abs(total_debit - total_credit);
            const $diff_row = this.page.main.find('#td-difference-row');
            if (diff > 0.01) {
                $diff_row.removeClass('d-none');
                this.page.main.find('#td-difference-amount').text(format_currency(diff, this.defaults.currency));
            } else {
                $diff_row.addClass('d-none');
            }

            $bar.html('');  // JV shows totals in table footer
        } else if (cfg.is_payment) {
            // Payment shows amount directly
            $bar.html('');
        }
    }

    // ─── Recent Entries ─────────────────────────────────────
    async load_recent_entries() {
        const $panel = this.page.main.find('.td-recent-list');
        $panel.html(`<div class="text-muted small"><i class="fa fa-spinner fa-spin"></i></div>`);

        try {
            const entries = await frappe.xcall('kniterp.api.transaction_desk.get_recent_transactions', {
                voucher_type: this.current_type,
                limit: 10,
            });

            if (!entries || !entries.length) {
                $panel.html(`<p class="text-muted small">${__('No recent entries')}</p>`);
                return;
            }

            const cfg = this.current_config;
            let html = '';
            entries.forEach(e => {
                const status_class = e.docstatus === 1 ? 'text-success' : 'text-warning';
                const status_label = e.docstatus === 1 ? __('Submitted') : __('Draft');
                const display = e.customer_name || e.supplier_name || e.party_name || '';
                const amount = e.grand_total || e.paid_amount || e.total_debit || 0;

                html += `
                    <a href="/app/${frappe.router.slug(cfg.doctype)}/${e.name}" class="td-recent-entry" target="_blank">
                        <div class="d-flex justify-content-between">
                            <span class="small font-weight-bold">${e.name}</span>
                            <span class="small ${status_class}">${status_label}</span>
                        </div>
                        <div class="small text-muted">${display}</div>
                        <div class="small">${format_currency(amount, this.defaults.currency)}</div>
                    </a>
                `;
            });
            $panel.html(html);
        } catch (e) {
            $panel.html(`<p class="text-muted small">${__('Could not load recent entries')}</p>`);
        }
    }

    // ─── Submit Flow ────────────────────────────────────────
    validate_form() {
        const cfg = this.current_config;
        const errors = [];

        // Check required fields
        for (const [name, ctrl] of Object.entries(this.form_controls)) {
            if (ctrl.df && ctrl.df.reqd && !ctrl.get_value()) {
                errors.push(__('"{0}" is required', [ctrl.df.label || name]));
            }
        }

        // Items validation
        if (cfg.has_items) {
            const valid_items = this.item_rows.filter(r => r && r.item_ctrl.get_value());
            if (!valid_items.length) {
                errors.push(__('At least one item is required'));
            }
        }

        // Accounts validation
        if (cfg.is_journal) {
            const valid_accounts = this.account_rows.filter(r => r && r.account_ctrl.get_value());
            if (valid_accounts.length < 2) {
                errors.push(__('At least two account rows are required'));
            }

            // Check debit = credit
            let total_debit = 0, total_credit = 0;
            this.account_rows.forEach(row => {
                if (!row) return;
                total_debit += flt(row.debit_ctrl.get_value());
                total_credit += flt(row.credit_ctrl.get_value());
            });
            if (Math.abs(total_debit - total_credit) > 0.01) {
                errors.push(__('Total Debit must equal Total Credit (difference: {0})', [
                    format_currency(Math.abs(total_debit - total_credit), this.defaults.currency)
                ]));
            }
        }

        return errors;
    }

    submit_form() {
        const errors = this.validate_form();
        if (errors.length) {
            frappe.msgprint({
                title: __('Validation Error'),
                message: errors.map(e => `• ${e}`).join('<br>'),
                indicator: 'orange',
            });
            return;
        }

        // Ask: Submit or Draft?
        const d = new frappe.ui.Dialog({
            title: __('Create {0}', [this.current_config.label]),
            fields: [
                {
                    fieldtype: 'HTML',
                    options: `<p class="text-muted">${__('How would you like to save this transaction?')}</p>`,
                },
            ],
            primary_action_label: __('Submit'),
            primary_action: () => {
                d.hide();
                this.do_create(true);
            },
            secondary_action_label: __('Save as Draft'),
            secondary_action: () => {
                d.hide();
                this.do_create(false);
            },
        });
        d.show();
    }

    async do_create(submit) {
        const cfg = this.current_config;
        const data = this.collect_form_data();

        this.page.main.find('.td-form-body, .td-item-table, .td-accounts-table').css('opacity', '0.5');
        this.page.btn_primary.prop('disabled', true);

        try {
            const result = await frappe.xcall('kniterp.api.transaction_desk.create_transaction', {
                voucher_type: this.current_type,
                data: data,
                submit: submit,
            });

            this.show_success(result, submit);
        } catch (e) {
            frappe.msgprint({
                title: __('Error'),
                message: e.message || __('Failed to create transaction'),
                indicator: 'red',
            });
            this.page.main.find('.td-form-body, .td-item-table, .td-accounts-table').css('opacity', '1');
            this.page.btn_primary.prop('disabled', false);
        }
    }

    collect_form_data() {
        const cfg = this.current_config;
        const data = {};

        // Collect all form control values
        for (const [name, ctrl] of Object.entries(this.form_controls)) {
            data[name] = ctrl.get_value();
        }

        // Collect items
        if (cfg.has_items) {
            data.items = [];
            this.item_rows.forEach(row => {
                if (!row) return;
                const item_code = row.item_ctrl.get_value();
                if (!item_code) return;
                data.items.push({
                    item_code: item_code,
                    qty: flt(row.qty_ctrl.get_value()) || 1,
                    rate: flt(row.rate_ctrl.get_value()),
                    uom: row.uom_ctrl ? row.uom_ctrl.get_value() : '',
                    description: row.desc_ctrl ? row.desc_ctrl.get_value() : '',
                    warehouse: data.warehouse || '',
                    transaction_params: row.transaction_params || [],
                });
            });
        }

        // Collect accounts
        if (cfg.is_journal) {
            data.accounts = [];
            this.account_rows.forEach(row => {
                if (!row) return;
                const account = row.account_ctrl.get_value();
                if (!account) return;
                data.accounts.push({
                    account: account,
                    debit: flt(row.debit_ctrl.get_value()),
                    credit: flt(row.credit_ctrl.get_value()),
                });
            });
        }

        return data;
    }

    show_success(result, was_submitted) {
        const cfg = this.current_config;
        const status = was_submitted ? __('Submitted') : __('Draft');
        const status_class = was_submitted ? 'success' : 'warning';
        const amount = result.grand_total || result.paid_amount || result.total_debit || 0;
        const doc_route = `/app/${frappe.router.slug(cfg.doctype)}/${result.name}`;

        this.page.main.html(`
            <div class="td-container">
                <div class="td-success-card text-center">
                    <div class="td-success-icon">
                        <i class="fa fa-check-circle fa-4x text-${status_class}"></i>
                    </div>
                    <h3 class="mt-3 mb-2">${cfg.label} ${__('Created!')}</h3>
                    <div class="mb-3">
                        <a href="${doc_route}" class="h5" target="_blank">${result.name}</a>
                        <span class="badge badge-${status_class} ml-2">${status}</span>
                    </div>
                    ${amount ? `<div class="mb-3 h4">${format_currency(amount, this.defaults.currency)}</div>` : ''}
                    <div class="mt-4">
                        <button class="btn btn-primary btn-lg mr-2 btn-create-another">
                            <i class="fa fa-plus mr-1"></i>${__('Create Another {0}', [cfg.label])}
                        </button>
                        <a href="${doc_route}" class="btn btn-default btn-lg" target="_blank">
                            <i class="fa fa-external-link mr-1"></i>${__('Open in Full Form')}
                        </a>
                        <button class="btn btn-default btn-lg ml-2 btn-back-to-types">
                            <i class="fa fa-th mr-1"></i>${__('Back to Types')}
                        </button>
                    </div>
                </div>
            </div>
        `);

        this.page.main.find('.btn-create-another').on('click', () => this.init_form(this.current_type));
        this.page.main.find('.btn-back-to-types').on('click', () => this.render_type_selector());
    }

    // ─── Keyboard Shortcuts ─────────────────────────────────
    setup_keyboard_shortcuts() {
        // Remove old handlers
        $(document).off('keydown.transaction_desk');

        $(document).on('keydown.transaction_desk', (e) => {
            // Alt+Enter → Submit
            if (e.altKey && e.key === 'Enter') {
                e.preventDefault();
                this.submit_form();
            }
            // Escape → back to type selector
            if (e.key === 'Escape' && !$('.modal.show').length) {
                e.preventDefault();
                this.render_type_selector();
            }
        });
    }
}
