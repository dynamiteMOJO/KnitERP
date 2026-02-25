"""
Smart Item Search API for KnitERP.

Provides a multi-layer fuzzy search that resolves user-typed abbreviations
(e.g., "30s ctn slb sj") into canonical tokens and finds matching items.

Resolution layers (in order):
  1. Exact alias match
  2. Fuzzy alias match (Levenshtein distance ≤ 2)
  3. Prefix match on aliases
  4. LIKE fallback on item_name
"""

import frappe
import re
from frappe.utils import cint


# ── Levenshtein distance (no external dependency) ──────────────────────

def _levenshtein(s1, s2):
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr_row.append(min(
                curr_row[j] + 1,       # insert
                prev_row[j + 1] + 1,   # delete
                prev_row[j] + cost     # replace
            ))
        prev_row = curr_row
    return prev_row[-1]


# ── Alias cache ────────────────────────────────────────────────────────

_alias_cache = None
_alias_cache_ts = 0

def _get_alias_map():
    """
    Load all aliases into a dict: {alias_lowercase: {canonical, dimension}}.
    Cached in-memory, refreshed every 60 seconds.
    """
    global _alias_cache, _alias_cache_ts
    import time
    now = time.time()

    if _alias_cache is not None and (now - _alias_cache_ts) < 60:
        return _alias_cache

    rows = frappe.get_all(
        "Item Token Alias",
        fields=["alias", "canonical", "dimension"],
        limit_page_length=0
    )

    _alias_cache = {}
    for r in rows:
        _alias_cache[r.alias.lower()] = {
            "canonical": r.canonical,
            "dimension": r.dimension
        }

    _alias_cache_ts = now
    return _alias_cache


def invalidate_alias_cache():
    """Call after alias table changes."""
    global _alias_cache, _alias_cache_ts
    _alias_cache = None
    _alias_cache_ts = 0


# ── Token resolution ──────────────────────────────────────────────────

def resolve_tokens(raw_text):
    """
    Parse raw user input into resolved canonical tokens.

    Args:
        raw_text: User input e.g. "30s ctn slb sj"

    Returns:
        list of dicts: [
            {"original": "30s", "canonical": "30's", "dimension": "count",
             "confidence": "exact"},
            ...
        ]

    Also returns unresolved tokens under confidence="unresolved".
    """
    if not raw_text or not raw_text.strip():
        return []

    alias_map = _get_alias_map()

    # Normalize: lowercase, collapse whitespace, remove leading/trailing
    text = raw_text.strip().lower()
    # Strip only: apostrophe, comma, plus, percent
    # Keep: / (2/20 ply, s/j, y/d) and . (p.c., vis.) — they are in aliases
    text = re.sub(r"[',+%]", "", text)
    text = re.sub(r"\s+", " ", text)

    raw_tokens = text.split()
    results = []
    skip_next = False
    seen_canonicals = set()  # Deduplicate: prevent same canonical appearing twice

    for i, token in enumerate(raw_tokens):
        if skip_next:
            skip_next = False
            continue

        # Skip tokens shorter than 2 chars (unless numeric)
        if len(token) < 2 and not token.isdigit():
            continue

        resolved = None

        # ── Layer 1: Try multi-word join FIRST (before single-word) ──
        # This ensures "poly cotton" → P.C. instead of "poly" → Polyester
        if i + 1 < len(raw_tokens):
            joined = f"{token} {raw_tokens[i + 1]}"
            if joined in alias_map:
                resolved = {
                    "original": joined,
                    "canonical": alias_map[joined]["canonical"],
                    "dimension": alias_map[joined]["dimension"],
                    "confidence": "exact"
                }
                skip_next = True

        # ── Layer 2: Exact single-word alias match ──
        if not resolved and token in alias_map:
            resolved = {
                "original": token,
                "canonical": alias_map[token]["canonical"],
                "dimension": alias_map[token]["dimension"],
                "confidence": "exact"
            }

        # For short tokens (≤3 chars), prefix match is more reliable than fuzzy
        # because short tokens have too many fuzzy neighbours (e.g. "sn" vs "sj")
        # For longer tokens, fuzzy first then prefix as fallback.

        # ── Layer 3a: Prefix match (for short tokens, run FIRST) ──
        if not resolved and len(token) <= 3:
            resolved = _try_prefix_match(token, alias_map)

        # ── Layer 3b: Fuzzy alias match (Levenshtein ≤ 2) ──
        # Skip fuzzy for purely numeric tokens — numbers are specific
        # (e.g. "100" should NOT fuzzy-match "10" alias for "10's")
        if not resolved and not token.isdigit():
            best_match = None
            best_dist = 3  # threshold
            best_alias_len_diff = 999

            for alias_key, alias_data in alias_map.items():
                # Only compare with aliases of similar length (optimization)
                if abs(len(alias_key) - len(token)) > 2:
                    continue

                dist = _levenshtein(token, alias_key)
                alias_len_diff = abs(len(alias_key) - len(token))

                if dist < best_dist:
                    best_dist = dist
                    best_match = alias_data
                    best_alias_len_diff = alias_len_diff
                elif dist == best_dist:
                    # Tie-break: prefer alias whose length is closest to token
                    if alias_len_diff < best_alias_len_diff:
                        best_match = alias_data
                        best_alias_len_diff = alias_len_diff

            if best_match:
                # Quality gate: reject fuzzy matches where edit distance
                # is too large relative to token/alias length.
                # For short tokens (≤3), require distance ≤ 1 to prevent
                # false matches like 'xyz'→Lycra or 'dye'→Diagonal.
                if len(token) <= 3:
                    max_allowed_dist = 1
                else:
                    max_allowed_dist = 2
                if best_dist <= max_allowed_dist:
                    resolved = {
                        "original": token,
                        "canonical": best_match["canonical"],
                        "dimension": best_match["dimension"],
                        "confidence": "fuzzy"
                    }

        # ── Layer 4: Prefix match (for longer tokens, as fallback) ──
        if not resolved and len(token) > 3:
            resolved = _try_prefix_match(token, alias_map)

        if resolved:
            # Deduplicate: don't add the same canonical twice
            if resolved["canonical"] not in seen_canonicals:
                results.append(resolved)
                seen_canonicals.add(resolved["canonical"])
        else:
            results.append({
                "original": token,
                "canonical": None,
                "dimension": None,
                "confidence": "unresolved"
            })

    return results


