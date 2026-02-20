frappe.pages['bom_designer'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'BOM Designer',
        single_column: true
    });

    class BomDesigner {
        constructor(wrapper, page) {
            this.wrapper = $(wrapper);
            this.page = page;
            this.body = this.page.main;
            this.PRECISION = 3;
            this.operations = [];

            // Check for params
            const url_params = new URLSearchParams(window.location.search);
            this.initial_item = (frappe.route_options && frappe.route_options.item_code) || url_params.get('item_code');
            this.bom_no = (frappe.route_options && frappe.route_options.bom_no) || url_params.get('bom_no');
            this.sales_order_item = (frappe.route_options && frappe.route_options.sales_order_item) || url_params.get('sales_order_item');
            this.return_to = (frappe.route_options && frappe.route_options.return_to) || url_params.get('return_to');

            // Clear route options so they don't persist on refresh unintentionally
            frappe.route_options = null;

            this.setup_ui();

            if (this.bom_no) {
                this.load_existing_bom(this.bom_no);
            }
        }

        load_existing_bom(bom_no) {
            frappe.call({
                method: 'kniterp.api.bom_tool.get_multilevel_bom',
                args: { bom_no: bom_no },
                freeze: true,
                callback: (r) => {
                    if (r.message) {
                        this.populate_from_data(r.message);
                    }
                }
            });
        }

        check_and_load_bom(item_code) {
            if (this.bom_no) return;
            if (this.is_populating) return;
            if (this.operations.length > 0) return;
            if (this.last_checked_item === item_code) return;
            if (this.bom_prompt_shown) return;

            this.last_checked_item = item_code;
            this.bom_prompt_shown = true;

            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'BOM',
                    filters: {
                        item: item_code,
                        is_active: 1,
                        is_default: 1,
                        docstatus: 1
                    },
                    fields: ['name'],
                    limit: 1
                },
                callback: (r) => {
                    if (r.message && r.message.length > 0) {
                        let bom_name = r.message[0].name;
                        frappe.confirm(
                            `A default BOM (${bom_name}) exists for this item. Would you like to load it?`,
                            () => {
                                this.load_existing_bom(bom_name);
                            },
                            () => {
                                this.bom_prompt_shown = false;
                            }
                        );
                    } else {
                        this.bom_prompt_shown = false;
                    }
                }
            });
        }

        populate_from_data(data) {
            this.is_populating = true;

            // Set Final Good
            if (this.fg_item_select) {
                this.fg_item_select.set_value(data.final_good);
            }
            this.page.main.find('.final-qty').val(data.final_qty);

            // Set rm_cost_as_per
            if (data.rm_cost_as_per && this.rm_cost_select) {
                this.rm_cost_select.set_value(data.rm_cost_as_per);
            }

            // Clear existing ops
            this.operations = [];
            this.page.main.find('.workflow-stack').empty();

            // Add operations
            for (let op of data.operations) {
                let type = op.type;
                this.add_operation(type);

                let current_op = this.operations.find(o => o.type === type);
                if (!current_op) continue;

                let $card = current_op.$el;

                // Set Loss
                $card.find('.input-loss').val(op.loss_percent);

                // Set Job Work
                $card.find('.chk-job-work').prop('checked', op.is_job_work);

                // Set Job Work Direction (for knitting)
                if (type === 'knitting' && op.is_job_work && op.job_work_direction) {
                    setTimeout(() => {
                        $card.find('.jw-direction-section').show();
                        $card.find(`.jw-direction-radio[value="${op.job_work_direction}"]`)
                            .prop('checked', true).trigger('change');
                    }, 150);
                }

                // Set Output Item (SFG)
                if (op.output_item && type !== 'dyeing') {
                    setTimeout(() => {
                        let sfg_ctrl = $card.data('sfg_control');
                        if (sfg_ctrl) {
                            sfg_ctrl.set_value(op.output_item);
                        }
                    }, 200);
                }

                // Inputs
                let $inputs_list = $card.find('.inputs-list');
                $inputs_list.empty();

                for (let inp of op.inputs) {
                    this.add_input_row($card);
                    let $row = $inputs_list.find('.input-row-mini').last();

                    setTimeout(() => {
                        let ctrl = $row.data('control');
                        // For CP items in inward job work, use the base item for display
                        let display_item = inp.base_item || inp.item;
                        if (ctrl) ctrl.set_value(display_item);
                        $row.find('.input-mix').val(inp.mix);

                        // Set checkbox states
                        if (inp.sourced_by_supplier) {
                            $row.find('.chk-sourced-by-supplier').prop('checked', true);
                        }
                        if (inp.customer_provided) {
                            $row.find('.chk-customer-provided').prop('checked', true);
                        }
                    }, 300);
                }
            }

            setTimeout(() => {
                this.update_sfg_visibility();
                this.update_all_jw_sections();
                this.calculate_quantities();
                this.is_populating = false;
            }, 500);
        }

        setup_ui() {
            const html = `
                <div class="bom-designer-container">
                    <div class="mb-5 d-flex justify-content-between align-items-center">
                        <h3 class="font-weight-bold" style="color: #fff; letter-spacing: -0.5px;">BOM Designer</h3>
                        <div class="text-muted small">Streamlining Multi-level Textile BOMs</div>
                    </div>

                    <div class="header-card p-4 mb-5">
                        <div class="row align-items-end">
                            <div class="col-md-5 mb-3 mb-md-0">
                                <label class="section-label">Final Good Name</label>
                                <div class="fg-selector-target"></div>
                            </div>
                            <div class="col-md-2 mb-3 mb-md-0">
                                <label class="section-label">Total Quantity (Kg)</label>
                                <div class="unit-input-group">
                                    <input type="number" class="form-control final-qty" value="100">
                                    <span class="unit-label">Kg</span>
                                </div>
                            </div>
                            <div class="col-md-3 mb-3 mb-md-0">
                                <label class="section-label">RM Cost Based On</label>
                                <div class="rm-cost-target"></div>
                            </div>
                        </div>
                    </div>

                    <div class="mb-3 d-flex justify-content-between align-items-center" style="border-bottom: 1px solid #333; padding-bottom: 10px;">
                        <label class="section-label m-0">Production Workflow</label>
                        <span class="text-muted small">Add stages to define the process</span>
                    </div>

                    <div class="sequence-bar d-flex align-items-center mb-5">
                        <span class="mr-4 font-weight-bold small text-muted">Add Stage:</span>
                        <div class="d-flex gap-3">
                            <button class="op-pill pill-yarn btn-add-op" data-type="yarn_processing">
                                <i class="fa fa-archive" style="color: var(--yarn-accent)"></i> Yarn Processing
                            </button>
                            <button class="op-pill pill-knit btn-add-op" data-type="knitting">
                                <i class="fa fa-th" style="color: var(--knit-accent)"></i> Knitting
                            </button>
                            <button class="op-pill pill-dye btn-add-op" data-type="dyeing">
                                <i class="fa fa-tint" style="color: var(--dye-accent)"></i> Dyeing
                            </button>
                        </div>
                    </div>

                    <div class="workflow-stack d-flex flex-column align-items-center mb-5"></div>
                </div>
            `;

            this.body.html(html);

            // Primary action
            this.page.set_primary_action('Generate BOMs', () => this.create_bom(), 'fa fa-magic');

            // Initialize Final Good Link Control
            const $fg_target = this.wrapper.find('.fg-selector-target');
            if ($fg_target.length) {
                $fg_target.empty();
                try {
                    this.fg_item_select = frappe.ui.form.make_control({
                        df: {
                            fieldname: 'final_good_' + frappe.utils.get_random(5),
                            fieldtype: 'Link',
                            options: 'Item',
                            placeholder: 'Search Finished Good...',
                            read_only: 0,
                            change: () => {
                                let val = this.fg_item_select.get_value();
                                if (val) {
                                    this.check_and_load_bom(val);
                                    this.sync_dyeing();
                                    this.sync_all_knitting_outputs();
                                    frappe.db.get_value('Item', val, 'item_name').then(r => {
                                        let name_val = '';
                                        if (r && r.message) {
                                            name_val = typeof r.message === 'object' ? r.message.item_name : r.message;
                                        } else if (r && r.item_name) {
                                            name_val = r.item_name;
                                        }
                                        this.fg_item_name = name_val;
                                        this.sync_dyeing();
                                        this.sync_all_knitting_outputs();
                                    }).catch(() => {
                                        this.sync_dyeing();
                                        this.sync_all_knitting_outputs();
                                    });
                                } else {
                                    this.fg_item_name = '';
                                    this.sync_dyeing();
                                    this.sync_all_knitting_outputs();
                                }
                            }
                        },
                        parent: $fg_target[0],
                        render_input: true
                    });

                    if (this.fg_item_select) {
                        this.fg_item_select.make();
                        this.fg_item_select.refresh();
                        if (this.initial_item) {
                            this.fg_item_select.set_value(this.initial_item);
                        }
                        this.bind_item_selector_dblclick(this.fg_item_select, $fg_target);
                    }
                } catch (e) {
                    frappe.msgprint(__('Error initializing Final Good selector'));
                }
            }

            // Initialize RM Cost As Per Select
            const $rm_target = this.wrapper.find('.rm-cost-target');
            if ($rm_target.length) {
                $rm_target.empty();
                try {
                    this.rm_cost_select = frappe.ui.form.make_control({
                        df: {
                            fieldname: 'rm_cost_as_per_' + frappe.utils.get_random(5),
                            fieldtype: 'Select',
                            options: 'Valuation Rate\nLast Purchase Rate\nPrice List',
                            default: 'Valuation Rate',
                            read_only: 0,
                        },
                        parent: $rm_target[0],
                        render_input: true
                    });
                    if (this.rm_cost_select) {
                        this.rm_cost_select.make();
                        this.rm_cost_select.refresh();
                        this.rm_cost_select.set_value('Valuation Rate');
                    }
                } catch (e) {
                    frappe.msgprint(__('Error initializing RM Cost selector'));
                }
            }

            this.bind_events();
        }

        bind_events() {
            this.body.on('click', '.btn-add-op', (e) => {
                this.add_operation($(e.currentTarget).data('type'));
            });

            this.body.on('click', '.btn-remove-op', (e) => {
                let idx = $(e.currentTarget).closest('.op-card-wrapper').index('.op-card-wrapper');
                this.remove_operation(idx);
            });

            this.body.on('click', '.btn-add-mini', (e) => {
                this.add_input_row($(e.currentTarget).closest('.op-card'));
            });

            this.body.on('click', '.btn-remove-input', (e) => {
                this.remove_input_row($(e.currentTarget).closest('.input-row-mini'));
            });

            // Auto-calculate on loss/mix/qty change
            this.body.on('change', '.input-loss, .input-mix, .final-qty', () => {
                this.calculate_quantities();
            });

            // Job work checkbox change for knitting
            this.body.on('change', '.chk-job-work', (e) => {
                let $card = $(e.currentTarget).closest('.op-card');
                this.update_jw_section($card);
                this.update_workstation_display($card);
            });

            // Job work direction change
            this.body.on('change', '.jw-direction-radio', (e) => {
                let $card = $(e.currentTarget).closest('.op-card');
                this.update_rm_checkboxes($card);
            });
        }

        bind_item_selector_dblclick(control, $target) {
            $target.off('dblclick', 'input');
            $target.on('dblclick', 'input', () => {
                if (typeof kniterp_open_item_selector !== 'undefined') {
                    kniterp_open_item_selector({
                        on_select: (item_code) => {
                            if (control && typeof control.set_value === 'function') {
                                control.set_value(item_code);
                                if (control.df.change) control.df.change();
                            }
                        }
                    });
                }
            });

            setTimeout(() => {
                $target.find('input').attr('placeholder', 'Double-click for attribute selector...');
            }, 100);
        }

        add_operation(type) {
            let existing = this.operations.find(o => o.type === type);
            if (existing) {
                frappe.msgprint(`${frappe.unscrub(type)} operation already exists`);
                return;
            }

            let op = {
                type: type,
                $el: this.render_op_card(type, 0)
            };

            this.operations.push(op);
            this.sort_operations();
            this.render_operations();
            this.update_buttons_visibility();
            this.update_sfg_visibility();

            if (type === 'dyeing') this.sync_dyeing();
            if (type === 'yarn_processing') this.sync_yarn_output();
            if (type === 'knitting') {
                setTimeout(() => this.sync_knitting_output(op.$el), 150);
            }

            this.calculate_quantities();
            setTimeout(() => this.sync_yarn_output(), 250);
        }

        sort_operations() {
            const order = { 'yarn_processing': 1, 'knitting': 2, 'dyeing': 3 };
            this.operations.sort((a, b) => order[a.type] - order[b.type]);
        }

        render_operations() {
            this.page.main.find('.workflow-stack').children().detach();

            this.operations.forEach((op, idx) => {
                if (idx > 0) {
                    this.page.main.find('.workflow-stack').append('<div class="arrow-icon"><i class="fa fa-chevron-down"></i></div>');
                }
                op.$el.find('.step-num').text(idx + 1);
                this.page.main.find('.workflow-stack').append(op.$el);
            });
        }

        remove_operation(idx) {
            this.operations.splice(idx, 1);
            this.render_operations();
            this.update_buttons_visibility();
            this.update_sfg_visibility();
            this.calculate_quantities();
            setTimeout(() => this.sync_yarn_output(), 250);
        }

        renumber_steps() {
            this.page.main.find('.op-card-wrapper').each((i, el) => {
                $(el).find('.step-num').text(i + 1);
            });
        }

        update_buttons_visibility() {
            // All operation buttons are always visible
        }

        update_sfg_visibility() {
            let has_dyeing = this.operations.some(o => o.type === 'dyeing');
            this.operations.forEach((op) => {
                if (op.type === 'knitting') {
                    let $card = op.$el;
                    let $sfg_section = $card.find('.sfg-output-section');

                    if (has_dyeing) {
                        $sfg_section.stop(true, true).show();
                    } else {
                        setTimeout(() => {
                            if (!this.operations.some(o => o.type === 'dyeing')) {
                                $sfg_section.hide();
                            }
                        }, 250);
                    }
                    this.sync_knitting_output($card);
                }
            });
        }

        sync_knitting_output($card) {
            let has_dyeing = this.operations.some(o => o.type === 'dyeing');

            if (!has_dyeing) {
                let fg = this.fg_item_select ? this.fg_item_select.get_value() : '';
                let display = fg;
                if (fg && this.fg_item_name) {
                    display = `${fg} : ${this.fg_item_name}`;
                }
                $card.find('.output-item-name').text(display || 'Select Final Good...');
            } else {
                let sfg_ctrl = $card.data('sfg_control');
                if (sfg_ctrl && sfg_ctrl.get_value()) {
                    this.sync_output_display($card);
                } else {
                    $card.find('.output-item-name').text('Select SFG...');
                }
            }
        }

        // Auto-determine workstation type
        get_workstation_type(type, is_job_work) {
            if (type === 'knitting') {
                return is_job_work ? 'Knitting Job Work' : 'Knitting in-house';
            } else if (type === 'dyeing') {
                return 'Dyeing Job Work';
            } else if (type === 'yarn_processing') {
                return 'Yarn Processing';
            }
            return '';
        }

        render_op_card(type, step_num) {
            let title = frappe.unscrub(type);
            let theme_class = `card-${type.replace('_', '-')}`;
            let is_yarn = type === 'yarn_processing';
            let is_knit = type === 'knitting';
            let is_dye = type === 'dyeing';

            // Determine initial workstation type
            let initial_jw = is_yarn || is_dye;
            let ws_type = this.get_workstation_type(type, initial_jw);

            let $card = $(`
                <div class="op-card-wrapper w-100" style="max-width: 900px;">
                    <div class="op-card mb-4 ${theme_class}">
                        <div class="op-card-header d-flex justify-content-between align-items-center">
                            <div>
                                <span class="step-label">STAGE <span class="step-num">${step_num}</span></span>
                                <span class="font-weight-bold" style="letter-spacing: 0.5px;">${title}</span>
                            </div>
                            <button class="btn btn-sm btn-link text-muted btn-remove-op" style="font-size: 16px;"><i class="fa fa-times-circle"></i></button>
                        </div>
                        <div class="card-body p-0">
                            <div class="row no-gutters">
                                <!-- Inputs section -->
                                <div class="col-md-4 p-4" style="background: rgba(0,0,0,0.1);">
                                    <div class="col-label">${is_knit ? 'Yarns Mix' : 'Raw Material'}</div>
                                    <div class="inputs-list"></div>
                                    ${is_knit ? `
                                    <button class="btn btn-add-mini mt-3 w-100 py-2"><i class="fa fa-plus-circle mr-2"></i> Add Item</button>
                                    ` : ''}
                                </div>

                                <!-- Settings section -->
                                <div class="col-md-4 p-4 border-left border-right" style="border-color: #333 !important;">
                                    <div class="mb-4 d-flex gap-2">
                                        <div class="frappe-control" style="margin-right: 15px;">
                                            <div class="checkbox">
                                                <label>
                                                    <input type="checkbox" class="chk-job-work" ${is_yarn || is_dye ? 'checked disabled' : ''}>
                                                    <span class="label-area small ml-2 text-muted">Job Work</span>
                                                </label>
                                            </div>
                                        </div>
                                    </div>

                                    ${is_knit ? `
                                    <div class="mb-4 jw-direction-section" style="display: none;">
                                        <label class="small text-muted mb-2">Job Work Direction</label>
                                        <div class="d-flex gap-3">
                                            <label class="small text-muted" style="cursor: pointer;">
                                                <input type="radio" name="jw_direction_${Date.now()}" class="jw-direction-radio" value="outward" checked>
                                                <span class="ml-1">Out-House</span>
                                            </label>
                                            <label class="small text-muted" style="cursor: pointer;">
                                                <input type="radio" name="jw_direction_${Date.now()}" class="jw-direction-radio" value="inward">
                                                <span class="ml-1">In-House</span>
                                            </label>
                                        </div>
                                    </div>
                                    ` : ''}

                                    ${is_knit || is_yarn ? `
                                    <div class="mb-4 sfg-output-section">
                                        <label class="small text-muted mb-2">Target Output (SFG)</label>
                                        <div class="sfg-output-target"></div>
                                    </div>
                                    ` : ''}

                                    <div class="mb-4">
                                        <label class="small text-muted mb-2">Workstation Type</label>
                                        <div class="workstation-type-display" style="background: #262626; border: 1px solid #404040; border-radius: 6px; padding: 8px 12px; color: #aaa; font-size: 13px;">
                                            ${ws_type}
                                        </div>
                                    </div>

                                    <div>
                                        <label class="small text-muted mb-2">Process Loss (%)</label>
                                        <div class="unit-input-group">
                                            <input type="number" class="form-control form-control-sm input-loss" value="2">
                                            <span class="unit-label">%</span>
                                        </div>
                                    </div>
                                </div>

                                <!-- Output section -->
                                <div class="col-md-4 p-4 d-flex flex-column justify-content-center">
                                    <div class="col-label output-label">Total Output</div>
                                    <div class="output-box p-3 shadow-inner">
                                        <div class="font-weight-bold output-item-name" style="font-size: 15px; margin-bottom: 4px;">Select...</div>
                                        <div class="small text-muted mt-2 pt-2 border-top d-none output-qty-display" style="border-color: rgba(255,255,255,0.1) !important;">
                                            <span class="font-weight-bold" style="color: #fff; font-size: 16px;"><span class="val">0</span> <span style="font-size: 12px; font-weight: normal; color: #888;">kg</span></span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `);

            // Initialize SFG Selectors
            if (!is_dye) {
                setTimeout(() => {
                    let target = $card.find('.sfg-output-target');
                    if (target.length) {
                        target.empty();
                        try {
                            let ctrl = frappe.ui.form.make_control({
                                df: {
                                    fieldname: 'sfg_item_' + frappe.utils.get_random(5),
                                    fieldtype: 'Link',
                                    options: 'Item',
                                    placeholder: 'SFG Item...',
                                    read_only: 0,
                                    change: () => {
                                        let val = ctrl.get_value();
                                        if (val) {
                                            this.sync_output_display($card);
                                            this.sync_dyeing();
                                            this.sync_yarn_output();
                                            frappe.db.get_value('Item', val, 'item_name').then(r => {
                                                let name_val = '';
                                                if (r && r.message) {
                                                    name_val = typeof r.message === 'object' ? r.message.item_name : r.message;
                                                } else if (r && r.item_name) {
                                                    name_val = r.item_name;
                                                }
                                                $card.data('item_name', name_val);
                                                this.sync_output_display($card);
                                                this.sync_dyeing();
                                                this.sync_yarn_output();
                                            }).catch(() => {
                                                this.sync_output_display($card);
                                                this.sync_dyeing();
                                                this.sync_yarn_output();
                                            });
                                        } else {
                                            $card.data('item_name', '');
                                            this.sync_output_display($card);
                                            this.sync_dyeing();
                                            this.sync_yarn_output();
                                        }
                                    }
                                },
                                parent: target[0],
                                render_input: true
                            });
                            if (ctrl) {
                                ctrl.make();
                                ctrl.refresh();
                                this.bind_item_selector_dblclick(ctrl, target);
                                $card.data('sfg_control', ctrl);
                            }
                        } catch (e) {
                            // SFG control creation failed silently
                        }
                    }
                }, 100);
            }

            this.add_input_row($card);
            return $card;
        }

        add_input_row($el) {
            const $card = $el.hasClass('op-card') ? $el : $el.find('.op-card');
            let is_knit = $card.hasClass('card-knitting');
            let is_dye = $card.hasClass('card-dyeing');
            let $list = $card.find('.inputs-list');

            let $row = $(`
                <div class="input-row-mini mb-3" style="position: relative;">
                    <button class="btn btn-sm btn-link text-danger btn-remove-input" style="position: absolute; top: -5px; right: -5px; padding: 2px 6px; font-size: 18px; line-height: 1; z-index: 10;" title="Remove item">
                        <i class="fa fa-times-circle"></i>
                    </button>
                    <div class="small-header mb-1">Item</div>
                    <div class="item-link-target mb-3"></div>
                    <div class="row no-gutters">
                        ${is_knit ? `
                        <div class="col-12">
                            <div class="small-header mb-1">Ratio</div>
                            <div class="unit-input-group">
                                <input type="number" class="form-control form-control-sm input-mix" value="100">
                                <span class="unit-label">%</span>
                            </div>
                        </div>
                        ` : `
                        <input type="hidden" class="input-mix" value="100">
                        `}
                    </div>
                    <!-- Sourced by Supplier checkbox (for job work outward) -->
                    <div class="mt-2 sourced-by-supplier-section" style="display: none;">
                        <div class="checkbox">
                            <label class="small text-muted" style="cursor: pointer;">
                                <input type="checkbox" class="chk-sourced-by-supplier" style="margin-right: 4px;">
                                Sourced by Supplier
                            </label>
                        </div>
                    </div>
                    <!-- Customer Provided checkbox (for job work inward) -->
                    <div class="mt-2 customer-provided-section" style="display: none;">
                        <div class="checkbox">
                            <label class="small text-muted" style="cursor: pointer;">
                                <input type="checkbox" class="chk-customer-provided" style="margin-right: 4px;">
                                Customer Provided
                            </label>
                        </div>
                    </div>
                    <div class="mt-2 text-right d-none row-qty-display">
                        <span class="small" style="color: #48bb78; font-weight: 600;"><span class="val">0</span> kg</span>
                    </div>
                </div>
            `);

            setTimeout(() => {
                let target = $row.find('.item-link-target');
                if (target.length) {
                    target.empty();
                    try {
                        let ctrl = frappe.ui.form.make_control({
                            df: {
                                fieldname: 'input_item_' + frappe.utils.get_random(5),
                                fieldtype: 'Link',
                                options: 'Item',
                                read_only: 0,
                                placeholder: 'Input Item'
                            },
                            parent: target[0],
                            render_input: true
                        });
                        if (ctrl) {
                            ctrl.make();
                            ctrl.refresh();
                            this.bind_item_selector_dblclick(ctrl, target);
                            $row.data('control', ctrl);
                            if (is_dye) this.sync_dyeing();
                        }
                    } catch (e) {
                        // Input control creation failed silently
                    }
                }
            }, 100);

            $list.append($row);

            // Update RM checkbox visibility based on current JW state
            this.update_rm_checkboxes($card);
        }

        remove_input_row($row) {
            let $card = $row.closest('.op-card');
            let $list = $card.find('.inputs-list');
            let row_count = $list.find('.input-row-mini').length;

            if (row_count <= 1) {
                frappe.msgprint('At least one input item is required');
                return;
            }

            $row.remove();
            this.calculate_quantities();
        }

        sync_output_display($card) {
            let item = $card.find('.sfg-output-target .form-control').val();
            let name = $card.data('item_name');
            let display = item;
            if (item && name) {
                display = `${item} : ${name}`;
            }
            $card.find('.output-item-name').text(display || 'Select SFG...');
        }

        sync_all_knitting_outputs() {
            this.operations.forEach(op => {
                if (op.type === 'knitting') {
                    this.sync_knitting_output(op.$el);
                }
            });
        }

        sync_dyeing() {
            let dyeing_op = this.operations.find(o => o.type === 'dyeing');
            if (!dyeing_op) return;

            let $dye_card = dyeing_op.$el;

            // 1. Sync Output (always Final Good)
            let fg = this.fg_item_select ? this.fg_item_select.get_value() : '';
            let display = fg;
            if (fg && this.fg_item_name) {
                display = `${fg} : ${this.fg_item_name}`;
            }
            $dye_card.find('.output-item-name').text(display || 'Select Final Good...');

            // 2. Sync Input (from Knitting Output)
            let knitting_op = this.operations.find(o => o.type === 'knitting');
            if (knitting_op) {
                let knitting_sfg = knitting_op.$el.find('.sfg-output-target .form-control').val();
                if (knitting_sfg) {
                    let $row = $dye_card.find('.input-row-mini').first();
                    let ctrl = $row.data('control');
                    if (ctrl && ctrl.get_value() !== knitting_sfg) {
                        ctrl.set_value(knitting_sfg);
                    }
                }
            }
        }

        sync_yarn_output() {
            let yarn_op = this.operations.find(o => o.type === 'yarn_processing');
            if (!yarn_op) return;

            let yarn_sfg = yarn_op.$el.find('.sfg-output-target .form-control').val();
            if (!yarn_sfg) return;

            let knitting_op = this.operations.find(o => o.type === 'knitting');
            let dyeing_op = this.operations.find(o => o.type === 'dyeing');

            if (knitting_op) {
                let $knit_card = knitting_op.$el;
                let exists = false;
                let empty_ctrl = null;

                $knit_card.find('.input-row-mini').each((_, el) => {
                    let ctrl = $(el).data('control');
                    if (ctrl) {
                        let val = ctrl.get_value();
                        if (val === yarn_sfg) {
                            exists = true;
                        } else if (!val && !empty_ctrl) {
                            empty_ctrl = ctrl;
                        }
                    }
                });

                if (!exists) {
                    if (empty_ctrl) {
                        empty_ctrl.set_value(yarn_sfg);
                    } else {
                        // Add a new row and set it
                        this.add_input_row($knit_card);
                        setTimeout(() => {
                            let $last_row = $knit_card.find('.input-row-mini').last();
                            let ctrl = $last_row.data('control');
                            if (ctrl) ctrl.set_value(yarn_sfg);
                        }, 250);
                    }
                }
            } else if (dyeing_op) {
                let $dye_card = dyeing_op.$el;
                let $row = $dye_card.find('.input-row-mini').first();
                let ctrl = $row.data('control');
                if (ctrl && ctrl.get_value() !== yarn_sfg) {
                    ctrl.set_value(yarn_sfg);
                }
            }
        }

        // --- Job Work In/Out Section Management ---

        update_jw_section($card) {
            let is_knit = $card.hasClass('card-knitting');
            if (!is_knit) return;

            let is_job_work = $card.find('.chk-job-work').prop('checked');
            let $jw_section = $card.find('.jw-direction-section');

            if (is_job_work) {
                $jw_section.show();
            } else {
                $jw_section.hide();
            }

            this.update_rm_checkboxes($card);
        }

        update_all_jw_sections() {
            this.operations.forEach(op => {
                this.update_jw_section(op.$el.find('.op-card'));
                this.update_workstation_display(op.$el.find('.op-card'));
            });
        }

        update_workstation_display($card) {
            let type = '';
            if ($card.hasClass('card-knitting')) type = 'knitting';
            else if ($card.hasClass('card-dyeing')) type = 'dyeing';
            else if ($card.hasClass('card-yarn-processing')) type = 'yarn_processing';

            let is_job_work = $card.find('.chk-job-work').prop('checked');
            let ws_type = this.get_workstation_type(type, is_job_work);
            $card.find('.workstation-type-display').text(ws_type);
        }

        update_rm_checkboxes($card) {
            let is_knit = $card.hasClass('card-knitting');
            let is_yarn = $card.hasClass('card-yarn-processing');
            let is_dye = $card.hasClass('card-dyeing');
            let is_job_work = $card.find('.chk-job-work').prop('checked');

            if (is_knit && is_job_work) {
                let direction = $card.find('.jw-direction-radio:checked').val() || 'outward';

                $card.find('.input-row-mini').each((_, el) => {
                    let $row = $(el);
                    if (direction === 'outward') {
                        $row.find('.sourced-by-supplier-section').show();
                        $row.find('.customer-provided-section').hide();
                        $row.find('.chk-customer-provided').prop('checked', false);
                    } else if (direction === 'inward') {
                        $row.find('.customer-provided-section').show();
                        $row.find('.sourced-by-supplier-section').hide();
                        $row.find('.chk-sourced-by-supplier').prop('checked', false);
                    }
                });
            } else if ((is_yarn || is_dye) && is_job_work) {
                // Yarn processing and dyeing are always outward
                $card.find('.input-row-mini').each((_, el) => {
                    let $row = $(el);
                    $row.find('.sourced-by-supplier-section').show();
                    $row.find('.customer-provided-section').hide();
                    $row.find('.chk-customer-provided').prop('checked', false);
                });
            } else {
                // Not job work — hide both
                $card.find('.input-row-mini').each((_, el) => {
                    let $row = $(el);
                    $row.find('.sourced-by-supplier-section').hide();
                    $row.find('.customer-provided-section').hide();
                    $row.find('.chk-sourced-by-supplier').prop('checked', false);
                    $row.find('.chk-customer-provided').prop('checked', false);
                });
            }
        }

        // --- Calculation ---

        calculate_quantities() {
            let final_qty = flt(this.page.main.find('.final-qty').val());
            if (!final_qty) return;

            let current_output_qty = final_qty;

            for (let i = this.operations.length - 1; i >= 0; i--) {
                let $card = this.operations[i].$el;
                let loss = flt($card.find('.input-loss').val());

                $card.find('.output-qty-display').removeClass('d-none').find('.val').text(flt(current_output_qty, this.PRECISION));

                let total_input_for_op = 0;
                $card.find('.input-row-mini').each((_, el) => {
                    let $row = $(el);
                    let mix = flt($row.find('.input-mix').val());
                    let row_qty = (current_output_qty * (mix / 100)) / (1 - (loss / 100));
                    $row.find('.row-qty-display').removeClass('d-none').find('.val').text(flt(row_qty, this.PRECISION));
                    total_input_for_op += row_qty;
                });

                current_output_qty = total_input_for_op;
            }
        }

        // --- Validation ---

        validate_data(data) {
            let errors = [];

            // Validate each operation
            for (let i = 0; i < data.operations.length; i++) {
                let op = data.operations[i];
                let op_label = `Stage ${i + 1} (${frappe.unscrub(op.type)})`;

                // Check all input items are filled
                for (let j = 0; j < op.inputs.length; j++) {
                    if (!op.inputs[j].item) {
                        errors.push(`${op_label}: Input item ${j + 1} is empty`);
                    }
                }

                // Check mix percentages sum to 100% for knitting
                if (op.type === 'knitting') {
                    let mix_sum = op.inputs.reduce((sum, inp) => sum + flt(inp.mix), 0);
                    if (Math.abs(mix_sum - 100) > 0.01) {
                        errors.push(`${op_label}: Mix percentages must sum to 100% (currently ${mix_sum}%)`);
                    }
                }

                // Check SFG items are selected when dyeing exists
                let has_dyeing = data.operations.some(o => o.type === 'dyeing');
                if (op.type === 'knitting' && has_dyeing && !op.output_item) {
                    errors.push(`${op_label}: SFG (Target Output) must be selected when Dyeing stage exists`);
                }

                // Check for duplicate items within an operation
                let items = op.inputs.map(inp => inp.item).filter(Boolean);
                let duplicates = items.filter((item, idx) => items.indexOf(item) !== idx);
                if (duplicates.length > 0) {
                    errors.push(`${op_label}: Duplicate items found: ${[...new Set(duplicates)].join(', ')}`);
                }

                // Loss % range validation (>= 0 and < 10)
                if (op.loss_percent < 0 || op.loss_percent >= 10) {
                    errors.push(`${op_label}: Loss % must be >= 0 and < 10 (currently ${op.loss_percent}%)`);
                }
            }

            if (errors.length > 0) {
                frappe.msgprint({
                    title: __('Validation Errors'),
                    indicator: 'red',
                    message: '<ul>' + errors.map(e => `<li>${e}</li>`).join('') + '</ul>'
                });
                return false;
            }
            return true;
        }

        // --- Data Collection ---

        get_operation_output_item(type, $card, final_good, sfg_ctrl) {
            if (type === 'dyeing') {
                return final_good;
            }

            let has_dyeing = this.operations.some(o => o.type === 'dyeing');

            if (type === 'knitting' && !has_dyeing) {
                return final_good;
            }

            return sfg_ctrl ? sfg_ctrl.get_value() : $card.find('.sfg-output-target .form-control').val();
        }

        get_data() {
            let data = {
                final_good: this.fg_item_select ? this.fg_item_select.get_value() : null,
                final_qty: flt(this.page.main.find('.final-qty').val()),
                rm_cost_as_per: this.rm_cost_select ? this.rm_cost_select.get_value() : 'Valuation Rate',
                operations: []
            };

            this.page.main.find('.op-card-wrapper').each((i, el) => {
                let $card = $(el);
                let op_ref = this.operations[i];
                if (!op_ref) return;

                let type = op_ref.type;
                let sfg_ctrl = $card.data('sfg_control');
                let is_job_work = $card.find('.chk-job-work').prop('checked');

                // Determine job work direction
                let jw_direction = '';
                if (is_job_work) {
                    if (type === 'knitting') {
                        jw_direction = $card.find('.jw-direction-radio:checked').val() || 'outward';
                    } else {
                        jw_direction = 'outward'; // yarn/dyeing always outward
                    }
                }

                let op_data = {
                    type: type,
                    is_job_work: is_job_work,
                    job_work_direction: jw_direction,
                    loss_percent: flt($card.find('.input-loss').val()),
                    output_item: this.get_operation_output_item(type, $card, data.final_good, sfg_ctrl),
                    output_qty: flt($card.find('.output-qty-display .val').text()),
                    workstation_type: this.get_workstation_type(type, is_job_work),
                    inputs: []
                };

                $card.find('.input-row-mini').each((_, rel) => {
                    let $row = $(rel);
                    let ctrl = $row.data('control');

                    let inp = {
                        item: ctrl ? ctrl.get_value() : $row.find('.item-link-target .form-control').val(),
                        mix: flt($row.find('.input-mix').val()),
                        qty: flt($row.find('.row-qty-display .val').text()),
                    };

                    // Collect per-RM flags
                    if (is_job_work && jw_direction === 'outward') {
                        inp.sourced_by_supplier = $row.find('.chk-sourced-by-supplier').prop('checked') || false;
                    }
                    if (is_job_work && jw_direction === 'inward') {
                        inp.customer_provided = $row.find('.chk-customer-provided').prop('checked') || false;
                    }

                    op_data.inputs.push(inp);
                });

                data.operations.push(op_data);
            });

            return data;
        }

        create_bom() {
            let data = this.get_data();
            data.sales_order_item = this.sales_order_item; // Pass SO context for SB validation
            if (!data.final_good) {
                frappe.msgprint("Please select Final Good");
                return;
            }
            if (!data.operations.length) {
                frappe.msgprint("Please add at least one stage");
                return;
            }

            // Run frontend validations
            if (!this.validate_data(data)) {
                return;
            }

            frappe.confirm(`Create multi-level BOM stack for ${data.final_good}?`, () => {
                frappe.call({
                    method: 'kniterp.api.bom_tool.create_multilevel_bom',
                    args: { data: data },
                    freeze: true,
                    callback: (r) => {
                        if (r.message && r.message.message) {
                            frappe.msgprint(r.message.message);

                            // Return flow
                            if (this.return_to === 'production-wizard' && this.sales_order_item) {
                                let bom_name = r.message.name;
                                if (bom_name) {
                                    frappe.call({
                                        method: 'kniterp.api.production_wizard.update_so_item_bom',
                                        args: {
                                            sales_order_item: this.sales_order_item,
                                            bom_no: bom_name
                                        },
                                        callback: () => {
                                            frappe.set_route('production-wizard', { selected_item: this.sales_order_item });
                                        }
                                    });
                                } else {
                                    frappe.set_route('production-wizard', { selected_item: this.sales_order_item });
                                }
                            } else {
                                frappe.set_route('List', 'BOM', { item: data.final_good });
                            }
                        }
                    }
                });
            });
        }
    }

    new BomDesigner(wrapper, page);
};
