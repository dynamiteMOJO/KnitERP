"""
Seed Item Token master from existing Item Token Alias canonical names.

Derives short codes from Textile Attribute Value or from canonical name.

Run via:
    bench --site erp16.localhost execute kniterp.api.seed_item_tokens.seed_item_tokens
"""

import re
import frappe


# Manual short code overrides for canonicals where auto-derivation won't work well
SHORT_CODE_MAP = {
    # Counts — use the numeric portion
    # (handled by auto-derivation: strip non-digits)

    # Fibers
    "Cotton": "CTN",
    "P.C.": "PC",
    "Polyester": "POLY",
    "Viscose": "VIS",
    "Modal": "MDL",
    "Linen": "LIN",
    "Hemp": "HEMP",
    "Tencel": "TNCL",
    "Lyocell": "LYOCL",
    "Spun Poly": "SPNP",
    "P.V.": "PV",
    "Ctn. Modal": "CM",
    "Vis. Linen": "VL",
    "Ctn. Linen": "CL",
    "Ctn. Poly": "CP",

    # Modifiers
    "Org.": "ORG",
    "BCI": "BCI",
    "Recycle": "RCY",
    "Compact": "CPT",
    "Open End": "OE",
    "Vortex": "VTX",
    "IC-2": "IC2",
    "Semi Combed": "SCMB",
    "Combed": "CMBD",
    "Carded": "CRD",
    "Gassed": "GSD",
    "Mercerized": "MRCZ",
    "Slub": "SLB",
    "Snow Slub": "SNW",
    "Tilly Slub": "TILY",
    "Tinny Slub": "TINS",
    "Neps": "NEPS",
    "Sparkle": "SPK",
    "Lurex": "LRX",
    "Negative": "NEG",
    "Glitter": "GLT",
    "Melange": "MEL",
    "Stripe": "STP",
    "Y/D Stripe": "YDST",
    "Yarn": "YRN",
    "Fabric": "FAB",

    # Structures
    "S/Jersey": "SJ",
    "1x1 Rib": "1X1",
    "2x1 Rib": "2X1",
    "3x2 Rib": "3X2",
    "3x3 Rib": "3X3",
    "2x2 Rib": "2X2",
    "6x2 Rib": "6X2",
    "7x3 Rib": "7X3",
    "9x4 Rib": "9X4",
    "Rib": "RIB",
    "Terry": "TRY",
    "2Th. Terry": "2TH",
    "3Th. Terry": "3TH",
    "Fleece": "FLC",
    "Interlock": "ILCK",
    "Pique": "PIQ",
    "Waffle": "WFL",
    "Velour": "VLR",
    "Flat Knit": "FK",
    "Drop Needle": "DN",
    "Variegated Rib": "VRG",
    "Jacquard": "JAQ",
    "Loose Knit": "LSK",
    "Papcon": "PAP",
    "Pointal": "PNT",
    "Diagonal": "DGL",
    "Thermal": "THRM",
    "Patti": "PTI",
    "Towel": "TWL",

    # Lycra
    "Lycra": "LYC",
    "20Dn": "20D",
    "40Dn": "40D",
    "70Dn": "70D",
    "80Dn": "80D",
    "150Dn": "150D",
    "30Dn": "30D",
    "50Dn": "50D",

    # States
    "Raw": "RAW",
    "Dyed": "DYED",
    "Rfd": "RFD",
    "Y/D": "YD",
    "Bleached": "BLCH",
    "Bio Wash": "BW",
}


def _derive_short_code(canonical, dimension):
    """Auto-derive a short code if not in the manual map."""
    # For counts: extract numeric portion and symbols
    if dimension == "count":
        # "30's" → "30", "2/20's" → "2/20", "2x10's" → "2X10"
        code = re.sub(r"'s$", "", canonical)  # strip trailing 's
        code = re.sub(r"[\s]", "", code).upper()
        return code

    # Fallback: first 3-4 uppercase chars
    code = re.sub(r"[^A-Za-z0-9]", "", canonical).upper()
    return code[:4] if len(code) > 4 else code


def seed_item_tokens():
    """
    Create Item Token master records from distinct canonical names
    in the Item Token Alias table.
    """
    # Get all unique canonical+dimension pairs from aliases
    canonicals = frappe.db.sql("""
        SELECT DISTINCT canonical, dimension
        FROM `tabItem Token Alias`
        WHERE canonical IS NOT NULL AND canonical != ''
        ORDER BY dimension, canonical
    """, as_dict=True)

    created = 0
    skipped = 0
    linked = 0

    for row in canonicals:
        canonical = row["canonical"]
        dimension = row["dimension"]

        # Skip if already exists
        if frappe.db.exists("Item Token", canonical):
            skipped += 1
        else:
            # Derive short code
            short_code = SHORT_CODE_MAP.get(canonical, _derive_short_code(canonical, dimension))

            doc = frappe.get_doc({
                "doctype": "Item Token",
                "canonical": canonical,
                "dimension": dimension,
                "short_code": short_code,
                "sort_order": 10,
                "is_active": 1,
            })
            doc.insert(ignore_permissions=True)
            created += 1

        # Link all aliases with this canonical to the Item Token
        frappe.db.sql("""
            UPDATE `tabItem Token Alias`
            SET token = %s
            WHERE canonical = %s AND (token IS NULL OR token = '')
        """, (canonical, canonical))
        linked += 1

    frappe.db.commit()
    msg = f"Created {created} Item Tokens, skipped {skipped} existing, linked {linked} alias groups"
    print(msg)
    return msg
