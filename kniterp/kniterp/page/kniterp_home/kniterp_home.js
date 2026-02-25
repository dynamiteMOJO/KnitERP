frappe.pages['kniterp-home'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __('Home'),
        single_column: true
    });

    frappe.kniterp_home = new KniterpHome(wrapper, page);
}

frappe.pages['kniterp-home'].on_page_refresh = function (wrapper) {
    if (frappe.kniterp_home) {
        frappe.kniterp_home.refresh();
    }
}

class KniterpHome {
    constructor(wrapper, page) {
        this.wrapper = wrapper;
        this.page = page;
        this.body = this.page.main;
        this.setup_page();
    }

    setup_page() {
        let greeting = "Good Morning";
        const hour = new Date().getHours();
        if (hour >= 12 && hour < 17) {
            greeting = "Good Afternoon";
        } else if (hour >= 17) {
            greeting = "Good Evening";
        }

        this.body.html(`
<div class="kniterp-home-container">
    <div class="kniterp-header">
        <div class="greeting-wrapper">
            <h1 class="greeting-text"><span id="greeting-time">${greeting}</span>, <span id="user-first-name">User</span></h1>
            <p class="sub-greeting">Here's what's happening with your business today.</p>
        </div>
        <button class="btn btn-primary show-reports-btn">Show Reports</button>
    </div>

    <div class="dashboard-grid">
        <!-- Sales Card -->
        <div class="dashboard-card sales-card">
            <div class="card-header">
                <div class="icon-bg icon-sales">
                    <i class="fa fa-shopping-cart"></i>
                </div>
                <span class="card-title">Sales</span>
                <button class="btn-create" data-doctype="Sales Order">
                    <i class="fa fa-plus"></i>
                </button>
            </div>
            <div class="card-body">
                <div class="metric-row">
                    <div class="metric-block" data-action="sales-active">
                        <div class="metric-value" id="sales-active-orders">0</div>
                        <div class="metric-label">Active Orders</div>
                    </div>
                    <div class="metric-block" data-action="sales-fy">
                        <div class="metric-value" id="sales-fy-orders">0</div>
                        <div class="metric-label">Orders this FY</div>
                    </div>
                </div>
                <div class="urgent-row" data-action="sales-urgent">
                    <span class="urgent-text"><i class="fa fa-exclamation-circle"></i> <span
                            id="sales-urgent-count">0</span>&nbsp;Urgent</span>
                    <a href="#" class="view-all" data-action="sales-view-all">View All</a>
                </div>
            </div>
        </div>

        <!-- Purchase Card -->
        <div class="dashboard-card purchase-card">
            <div class="card-header">
                <div class="icon-bg icon-purchase">
                    <i class="fa fa-shopping-bag"></i>
                </div>
                <span class="card-title">Purchase</span>
                <button class="btn-create" data-doctype="Purchase Order">
                    <i class="fa fa-plus"></i>
                </button>
            </div>
            <div class="card-body">
                <div class="metric-row">
                    <div class="metric-block" data-action="purchase-pending">
                        <div class="metric-value" id="purchase-pending-orders">0</div>
                        <div class="metric-label">Pending Orders</div>
                    </div>
                    <div class="metric-block" data-action="purchase-fy">
                        <div class="metric-value" id="purchase-fy-orders">0</div>
                        <div class="metric-label">Orders this FY</div>
                    </div>
                </div>
                <div class="urgent-row" data-action="purchase-urgent">
                    <span class="urgent-text"><i class="fa fa-exclamation-circle"></i> <span
                            id="purchase-urgent-count">0</span>&nbsp;Urgent</span>
                    <a href="#" class="view-all" data-action="purchase-view-all">View All</a>
                </div>
            </div>
        </div>

        <!-- Job Work Card -->
        <div class="dashboard-card job-work-card">
            <div class="card-header">
                <div class="icon-bg icon-jobwork">
                    <i class="fa fa-users"></i>
                </div>
                <span class="card-title">Job Work</span>
            </div>
            <div class="card-body jw-body">
                <div class="jw-column">
                    <div class="jw-label">Inward</div>
                    <div class="metric-block" data-action="jw-inward">
                        <div class="metric-value" id="jw-inward-count">0</div>
                        <div class="metric-label">Active Jobs</div>
                    </div>
                    <a href="#" class="view-all" data-action="jw-inward-view-all">View All</a>
                </div>
                <div class="jw-divider"></div>
                <div class="jw-column">
                    <div class="jw-label">Outward</div>
                    <div class="metric-block" data-action="jw-outward">
                        <div class="metric-value" id="jw-outward-count">0</div>
                        <div class="metric-label">Active Jobs</div>
                    </div>
                    <a href="#" class="view-all" data-action="jw-outward-view-all">View All</a>
                </div>
            </div>
        </div>

        <!-- Items Card -->
        <div class="dashboard-card items-card">
            <div class="card-header">
                <div class="icon-bg icon-items">
                    <i class="fa fa-cubes"></i>
                </div>
                <span class="card-title">Items</span>
                <button class="btn-create" data-doctype="Item">
                    <i class="fa fa-plus"></i>
                </button>
            </div>
            <div class="card-body">
                <div class="metric-row">
                    <div class="metric-block" data-action="items-stock">
                        <div class="metric-value" id="items-stock-count">0</div>
                        <div class="metric-label">Stock Items</div>
                    </div>
                    <div class="metric-block" data-action="items-service">
                        <div class="metric-value" id="items-service-count">0</div>
                        <div class="metric-label">Service Items</div>
                    </div>
                </div>
                <div class="card-footer">
                    <button class="btn btn-primary metric-btn" id="stock-report-btn">Stock Report</button>
                    <a href="#" class="view-all" data-action="items-view-all">View All</a>
                </div>
            </div>
        </div>

        <!-- BOM Card -->
        <div class="dashboard-card bom-card">
            <div class="card-header">
                <div class="icon-bg icon-bom">
                    <i class="fa fa-sitemap"></i>
                </div>
                <span class="card-title">BOM</span>
                <button class="btn-create" data-doctype="BOM">
                    <i class="fa fa-plus"></i>
                </button>
            </div>
            <div class="card-body">
                <div class="metric-row">
                    <div class="metric-block" data-action="bom-active">
                        <div class="metric-value" id="bom-active-count">0</div>
                        <div class="metric-label">Active BOMs</div>
                    </div>
                    <div class="metric-block" data-action="bom-jw">
                        <div class="metric-value" id="bom-jw-count">0</div>
                        <div class="metric-label">Active JW BOMs</div>
                    </div>
                </div>
                <div class="card-footer">
                    <button class="btn btn-primary metric-btn" id="show-bom-report-btn">Show Reports</button>
                    <a href="#" class="view-all" data-action="bom-view-all">View All</a>
                </div>
            </div>
        </div>

        <!-- Employees Card -->
        <div class="dashboard-card employees-card">
            <div class="card-header">
                <div class="icon-bg icon-employees">
                    <i class="fa fa-users"></i>
                </div>
                <span class="card-title">Employees</span>
                <button class="btn-create" data-tool="attendance">
                    <i class="fa fa-plus"></i>
                </button>
            </div>
            <div class="card-body">
                <div class="metric-row">
                    <div class="metric-block" data-action="employees-today">
                        <div class="metric-value" id="employees-present-count">0</div>
                        <div class="metric-label">Present Today</div>
                    </div>
                    <div class="metric-block" data-action="employees-absent">
                        <div class="metric-value" id="employees-absent-count">0</div>
                        <div class="metric-label">Absent</div>
                    </div>
                </div>
                <div class="card-footer">
                    <div class="quick-links">
                        <button class="btn btn-secondary quick-btn" data-tool="attendance">Attendance</button>
                        <button class="btn btn-secondary quick-btn" data-tool="payroll">Payroll</button>
                        <button class="btn btn-secondary quick-btn" data-tool="conveyance">Conveyance</button>
                    </div>
                    <a href="#" class="view-all" data-action="employees-view-all">View All</a>
                </div>
            </div>
        </div>
    </div>
</div>
        `);
        this.bind_events();
        this.refresh();
    }

