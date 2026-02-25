"""
Seed comprehensive test items covering all Busy data patterns.

Run via:
    bench --site erp16.localhost execute kniterp.api.seed_test_items.seed_test_items
"""

import frappe


# Test items covering all patterns from the Busy data analysis.
# Format: (item_code, item_name, item_group)
# item_group: "Knitted Fabrics" for fabric, "Yarn" for yarn

TEST_ITEMS = [
    # ── Basic patterns (count + fiber + structure + state) ──
    ("YR-30-CTN-RAW", "30's Cotton Yarn Raw", "Raw Material"),
    ("YR-30-CTN-DYED", "30's Cotton Yarn Dyed", "Raw Material"),
    ("YR-24-CTN-RAW", "24's Cotton Yarn Raw", "Raw Material"),
    ("YR-40-CTN-RAW", "40's Cotton Yarn Raw", "Raw Material"),
    ("YR-20-CTN-RAW", "20's Cotton Yarn Raw", "Raw Material"),

    # ── Fiber variations ──
    ("FB-30-CTN-SJ-RAW", "30's Cotton S/Jersey Raw", "Raw Material"),
    ("FB-30-CTN-SJ-DYED", "30's Cotton S/Jersey Dyed", "Raw Material"),
    ("FB-30-PC-SJ-RAW", "30's P.C. S/Jersey Raw", "Raw Material"),
    ("FB-24-PC-SJ-RAW", "24's P.C. S/Jersey Raw", "Raw Material"),
    ("FB-30-VIS-SJ-RAW", "30's Viscose S/Jersey Raw", "Raw Material"),
    ("FB-30-CM-SJ-RAW", "30's Ctn. Modal S/Jersey Raw", "Raw Material"),
    ("FB-30-CL-SJ-RAW", "30's Ctn. Linen S/Jersey Raw", "Raw Material"),
    ("FB-30-PV-SJ-RAW", "30's P.V. S/Jersey Raw", "Raw Material"),

    # ── Modifier variations ──
    ("FB-30-CTN-SLB-SJ-RAW", "30's Cotton Slub S/Jersey Raw", "Raw Material"),
    ("FB-30-CTN-SLB-SJ-DYED", "30's Cotton Slub S/Jersey Dyed", "Raw Material"),
    ("FB-30-CTN-SNW-SJ-RAW", "30's Cotton Snow Slub S/Jersey Raw", "Raw Material"),
    ("FB-30-CTN-MEL-SJ-RAW", "30's Cotton Melange S/Jersey Raw", "Raw Material"),
    ("FB-30-CTN-NEP-SJ-RAW", "30's Cotton Neps S/Jersey Raw", "Raw Material"),
    ("FB-30-CTN-CPT-SJ-RAW", "30's Cotton Compact S/Jersey Raw", "Raw Material"),
    ("FB-30-CTN-SPK-SJ-RAW", "30's Cotton Sparkle S/Jersey Raw", "Raw Material"),
    ("FB-30-CTN-NEG-SJ-RAW", "30's Cotton Negative S/Jersey Raw", "Raw Material"),
    ("FB-30-CTN-GLT-SJ-RAW", "30's Cotton Glitter S/Jersey Raw", "Raw Material"),

    # ── Structure variations ──
    ("FB-30-CTN-1X1-RAW", "30's Cotton 1x1 Rib Raw", "Raw Material"),
    ("FB-30-CTN-2X1-RAW", "30's Cotton 2x1 Rib Raw", "Raw Material"),
    ("FB-30-CTN-TERRY-RAW", "30's Cotton Terry Raw", "Raw Material"),
    ("FB-30-CTN-2TH-RAW", "30's Cotton 2Th. Terry Raw", "Raw Material"),
    ("FB-30-CTN-3TH-RAW", "30's Cotton 3Th. Terry Raw", "Raw Material"),
    ("FB-30-CTN-FLEECE-RAW", "30's Cotton Fleece Raw", "Raw Material"),
    ("FB-30-CTN-ILOCK-RAW", "30's Cotton Interlock Raw", "Raw Material"),
    ("FB-30-CTN-PIQ-RAW", "30's Cotton Pique Raw", "Raw Material"),
    ("FB-30-CTN-WAFFLE-RAW", "30's Cotton Waffle Raw", "Raw Material"),
    ("FB-30-CTN-JACQ-RAW", "30's Cotton Jacquard Raw", "Raw Material"),
    ("FB-30-CTN-DGNL-RAW", "30's Cotton Diagonal Raw", "Raw Material"),
    ("FB-30-CTN-THERM-RAW", "30's Cotton Thermal Raw", "Raw Material"),
    ("FB-30-CTN-DN-RAW", "30's Cotton Drop Needle Raw", "Raw Material"),
    ("FB-30-CTN-FK-RAW", "30's Cotton Flat Knit Raw", "Raw Material"),

    # ── Lycra variations ──
    ("FB-30-CTN-SJ-LY20-RAW", "30's Cotton S/Jersey Lycra 20Dn Raw", "Raw Material"),
    ("FB-30-CTN-SJ-LY40-RAW", "30's Cotton S/Jersey Lycra 40Dn Raw", "Raw Material"),
    ("FB-30-CTN-2X1-LY-RAW", "30's Cotton 2x1 Rib Lycra Raw", "Raw Material"),
    ("FB-30-CTN-2X1-LY-DYED", "30's Cotton 2x1 Rib Lycra Dyed", "Raw Material"),
    ("FB-24-CTN-2X1-LY-RAW", "24's Cotton 2x1 Rib Lycra Raw", "Raw Material"),

    # ── Multi-count patterns (from Busy: 24+24+10's, 24+50+10, etc.) ──
    ("FB-24+24+10-CTN-3TH-DYED", "24+24+10's Cotton 3Th. Terry Dyed", "Raw Material"),
    ("FB-24+24+24-CM-3TH-RAW", "24+24+24 Ctn. Modal 3Th. Terry Raw", "Raw Material"),
    ("FB-24+24+2X10-CTN-TRY-DYED", "24+24+2x10 Cotton Terry Dyed", "Raw Material"),
    ("FB-24+50+10-PC-TRY", "24+50+10 P.C. Terry", "Raw Material"),
    ("FB-20+20+10-CTN-3TH-RAW", "20+20+10's Ctn. 3Th. Terry Raw", "Raw Material"),
    ("FB-24+70DN-2X1-LY-RAW", "24+70Dn 2x1 Rib Lycra Raw", "Raw Material"),

    # ── Quality modifier + fiber ──
    ("FB-30-ORG-CTN-SJ-RAW", "30's Org. Cotton S/Jersey Raw", "Raw Material"),
    ("FB-30-BCI-CTN-SJ-RAW", "30's BCI Cotton S/Jersey Raw", "Raw Material"),
    ("FB-30-RCY-CTN-SJ-RAW", "30's Recycle Cotton S/Jersey Raw", "Raw Material"),
    ("FB-40-ORG-CTN-SLB-SJ-RAW", "40's Org. Cotton Slub S/Jersey Raw", "Raw Material"),

    # ── Compound abbreviation items (from Busy near-duplicates) ──
    ("FB-30-CTN-MEL-1X1", "30's Cotton Melange 1x1 Rib", "Raw Material"),
    ("FB-30-ORG-CTN-MEL-1X1", "30's Org. Cotton Melange 1x1 Rib", "Raw Material"),
    ("FB-30-PC-SNW-SJ-RAW", "30's P.C. Snow Slub S/Jersey Raw", "Raw Material"),
    ("FB-30-PC-SNW-1X1-LY-RAW", "30's P.C. Snow Slub 1x1 Rib Lycra Raw", "Raw Material"),

    # ── Process state variations ──
    ("FB-30-CTN-SJ-RFD", "30's Cotton S/Jersey Rfd", "Raw Material"),
    ("FB-30-CTN-SJ-YD", "30's Cotton S/Jersey Y/D", "Raw Material"),

    # ── Open End / Vortex variants ──
    ("FB-10-OE-CTN-SJ-RAW", "10's Open End Cotton S/Jersey Raw", "Raw Material"),
    ("FB-10-VTX-CTN-SJ-RAW", "10's Vortex Cotton S/Jersey Raw", "Raw Material"),

    # ── Yarn items ──
    ("YR-30-CTN-MEL", "30's Cotton Melange Yarn", "Raw Material"),
    ("YR-30-CTN-SLB", "30's Cotton Slub Yarn", "Raw Material"),
    ("YR-24-PC-RAW", "24's P.C. Yarn Raw", "Raw Material"),
    ("YR-24-PC-DYED", "24's P.C. Yarn Dyed", "Raw Material"),
    ("YR-40-PC-RAW", "40's P.C. Yarn Raw", "Raw Material"),
    ("YR-30-CM-RAW", "30's Ctn. Modal Yarn Raw", "Raw Material"),
    ("YR-30-CM-DYED", "30's Ctn. Modal Yarn Dyed", "Raw Material"),

    # ── Edge case items ──
    ("FB-30-CTN-TILLY-SJ", "30's Cotton Tilly Slub S/Jersey", "Raw Material"),
    ("FB-30-CTN-TINNY-SJ", "30's Cotton Tinny Slub S/Jersey", "Raw Material"),
    ("FB-30-CTN-YD-STRIPE-SJ", "30's Cotton Y/D Stripe S/Jersey", "Raw Material"),
    ("FB-60-CTN-SJ-RAW", "60's Cotton S/Jersey Raw", "Raw Material"),
    ("FB-50-PC-SJ-RAW", "50's P.C. S/Jersey Raw", "Raw Material"),
]


def seed_test_items():
    """Create test items if they don't already exist."""
    created = 0
    skipped = 0

    for item_code, item_name, item_group in TEST_ITEMS:
        if frappe.db.exists("Item", item_code):
            skipped += 1
            continue

        doc = frappe.get_doc({
            "doctype": "Item",
            "item_code": item_code,
            "item_name": item_name,
            "item_group": item_group,
            "stock_uom": "Kg",
            "is_stock_item": 1,
            "include_item_in_manufacturing": 1,
            "gst_hsn_code": "60061000",
        })
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        created += 1

    frappe.db.commit()
    msg = f"Created {created} test items, skipped {skipped} existing"
    print(msg)
    return msg
