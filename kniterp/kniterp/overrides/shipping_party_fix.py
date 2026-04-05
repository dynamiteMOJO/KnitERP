"""Monkey-patch: allow shipping to a different customer.

ERPNext's ``validate_party_address`` (accounts_controller.py) rejects
``shipping_address_name`` if it doesn't belong to the billing customer.
When ``custom_shipping_party`` is set, the shipping address intentionally
belongs to a *different* customer.  Our ``before_validate`` hook in
``kniterp.api.shipping_party`` already validates the address against
the shipping party, so we simply skip the standard shipping-address
check here.

Guard: only patches when the method signature matches what we expect.
"""

from erpnext.controllers.accounts_controller import AccountsController

_original = AccountsController.validate_party_address


def _patched_validate_party_address(self, party, party_type, billing_address, shipping_address=None):
    if self.get("custom_shipping_party") and shipping_address:
        # Validate billing address only; shipping address is validated
        # by kniterp.api.shipping_party.validate_shipping_party instead.
        _original(self, party, party_type, billing_address, None)
        return
    _original(self, party, party_type, billing_address, shipping_address)


# Guard: only apply if signature hasn't changed
import inspect as _inspect

_params = list(_inspect.signature(_original).parameters)
if _params == ["self", "party", "party_type", "billing_address", "shipping_address"]:
    AccountsController.validate_party_address = _patched_validate_party_address
else:
    import frappe

    frappe.log_error(
        title="KnitERP: shipping_party_fix patch skipped",
        message=f"Expected params ['self','party','party_type','billing_address','shipping_address'], got {_params}",
    )
