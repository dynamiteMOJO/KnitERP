"""
Brute-force test for smart item search system.
Tests token resolution and search results across all edge cases.

Run: bench --site erp16.localhost execute kniterp.tests.test_smart_search.run_all_tests
"""

import frappe
import json
from datetime import datetime


def run_all_tests():
    """Run all tests and write results to a file."""
    results = []
    results.append("=" * 80)
    results.append(f"SMART SEARCH BRUTE-FORCE TEST — {datetime.now()}")
    results.append("=" * 80)

    from kniterp.api.item_search import resolve_tokens, smart_search, _get_alias_map

    # ─── Section 0: System state ────────────────────────────────────
    results.append("\n\n## SECTION 0: SYSTEM STATE")
    results.append("-" * 40)

    alias_count = frappe.db.count("Item Token Alias")
    token_count = frappe.db.count("Item Search Token")
    item_count = frappe.db.count("Item")
    results.append(f"Aliases in DB: {alias_count}")
    results.append(f"Search tokens in DB: {token_count}")
    results.append(f"Total items in DB: {item_count}")

    # Show all items and their tokens
    items = frappe.get_all("Item", fields=["name", "item_name", "disabled"],
                           order_by="item_name", limit_page_length=0)
    results.append(f"\nAll items ({len(items)}):")
    for item in items:
        tokens = frappe.get_all("Item Search Token",
                                filters={"item_code": item.name},
                                fields=["token", "dimension"],
                                order_by="sequence")
        token_str = ", ".join([f"{t.token}({t.dimension})" for t in tokens])
        disabled = " [DISABLED]" if item.disabled else ""
        results.append(f"  {item.name} = \"{item.item_name}\"{disabled}")
        results.append(f"    tokens: [{token_str}]")

    # ─── Section 1: Token resolution tests ──────────────────────────
    results.append("\n\n## SECTION 1: TOKEN RESOLUTION")
    results.append("-" * 40)

    resolution_tests = [
        # (input, description, expected_canonicals_or_note)
        # ── Exact matches ──
        ("30s ctn sj", "All exact aliases", "30's, Cotton, S/Jersey"),
        ("ctn slb terry", "Common abbreviations", "Cotton, Slub, Terry"),
        ("mel pc 1x1", "Melange P.C. 1x1 Rib", "Melange, P.C., 1x1 Rib"),
        ("20s poly fleece", "Polyester fleece", "20's, Polyester, Fleece"),
        ("40s vis interlock", "Viscose interlock", "40's, Viscose, Interlock"),
        ("org ctn sj raw", "Organic cotton SJ raw", "Org., Cotton, S/Jersey, Raw"),
        ("bci ctn terry dyed", "BCI cotton terry dyed", "BCI, Cotton, Terry, Dyed"),
        ("ly 20dn", "Lycra denier", "Lycra, 20Dn"),
        ("y/d", "Yarn dyed", "Y/D"),
        ("rfd", "RFD state", "Rfd"),

        # ── Fuzzy matches (typos) ──
        ("coton", "Typo: coton → Cotton", "Cotton"),
        ("cnt", "Transposition: cnt → ctn → Cotton", "Cotton"),
        ("jrsey", "Typo: jrsey → Jersey (should fail or match)", "?"),
        ("polyster", "Typo: polyster → Polyester", "Polyester"),
        ("milange", "Alt spelling: milange → Melange", "Melange"),
        ("millange", "Alt spelling: millange → Melange", "Melange"),
        ("licra", "Alt spelling: licra → Lycra", "Lycra"),
        ("s/jersy", "Typo: s/jersy → S/Jersey", "S/Jersey"),

        # ── Prefix matches ──
        ("sn", "Short prefix: sn → Snow Slub", "Snow Slub"),
        ("fl", "Short prefix: fl → Fleece", "Fleece"),
        ("lin", "Short prefix: lin → Linen", "Linen"),
        ("therm", "Prefix: therm → Thermal", "Thermal"),

        # ── Multi-word ──
        ("single jersey", "Multi-word exact alias", "S/Jersey"),
        ("open end", "Multi-word modifier", "Open End"),
        ("drop needle", "Multi-word structure", "Drop Needle"),
        ("flat knit", "Multi-word structure", "Flat Knit"),
        ("poly cotton", "Multi-word fiber", "P.C."),

        # ── Order independence ──
        ("sj ctn 30s", "Reverse order", "S/Jersey, Cotton, 30's"),
        ("raw sj ctn 30s mel", "Shuffled order", "Raw, S/Jersey, Cotton, 30's, Melange"),

        # ── Ambiguous / problematic tokens ──
        ("40", "Ambiguous: 40 → 40's (yarn) or 40D (lycra)?", "40's (expected)"),
        ("100", "Ambiguous: 100 in '100% Cotton'", "?"),
        ("30 40", "Two counts: 30 + 40", "30's, 40's"),
        ("pc", "P.C. or P/C", "P.C."),

        # ── Short / too short tokens ──
        ("j", "Single char: should be skipped", "skipped"),
        ("s", "Single char: should be skipped", "skipped"),
        ("30", "Numeric 2-char: should work", "30's"),
        ("10", "Numeric 2-char: should work", "10's"),

        # ── Gibberish / unrecognizable ──
        ("xyz", "Gibberish", "unresolved"),
        ("blah", "Gibberish", "unresolved"),
        ("asdf qwer", "All gibberish", "all unresolved"),
        ("abc123", "Mixed gibberish", "unresolved"),

        # ── Mixed good + bad ──
        ("30s xyz ctn", "Good + gibberish + good", "30's, unresolved, Cotton"),
        ("ctn blah sj", "Good + gibberish + good", "Cotton, unresolved, S/Jersey"),

        # ── Punctuation handling ──
        ("30's cotton s/jersey", "Full canonical names with punctuation", "30's, Cotton, S/Jersey"),
        ("p.c.", "With periods", "P.C."),
        ("2/20", "Ply count with slash", "2/20's"),

        # ── Empty / whitespace ──
        ("", "Empty string", "empty"),
        ("   ", "Only whitespace", "empty"),
        ("  30s  ctn  ", "Extra whitespace", "30's, Cotton"),
    ]

    for input_text, description, expected in resolution_tests:
        resolved = resolve_tokens(input_text)
        canonicals = [r["canonical"] or f"UNRESOLVED({r['original']})" for r in resolved]
        confidences = [r["confidence"] for r in resolved]
        result_str = ", ".join([f"{c} [{conf}]" for c, conf in zip(canonicals, confidences)])

        status = "✓" if result_str else "—"
        results.append(f"\n  INPUT: \"{input_text}\"")
        results.append(f"  DESC:  {description}")
        results.append(f"  WANT:  {expected}")
        results.append(f"  GOT:   {result_str or '(empty)'}")

        # Flag potential issues
        if any("UNRESOLVED" in c for c in canonicals) and "unresolved" not in expected.lower():
            results.append(f"  ⚠️ UNEXPECTED UNRESOLVED TOKEN")
        if not resolved and "empty" not in expected.lower():
            results.append(f"  ⚠️ NO RESULTS")

    # ─── Section 2: Search result tests ─────────────────────────────
    results.append("\n\n## SECTION 2: SEARCH RESULTS (smart_search)")
    results.append("-" * 40)

    search_tests = [
        # (input, description, should_be_first_or_note)
        ("30s ctn", "Basic 2-token", "30's Cotton items"),
        ("30 40 ctn", "Multi-count + fiber", "30s + 40D Cotton BCI should be first"),
        ("30s 100 ctn", "100% Cotton specific", "30s 100% Cotton should be first"),
        ("ctn sj", "Fiber + structure", "Cotton S/Jersey items"),
        ("ctn", "Single token — broad", "All Cotton items"),
        ("30", "Single count — very broad", "All 30's items"),
        ("30s ctn sj raw", "Full spec 4 tokens", "narrowest match"),
        ("xyz", "Gibberish", "empty or minimal"),
        ("", "Empty", "all recent items"),
        ("30s 100% cotton", "Full canonical text", "30s 100% Cotton first"),
    ]

    for input_text, description, expected in search_tests:
        search_results = smart_search("Item", input_text)
        result_count = len(search_results)

        results.append(f"\n  SEARCH: \"{input_text}\"")
        results.append(f"  DESC:   {description}")
        results.append(f"  EXPECT: {expected}")
        results.append(f"  COUNT:  {result_count} results")
        if search_results:
            for i, sr in enumerate(search_results[:5]):
                marker = "→" if i == 0 else " "
                if isinstance(sr, dict):
                    results.append(f"    {marker} {sr['value']} = \"{sr['description']}\"")
                else:
                    results.append(f"    {marker} {sr[0]} = \"{sr[1]}\"")
            if result_count > 5:
                results.append(f"    ... and {result_count - 5} more")
        else:
            results.append(f"    (no results)")

    # ─── Section 3: Alias coverage analysis ─────────────────────────
    results.append("\n\n## SECTION 3: ALIAS COVERAGE")
    results.append("-" * 40)

    alias_map = _get_alias_map()
    dims = {}
    for a, data in alias_map.items():
        dim = data["dimension"]
        dims.setdefault(dim, []).append(a)

    for dim in sorted(dims.keys()):
        aliases = sorted(dims[dim])
        results.append(f"\n  {dim.upper()} ({len(aliases)} aliases):")
        # Group by canonical
        by_canonical = {}
        for a in aliases:
            canon = alias_map[a]["canonical"]
            by_canonical.setdefault(canon, []).append(a)
        for canon in sorted(by_canonical.keys()):
            alias_list = ", ".join(sorted(by_canonical[canon]))
            results.append(f"    {canon}: [{alias_list}]")

    # ─── Section 4: Token index coverage ────────────────────────────
    results.append("\n\n## SECTION 4: TOKEN INDEX COVERAGE")
    results.append("-" * 40)

    items_without_tokens = []
    for item in items:
        if item.disabled:
            continue
        count = frappe.db.count("Item Search Token", {"item_code": item.name})
        if count == 0:
            items_without_tokens.append(item)

    if items_without_tokens:
        results.append(f"\n  ⚠️ {len(items_without_tokens)} items have NO search tokens:")
        for item in items_without_tokens:
            results.append(f"    {item.name} = \"{item.item_name}\"")
    else:
        results.append(f"\n  ✓ All enabled items have search tokens")

    # ─── Section 5: Recommendations ─────────────────────────────────
    results.append("\n\n## SECTION 5: KNOWN LIMITATIONS & USER GUIDANCE")
    results.append("-" * 40)
    results.append("""
  1. AMBIGUOUS SHORT TOKENS: "40" resolves to "40's" (yarn count),
     not "40D" (lycra denier). To search for 40D lycra items,
     type "40d" or "40dn" explicitly.

  2. PERCENTAGE TOKENS: "100" in "100% Cotton" is not a meaningful
     search token — it fuzzy-matches to "10's" (yarn count).
     Users should search "30s ctn" (not "30s 100 ctn") for 100% Cotton.

  3. TRANSPOSITIONS: Levenshtein treats letter swaps as 2 edits (not 1).
     "cnt" resolves correctly via fuzzy → "ctn" → Cotton, but only because
     the quality threshold allows distance-2 matches for 3-char tokens.

  4. VERY SHORT TOKENS: Single characters (j, s, etc.) are skipped.
     Users should type at least 2 characters.

  5. ITEM NAME LIKE: The secondary LIKE scoring matches raw tokens
     against item_name. Since item names use full words ("Cotton" not "ctn"),
     abbreviated tokens won't boost LIKE score. This is by design.
    """)

    # Write to file
    output = "\n".join(results)
    output_path = "/tmp/smart_search_test_results.txt"
    with open(output_path, "w") as f:
        f.write(output)

    print(f"Test results written to {output_path}")
    print(f"Total tests: {len(resolution_tests)} resolution + {len(search_tests)} search")
    return output_path
