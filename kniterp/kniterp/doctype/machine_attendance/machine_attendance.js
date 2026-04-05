// Copyright (c) 2026, Kartik and contributors
// For license information, please see license.txt

const PRESENT_OPERATORS_METHOD =
	"kniterp.kniterp.doctype.machine_attendance.machine_attendance.get_present_operators";

frappe.ui.form.on("Machine Attendance", {
	refresh(frm) {
		frm.trigger("set_employee_query");
	},

	date(frm) {
		frm.set_value("employee", "");
		frm.trigger("set_employee_query");
	},

	shift(frm) {
		frm.set_value("employee", "");
		frm.trigger("set_employee_query");
	},

	set_employee_query(frm) {
		frm.set_query("employee", () => ({
			query: PRESENT_OPERATORS_METHOD,
			filters: { date: frm.doc.date || "", shift: frm.doc.shift || "" }
		}));
	}
});