def _try_prefix_match(token, alias_map):
    """Try to match token as a prefix of known aliases."""
    prefix_matches = []
    for alias_key, alias_data in alias_map.items():
        if alias_key.startswith(token) and len(token) >= 2:
            prefix_matches.append((alias_key, alias_data))

    if len(prefix_matches) == 1:
        return {
            "original": token,
            "canonical": prefix_matches[0][1]["canonical"],
            "dimension": prefix_matches[0][1]["dimension"],
            "confidence": "prefix"
        }
    elif len(prefix_matches) > 1:
        # Prefer the shortest alias (most specific match)
        prefix_matches.sort(key=lambda x: len(x[0]))
        return {
            "original": token,
            "canonical": prefix_matches[0][1]["canonical"],
            "dimension": prefix_matches[0][1]["dimension"],
            "confidence": "prefix_ambiguous"
        }
    return None


# ── Search API (Frappe query override) ────────────────────────────────

@frappe.whitelist()
def smart_search(doctype, txt, searchfield=None, start=0, page_length=20,
                 filters=None, as_dict=False, **kwargs):
    """
    Smart item search that replaces Frappe's default link search.

    Called by frm.set_query("item_code", "items", {query: "kniterp.api.item_search.smart_search"}).

    Args:
        doctype: Always "Item"
        txt: Raw user input e.g. "30s ctn slb sj"
        searchfield, start, page_length, filters: Standard Frappe args

    Returns:
        List of [item_code, item_name] tuples for Frappe autosuggest.
    """
    start = cint(start)
    page_length = cint(page_length) or 20

    if not txt or not txt.strip():
        # Fallback: return recent/popular items
        return frappe.get_all(
            "Item",
            filters={"disabled": 0},
            fields=["name as value", "item_name as description"],
            order_by="modified desc",
            limit_start=start,
            limit_page_length=page_length,
            as_list=not as_dict
        )

    # Resolve tokens
    resolved = resolve_tokens(txt)

    canonical_tokens = [r["canonical"] for r in resolved if r["canonical"]]
    unresolved_tokens = [r["original"] for r in resolved if not r["canonical"]]

    if not canonical_tokens and not unresolved_tokens:
        return []

    # ── Build query ──
    # Dual scoring:
    #   Primary: count of canonical tokens matched in search index
    #   Secondary: count of raw tokens found in item_name (via LIKE)
    # Secondary breaks ties when token scores are equal, e.g.
    # "30 100 ctn" → both BCI and 100% items match 30's + Cotton,
    # but "100" appears in "30s 100% Cotton" name → higher LIKE score.

    # Collect ALL raw tokens for LIKE scoring (not just unresolved)
    all_raw_tokens = [r["original"] for r in resolved if len(r["original"]) >= 2]

    token_num = len(canonical_tokens)

    if canonical_tokens:
        placeholders = ", ".join(["%s"] * token_num)
        token_subquery = f"""(
            SELECT
                ist.item_code,
                COUNT(DISTINCT ist.token) AS match_count
            FROM `tabItem Search Token` ist
            WHERE ist.token IN ({placeholders})
            GROUP BY ist.item_code
        )"""
        token_params = list(canonical_tokens)
    else:
        token_subquery = None
        token_params = []

    # Build LIKE score expression using CASE WHEN (more compatible than boolean)
    like_score_parts = []
    like_score_params = []
    if all_raw_tokens:
        for rt in all_raw_tokens:
            like_score_parts.append("CASE WHEN i.item_name LIKE %s THEN 1 ELSE 0 END")
            like_score_params.append(f"%{rt}%")
        like_score_expr = " + ".join(like_score_parts)
    else:
        like_score_expr = "0"

    # LIKE conditions for unresolved tokens (WHERE filter)
    like_where_conditions = []
    like_where_params = []
    for ut in unresolved_tokens:
        if len(ut) >= 2:
            like_where_conditions.append("i.item_name LIKE %s")
            like_where_params.append(f"%{ut}%")

    # Build final query
    if token_subquery:
        # Items found via token index, ranked by token match + LIKE score
        if like_where_conditions:
            # Also include items matched only by LIKE (unresolved token fallback)
            where_extra = f" OR ({' AND '.join(like_where_conditions)})"
            where_params = like_where_params
        else:
            where_extra = ""
            where_params = []

        sql = f"""
            SELECT i.name AS value, i.item_name AS description,
                   COALESCE(tm.match_count, 0) AS _token_score,
                   ({like_score_expr}) AS _like_score
            FROM `tabItem` i
            LEFT JOIN {token_subquery} tm ON tm.item_code = i.name
            WHERE i.disabled = 0
                AND (tm.item_code IS NOT NULL{where_extra})
            ORDER BY _token_score DESC, _like_score DESC, i.item_name ASC
            LIMIT %s, %s
        """
        # IMPORTANT: params order must match %s left-to-right in SQL text:
        # 1. CASE WHEN LIKE %s (in SELECT) → like_score_params
        # 2. IN (%s) (in subquery)         → token_params
        # 3. WHERE LIKE %s (if any)        → where_params
        # 4. LIMIT %s, %s                  → start, page_length
        final_params = like_score_params + token_params + where_params + [start, page_length]

    elif like_where_conditions:
        # Only LIKE fallback (no canonical tokens resolved)
        sql = f"""
            SELECT i.name AS value, i.item_name AS description,
                   0 AS _token_score,
                   ({like_score_expr}) AS _like_score
            FROM `tabItem` i
            WHERE i.disabled = 0
                AND ({' AND '.join(like_where_conditions)})
            ORDER BY _like_score DESC, i.item_name ASC
            LIMIT %s, %s
        """
        final_params = like_score_params + like_where_params + [start, page_length]
    else:
        return []

    results = frappe.db.sql(sql, final_params, as_dict=True)

    # Remove internal score fields before returning
    for r in results:
        r.pop("_token_score", None)
        r.pop("_like_score", None)

    if as_dict:
        return results

    return [[r["value"], r["description"]] for r in results]


