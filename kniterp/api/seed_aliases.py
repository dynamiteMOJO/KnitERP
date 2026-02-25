"""
Seed the Item Token Alias table with known abbreviations
from the Busy data analysis.

Run via bench console:
    from kniterp.api.seed_aliases import seed_all_aliases
    seed_all_aliases()
"""

import frappe


# ── Master alias data ─────────────────────────────────────────────────
# Derived from analysis of 802 real items from Busy software.
# Format: (alias, canonical, dimension)

ALIASES = [
    # ── Yarn Counts ──
    # Every count needs both "Ns" and numeric-only "N" alias
    ("10s", "10's", "count"),
    ("10", "10's", "count"),
    ("12s", "12's", "count"),
    ("12", "12's", "count"),
    ("14s", "14's", "count"),
    ("14", "14's", "count"),
    ("16s", "16's", "count"),
    ("16", "16's", "count"),
    ("18s", "18's", "count"),
    ("18", "18's", "count"),
    ("20s", "20's", "count"),
    ("20", "20's", "count"),
    ("21s", "21's", "count"),
    ("21", "21's", "count"),
    ("24s", "24's", "count"),
    ("24", "24's", "count"),
    ("25s", "25's", "count"),
    ("25", "25's", "count"),
    ("26s", "26's", "count"),
    ("26", "26's", "count"),
    ("28s", "28's", "count"),
    ("28", "28's", "count"),
    ("30s", "30's", "count"),
    ("30", "30's", "count"),
    ("32s", "32's", "count"),
    ("32", "32's", "count"),
    ("34s", "34's", "count"),
    ("34", "34's", "count"),
    ("36s", "36's", "count"),
    ("36", "36's", "count"),
    ("40s", "40's", "count"),
    ("40", "40's", "count"),
    ("44s", "44's", "count"),
    ("44", "44's", "count"),
    ("46s", "46's", "count"),
    ("46", "46's", "count"),
    ("50s", "50's", "count"),
    ("50", "50's", "count"),
    ("52s", "52's", "count"),
    ("52", "52's", "count"),
    ("54s", "54's", "count"),
    ("54", "54's", "count"),
    ("56s", "56's", "count"),
    ("56", "56's", "count"),
    ("58s", "58's", "count"),
    ("58", "58's", "count"),
    ("60s", "60's", "count"),
    ("60", "60's", "count"),
    # Ply counts (NxN multiplied format + N/N twisted format)
    ("2/20", "2/20's", "count"),
    ("2/24", "2/24's", "count"),
    ("2/30", "2/30's", "count"),
    ("2/34", "2/34's", "count"),
    ("2/40", "2/40's", "count"),
    ("2x10", "2x10's", "count"),
    ("2x20", "2x20's", "count"),
    ("2x24", "2x24's", "count"),
    ("3x10", "3x10's", "count"),
    ("3x20", "3x20's", "count"),
    ("3x24", "3x24's", "count"),

    # ── Fibers / Composition ──
    ("cotton", "Cotton", "fiber"),
    ("ctn", "Cotton", "fiber"),
    ("ctn.", "Cotton", "fiber"),
    ("coton", "Cotton", "fiber"),
    ("cottn", "Cotton", "fiber"),
    ("pc", "P.C.", "fiber"),
    ("p.c.", "P.C.", "fiber"),
    ("p.c", "P.C.", "fiber"),
    ("p/c", "P.C.", "fiber"),
    ("poly cotton", "P.C.", "fiber"),
    ("polyctn", "P.C.", "fiber"),
    ("polycotton", "P.C.", "fiber"),
    ("poly", "Polyester", "fiber"),
    ("polyester", "Polyester", "fiber"),
    ("polyster", "Polyester", "fiber"),
    ("viscose", "Viscose", "fiber"),
    ("vis", "Viscose", "fiber"),
    ("vis.", "Viscose", "fiber"),
    ("modal", "Modal", "fiber"),
    ("linen", "Linen", "fiber"),
    ("lin", "Linen", "fiber"),
    ("hemp", "Hemp", "fiber"),
    ("tencel", "Tencel", "fiber"),
    ("lyocell", "Lyocell", "fiber"),
    ("spun poly", "Spun Poly", "fiber"),
    ("spun", "Spun Poly", "fiber"),
    ("pv", "P.V.", "fiber"),
    ("p.v.", "P.V.", "fiber"),
    ("p.v", "P.V.", "fiber"),
    ("poly viscose", "P.V.", "fiber"),
    # Blend modifiers (on fiber)
    # Both dotted and undotted forms needed: undotted for user typing, dotted for item name parsing
    ("cm", "Ctn. Modal", "fiber"),
    ("c.m.", "Ctn. Modal", "fiber"),
    ("ctn.modal", "Ctn. Modal", "fiber"),
    ("ctn modal", "Ctn. Modal", "fiber"),
    ("ctn. modal", "Ctn. Modal", "fiber"),
    ("cotton modal", "Ctn. Modal", "fiber"),
    ("vis.linen", "Vis. Linen", "fiber"),
    ("vis. linen", "Vis. Linen", "fiber"),
    ("viscose linen", "Vis. Linen", "fiber"),
    ("ctn.linen", "Ctn. Linen", "fiber"),
    ("ctn. linen", "Ctn. Linen", "fiber"),
    ("cotton linen", "Ctn. Linen", "fiber"),
    ("ctn.poly", "Ctn. Poly", "fiber"),
    ("ctn. poly", "Ctn. Poly", "fiber"),
    ("cotton poly", "Ctn. Poly", "fiber"),

    # ── Fiber quality modifiers ──
    ("organic", "Org.", "modifier"),
    ("org", "Org.", "modifier"),
    ("org.", "Org.", "modifier"),
    ("bci", "BCI", "modifier"),
    ("recycle", "Recycle", "modifier"),
    ("recy", "Recycle", "modifier"),
    ("rcy", "Recycle", "modifier"),
    ("rcy.", "Recycle", "modifier"),
    ("compact", "Compact", "modifier"),
    ("open end", "Open End", "modifier"),
    ("openend", "Open End", "modifier"),
    ("oe", "Open End", "modifier"),
    ("vortex", "Vortex", "modifier"),
    ("ic-2", "IC-2", "modifier"),
    ("ic2", "IC-2", "modifier"),
    ("semi combed", "Semi Combed", "modifier"),
    ("combed", "Combed", "modifier"),
    ("carded", "Carded", "modifier"),
    ("gassed", "Gassed", "modifier"),
    ("mercerized", "Mercerized", "modifier"),

    # ── Yarn type modifiers ──
    ("slub", "Slub", "modifier"),
    ("slb", "Slub", "modifier"),
    ("snow slub", "Snow Slub", "modifier"),
    ("snow", "Snow Slub", "modifier"),
    ("tilly slub", "Tilly Slub", "modifier"),
    ("tilly", "Tilly Slub", "modifier"),
    ("tinny slub", "Tinny Slub", "modifier"),
    ("neps", "Neps", "modifier"),
    ("sparkle", "Sparkle", "modifier"),
    ("lurex", "Lurex", "modifier"),
    ("negative", "Negative", "modifier"),
    ("neg", "Negative", "modifier"),
    ("gliter", "Glitter", "modifier"),
    ("glitter", "Glitter", "modifier"),
    ("tinny", "Tinny Slub", "modifier"),
    ("stripe", "Stripe", "modifier"),
    ("y/d stripe", "Y/D Stripe", "modifier"),

    # ── Melange (treated as modifier) ──
    ("melange", "Melange", "modifier"),
    ("mel", "Melange", "modifier"),
    ("mel.", "Melange", "modifier"),
    ("milange", "Melange", "modifier"),
    ("millange", "Melange", "modifier"),
    ("milanj", "Melange", "modifier"),
    ("mell.", "Melange", "modifier"),

    # ── Knit Structures ──
    ("s/jersey", "S/Jersey", "structure"),
    ("s/j", "S/Jersey", "structure"),
    ("sj", "S/Jersey", "structure"),
    ("single jersey", "S/Jersey", "structure"),
    ("single", "S/Jersey", "structure"),
    ("jersey", "S/Jersey", "structure"),
    ("s/jersy", "S/Jersey", "structure"),
    ("s/jerey", "S/Jersey", "structure"),
    ("1x1 rib", "1x1 Rib", "structure"),
    ("1x1rib", "1x1 Rib", "structure"),
    ("1x1", "1x1 Rib", "structure"),
    ("2x1 rib", "2x1 Rib", "structure"),
    ("2x1rib", "2x1 Rib", "structure"),
    ("2x1", "2x1 Rib", "structure"),
    ("3x2 rib", "3x2 Rib", "structure"),
    ("3x3 rib", "3x3 Rib", "structure"),
    ("2x2 rib", "2x2 Rib", "structure"),
    ("6x2 rib", "6x2 Rib", "structure"),
    ("7x3 rib", "7x3 Rib", "structure"),
    ("9x4 rib", "9x4 Rib", "structure"),
    ("rib", "Rib", "structure"),
    ("terry", "Terry", "structure"),
    ("2th terry", "2Th. Terry", "structure"),
    ("2th.terry", "2Th. Terry", "structure"),
    ("2th", "2Th. Terry", "structure"),
    ("3th terry", "3Th. Terry", "structure"),
    ("3th.terry", "3Th. Terry", "structure"),
    ("3th", "3Th. Terry", "structure"),
    ("fleece", "Fleece", "structure"),
    ("interlock", "Interlock", "structure"),
    ("ilock", "Interlock", "structure"),
    ("i.lock", "Interlock", "structure"),
    ("pique", "Pique", "structure"),
    ("waffle", "Waffle", "structure"),
    ("velour", "Velour", "structure"),
    ("vellour", "Velour", "structure"),
    ("flat knit", "Flat Knit", "structure"),
    ("flatknit", "Flat Knit", "structure"),
    ("drop needle", "Drop Needle", "structure"),
    ("dropneedle", "Drop Needle", "structure"),
    ("d/n", "Drop Needle", "structure"),
    ("dn rib", "Drop Needle", "structure"),
    ("variegated", "Variegated Rib", "structure"),
    ("verigated", "Variegated Rib", "structure"),
    ("verycated", "Variegated Rib", "structure"),
    ("verygated", "Variegated Rib", "structure"),
    ("verigeted", "Variegated Rib", "structure"),
    ("jacquard", "Jacquard", "structure"),
    ("jacq", "Jacquard", "structure"),
    ("jacq.", "Jacquard", "structure"),
    ("loose knit", "Loose Knit", "structure"),
    ("loose", "Loose Knit", "structure"),
    ("papcon", "Papcon", "structure"),
    ("pointal", "Pointal", "structure"),
    ("diagonal", "Diagonal", "structure"),
    ("diognal", "Diagonal", "structure"),
    ("dignal", "Diagonal", "structure"),
    ("diag", "Diagonal", "structure"),
    ("diag.", "Diagonal", "structure"),
    ("thermal", "Thermal", "structure"),

    # ── Lycra / Spandex ──
    ("lycra", "Lycra", "lycra"),
    ("ly", "Lycra", "lycra"),
    ("ly.", "Lycra", "lycra"),
    ("licra", "Lycra", "lycra"),
    ("spandex", "Lycra", "lycra"),
    ("spx", "Lycra", "lycra"),
    ("20dn", "20Dn", "lycra"),
    ("20d", "20Dn", "lycra"),
    ("40dn", "40Dn", "lycra"),
    ("40d", "40Dn", "lycra"),
    ("70dn", "70Dn", "lycra"),
    ("70d", "70Dn", "lycra"),
    ("80dn", "80Dn", "lycra"),
    ("80d", "80Dn", "lycra"),
    ("150dn", "150Dn", "lycra"),
    ("150d", "150Dn", "lycra"),
    ("30dn", "30Dn", "lycra"),
    ("30d", "30Dn", "lycra"),
    ("50dn", "50Dn", "lycra"),
    ("50d", "50Dn", "lycra"),

    # ── Process State ──
    ("raw", "Raw", "state"),
    ("dyed", "Dyed", "state"),
    ("rfd", "Rfd", "state"),
    ("y/d", "Y/D", "state"),
    ("yd", "Y/D", "state"),
    ("yarn dyed", "Y/D", "state"),
    ("y/dyed", "Y/D", "state"),
    ("bleached", "Bleached", "state"),
    ("bio wash", "Bio Wash", "state"),
    ("biowash", "Bio Wash", "state"),
    ("bw", "Bio Wash", "state"),

    # ── Item classification keywords ──
    ("yarn", "Yarn", "modifier"),
    ("fabric", "Fabric", "modifier"),
    ("patti", "Patti", "structure"),
    ("towel", "Towel", "structure"),
]


def seed_all_aliases():
    """Insert all aliases into Item Token Alias, skipping existing ones."""
    inserted = 0
    skipped = 0

    for alias, canonical, dimension in ALIASES:
        alias_lower = alias.strip().lower()

        if frappe.db.exists("Item Token Alias", {"alias": alias_lower}):
            skipped += 1
            continue

        doc = frappe.get_doc({
            "doctype": "Item Token Alias",
            "alias": alias_lower,
            "canonical": canonical,
            "dimension": dimension,
            "is_auto": 1
        })
        doc.insert(ignore_permissions=True)
        inserted += 1

    frappe.db.commit()
    msg = f"Seeded {inserted} aliases, skipped {skipped} existing"
    print(msg)
    return msg
