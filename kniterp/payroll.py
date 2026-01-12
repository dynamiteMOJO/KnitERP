import frappe
from frappe.utils import getdate, add_days

my_logger = frappe.logger("payroll_custom_logs")

MACHINE_EXTRA_RATE = 150


def calculate_variable_pay(slip, method):
    employee = slip.employee
    start = slip.start_date
    end = slip.end_date

    per_day_salary = get_per_day_salary(slip)
    tea = get_variable_pay(employee, start)

    # reset components
    # set_component(slip, "Dual Shift Pay", 0)
    # set_component(slip, "Machine Extra Pay", 0)
    # set_component(slip, "Conveyance Allowance", 0)
    # set_component(slip, "Absent / Rejected Day Deduction", 0)

    sunday_pays = get_sunday_pay(employee, start, end)
    dual_shift_days = get_dual_shift_days(employee, start, end)
    machine_extra_pay = get_machine_extra_pay(employee, start, end)
    conveyance = get_conveyance(employee, start, end)
    rejected_days = get_rejected_holiday_days(employee, start, end)
    tea_pay = (slip.payment_days - rejected_days) * (tea / slip.total_working_days)
    set_component(slip, "Sunday Pay", sunday_pays * per_day_salary)
    set_component(slip, "Dual Shift Pay", dual_shift_days * per_day_salary)
    set_component(slip, "Machine Extra Pay", machine_extra_pay)
    set_component(slip, "Conveyance Allowance", conveyance)
    set_component(
        slip,
        "Rejected Holiday Deduction",
        rejected_days * per_day_salary
    )
    print("tea_pay:", tea_pay)
    print("per_day_salary:", per_day_salary)
    set_component(slip, "Tea Allowance", tea_pay)

    slip.calculate_net_pay()
    


def get_component_amount(slip, component_name):
    for row in slip.earnings:
        if row.salary_component == component_name:
            return row.amount or 0
    return 0


def get_per_day_salary(slip):
    ssa = frappe.get_value(
        "Salary Structure Assignment",
        {
            "employee": slip.employee,
            "from_date": ["<=", slip.start_date],
            "docstatus": 1,
        },
        ["base"],
    )

    base = ssa if ssa else 0
    tea = get_variable_pay(slip.employee, slip.start_date)
      

    # HRMS already calculates total_working_days correctly
    if not slip.total_working_days:
        return 0

    return int((base + tea) / slip.total_working_days)


def get_variable_pay(employee, start):
    tea = frappe.db.sql("""
        SELECT variable
        FROM `tabSalary Structure Assignment`
        WHERE employee=%s
        AND from_date <= %s
        ORDER BY from_date DESC
        LIMIT 1
    """, (employee, start), as_dict=True)

    return tea[0]['variable'] if tea[0]['variable'] else 0

def get_sunday_pay(employee, start, end):
    rows = frappe.db.sql("""
        SELECT distinct attendance_date
        FROM `tabAttendance`
        WHERE employee=%s
        AND attendance_date BETWEEN %s AND %s
        AND status='Present'
    """, (employee, start, end), as_dict=True)

    sunday_count = 0
    for r in rows:
        if getdate(r.attendance_date).weekday() == 6:
            sunday_count += 1

    return sunday_count

def get_dual_shift_days(employee, start, end):
    rows = frappe.db.sql("""
        SELECT attendance_date, COUNT(*) cnt
        FROM `tabAttendance`
        WHERE employee=%s
        AND attendance_date BETWEEN %s AND %s
        AND status='Present'
        GROUP BY attendance_date
        HAVING cnt > 1
    """, (employee, start, end), as_dict=True)

    return len(rows)


def get_machine_extra_pay(employee, start, end):
    rows = frappe.db.sql("""
        SELECT date, COUNT(*) cnt
        FROM `tabMachine Attendance`
        WHERE employee=%s
        AND date BETWEEN %s AND %s
        AND production_qty_kg > 30
        GROUP BY date
        HAVING cnt > 1
    """, (employee, start, end), as_dict=True)

    total_extra = 0
    for r in rows:
        extra_machines = r.cnt - 1
        total_extra += extra_machines * 150

    return total_extra


def get_conveyance(employee, month_start, month_end):
    amount  = frappe.db.sql("""
        SELECT SUM(amount) as amount
        FROM `tabMonthly Conveyance`
        WHERE employee=%s
        AND month BETWEEN %s AND %s
    """, (employee, month_start, month_end), as_dict=True)

    return amount[0]['amount'] if amount[0]['amount'] is not None else 0

def get_rejected_holiday_days(employee, start, end):
    rejected = 0

    holidays = frappe.get_all(
        "Holiday",
        filters={"holiday_date": ["between", [start, end]]},
        pluck="holiday_date"
    )

    for h in holidays:
        if is_present(employee, h):
            continue

        prev_day = add_days(h, -1)
        next_day = add_days(h, 1)

        if is_absent(employee, prev_day) and is_absent(employee, next_day):
            rejected += 1

    return rejected


def is_present(employee, date):
    return frappe.db.exists(
        "Attendance",
        {
            "employee": employee,
            "attendance_date": date,
            "status": "Present"
        }
    )


def is_absent(employee, date):
    return frappe.db.exists(
        "Attendance",
        {
            "employee": employee,
            "attendance_date": date,
            "status": "Absent"
        }
    )

def is_deduction(component):
    return frappe.get_value(
        "Salary Component", component, "type"
    ) == "Deduction"

def set_component(slip, component, amount):
    if amount==0:
        return

    comp_type = frappe.get_value("Salary Component", component, "type")
    is_deduction = comp_type == "Deduction"

    for row in slip.earnings + slip.deductions:
        if row.salary_component == component:
            row.amount = amount
            return
        
    slip.append(
        "deductions" if is_deduction else "earnings",
        {
            "salary_component": component,
            "amount": amount,
        },
    )
