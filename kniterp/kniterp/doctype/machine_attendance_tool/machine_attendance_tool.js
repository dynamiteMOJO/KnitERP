// Copyright (c) 2026, Kartik and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Machine Attendance Tool", {
// 	refresh(frm) {

// 	},
// });

const PRESENT_OPERATORS_METHOD =
	"kniterp.kniterp.doctype.machine_attendance.machine_attendance.get_present_operators";

frappe.ui.form.on("Machine Attendance Tool", {

	prevent_duplicate_machines(frm) {
		let machines = [];
		let duplicates = [];
		// console.log("prevent duplicate machines");

		(frm.doc.entries || []).forEach((row) => {
			if (row.machine) {
				if (machines.includes(row.machine)) {
					duplicates.push(row.machine);
				} else {
					machines.push(row.machine);
				}
			}
		});

		if (duplicates.length) {
			frappe.show_alert({
				message: __("Duplicate machine not allowed: {0}", [duplicates.join(", ")]),
				indicator: "red",
			});
		}
	},

	refresh(frm) {
		frm.trigger("reset_tool_actions");
		frm.trigger("prevent_duplicate_machines");
		frm.trigger("set_employee_queries");
	},

	set_employee_queries(frm) {
		const date = frm.doc.date || "";
		frm.set_query("morning_employee", "entries", () => ({
			query: PRESENT_OPERATORS_METHOD,
			filters: { date: date, shift: "" }
		}));
		frm.set_query("night_employee", "entries", () => ({
			query: PRESENT_OPERATORS_METHOD,
			filters: { date: date, shift: "" }
		}));
	},

	onload_post_render(frm) {
		if (!frm.doc.entries || !frm.doc.entries.length) {
			frm.reload_doc();
		}
	},

	onload(frm) {
		frm.set_value("date", frappe.datetime.get_today());
	},

	date(frm) {
		frm.trigger("reset_tool_actions");
		frm.trigger("set_employee_queries");
	},
	
	entries_add(frm, cdt, cdn) {
		// console.log("entries add");
		frm.trigger("prevent_duplicate_machines");
	},

	entries_remove(frm, cdt, cdn) {
		// console.log("entries remove");
		frm.trigger("prevent_duplicate_machines");
	},

	reset_tool_actions(frm) {
		frm.disable_save();

		// Set primary action button
		frm.page.set_primary_action(
			__("Generate Attendance"),
			() => frm.trigger("generate_attendance")
		);
	},

	// === PRIMARY ACTION ===
	generate_attendance(frm) {
		if (!frm.doc.date) {
			frappe.throw({
				message: __("Please select a date."),
				title: __("Mandatory"),
			});
		}

		if (!frm.doc.entries || !frm.doc.entries.length) {
			frappe.throw({
				message: __("No machine entries found."),
				title: __("Nothing to Generate"),
			});
		}

		frappe
			.call({
				method:
					"kniterp.kniterp.doctype.machine_attendance_tool.machine_attendance_tool.generate_attendance",
				args: {
					date: frm.doc.date,
					company: frm.doc.company,
					entries: frm.doc.entries,
				},
				freeze: true,
				freeze_message: __("Generating Machine Attendance"),
			})
			.then((r) => {
				if (!r.exc) {
					frappe.show_alert({
						message: __("Machine Attendance generated successfully"),
						indicator: "green",
					});
				}
			});
	},

	
});