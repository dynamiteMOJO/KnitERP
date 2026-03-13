import frappe
from frappe import _
from frappe.utils import getdate, add_days, get_first_day, get_last_day
import calendar

from kniterp.payroll import (
    get_sunday_pay,
    get_dual_shift_days,
    get_machine_extra_pay,
    get_conveyance,
    get_rejected_holiday_days,
)

MONTH_MAP = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}

def _get_machine_extra_rate():
    from kniterp.kniterp.doctype.kniterp_settings.kniterp_settings import KnitERPSettings
    return KnitERPSettings.get_settings().machine_extra_rate or 150


def execute(filters=None):
    if not filters:
        return [], []

    month_num = MONTH_MAP.get(filters.get("month"))
    year = int(filters.get("year"))
    if not month_num or not year:
        return [], []

    start_date = getdate(f"{year}-{month_num:02d}-01")
    days_in_month = calendar.monthrange(year, month_num)[1]
    end_date = getdate(f"{year}-{month_num:02d}-{days_in_month:02d}")

    employees = get_employees(filters)
    if not employees:
        return get_columns(), []

    emp_ids = [e.name for e in employees]

    attendance_map = get_attendance_summary(emp_ids, start_date, end_date)
    salary_slip_map = get_salary_slip_data(emp_ids, start_date, end_date)
    ssa_map = get_ssa_data(emp_ids, start_date)
    holidays_map = get_holiday_count_map(emp_ids, start_date, end_date)

    data = []
    for emp in employees:
        eid = emp.name
        att = attendance_map.get(eid, {})
        ss = salary_slip_map.get(eid, {})
        ssa = ssa_map.get(eid, {})
        base = ssa.get("base", 0) if ssa else 0
        variable = ssa.get("variable", 0) if ssa else 0
        has_slip = bool(ss)

        sunday_pays = get_sunday_pay(eid, start_date, end_date)
        dual_shifts = get_dual_shift_days(eid, start_date, end_date)
        machine_pay = get_machine_extra_pay(eid, start_date, end_date)
        conveyance_amt, conveyance_km = get_conveyance(eid, start_date, end_date)
        rejected = get_rejected_holiday_days(eid, start_date, end_date)
        festivals = get_festival_count(eid, start_date, end_date)

        extra_machines = machine_pay // _get_machine_extra_rate() if machine_pay else 0

        per_day_salary = int(base / days_in_month) if days_in_month else 0

        if has_slip:
            payable_days = ss.get("payment_days", 0)
            tea = get_component_value(ss, "Tea Allowance")
            payable_salary = ss.get("net_pay", 0)
            per_day_salary = ss.get("custom_per_day_salary", 0) or per_day_salary
        else:
            total_holidays = holidays_map.get(eid, 0)
            absent = att.get("Absent", 0)
            payable_days = days_in_month - absent - rejected
            tea_days = payable_days - rejected
            tea = min(tea_days * (variable / days_in_month), variable) if variable and days_in_month else 0

            payable_salary = (
                per_day_salary * payable_days
                + sunday_pays * per_day_salary
                + dual_shifts * per_day_salary
                + machine_pay
                + conveyance_amt
                + tea
                - rejected * per_day_salary
            )

        row = {
            "employee": eid,
            "employee_name": emp.employee_name,
            "absence": att.get("Absent", 0),
            "presence": att.get("Present", 0),
            "overtime": dual_shifts,
            "half_day": att.get("Half Day", 0),
            "sunday_rejected": rejected,
            "paid_leave": att.get("On Leave", 0),
            "festival": festivals,
            "days_in_month": days_in_month,
            "sunday_pay": sunday_pays,
            "double_mc": extra_machines,
            "double_mc_amt": machine_pay,
            "tea": tea,
            "km": conveyance_km,
            "conveyance": conveyance_amt,
            "payable_days": payable_days,
            "basic_salary": base,
            "per_day_salary": per_day_salary,
            "payable_salary": payable_salary,
            "salary_slip": ss.get("name", "") if has_slip else "",
        }
        data.append(row)

    return get_columns(), data


def get_employees(filters):
    emp_filters = {"status": "Active"}
    if filters.get("employee"):
        emp_filters["name"] = filters["employee"]

    return frappe.get_all(
        "Employee",
        filters=emp_filters,
        fields=["name", "employee_name"],
        order_by="name",
    )


def get_attendance_summary(emp_ids, start, end):
    rows = frappe.db.sql("""
        SELECT employee, status, COUNT(*) as cnt
        FROM `tabAttendance`
        WHERE employee IN %s
        AND attendance_date BETWEEN %s AND %s
        AND docstatus = 1
        GROUP BY employee, status
    """, (emp_ids, start, end), as_dict=True)

    result = {}
    for r in rows:
        result.setdefault(r.employee, {})[r.status] = r.cnt
    return result


