"""
Item Composer API — backend for the Phase 2 Composer dialog.

Provides:
    - get_composer_options()  — dropdown data grouped by dimension
    - preview_item()          — generate name, code, check duplicates
    - create_composer_item()  — create Item with all fields
    - add_new_token()         — create master + aliases with duplicate checks
"""

import json
import frappe


# ──────────────────────────────────────────────
# 1. OPTIONS (populate dropdowns)
# ──────────────────────────────────────────────
@frappe.whitelist()
def get_composer_options():
    """
    Returns all active Item Tokens grouped by dimension,
    with aliases for each token (for autocomplete matching).
    """
    tokens = frappe.db.sql("""
        SELECT canonical, dimension, short_code, sort_order
        FROM `tabItem Token`
        WHERE is_active = 1
        ORDER BY sort_order ASC, canonical ASC
    """, as_dict=True)

    # Get all aliases grouped by canonical
    aliases_raw = frappe.db.sql("""
        SELECT alias, canonical
        FROM `tabItem Token Alias`
    """, as_dict=True)

    alias_map = {}
    for a in aliases_raw:
        alias_map.setdefault(a["canonical"], []).append(a["alias"])

    # Group by dimension, include aliases
    options = {}
    for t in tokens:
        dim = t["dimension"]
        if dim not in options:
            options[dim] = []
        options[dim].append({
            "canonical": t["canonical"],
            "short_code": t["short_code"],
            "aliases": alias_map.get(t["canonical"], []),
        })

    return options


# ──────────────────────────────────────────────
# 1b. RESOLVE FREE TEXT → SLOT ASSIGNMENTS
# ──────────────────────────────────────────────
@frappe.whitelist()
def resolve_for_composer(text):
    """
    Takes free text (e.g. "30 ctn slub sj raw"), resolves each word
    via Item Token Alias, and returns slot assignments.

    Returns:
        {
            resolved: { count: "30's", fiber: "Cotton", ... },
            unresolved: ["xyz"]
        }
    """
    import re
    text = (text or "").strip().lower()
    if not text:
        return {"resolved": {}, "unresolved": []}

    # Tokenize — split on whitespace but keep compound tokens like 24+24+10
    raw_tokens = re.split(r"\s+", text)

    resolved = {}
    modifiers = []
    unresolved = []

    for token in raw_tokens:
        if not token:
            continue

        # Look up in alias table
        alias = frappe.db.get_value(
            "Item Token Alias",
            {"alias": token},
            ["canonical", "dimension"],
            as_dict=True
        )

        if alias:
            dim = alias["dimension"]
            canonical = alias["canonical"]

            if dim == "modifier":
                modifiers.append(canonical)
            elif dim in resolved:
                # Already have a value for this dimension — skip or override
                pass
            else:
                resolved[dim] = canonical
        else:
            unresolved.append(token)

    if modifiers:
        # Dedup: if one modifier contains another, keep only the specific one
        # e.g., ["Snow Slub", "Slub"] → ["Snow Slub"]
        deduped = []
        for m in modifiers:
            # Check if this modifier is a substring of another modifier
            is_contained = any(
                m != other and m.lower() in other.lower()
                for other in modifiers
            )
            if not is_contained and m not in deduped:
                deduped.append(m)

        if deduped:
            resolved["modifier1"] = deduped[0]
        if len(deduped) > 1:
            resolved["modifier2"] = deduped[1]

    return {
        "resolved": resolved,
        "unresolved": unresolved,
    }

