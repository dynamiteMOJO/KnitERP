// Override "+ Add Sales Order" to redirect to Transaction Desk
frappe.listview_settings['Sales Order'] = Object.assign(
    frappe.listview_settings['Sales Order'] || {},
    {
        primary_action: function () {
            frappe.set_route('transaction-desk', { type: 'sales-order' });
        },
    }
);
