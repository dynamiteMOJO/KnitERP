// Override "+ Add Purchase Order" to redirect to Transaction Desk
frappe.listview_settings['Purchase Order'] = Object.assign(
    frappe.listview_settings['Purchase Order'] || {},
    {
        primary_action: function () {
            frappe.set_route('transaction-desk', { type: 'purchase-order' });
        },
    }
);