# ──────────────────────────────────────────────
# 2. PREVIEW (name + code + duplicate check)
# ──────────────────────────────────────────────
@frappe.whitelist()
def preview_item(selections, classification):
    """
    Given user selections, generate canonical item name, item code,
    and check for duplicates.

    Args:
        selections: JSON string or dict with keys:
            count, fiber, modifier (list), structure, lycra, denier, state
        classification: "Fabric" or "Yarn"

    Returns:
        dict with item_name, item_code, duplicates (list)
    """
    if isinstance(selections, str):
        selections = json.loads(selections)

    item_name = _build_item_name(selections, classification)
    item_code = _build_item_code(selections, classification)

    # Check for exact duplicate
    duplicates = []
    if frappe.db.exists("Item", item_code):
        duplicates.append({
            "item_code": item_code,
            "item_name": frappe.db.get_value("Item", item_code, "item_name"),
            "match": "exact_code"
        })

    # Also check by name
    name_matches = frappe.db.sql("""
        SELECT name, item_name FROM `tabItem`
        WHERE item_name = %s AND name != %s
        LIMIT 5
    """, (item_name, item_code), as_dict=True)

    for m in name_matches:
        duplicates.append({
            "item_code": m["name"],
            "item_name": m["item_name"],
            "match": "same_name"
        })

    return {
        "item_name": item_name,
        "item_code": item_code,
        "duplicates": duplicates,
    }


def _build_item_name(selections, classification):
    """Build canonical item name from selections."""
    parts = []

    if selections.get("count"):
        parts.append(selections["count"])

    if selections.get("fiber"):
        parts.append(selections["fiber"])

    # Modifiers (list)
    modifiers = selections.get("modifier") or []
    if isinstance(modifiers, str):
        modifiers = [modifiers] if modifiers else []
    for m in modifiers:
        if m:
            parts.append(m)

    # For Yarn: append "Yarn" before structure/state
    if classification == "Yarn":
        parts.append("Yarn")
    else:
        # Structure (only for Fabric)
        if selections.get("structure"):
            parts.append(selections["structure"])

    # Lycra
    if selections.get("lycra"):
        parts.append(selections["lycra"])
        if selections.get("denier"):
            parts.append(selections["denier"])

    # State
    if selections.get("state"):
        parts.append(selections["state"])

    return " ".join(parts)


def _build_item_code(selections, classification):
    """Build item code from selections using short codes."""
    prefix = "FB" if classification == "Fabric" else "YR"
    parts = [prefix]

    # Count — extract numeric portion
    if selections.get("count"):
        count_code = _get_short_code(selections["count"])
        if count_code:
            parts.append(count_code)

    # Fiber
    if selections.get("fiber"):
        fiber_code = _get_short_code(selections["fiber"])
        if fiber_code:
            parts.append(fiber_code)

    # Modifiers
    modifiers = selections.get("modifier") or []
    if isinstance(modifiers, str):
        modifiers = [modifiers] if modifiers else []
    for m in modifiers:
        if m:
            m_code = _get_short_code(m)
            if m_code:
                parts.append(m_code)

    # Structure (Fabric only — Yarn uses "Yarn" in name, not in code)
    if classification == "Fabric" and selections.get("structure"):
        s_code = _get_short_code(selections["structure"])
        if s_code:
            parts.append(s_code)

    # Lycra
    if selections.get("lycra"):
        l_code = _get_short_code(selections["lycra"])
        if l_code:
            parts.append(l_code)
        if selections.get("denier"):
            d_code = _get_short_code(selections["denier"])
            if d_code:
                parts.append(d_code)

    # State
    if selections.get("state"):
        st_code = _get_short_code(selections["state"])
        if st_code:
            parts.append(st_code)

    return "-".join(parts)


def _get_short_code(canonical):
    """Look up the short code for a canonical name from Item Token."""
    code = frappe.db.get_value("Item Token", canonical, "short_code")
    return code or ""