    update_greeting() {
        let greeting = "Good Morning";
        const hour = new Date().getHours();
        if (hour >= 12 && hour < 17) {
            greeting = "Good Afternoon";
        } else if (hour >= 17) {
            greeting = "Good Evening";
        }
        this.body.find("#greeting-time").text(greeting);
    }

    refresh() {
        this.update_greeting();
        frappe.call({
            method: "kniterp.kniterp.page.kniterp_home.kniterp_home.get_dashboard_metrics",
            callback: (r) => {
                if (r.message) {
                    this.update_metrics(r.message);
                }
            }
        });
    }

    update_metrics(data) {
        // User info
        this.body.find("#user-first-name").text(data.user.first_name);

        // Sales
        this.body.find("#sales-active-orders").text(data.sales.active_orders);
        this.body.find("#sales-fy-orders").text(data.sales.orders_this_fy);
        this.body.find("#sales-urgent-count").text(data.sales.urgent_count);

        // Purchase
        this.body.find("#purchase-pending-orders").text(data.purchase.pending_orders);
        this.body.find("#purchase-fy-orders").text(data.purchase.orders_this_fy);
        this.body.find("#purchase-urgent-count").text(data.purchase.urgent_count);

        // Job Work
        this.body.find("#jw-inward-count").text(data.job_work.inward_active);
        this.body.find("#jw-outward-count").text(data.job_work.outward_active);

        // Items
        this.body.find("#items-stock-count").text(data.items.stock_items);
        this.body.find("#items-service-count").text(data.items.service_items);

        // BOM
        this.body.find("#bom-active-count").text(data.bom.active_boms);
        this.body.find("#bom-jw-count").text(data.bom.active_jw_boms);

        // Employees
        this.body.find("#employees-present-count").text(data.employees.present_today);
        this.body.find("#employees-absent-count").text(data.employees.absent_today);
    }

