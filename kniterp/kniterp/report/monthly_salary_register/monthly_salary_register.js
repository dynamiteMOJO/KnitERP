frappe.query_reports["Monthly Salary Register"] = {
    after_datatable_render(datatable) {
        const wrapper = datatable.wrapper;

        // Widths matching report column definitions
        const col0Width = 100; // Employee (col-1)
        const col1Width = 120; // Name (col-2)

        // Inject a persistent style for sticky body cells
        const style = document.createElement("style");
        style.id = "msr-sticky-style";
        style.textContent = `
			.msr-sticky-col-0 {
				position: sticky !important;
				left: 0 !important;
				z-index: 1 !important;
				background: var(--card-bg, #fff) !important;
			}
			.msr-sticky-col-1 {
				position: sticky !important;
				left: ${col0Width}px !important;
				z-index: 1 !important;
				background: var(--card-bg, #fff) !important;
				box-shadow: inset -1px 0 0 var(--border-color, #d1d8dd);
			}
			.dt-row:nth-child(odd) .dt-cell {
				background-color: var(--control-bg, #f8f8f8) !important;
			}
			.dt-row:nth-child(odd) .msr-sticky-col-0,
			.dt-row:nth-child(odd) .msr-sticky-col-1 {
				background-color: var(--control-bg, #f8f8f8) !important;
			}
		`;
        wrapper.appendChild(style);

        // Mark body cells for the first two columns
        const markBodyCells = () => {
            wrapper.querySelectorAll(".dt-cell--col-1:not(.dt-cell--header)").forEach(el => {
                el.classList.add("msr-sticky-col-0");
            });
            wrapper.querySelectorAll(".dt-cell--col-2:not(.dt-cell--header)").forEach(el => {
                el.classList.add("msr-sticky-col-1");
            });
        };
        markBodyCells();

        // For headers: counteract the translateX scroll offset
        const bodyScrollable = wrapper.querySelector(".dt-scrollable");
        const headerRow = wrapper.querySelector(".dt-row-header");
        if (!bodyScrollable || !headerRow) return;

        const headerCol0 = headerRow.querySelector(".dt-cell--col-1");
        const headerCol1 = headerRow.querySelector(".dt-cell--col-2");

        if (headerCol0) {
            Object.assign(headerCol0.style, {
                position: "sticky",
                zIndex: "3",
                background: "var(--card-bg, #fff)",
            });
        }
        if (headerCol1) {
            Object.assign(headerCol1.style, {
                position: "sticky",
                zIndex: "3",
                background: "var(--card-bg, #fff)",
                boxShadow: "inset -1px 0 0 var(--border-color, #d1d8dd)",
            });
        }

        // The header is moved with translateX by DataTable's style.js bindScrollHeader.
        // We counteract that by updating left on the sticky header cells on scroll.
        bodyScrollable.addEventListener("scroll", () => {
            const scrollLeft = bodyScrollable.scrollLeft;
            if (headerCol0) headerCol0.style.left = scrollLeft + "px";
            if (headerCol1) headerCol1.style.left = scrollLeft + col0Width + "px";
        });
    },
    filters: [
        {
            fieldname: "year",
            label: __("Year"),
            fieldtype: "Select",
            options: (() => {
                let years = [];
                let cur = new Date().getFullYear();
                for (let i = cur; i >= cur - 3; i--) years.push(i);
                return years.join("\n");
            })(),
            default: new Date().getFullYear(),
            reqd: 1,
        },
        {
            fieldname: "month",
            label: __("Month"),
            fieldtype: "Select",
            options: [
                "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"
            ].join("\n"),
            default: [
                "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"
            ][new Date().getMonth() === 0 ? 11 : new Date().getMonth() - 1],
            reqd: 1,
        },
        {
            fieldname: "employee",
            label: __("Employee"),
            fieldtype: "Link",
            options: "Employee",
        },
    ],
};