# ──────────────────────────────────────────────
# 3. CREATE ITEM
# ──────────────────────────────────────────────
@frappe.whitelist()
def create_composer_item(selections, classification, item_group, hsn_code,
                         stock_uom="Kg", is_stock_item=1):
    """
    Create a new Item from Composer selections.

    Args:
        selections: JSON string or dict with dimension values
        classification: "Fabric", "Yarn", or "Other"
        item_group: Item Group name
        hsn_code: GST HSN Code
        stock_uom: UOM (default Kg for textile)
        is_stock_item: 1 or 0

    Returns:
        dict with item_code, item_name
    """
    if isinstance(selections, str):
        selections = json.loads(selections)
    is_stock_item = int(is_stock_item)

    if classification == "Other":
        # Simple creation — user provides name and code directly
        item_code = selections.get("item_code", "").strip()
        item_name = selections.get("item_name", "").strip()

        if not item_code or not item_name:
            frappe.throw("Item Code and Item Name are required")

        if frappe.db.exists("Item", item_code):
            frappe.throw(f"Item {item_code} already exists")
    else:
        # Textile item — generate name and code
        item_name = _build_item_name(selections, classification)
        item_code = _build_item_code(selections, classification)

        if frappe.db.exists("Item", item_code):
            frappe.throw(f"Item {item_code} already exists")

    doc = frappe.get_doc({
        "doctype": "Item",
        "item_code": item_code,
        "item_name": item_name,
        "item_group": item_group,
        "stock_uom": stock_uom,
        "is_stock_item": is_stock_item,
        "gst_hsn_code": hsn_code,
        "custom_item_classification": classification,
        "include_item_in_manufacturing": 1 if classification != "Other" else 0,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "item_code": doc.name,
        "item_name": doc.item_name,
    }


# ──────────────────────────────────────────────
# 4. ADD NEW TOKEN
# ──────────────────────────────────────────────
@frappe.whitelist()
def add_new_token(canonical, dimension, short_code, aliases=""):
    """
    Create a new Item Token master and its aliases.

    Args:
        canonical: Display name (e.g., "Bamboo Cotton")
        dimension: count/fiber/modifier/structure/lycra/state
        short_code: For item code (e.g., "BMB")
        aliases: Comma-separated aliases (e.g., "bamboo, bmb, bmbctn")

    Returns:
        dict with the new token info

    Raises:
        frappe.ValidationError on duplicates
    """
    canonical = canonical.strip()
    short_code = short_code.strip().upper()
    dimension = dimension.strip().lower()

    # ── Duplicate checks ──

    # 1. Canonical already exists?
    if frappe.db.exists("Item Token", canonical):
        frappe.throw(
            f"Token '{canonical}' already exists",
            frappe.DuplicateEntryError
        )

    # 2. Short code already used in same dimension?
    existing = frappe.db.get_value(
        "Item Token",
        {"short_code": short_code, "dimension": dimension},
        "canonical"
    )
    if existing:
        frappe.throw(
            f"Short code '{short_code}' already used for '{existing}' in dimension '{dimension}'",
            frappe.DuplicateEntryError
        )

    # 3. Parse aliases
    alias_list = [a.strip().lower() for a in aliases.split(",") if a.strip()]
    # Always include the canonical itself as an alias (lowercased)
    canonical_lower = canonical.lower()
    if canonical_lower not in alias_list:
        alias_list.insert(0, canonical_lower)

    # 4. Check alias collisions
    for alias in alias_list:
        existing_alias = frappe.db.get_value(
            "Item Token Alias",
            {"alias": alias},
            ["canonical", "dimension"],
            as_dict=True
        )
        if existing_alias:
            frappe.throw(
                f"Alias '{alias}' already mapped to '{existing_alias['canonical']}' ({existing_alias['dimension']})",
                frappe.DuplicateEntryError
            )

    # ── Create master token ──
    token_doc = frappe.get_doc({
        "doctype": "Item Token",
        "canonical": canonical,
        "dimension": dimension,
        "short_code": short_code,
        "sort_order": 10,
        "is_active": 1,
    })
    token_doc.insert(ignore_permissions=True)

    # ── Create aliases ──
    for alias in alias_list:
        frappe.get_doc({
            "doctype": "Item Token Alias",
            "alias": alias,
            "canonical": canonical,
            "dimension": dimension,
            "token": canonical,
            "is_auto": 0,
        }).insert(ignore_permissions=True)

    frappe.db.commit()

    return {
        "canonical": canonical,
        "dimension": dimension,
        "short_code": short_code,
        "aliases": alias_list,
    }
