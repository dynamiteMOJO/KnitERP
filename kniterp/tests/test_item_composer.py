"""
Unit tests for item_composer.update_item_token API.

Run: bench --site erp16.localhost execute kniterp.tests.test_item_composer.run_all_tests
"""

import frappe


def _make_token(canonical, dimension, short_code, aliases=None):
    """Create a test Item Token and its canonical alias."""
    if not frappe.db.exists("Item Token", canonical):
        frappe.get_doc({
            "doctype": "Item Token",
            "canonical": canonical,
            "dimension": dimension,
            "short_code": short_code,
            "sort_order": 10,
            "is_active": 1,
        }).insert(ignore_permissions=True)
    for alias in (aliases or [canonical.lower()]):
        if not frappe.db.exists("Item Token Alias", alias):
            frappe.get_doc({
                "doctype": "Item Token Alias",
                "alias": alias,
                "canonical": canonical,
                "dimension": dimension,
                "token": canonical,
                "is_auto": 0,
            }).insert(ignore_permissions=True)
    frappe.db.commit()


def _cleanup():
    for canonical in ["TestFiber", "TestFiberRenamed", "TestFiber2"]:
        frappe.db.delete("Item Token Alias", {"canonical": canonical})
        if frappe.db.exists("Item Token", canonical):
            frappe.db.delete("Item Token", canonical)
    frappe.db.commit()


def _assert(condition, message):
    if not condition:
        raise AssertionError(message)


def test_update_short_code_only():
    from kniterp.api.item_composer import update_item_token
    _cleanup()
    _make_token("TestFiber", "fiber", "TF1", ["testfiber", "tf1"])
    result = update_item_token("TestFiber", "TestFiber", "TF2")
    _assert(result["short_code"] == "TF2", f"Expected TF2, got {result['short_code']}")
    db_code = frappe.db.get_value("Item Token", "TestFiber", "short_code")
    _assert(db_code == "TF2", f"DB short_code expected TF2, got {db_code}")
    return "PASS"


def test_update_aliases():
    from kniterp.api.item_composer import update_item_token
    _cleanup()
    _make_token("TestFiber", "fiber", "TF1", ["testfiber"])
    result = update_item_token("TestFiber", "TestFiber", "TF1", "testfiber, tf1alias")
    _assert("testfiber" in result["aliases"], "Expected 'testfiber' in aliases")
    _assert("tf1alias" in result["aliases"], "Expected 'tf1alias' in aliases")
    return "PASS"


def test_remove_alias():
    from kniterp.api.item_composer import update_item_token
    _cleanup()
    _make_token("TestFiber", "fiber", "TF1", ["testfiber", "oldname"])
    update_item_token("TestFiber", "TestFiber", "TF1", "testfiber")
    aliases = frappe.db.get_all("Item Token Alias", {"canonical": "TestFiber"}, pluck="alias")
    _assert("testfiber" in aliases, "Expected 'testfiber' to remain")
    _assert("oldname" not in aliases, "Expected 'oldname' to be removed")
    return "PASS"


def test_rename_canonical():
    from kniterp.api.item_composer import update_item_token
    _cleanup()
    _make_token("TestFiber", "fiber", "TF1", ["testfiber"])
    result = update_item_token("TestFiber", "TestFiberRenamed", "TF1", "testfiberrenamed")
    _assert(result["canonical"] == "TestFiberRenamed", f"Expected TestFiberRenamed, got {result['canonical']}")
    _assert(not frappe.db.exists("Item Token", "TestFiber"), "Old token should not exist")
    _assert(frappe.db.exists("Item Token", "TestFiberRenamed"), "New token should exist")
    alias_canonical = frappe.db.get_value(
        "Item Token Alias", {"alias": "testfiberrenamed"}, "canonical"
    )
    _assert(alias_canonical == "TestFiberRenamed", f"Alias canonical expected TestFiberRenamed, got {alias_canonical}")
    return "PASS"


def test_rename_conflict_throws():
    from kniterp.api.item_composer import update_item_token
    _cleanup()
    _make_token("TestFiber", "fiber", "TF1", ["testfiber"])
    _make_token("TestFiber2", "fiber", "TF2", ["testfiber2"])
    try:
        update_item_token("TestFiber", "TestFiber2", "TF1")
        return "FAIL — expected DuplicateEntryError not raised"
    except frappe.exceptions.DuplicateEntryError:
        return "PASS"
    except Exception as e:
        return f"FAIL — wrong exception: {type(e).__name__}: {e}"


def test_short_code_conflict_throws():
    from kniterp.api.item_composer import update_item_token
    _cleanup()
    _make_token("TestFiber", "fiber", "TF1", ["testfiber"])
    _make_token("TestFiber2", "fiber", "TF2", ["testfiber2"])
    try:
        update_item_token("TestFiber", "TestFiber", "TF2")
        return "FAIL — expected DuplicateEntryError not raised"
    except frappe.exceptions.DuplicateEntryError:
        return "PASS"
    except Exception as e:
        return f"FAIL — wrong exception: {type(e).__name__}: {e}"


def run_all_tests():
    tests = [
        ("update short code only", test_update_short_code_only),
        ("update aliases", test_update_aliases),
        ("remove alias", test_remove_alias),
        ("rename canonical", test_rename_canonical),
        ("rename conflict throws", test_rename_conflict_throws),
        ("short code conflict throws", test_short_code_conflict_throws),
    ]

    passed = 0
    failed = 0
    print("\n=== Item Composer Tests ===")
    for name, fn in tests:
        try:
            result = fn()
            status = "PASS" if result == "PASS" else result
        except Exception as e:
            status = f"FAIL — {type(e).__name__}: {e}"

        icon = "✓" if status == "PASS" else "✗"
        print(f"  {icon} {name}: {status}")
        if status == "PASS":
            passed += 1
        else:
            failed += 1

    _cleanup()
    print(f"\n{passed + failed} tests: {passed} passed, {failed} failed\n")
    return failed == 0