# ── Search index builder ──────────────────────────────────────────────

def rebuild_search_index(item_code=None):
    """
    Parse item names into canonical tokens and populate Item Search Token.

    Args:
        item_code: If provided, rebuild only for this item.
                   If None, rebuild the entire index.
    """
    alias_map = _get_alias_map()

    # Build reverse map: canonical → dimension (for dimension assignment)
    canonical_to_dim = {}
    for alias_data in alias_map.values():
        canonical_to_dim[alias_data["canonical"]] = alias_data["dimension"]

    if item_code:
        items = frappe.get_all("Item", filters={"name": item_code},
                               fields=["name", "item_name", "disabled"])
    else:
        items = frappe.get_all("Item", filters={"disabled": 0},
                               fields=["name", "item_name"])

    for item in items:
        # Delete existing tokens for this item
        frappe.db.delete("Item Search Token", {"item_code": item.name})

        if not item.item_name:
            continue

        # Parse item_name into tokens using the alias map
        tokens = _extract_tokens_from_name(item.item_name, alias_map)

        for seq, tok in enumerate(tokens, 1):
            dim = canonical_to_dim.get(tok, "")
            frappe.get_doc({
                "doctype": "Item Search Token",
                "item_code": item.name,
                "item_name": item.item_name,
                "token": tok,
                "dimension": dim,
                "sequence": seq
            }).insert(ignore_permissions=True)

    frappe.db.commit()


def _extract_tokens_from_name(item_name, alias_map):
    """
    Parse item name into canonical tokens using resolve_tokens.

    Examples:
        "30s + 40D Cotton BCI" → ["30's", "40Dn", "Cotton", "BCI"]
        "30s 100% Cotton"      → ["30's", "Cotton"] ("100" is noise)
    """
    resolved = resolve_tokens(item_name)
    tokens = []
    for r in resolved:
        if r["canonical"] and r["canonical"] not in tokens:
            tokens.append(r["canonical"])
    return tokens


# ── Hook: rebuild index on Item save ──────────────────────────────────

def on_item_save(doc, method=None):
    """Called via doc_events hook when an Item is saved."""
    rebuild_search_index(item_code=doc.name)


# ── Bench command: full rebuild ───────────────────────────────────────

@frappe.whitelist()
def rebuild_all_search_tokens():
    """Rebuild search tokens for all items. Call via bench console or API."""
    rebuild_search_index()
    return f"Rebuilt search index for all items"
