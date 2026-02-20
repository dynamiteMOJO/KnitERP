import frappe
from frappe import _


PRODUCTION_WRITE_ROLES = (
    "System Manager",
    "Manufacturing Manager",
    "Manufacturing User",
)

ACTION_CENTER_WRITE_ROLES = PRODUCTION_WRITE_ROLES + ("Stock Manager",)


def _get_current_user():
    session = getattr(frappe.local, "session", None)
    if session and getattr(session, "user", None):
        return session.user

    fallback = getattr(frappe, "session", None)
    return getattr(fallback, "user", None)


def has_any_role(allowed_roles):
    current_user = _get_current_user()
    if current_user == "Administrator":
        return True

    user_roles = set(frappe.get_roles())
    return bool(user_roles.intersection(set(allowed_roles)))


def require_roles(allowed_roles, operation):
    if has_any_role(allowed_roles):
        return

    allowed = ", ".join(allowed_roles)
    frappe.throw(
        _("You are not permitted to {0}. Required role: {1}").format(operation, allowed),
        frappe.PermissionError,
    )


def require_production_write_access(operation="perform this action"):
    require_roles(PRODUCTION_WRITE_ROLES, operation)


def require_action_center_write_access(operation="perform this action"):
    require_roles(ACTION_CENTER_WRITE_ROLES, operation)
