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

            // Check for pre-populated item from URL
            const url_params = new URLSearchParams(window.location.search);
            this.initial_item = url_params.get('item_code');

            this.setup_ui();
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
                                    // Set interim display while fetching name
                                    this.sync_dyeing();
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
                                    }).catch(e => {
                                        console.error("Error fetching FG name:", e);
                                        this.sync_dyeing();
                                    });
                                } else {
                                    this.fg_item_name = '';
                                    this.sync_dyeing();
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
            let step_num = this.operations.length + 1;
            let op = {
                type: type,
                $el: this.render_op_card(type, step_num)
            };

            if (this.operations.length > 0) {
                this.page.main.find('.workflow-stack').append('<div class="arrow-icon"><i class="fa fa-chevron-down"></i></div>');
            }

            this.operations.push(op);
            this.page.main.find('.workflow-stack').append(op.$el);
            this.update_buttons_visibility();

            if (type === 'dyeing') this.sync_dyeing();

            this.calculate_quantities();
        }

        remove_operation(idx) {
            let $wrappers = this.page.main.find('.op-card-wrapper');
            let $arrow = $wrappers.eq(idx).prev('.arrow-icon');
            if ($arrow.length === 0) $arrow = $wrappers.eq(idx).next('.arrow-icon');

            $wrappers.eq(idx).remove();
            $arrow.remove();
            this.operations.splice(idx, 1);
            this.update_buttons_visibility();
            this.renumber_steps();
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
                                    <div class="mb-4">
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
                <div class="input-row-mini mb-3">
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

        sync_output_display($card) {
            let item = $card.find('.sfg-output-target .form-control').val();
            let name = $card.data('item_name');
            let display = item;
            if (item && name) {
                display = `${item} : ${name}`;
            }
            $card.find('.output-item-name').text(display || 'Select SFG...');
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
                    output_item: type === 'dyeing' ? data.final_good : (sfg_ctrl ? sfg_ctrl.get_value() : $card.find('.sfg-output-target .form-control').val()),
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
                            frappe.set_route('List', 'BOM', { item: data.final_good });
                        }
                    }
                });
            });
        }
    }

    new BomDesigner(wrapper, page);
};
