document.addEventListener('keydown', function(e) {
	if (e.key !== 'Escape') return;

	// Let Frappe close dialogs/modals
	if (cur_dialog) return;
	if ($('.modal.show').length > 0) return;

	// Let Frappe close grid rows
	if ($('.grid-row-open').length > 0) return;

	// Let Bootstrap close dropdowns
	if ($('.dropdown-menu.show').length > 0) return;

	// Let Frappe blur focused inputs first
	var ae = document.activeElement;
	if (ae && ['INPUT', 'TEXTAREA', 'SELECT'].indexOf(ae.tagName) !== -1) return;
	if (ae && ae.contentEditable === 'true') return;

	// Don't navigate if no history
	if (frappe.route_history.length <= 1) return;

	window.history.back();
}, true);