def get_salary_slip_data(emp_ids, start, end):
    slips = frappe.get_all(
        "Salary Slip",
        filters={
            "employee": ["in", emp_ids],
            "start_date": start,
            "end_date": end,
            "docstatus": ["in", [0, 1]],
        },
        fields=[
            "name", "employee", "payment_days", "total_working_days",
            "absent_days", "custom_per_day_salary",
            "net_pay", "gross_pay",
        ],
    )

    result = {}
    for s in slips:
        result[s.employee] = s
        s["_earnings"] = {}
        earnings = frappe.get_all(
            "Salary Detail",
            filters={"parent": s.name, "parentfield": "earnings"},
            fields=["salary_component", "amount"],
        )
        for e in earnings:
            s["_earnings"][e.salary_component] = e.amount

    return result


def get_ssa_data(emp_ids, start):
    rows = frappe.db.sql("""
        SELECT ssa.employee, ssa.base, ssa.variable
        FROM `tabSalary Structure Assignment` ssa
        INNER JOIN (
            SELECT employee, MAX(from_date) as max_date
            FROM `tabSalary Structure Assignment`
            WHERE employee IN %s AND from_date <= %s AND docstatus = 1
            GROUP BY employee
        ) latest ON ssa.employee = latest.employee AND ssa.from_date = latest.max_date
        WHERE ssa.docstatus = 1
    """, (emp_ids, start), as_dict=True)

    return {r.employee: {"base": r.base, "variable": r.variable or 0} for r in rows}


def get_holiday_count_map(emp_ids, start, end):
    result = {}
    for eid in emp_ids:
        holiday_list = frappe.get_value("Employee", eid, "holiday_list")
        if not holiday_list:
            result[eid] = 0
            continue
        count = frappe.db.count("Holiday", {
            "parent": holiday_list,
            "holiday_date": ["between", [start, end]],
        })
        result[eid] = count
    return result


def get_festival_count(employee, start, end):
    holiday_list = frappe.get_value("Employee", employee, "holiday_list")
    if not holiday_list:
        return 0

    holidays = frappe.get_all(
        "Holiday",
        filters={"parent": holiday_list, "holiday_date": ["between", [start, end]]},
        pluck="holiday_date",
    )

    count = 0
    for h in holidays:
        if getdate(h).weekday() != 6:
            count += 1
    return count


def get_component_value(ss, component_name):
    if not ss or "_earnings" not in ss:
        return 0
    return ss["_earnings"].get(component_name, 0)


def get_columns():
    return [
        {"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link",
         "options": "Employee", "width": 100},
        {"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 120},
        {"fieldname": "absence", "label": _("Absence"), "fieldtype": "Int", "width": 70},
        {"fieldname": "presence", "label": _("Presence"), "fieldtype": "Int", "width": 75},
        {"fieldname": "overtime", "label": _("Over Time"), "fieldtype": "Int", "width": 75},
        {"fieldname": "half_day", "label": _("Half Day"), "fieldtype": "Int", "width": 75},
        {"fieldname": "sunday_rejected", "label": _("Sunday Rejected"), "fieldtype": "Int", "width": 80},
        {"fieldname": "paid_leave", "label": _("Paid Leave"), "fieldtype": "Int", "width": 75},
        {"fieldname": "festival", "label": _("Festival"), "fieldtype": "Int", "width": 70},
        {"fieldname": "days_in_month", "label": _("Days In Month"), "fieldtype": "Int", "width": 70},
        {"fieldname": "sunday_pay", "label": _("Sunday Pay"), "fieldtype": "Float", "width": 80,
         "precision": 1},
        {"fieldname": "double_mc", "label": _("Double M/C"), "fieldtype": "Int", "width": 80},
        {"fieldname": "double_mc_amt", "label": _("Double M/C Amt"), "fieldtype": "Currency", "width": 95},
        {"fieldname": "tea", "label": _("Tea"), "fieldtype": "Currency", "width": 80},
        {"fieldname": "km", "label": _("Km"), "fieldtype": "Float", "width": 60},
        {"fieldname": "conveyance", "label": _("Conv."), "fieldtype": "Currency", "width": 80},
        {"fieldname": "payable_days", "label": _("Payable Days"), "fieldtype": "Float", "width": 80,
         "precision": 1},
        {"fieldname": "basic_salary", "label": _("Basic Salary"), "fieldtype": "Currency", "width": 95},
        {"fieldname": "per_day_salary", "label": _("Per Day Salary"), "fieldtype": "Currency", "width": 95},
        {"fieldname": "payable_salary", "label": _("Payable Salary"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "salary_slip", "label": _("Salary Slip"), "fieldtype": "Link",
         "options": "Salary Slip", "width": 120},
    ]