    bind_events() {
        const self = this;

        // Create (+) buttons
        this.body.on("click", ".btn-create", function () {
            const doctype = $(this).data("doctype");
            const tool = $(this).data("tool");

            if (doctype) {
                frappe.new_doc(doctype);
            } else if (tool === "attendance") {
                frappe.set_route("Form", "Employee Attendance Tool");
            }
        });

        // View All / Metric redirects
        this.body.on("click", ".view-all, .metric-block, .urgent-row", function (e) {
            e.preventDefault();
            const $target = $(this);
            const action = $target.data("action") || $target.closest("[data-action]").data("action");

            if (!action) return;

            if (action.startsWith("sales-")) {
                let filters = {
                    "docstatus": 1,
                    "is_subcontracted": 0,
                    "status": ["not in", ["Closed", "Completed", "Cancelled"]]
                };
                frappe.set_route("List", "Sales Order", filters);
            } else if (action.startsWith("purchase-")) {
                let filters = {
                    "docstatus": 1,
                    "is_subcontracted": 0,
                    "status": ["not in", ["Closed", "Completed", "Cancelled"]]
                };
                frappe.set_route("List", "Purchase Order", filters);
            } else if (action.startsWith("jw-")) {
                let options = {};
                if (action.includes("inward")) {
                    options.job_work = "Inward";
                } else if (action.includes("outward")) {
                    options.job_work = "Outward";
                }
                // Redirect to Production Wizard
                frappe.route_options = options;
                frappe.set_route("production-wizard");
            } else if (action === "items-view-all") {
                frappe.set_route("List", "Item");
            } else if (action === "bom-view-all") {
                frappe.set_route("List", "BOM");
            } else if (action === "employees-view-all") {
                frappe.set_route("List", "Employee");
            }
        });

        // Report Buttons
        this.body.on("click", "#stock-report-btn", function () {
            frappe.set_route("query-report", "Stock Balance");
        });

        this.body.on("click", "#show-bom-report-btn", function () {
            frappe.set_route("query-report", "BOM Stock Report");
        });

        this.body.on("click", ".show-reports-btn", function () {
            // General reports or dashboard
            frappe.set_route("List", "Report");
        });

        // Employee Quick Links
        this.body.on("click", ".quick-btn", function () {
            const tool = $(this).data("tool");
            if (tool === "attendance") {
                frappe.set_route("Form", "Employee Attendance Tool");
            } else if (tool === "payroll") {
                frappe.set_route("Workspaces", "Payroll Management");
            } else if (tool === "conveyance") {
                // Assuming Monthly Conveyance based on previous conversations maybe
                frappe.set_route("List", "Monthly Conveyance");
            }
        });
    }
}
