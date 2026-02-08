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
            // Skip if we're already loading a BOM from URL params
            if (this.bom_no) return;

            // Skip if we're currently populating data
            if (this.is_populating) return;

            // Skip if there are already operations (user has started designing)
            if (this.operations.length > 0) {
                return;
            }

            // Skip if we already checked this item (prevent duplicate prompts)
            if (this.last_checked_item === item_code) {
                return;
            }

            // Skip if a prompt is already being shown
            if (this.bom_prompt_shown) {
                return;
            }

            // Mark this item as checked
            this.last_checked_item = item_code;
            this.bom_prompt_shown = true;

            // Check if a default BOM exists for this item
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

                        // Ask user if they want to load the existing BOM
                        frappe.confirm(
                            `A default BOM (${bom_name}) exists for this item. Would you like to load it?`,
                            () => {
                                // User clicked Yes - load the BOM
                                this.load_existing_bom(bom_name);
                            },
                            () => {
                                // User clicked No - do nothing, let them design from scratch
                                console.log('User chose to design from scratch');
                                // Reset the flag so they can try again if they change the item
                                this.bom_prompt_shown = false;
                            }
                        );
                    } else {
                        // No BOM found, reset the flag
                        this.bom_prompt_shown = false;
                    }
                }
            });
        }

        populate_from_data(data) {
            // Set flag to prevent BOM check during population
            this.is_populating = true;

            // Set Final Good
            if (this.fg_item_select) {
                this.fg_item_select.set_value(data.final_good);
            }
            this.page.main.find('.final-qty').val(data.final_qty);

            // Clear existing ops just in case
            this.operations = [];
            this.page.main.find('.workflow-stack').empty();

            // Add operations
            for (let op of data.operations) {
                // Determine type from scrubbed name
                let type = op.type; // already scrubbed from backend

                // Add Op (this will sort and render)
                this.add_operation(type);

                // Find the operation we just added by type
                let current_op = this.operations.find(o => o.type === type);
                if (!current_op) continue;

                let $card = current_op.$el;

                // Set Loss
                $card.find('.input-loss').val(op.loss_percent);

                // Set Job Work
                $card.find('.chk-job-work').prop('checked', op.is_job_work);

                // Set Output Item (SFG) - wait for control to be ready
                if (op.output_item && type !== 'dyeing') {
                    setTimeout(() => {
                        let sfg_ctrl = $card.data('sfg_control');
                        if (sfg_ctrl) {
                            sfg_ctrl.set_value(op.output_item);
                        }
                    }, 200);
                }

                // Set Workstation Type
                if (op.workstation_type) {
                    // Wait for control to be ready (it's in a setTimeout in render_op_card)
                    // or we can just set the value on the control found in data
                    // But render_op_card is async-ish with those timeouts.
                    // Let's use a small timeout here or access the data directly if we can't wait.
                    // Better: access the data object on card after a moment?
                    // Or just set the value. checking render_op_card implementation...
                    // render_op_card uses setTimeouts (100ms). We need to wait.

                    setTimeout(() => {
                        let ws_ctrl = $card.data('ws_control');
                        if (ws_ctrl) ws_ctrl.set_value(op.workstation_type);
                    }, 200);
                }

                // Inputs
                let $inputs_list = $card.find('.inputs-list');
                $inputs_list.empty(); // Clear default row

                for (let inp of op.inputs) {
                    this.add_input_row($card);
                    let $row = $inputs_list.find('.input-row-mini').last();

                    setTimeout(() => {
                        let ctrl = $row.data('control');
                        if (ctrl) ctrl.set_value(inp.item);
                        $row.find('.input-mix').val(inp.mix);
                    }, 200);
                }
            }

            setTimeout(() => {
                this.update_sfg_visibility();
                this.calculate_quantities();
                // Clear the populating flag
                this.is_populating = false;
            }, 500);
        }

        setup_ui() {
            console.log("Setting up BOM Designer UI...");
            const html = `
                <div class="bom-designer-container">
                    <div class="mb-5 d-flex justify-content-between align-items-center">
                        <h3 class="font-weight-bold" style="color: #fff; letter-spacing: -0.5px;">BOM Designer</h3>
                        <div class="text-muted small">Streamlining Multi-level Textile BOMs</div>
                    </div>

                    <div class="header-card p-4 mb-5">
                        <div class="row align-items-end">
                            <div class="col-md-7 mb-3 mb-md-0">
                                <label class="section-label">Final Good Name</label>
                                <div class="fg-selector-target"></div>
                            </div>
                            <div class="col-md-3 mb-3 mb-md-0">
                                <label class="section-label">Total Quantity (Kg)</label>
                                <div class="unit-input-group">
                                    <input type="number" class="form-control final-qty" value="100">
                                    <span class="unit-label">Kg</span>
                                </div>
                            </div>
                            <div class="col-md-2">
                                <label class="section-label" style="visibility: hidden;">Action</label>
                                <button class="btn btn-primary btn-calculate w-100" style="font-weight: 600; height: 38px; display: flex; align-items: center; justify-content: center;">
                                    <i class="fa fa-refresh mr-2"></i> Sync
                                </button>
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

            // Primary action with specialized styling
            this.page.set_primary_action('Generate BOMs', () => this.create_bom(), 'fa fa-magic');

            // Initialize Final Good Link Control
            const $fg_target = this.wrapper.find('.fg-selector-target');
            console.log("FG Target element count in wrapper:", $fg_target.length);

            if ($fg_target.length) {
                $fg_target.empty(); // Prevent double rendering
                try {
                    this.fg_item_select = frappe.ui.form.make_control({
                        df: {
                            fieldname: 'final_good',
                            fieldtype: 'Link',
                            options: 'Item',
                            placeholder: 'Search Finished Good...',
                            read_only: 0,
                            change: () => {
                                let val = this.fg_item_select.get_value();
                                console.log("Final Good changed to:", val);
                                if (val) {
                                    // Check if BOM exists for this item
                                    this.check_and_load_bom(val);

                                    // Set interim display while fetching name
                                    this.sync_dyeing();
                                    this.sync_all_knitting_outputs();
                                    frappe.db.get_value('Item', val, 'item_name').then(r => {
                                        console.log("Fetched FG Name Response:", r);
                                        let name_val = '';
                                        if (r && r.message) {
                                            name_val = typeof r.message === 'object' ? r.message.item_name : r.message;
                                        } else if (r && r.item_name) {
                                            name_val = r.item_name;
                                        }
                                        this.fg_item_name = name_val;
                                        this.sync_dyeing();
                                        this.sync_all_knitting_outputs();
                                    }).catch(e => {
                                        console.error("Error fetching FG name:", e);
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

                        // Handle initial item from URL
                        if (this.initial_item) {
                            this.fg_item_select.set_value(this.initial_item);
                        }

                        this.bind_item_selector_dblclick(this.fg_item_select, $fg_target);
                        console.log("FG Control successfully created and refreshed. Parent innerHTML length:", $fg_target[0].innerHTML.length);
                    } else {
                        console.error("Failed to create FG Control instance");
                    }
                } catch (e) {
                    console.error("Exception during FG Control creation:", e);
                }
            } else {
                console.error("Critical: .fg-selector-target not found in wrapper");
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

            this.body.on('click', '.btn-calculate', () => {
                this.calculate_quantities();
            });

            this.body.on('click', '.btn-add-mini', (e) => {
                this.add_input_row($(e.currentTarget).closest('.op-card'));
            });

            this.body.on('click', '.btn-remove-input', (e) => {
                this.remove_input_row($(e.currentTarget).closest('.input-row-mini'));
            });

            // Auto-calculate on loss change
            this.body.on('change', '.input-loss, .input-mix, .final-qty', () => {
                this.calculate_quantities();
            });
        }

        bind_item_selector_dblclick(control, $target) {
            const $input = $target.find('input');
            $input.attr('placeholder', 'Double-click for attribute selector...');

            $input.on('dblclick', () => {
                if (typeof kniterp_open_item_selector !== 'undefined') {
                    kniterp_open_item_selector({
                        on_select: (item_code) => {
                            control.set_value(item_code);
                            if (control.df.change) control.df.change();
                        }
                    });
                } else {
                    console.error("kniterp_open_item_selector not found. Check if kniterp_item_selector.js is loaded.");
                }
            });
        }

        add_operation(type) {
            // Check if operation already exists
            let existing = this.operations.find(o => o.type === type);
            if (existing) {
                frappe.msgprint(`${frappe.unscrub(type)} operation already exists`);
                return;
            }

            let op = {
                type: type,
                $el: this.render_op_card(type, 0) // Step number will be set during render
            };

            this.operations.push(op);

            // Sort operations in the correct order: yarn_processing -> knitting -> dyeing
            this.sort_operations();

            // Re-render all operations in the correct order
            this.render_operations();

            this.update_buttons_visibility();
            this.update_sfg_visibility();

            if (type === 'dyeing') this.sync_dyeing();
            if (type === 'knitting') {
                // Sync knitting output to show final good if no dyeing
                setTimeout(() => this.sync_knitting_output(op.$el), 150);
            }

            this.calculate_quantities();
        }

        sort_operations() {
            // Define the correct order
            const order = { 'yarn_processing': 1, 'knitting': 2, 'dyeing': 3 };
            this.operations.sort((a, b) => order[a.type] - order[b.type]);
        }

        render_operations() {
            // Clear the workflow stack
            this.page.main.find('.workflow-stack').empty();

            // Render each operation in order
            this.operations.forEach((op, idx) => {
                // Add arrow between operations
                if (idx > 0) {
                    this.page.main.find('.workflow-stack').append('<div class="arrow-icon"><i class="fa fa-chevron-down"></i></div>');
                }

                // Update step number
                op.$el.find('.step-num').text(idx + 1);

                // Append to stack
                this.page.main.find('.workflow-stack').append(op.$el);
            });
        }

        remove_operation(idx) {
            // Remove from operations array
            this.operations.splice(idx, 1);

            // Re-render all operations
            this.render_operations();

            this.update_buttons_visibility();
            this.update_sfg_visibility();
            this.calculate_quantities();
        }

        renumber_steps() {
            this.page.main.find('.op-card-wrapper').each((i, el) => {
                $(el).find('.step-num').text(i + 1);
            });
        }

        update_buttons_visibility() {
            // All operation buttons are now always visible
        }

        update_sfg_visibility() {
            // Check if there's a dyeing operation
            let has_dyeing = this.operations.some(o => o.type === 'dyeing');

            // Update each knitting operation
            this.operations.forEach((op, idx) => {
                if (op.type === 'knitting') {
                    let $card = op.$el;
                    let $sfg_section = $card.find('.sfg-output-section');

                    if (has_dyeing) {
                        // Show SFG field when dyeing exists
                        $sfg_section.show();
                        // Clear the output display to show SFG prompt
                        this.sync_knitting_output($card);
                    } else {
                        // Hide SFG field and auto-use final good
                        $sfg_section.hide();
                        // Update output display to show final good
                        this.sync_knitting_output($card);
                    }
                }
            });
        }

        sync_knitting_output($card) {
            // When no dyeing operation, knitting outputs the final good
            let has_dyeing = this.operations.some(o => o.type === 'dyeing');

            if (!has_dyeing) {
                let fg = this.fg_item_select ? this.fg_item_select.get_value() : '';
                let display = fg;
                if (fg && this.fg_item_name) {
                    display = `${fg} : ${this.fg_item_name}`;
                }
                $card.find('.output-item-name').text(display || 'Select Final Good...');
            } else {
                // When dyeing exists, check if SFG is selected
                let sfg_ctrl = $card.data('sfg_control');
                if (sfg_ctrl && sfg_ctrl.get_value()) {
                    // SFG is selected, use sync_output_display
                    this.sync_output_display($card);
                } else {
                    // No SFG selected yet, show prompt
                    $card.find('.output-item-name').text('Select SFG...');
                }
            }
        }

        render_op_card(type, step_num) {
            let title = frappe.unscrub(type);
            let theme_class = `card-${type.replace('_', '-')}`;
            let is_yarn = type === 'yarn_processing';
            let is_knit = type === 'knitting';
            let is_dye = type === 'dyeing';

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

                                    ${is_knit || is_yarn ? `
                                    <div class="mb-4 sfg-output-section">
                                        <label class="small text-muted mb-2">Target Output (SFG)</label>
                                        <div class="sfg-output-target"></div>
                                    </div>
                                    ` : ''}

                                    ${is_knit ? `
                                    <div class="mb-4">
                                        <label class="small text-muted mb-2">Workstation Type</label>
                                        <div class="workstation-type-target"></div>
                                    </div>
                                    ` : ''}

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
                                    fieldname: 'sfg_item',
                                    fieldtype: 'Link',
                                    options: 'Item',
                                    placeholder: 'SFG Item...',
                                    read_only: 0,
                                    change: () => {
                                        let val = ctrl.get_value();
                                        console.log("SFG Item changed to:", val);
                                        if (val) {
                                            // Set interim display
                                            this.sync_output_display($card);
                                            this.sync_dyeing();
                                            frappe.db.get_value('Item', val, 'item_name').then(r => {
                                                console.log("Fetched SFG Name Response:", r);
                                                let name_val = '';
                                                if (r && r.message) {
                                                    name_val = typeof r.message === 'object' ? r.message.item_name : r.message;
                                                } else if (r && r.item_name) {
                                                    name_val = r.item_name;
                                                }
                                                $card.data('item_name', name_val);
                                                this.sync_output_display($card);
                                                this.sync_dyeing();
                                            }).catch(e => {
                                                console.error("Error fetching SFG name:", e);
                                                this.sync_output_display($card);
                                                this.sync_dyeing();
                                            });
                                        } else {
                                            $card.data('item_name', '');
                                            this.sync_output_display($card);
                                            this.sync_dyeing();
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
                            console.error("SFG Control Exception:", e);
                        }
                    }
                }, 100);

                // Initialize Workstation Type Selector (specifically for knitting)
                if (is_knit) {
                    setTimeout(() => {
                        let ws_target = $card.find('.workstation-type-target');
                        if (ws_target.length) {
                            try {
                                let ws_ctrl = frappe.ui.form.make_control({
                                    df: {
                                        fieldname: 'workstation_type',
                                        fieldtype: 'Link',
                                        options: 'Workstation Type',
                                        placeholder: 'Select Workstation Type...',
                                        read_only: 0,
                                        default: 'Knitting in-house'
                                    },
                                    parent: ws_target[0],
                                    render_input: true
                                });
                                if (ws_ctrl) {
                                    ws_ctrl.make();
                                    ws_ctrl.refresh();
                                    ws_ctrl.set_value('Knitting in-house');
                                    $card.data('ws_control', ws_ctrl);
                                }
                            } catch (e) {
                                console.error("Workstation Type Control Exception:", e);
                            }
                        }
                    }, 100);
                }
            }

            this.add_input_row($card); // Add initial row
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
                                fieldname: 'input_item',
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
                        console.error("Input Item Control Exception:", e);
                    }
                }
            }, 100);

            $list.append($row);
        }

        remove_input_row($row) {
            let $card = $row.closest('.op-card');
            let $list = $card.find('.inputs-list');
            let row_count = $list.find('.input-row-mini').length;

            // Ensure at least one row remains
            if (row_count <= 1) {
                frappe.msgprint('At least one input item is required');
                return;
            }

            // Remove the row
            $row.remove();

            // Recalculate quantities
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
            // Update all knitting operations to show final good when no dyeing exists
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

        get_operation_output_item(type, $card, final_good, sfg_ctrl) {
            // For dyeing, always use final good
            if (type === 'dyeing') {
                return final_good;
            }

            // For knitting, check if dyeing exists
            let has_dyeing = this.operations.some(o => o.type === 'dyeing');

            if (type === 'knitting' && !has_dyeing) {
                // If no dyeing operation, knitting outputs the final good
                return final_good;
            }

            // Otherwise use the SFG control value
            return sfg_ctrl ? sfg_ctrl.get_value() : $card.find('.sfg-output-target .form-control').val();
        }

        get_data() {
            let data = {
                final_good: this.fg_item_select ? this.fg_item_select.get_value() : null,
                final_qty: flt(this.page.main.find('.final-qty').val()),
                operations: []
            };

            this.page.main.find('.op-card-wrapper').each((i, el) => {
                let $card = $(el);
                let op_ref = this.operations[i];
                if (!op_ref) return;

                let type = op_ref.type;
                let sfg_ctrl = $card.data('sfg_control');
                let ws_ctrl = $card.data('ws_control');
                let op_data = {
                    type: type,
                    is_job_work: $card.find('.chk-job-work').prop('checked'),
                    loss_percent: flt($card.find('.input-loss').val()),
                    output_item: this.get_operation_output_item(type, $card, data.final_good, sfg_ctrl),
                    output_qty: flt($card.find('.output-qty-display .val').text()),
                    workstation_type: type === 'dyeing' ? 'Dyeing Job Work' : (ws_ctrl ? ws_ctrl.get_value() : $card.find('.workstation-type-target .form-control').val()),
                    inputs: []
                };

                $card.find('.input-row-mini').each((_, rel) => {
                    let $row = $(rel);
                    let ctrl = $row.data('control');

                    console.log(`- Input Row: item=${ctrl ? ctrl.get_value() : '?'}, mix=${$row.find('.input-mix').val()}`);

                    op_data.inputs.push({
                        item: ctrl ? ctrl.get_value() : $row.find('.item-link-target .form-control').val(),
                        mix: flt($row.find('.input-mix').val()),
                        qty: flt($row.find('.row-qty-display .val').text())
                    });
                });

                console.log(`Collected data for Stage ${i + 1} (${type}):`, op_data);
                data.operations.push(op_data);
            });

            console.log("Final payload for BOM creation:", data);
            return data;
        }

        create_bom() {
            let data = this.get_data();
            if (!data.final_good) {
                frappe.msgprint("Please select Final Good");
                return;
            }
            if (!data.operations.length) {
                frappe.msgprint("Please add at least one stage");
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
                            if (this.return_to === 'production_wizard' && this.sales_order_item) {
                                // Link BOM to Sales Order Item
                                let bom_name = r.message.name;
                                if (bom_name) {
                                    frappe.call({
                                        method: 'kniterp.api.production_wizard.update_so_item_bom',
                                        args: {
                                            sales_order_item: this.sales_order_item,
                                            bom_no: bom_name
                                        },
                                        callback: () => {
                                            frappe.set_route('production_wizard', { selected_item: this.sales_order_item });
                                        }
                                    });
                                } else {
                                    // Fallback
                                    frappe.set_route('production_wizard', { selected_item: this.sales_order_item });
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
