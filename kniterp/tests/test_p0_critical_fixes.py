import importlib.util
import inspect
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from kniterp.api import access_control
from kniterp.api import production_wizard
import kniterp.utils as kniterp_utils


class TestP0CriticalFixes(FrappeTestCase):
    def test_inhouse_complete_job_card_endpoint_works_and_returns_structured_response(self):
        expected = {
            "success": True,
            "job_card": "JC-0001",
            "message": "ok",
            "mode": "inhouse",
            "received_qty": None,
        }

        with (
            patch("kniterp.api.production_wizard.require_production_write_access") as guard,
            patch("kniterp.api.production_wizard._complete_job_card_inhouse", return_value=expected) as helper,
        ):
            result = production_wizard.complete_job_card("JC-0001")

        self.assertEqual(result, expected)
        guard.assert_called_once_with("complete job cards")
        helper.assert_called_once_with(
            job_card="JC-0001",
            additional_qty=0,
            process_loss_qty=0,
            wip_warehouse=None,
            skip_material_transfer=None,
            source_warehouses=None,
        )

    def test_subcontracted_complete_job_card_endpoint_uses_scr_received_qty(self):
        source = inspect.getsource(production_wizard._complete_job_card_subcontracted)
        self.assertIn("tabSubcontracting Receipt Item", source)
        self.assertIn("SUM(sri.qty)", source)
        self.assertIn("received_qty", source)

    def test_inhouse_and_subcontracted_completion_endpoints_are_distinct_and_callable(self):
        inhouse_result = {
            "success": True,
            "job_card": "JC-IN",
            "message": "inhouse",
            "mode": "inhouse",
            "received_qty": None,
        }
        subcontracted_result = {
            "success": True,
            "job_card": "JC-SUB",
            "message": "subcontracted",
            "mode": "subcontracted",
            "received_qty": 10.0,
        }

        with (
            patch("kniterp.api.production_wizard.require_production_write_access"),
            patch("kniterp.api.production_wizard._complete_job_card_inhouse", return_value=inhouse_result),
            patch("kniterp.api.production_wizard._complete_job_card_subcontracted", return_value=subcontracted_result),
        ):
            result_inhouse = production_wizard.complete_job_card("JC-IN")
            result_sub = production_wizard.complete_subcontracted_job_card("JC-SUB")

        self.assertEqual(result_inhouse["mode"], "inhouse")
        self.assertEqual(result_sub["mode"], "subcontracted")

    def test_write_api_guard_denies_non_manufacturing_roles(self):
        with (
            patch("kniterp.api.access_control._get_current_user", return_value="operator@example.com"),
            patch("frappe.get_roles", return_value=["Accounts User"]),
        ):
            with self.assertRaises(frappe.PermissionError):
                access_control.require_production_write_access("perform protected write")

    def test_write_api_guard_allows_manufacturing_roles(self):
        with (
            patch("kniterp.api.access_control._get_current_user", return_value="operator@example.com"),
            patch("frappe.get_roles", return_value=["Manufacturing User"]),
        ):
            access_control.require_production_write_access("perform protected write")

    def test_completion_flow_does_not_call_manual_commit(self):
        inhouse_source = inspect.getsource(production_wizard._complete_job_card_inhouse)
        subcontract_source = inspect.getsource(production_wizard._complete_job_card_subcontracted)

        self.assertNotIn("frappe.db.commit(", inhouse_source)
        self.assertNotIn("frappe.db.commit(", subcontract_source)

    def test_destructive_reset_utility_not_exposed_from_kniterp_utils(self):
        self.assertFalse(hasattr(kniterp_utils, "clear_all_transactions"))
        self.assertIsNone(importlib.util.find_spec("kniterp.utils.reset_transactions"))
