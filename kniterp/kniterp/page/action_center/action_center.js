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
                    // Create a fresh copy to avoid mutation of cached DOM data
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
                    // Create a fresh copy to avoid mutation of cached DOM data
                    frappe.route_options = JSON.parse(JSON.stringify(options));
                }
                frappe.set_route(link);
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

        // Order of cards
        const order = [
            'rm_shortage',
            'knitting_pending',
            'send_to_job_worker',
            'receive_from_job_worker',
            'receive_rm_from_customer',
            'pending_delivery',
            'pending_invoice'
        ];

        order.forEach(key => {
            const data = actions[key];
            if (data && data.count > 0) {
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

        // Count Badge Logic
        const badge_class = `badge-${data.color || 'secondary'}`;
        const status_class = `status-${data.color || 'secondary'}`;

        // Define default links for View All based on type if not passed
        // For the first two cards, we link to Production Wizard with filters
        let view_all_link = '';
        let view_all_options = '';

        if (data.label === 'Raw Material Shortage') {
            view_all_link = 'production-wizard';
            view_all_options = JSON.stringify({ 'materials_status': 'Shortage' });
        } else if (data.label === 'Ready for Knitting') {
            view_all_link = 'production-wizard';
            view_all_options = JSON.stringify({ 'materials_status': 'Ready' });
        }

        return `
            <div class="action-card ${status_class}">
                <div class="card-header">
                    <div class="card-title">
                        ${data.label}
                        <span class="card-badge ${badge_class}">${data.count}</span>
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
                        View Action Items
                    </button>
                </div>
                ` : ''}
            </div>
        `;
    }
}
