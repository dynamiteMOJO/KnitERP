# KnitERP Item System — Complete Technical Reference

> The Item System is KnitERP's second foundation layer. It governs how textile items
> (yarn, fabric) are discovered, created, named, coded, searched, and paired.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Data Model](#2-data-model)
3. [Item Discovery — Item Composer Dialog](#3-item-discovery--item-composer-dialog)
4. [Item Creation Flow (Step by Step)](#4-item-creation-flow-step-by-step)
5. [Textile Attribute Naming System](#5-textile-attribute-naming-system)
6. [Yarn Dual-Version Logic](#6-yarn-dual-version-logic--item-alternative)
7. [Smart Search Architecture](#7-smart-search-architecture)
8. [Hook & Event Wiring](#8-hook--event-wiring)
9. [ignore_permissions Audit](#9-ignore_permissions-audit)
10. [Edge Cases & Risks](#10-edge-cases--risks)
11. [File Reference Index](#11-file-reference-index)

---

## 1. Architecture Overview

```
                    ┌─────────────────────────────────────┐
                    │         Item Composer Dialog         │
                    │   (item_composer.js — global JS)     │
                    │                                     │
                    │  [Classification] [Item Group] [HSN]│
                    │  [Quick Fill ───────────────────]   │
                    │  [Count] [Fiber] [Mod1] [Mod2]     │
                    │  [Structure] [Lycra] [State]        │
                    │  ──── Preview ────                   │
                    │  Name: 30's Cotton Slub S/Jersey Raw│
                    │  Code: FB-30-CTN-SLB-SJ-RAW        │
                    │  [Create & Select]                  │
                    └───────────┬─────────────────────────┘
                                │
           ┌────────────────────┼────────────────────┐
           ▼                    ▼                    ▼
   item_composer.py      item_search.py       CustomItem
   (5 API methods)       (smart_search)       (override)
           │                    │                    │
           ▼                    ▼                    ▼
   ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐
   │  Item Token   │   │Item Search   │   │ ERPNext Item      │
   │  Item Token   │   │  Token       │   │ + custom_item_    │
   │   Alias       │   │(search index)│   │   classification  │
   └──────────────┘   └──────────────┘   └──────────────────┘
```

**Three classifications** govern behavior:
| Classification | Autoname | UOM | Dual-creation | Batch tracking |
|---------------|----------|-----|---------------|----------------|
| **Fabric** | Composer code (FB-...) | Kg | No | Yes (forced) |
| **Yarn** | Composer code (YR-...) | Kg | Yes (Base + CP) | Yes (forced) |
| **Other** | ERPNext default naming | User choice | No | No |

---

## 2. Data Model

### 2a. Custom Field on Item

| Field | Type | Options | Notes |
|-------|------|---------|-------|
| `custom_item_classification` | Select | Fabric / Yarn / Other | Created via Customize Form (not in KnitERP fixtures). Drives all branching logic. |

### 2b. Item Token (master)

> **DocType**: `Item Token` — `kniterp/kniterp/doctype/item_token/item_token.json`
>
> **Naming**: `format:{canonical}` (canonical IS the name)

| Field | Type | Description |
|-------|------|-------------|
| `canonical` | Data (unique, reqd) | Display name: "Cotton", "S/Jersey", "30's" |
| `dimension` | Select (reqd) | `count` / `fiber` / `modifier` / `structure` / `lycra` / `state` |
| `short_code` | Data (reqd) | For item_code generation: "CTN", "SJ", "30" |
| `sort_order` | Int (default 10) | Display order in Composer dropdowns |
| `is_active` | Check (default 1) | Show in Composer? |

**6 dimensions** define a textile item's identity:
1. **count** — yarn count: "30's", "2/20's", "40's"
2. **fiber** — material: "Cotton", "P.C.", "Viscose", "Ctn. Modal"
3. **modifier** — quality/effect: "Slub", "BCI", "Melange", "Compact" (up to 2)
4. **structure** — knit structure: "S/Jersey", "1x1 Rib", "Fleece" (Fabric only)
5. **lycra** — elastane: "Lycra", "20Dn", "40Dn"
6. **state** — process state: "Raw", "Dyed", "Y/D", "Rfd"

### 2c. Item Token Alias (search vocabulary)

> **DocType**: `Item Token Alias` — `kniterp/kniterp/doctype/item_token_alias/item_token_alias.json`
>
> **Naming**: `format:{alias}` (alias IS the name, globally unique)

| Field | Type | Description |
|-------|------|-------------|
| `alias` | Data (unique, reqd) | Lowercase search term: "ctn", "sj", "30s", "poly cotton" |
| `canonical` | Data (reqd) | Maps to: "Cotton", "S/Jersey", "30's", "P.C." |
| `dimension` | Select (reqd) | Same 6 dimensions as Item Token |
| `token` | Link → Item Token | Back-reference to master |
| `is_auto` | Check | 1 = seeded, 0 = user-created |

**Key design**: Many aliases → one canonical. Examples:
- "ctn", "cotton", "ctn.", "coton", "cottn" → **Cotton** (fiber)
- "sj", "s/j", "s/jersey", "single jersey", "jersey" → **S/Jersey** (structure)
- "30s", "30" → **30's** (count)
- "pc", "p.c.", "p/c", "poly cotton", "polyctn" → **P.C.** (fiber)

Seeded from analysis of 802 real items from legacy Busy software (`seed_aliases.py`).
Stored as fixture in `fixtures/item_token_alias.json`.

### 2d. Item Search Token (inverted index)

> **DocType**: `Item Search Token` — `kniterp/kniterp/doctype/item_search_token/item_search_token.json`
>
> **Naming**: Autoincrement

| Field | Type | Description |
|-------|------|-------------|
| `item_code` | Link → Item (reqd) | Which item this token belongs to |
| `item_name` | Data (read_only) | Denormalized for display |
| `token` | Data (reqd) | Canonical token: "30's", "Cotton", "Slub" |
| `dimension` | Select | Dimension of this token |
| `sequence` | Int | Order within the item's token list |

**Populated automatically** on Item insert/update via `on_item_save()` hook.
This is the **search index** — smart_search queries this table to find items by token match count.

---

## 3. Item Discovery — Item Composer Dialog

### Entry Points

The Item Composer (`item_composer.js`) is loaded globally via `app_include_js` and can be invoked from:

1. **Any Item Link field** — monkey-patches `ControlLink.prototype.new_doc` so clicking "+ Create a new Item" opens the Composer instead of navigating to `/app/item/new` (lines 845-912 of `item_composer.js`)
2. **Direct call** — `window.kniterp_open_item_composer(opts)` from any JS context
3. **Production Wizard / BOM Designer** — passes `on_select` callback + `quick_fill_text`

### Composer Dialog Structure

```
┌─────────────────────────────────────────────────────────┐
│ Classification: [Fabric ▼]  Item Group: [___]  HSN: [___]│
├─────────────────────────────────────────────────────────┤
│ Quick Fill: [30 ctn slub sj raw          ] [Fill Slots] │
│ ✓ Filled 5 slots: count: 30's, fiber: Cotton, ...      │
├─────────────────────────────────────────────────────────┤
│ Count: [30's    ▼] [+Add]  │  Fiber: [Cotton  ▼] [+Add]│
│ Modifier 1: [Slub ▼] [+Add]│  Modifier 2: [       ▼]  │
│ Structure: [S/Jersey ▼] [+] │  Lycra: [          ▼]    │
│ State: [Raw          ▼]     │                           │
├─────────────────────────────────────────────────────────┤
│ Preview:                                                │
│ Name: 30's Cotton Slub S/Jersey Raw                     │
│ Code: FB-30-CTN-SLB-SJ-RAW                             │
│ ✓ No duplicate found                                   │
│                              [Create & Select]          │
└─────────────────────────────────────────────────────────┘
```

### Field Visibility Rules

| Classification | Textile fields | Structure fields | Other fields |
|---------------|---------------|-----------------|--------------|
| **Fabric** | Shown | Shown | Hidden |
| **Yarn** | Shown | **Hidden** | Hidden |
| **Other** | Hidden | Hidden | Shown (name, code, UOM, is_stock) |

### Quick Fill Flow

1. User types free text: `"30 ctn slub sj raw"`
2. JS calls `kniterp.api.item_composer.resolve_for_composer`
3. Backend tokenizes on whitespace, looks up each token in `Item Token Alias` table
4. Returns `{resolved: {count: "30's", fiber: "Cotton", modifier1: "Slub", structure: "S/Jersey", state: "Raw"}, unresolved: []}`
5. JS fills each slot, shows green confirmation
6. Unresolved tokens show as yellow "+" buttons → clicking opens "Add Token" sub-dialog

### Alias-Aware Autocomplete

Each dimension dropdown overrides Awesomplete's `filter` function to match both:
- Canonical name directly (e.g., typing "Cotton" shows Cotton)
- Aliases (e.g., typing "ctn" shows Cotton, "sj" shows S/Jersey)

Built from the `aliases` array returned by `get_composer_options()`.

### "+ Add New" Token Sub-dialog

Available on: Count, Fiber, Modifier, Structure dropdowns.
Creates:
1. New `Item Token` master (with canonical, dimension, short_code)
2. New `Item Token Alias` records (canonical itself + comma-separated aliases)
3. Refreshes parent dialog dropdowns + re-applies alias autocomplete

---

## 4. Item Creation Flow (Step by Step)

### 4a. Textile Item (Fabric/Yarn) — Full Path

```
Step 1: User fills Composer dialog (manually or via Quick Fill)
        ↓
Step 2: Live preview calls `item_composer.preview_item()`
        → _build_item_name(selections, classification)
        → _build_item_code(selections, classification)
        → Duplicate check (exact code + name match)
        → Missing token check (_get_missing_tokens): canonicals with no short_code
          in Item Token table are returned as missing_tokens list
        → If missing_tokens non-empty: preview shows warning + "Fix" buttons
          per missing attribute. User must add short codes before creating.
          Each "Fix" button calls create_item_token(canonical, short_code) which
          creates the Item Token record permanently, fixing all future items.
        ↓
Step 3: User clicks "Create & Select"
        ↓
Step 4: JS calls `item_composer.create_composer_item()`
        Args: selections JSON, classification, item_group, hsn_code, stock_uom="Kg"
        ↓
Step 5: Backend builds name + code (same functions as preview)
        → Checks duplicate (throws if exists)
        → Creates Item doc:
            item_code = generated code (e.g., "FB-30-CTN-SLB-SJ-RAW")
            item_name = generated name (e.g., "30's Cotton Slub S/Jersey Raw")
            custom_item_classification = "Fabric" or "Yarn"
            include_item_in_manufacturing = 1
            stock_uom = "Kg"
        → doc.insert(ignore_permissions=True)
        → frappe.db.commit()
        ↓
Step 6: CustomItem.validate() fires (override):
        → If Fabric: sets is_sub_contracted_item = 1
        → If Services group: sets is_stock_item = 0
        → Calls super().validate()
        ↓
Step 7: CustomItem.autoname() fires (override):
        → If Fabric/Yarn: item_code IS the name (set by Composer)
          → If is_customer_provided_item: appends " - CP" suffix
        → Else: delegates to ERPNext default autoname
        ↓
Step 8: doc_events["Item"]["before_save"] fires:
        → enforce_batch_tracking_for_fabric_yarn():
          → If Fabric/Yarn: forces has_batch_no = 1
        ↓
Step 9: Item saved to DB
        ↓
Step 10: CustomItem.after_insert() fires:
         → If Yarn: ensure_dual_yarn_versions() [see Section 6]
         → If non-Yarn CP item: create_purchase_item() [legacy]
         ↓
Step 11: doc_events["Item"]["after_insert"] fires:
         → on_item_save() → rebuild_search_index(item_code)
         → Parses item_name into canonical tokens
         → Populates Item Search Token table
         ↓
Step 12: JS on_select callback fires
         → Sets the item_code in the calling Link field
         → Handles 3 tiers: child table row, parent field, custom page control
```

### 4b. Other Item — Simplified Path

```
Step 1: Classification = "Other" → textile fields hidden
Step 2: User enters item_name, item_code, UOM manually
Step 3: create_composer_item() creates Item with user-provided code/name
Step 4: CustomItem.autoname() delegates to super() (ERPNext default)
Step 5: No dual-version logic, no forced batch tracking
Step 6: Search index still built on save
```

### 4c. Link Field Intercept

When a user types in any Item Link field and clicks "Create a new Item":
1. The monkey-patched `ControlLink.new_doc()` intercepts (line 848)
2. Captures typed text as `quick_fill_text`
3. Opens Composer with that text pre-filled
4. On selection, uses 3-tier value setting:
   - **Tier 1**: `frappe.model.set_value(cdt, cdn, fieldname, item_code)` for child table rows
   - **Tier 2**: `frm.set_value(fieldname, item_code)` for parent-level fields
   - **Tier 3**: Direct internal state manipulation for custom pages (BOM designer, dialogs) — bypasses async validation that would clear the value

---

## 5. Textile Attribute Naming System

### Item Name Construction

`_build_item_name(selections, classification)` in `item_composer.py:185`

Parts concatenated with spaces in this order:

| # | Part | Fabric example | Yarn example |
|---|------|---------------|-------------|
| 1 | Count | 30's | 30's |
| 2 | Fiber | Cotton | Cotton |
| 3 | Modifier(s) | Slub | BCI |
| 4 | **Structure** (Fabric) / **"Yarn"** (Yarn) | S/Jersey | Yarn |
| 5 | Lycra | Lycra 20Dn | — |
| 6 | State | Raw | Raw |

**Fabric**: `"30's Cotton Slub S/Jersey Lycra 20Dn Raw"`
**Yarn**: `"30's Cotton BCI Yarn Raw"`

### Item Code Construction

`_build_item_code(selections, classification)` in `item_composer.py:224`

Parts joined with hyphens:

| # | Part | Source | Example |
|---|------|--------|---------|
| 1 | Prefix | "FB" (Fabric) or "YR" (Yarn) | FB |
| 2 | Count code | `_get_short_code("30's")` → "30" | 30 |
| 3 | Fiber code | `_get_short_code("Cotton")` → "CTN" | CTN |
| 4 | Modifier code(s) | `_get_short_code("Slub")` → "SLB" | SLB |
| 5 | Structure code (Fabric only) | `_get_short_code("S/Jersey")` → "SJ" | SJ |
| 6 | Lycra code | `_get_short_code("Lycra")` → "LYC" | LYC |
| 7 | State code | `_get_short_code("Raw")` → "RAW" | RAW |

**Result**: `FB-30-CTN-SLB-SJ-LYC-RAW`

`_get_short_code()` looks up `Item Token.short_code` by canonical name.

### Short Code Derivation

Defined in `seed_item_tokens.py:SHORT_CODE_MAP` (manual overrides) with auto-derivation fallback:
- **Counts**: strip `'s`, extract numeric: "30's" → "30", "2/20's" → "2/20"
- **Others**: first 3-4 uppercase alphanumeric chars of canonical

### CP Item Naming

In `CustomItem.autoname()` (line 13-15):
- If `is_customer_provided_item` and code doesn't end with " - CP", appends " - CP"
- Example: `YR-30-CTN-RAW` → `YR-30-CTN-RAW - CP`

---

## 6. Yarn Dual-Version Logic & Item Alternative

### Business Context

In textile manufacturing, yarn arrives from two sources:
1. **Base yarn** — purchased from suppliers (Purchase Order)
2. **Customer-Provided (CP) yarn** — supplied by the customer for job work/subcontracting

Both are the **same physical material** (e.g., "30's Cotton Raw") but have different:
- Purchasing behavior (`is_purchase_item` vs `is_customer_provided_item`)
- Material request type ("Purchase" vs "Customer Provided")
- Subcontracting flag
- Inventory valuation implications

KnitERP automatically creates **both versions** whenever one is created, linked as ERPNext **Item Alternatives** (two-way substitution).

### Flow: `ensure_dual_yarn_versions()` (item.py:40-63)

```
Trigger: CustomItem.after_insert() when classification == "Yarn"

Step 1: Enable allow_alternative_item on current item (via db_set)

Step 2: Determine current type:
        if is_customer_provided_item → current is CP
           → Create Base item if missing
        else → current is Base
           → Create CP item if missing

Step 3: Create the missing counterpart via create_variant_item()

Step 4: Create Item Alternative linking both (two-way)
```

### Created Item Properties

| Property | Base Item | CP Item |
|----------|-----------|---------|
| `item_code` | `YR-30-CTN-RAW` | `YR-30-CTN-RAW - CP` |
| `is_customer_provided_item` | 0 | 1 |
| `is_purchase_item` | 1 | 0 |
| `is_sub_contracted_item` | 0 | 1 |
| `is_sales_item` | 0 | 0 |
| `default_material_request_type` | Purchase | Customer Provided |
| `allow_alternative_item` | 1 | 1 |
| `include_item_in_manufacturing` | 1 | 1 |

### Item Alternative Record

```python
{
    "doctype": "Item Alternative",
    "item_code": "YR-30-CTN-RAW",           # Base
    "alternative_item_code": "YR-30-CTN-RAW - CP",  # CP
    "two_way": 1                              # Either can substitute the other
}
```

**Why two-way?** When creating a Work Order, the BOM might specify base yarn, but if the customer provides yarn, the system can substitute. Or vice versa.

### Legacy Path (non-Yarn CP items)

For non-Yarn items that are `is_customer_provided_item`, `create_purchase_item()` fires instead — creates only a Base version (no CP creation, no Item Alternative). This is legacy behavior retained for edge cases.

---

## 7. Smart Search Architecture

### Overview

KnitERP replaces Frappe's default Item link-field search with a **multi-layer fuzzy token search**.

```
hooks.py:
  standard_queries = {
      "Item": "kniterp.api.item_search.smart_search"
  }
```

Every Item Link field in the system automatically uses smart_search.

### Resolution Pipeline

When a user types `"30s ctn slb sj"` in any Item Link field:

```
Input: "30s ctn slb sj"
         ↓
  1. Exact link validation (full item_code match?)
     → No match → continue
         ↓
  2. resolve_tokens("30s ctn slb sj")
     ├── Normalize: lowercase, strip apostrophes/commas/+/%
     ├── Split on whitespace: ["30s", "ctn", "slb", "sj"]
     │
     │   For each token:
     │   ├── Layer 1: Multi-word join ("poly cotton" → P.C.)
     │   ├── Layer 2: Exact alias match ("ctn" → Cotton)
     │   ├── Layer 3a: Prefix match for short tokens ≤3 chars
     │   ├── Layer 3b: Fuzzy match (Levenshtein ≤ 2) for non-numeric tokens
     │   ├── Layer 4: Prefix match for longer tokens (fallback)
     │   └── Unresolved if no match
     │
     │   Results:
     │   ├── "30s" → exact → "30's" (count)
     │   ├── "ctn" → exact → "Cotton" (fiber)
     │   ├── "slb" → exact → "Slub" (modifier)
     │   └── "sj"  → exact → "S/Jersey" (structure)
         ↓
  3. Query Item Search Token index
     SELECT item_code, COUNT(DISTINCT token) AS match_count
     FROM Item Search Token
     WHERE token IN ("30's", "Cotton", "Slub", "S/Jersey")
     GROUP BY item_code
         ↓
  4. Dual scoring:
     PRIMARY: token match count (how many of user's tokens appear in item)
     SECONDARY: LIKE score (raw tokens found in item_name via LIKE %term%)
     → Secondary breaks ties (e.g., "100" in "100% Cotton" boosts that item)
         ↓
  5. Return sorted results: [[item_code, item_name], ...]
```

### Fuzzy Matching Rules

| Token length | Strategy order | Max Levenshtein distance |
|-------------|----------------|--------------------------|
| ≤ 3 chars | Prefix first, then fuzzy | 1 |
| > 3 chars | Fuzzy first, then prefix | 2 |
| Numeric | Prefix only (no fuzzy) | N/A |

**Rationale**: Short tokens have too many fuzzy neighbors (e.g., "sn" vs "sj" both distance 1). Prefix is more reliable for short tokens. Numeric tokens are specific — "100" should not fuzzy-match "10".

### Alias Cache

- In-memory dict: `{alias_lowercase: {canonical, dimension}}`
- Loaded from `Item Token Alias` table
- Refreshes every 60 seconds (`_alias_cache_ts`)
- Invalidated via `invalidate_alias_cache()` (call after alias table changes)

### Search Index Rebuild

**Automatic**: `on_item_save()` hook fires on `after_insert` and `on_update` → rebuilds index for that single item.

**Manual full rebuild**: `rebuild_all_search_tokens()` (whitelisted API or bench command).

Process:
1. Delete existing `Item Search Token` records for the item
2. Parse `item_name` through `resolve_tokens()` to extract canonical tokens
3. Insert one `Item Search Token` per canonical token found

---

## 8. Hook & Event Wiring

### hooks.py Configuration

```python
# Class override — controls autoname, validate, after_insert
override_doctype_class = {
    "Item": "kniterp.kniterp.overrides.item.CustomItem",
}

# Global search override — all Item Link fields use smart search
standard_queries = {
    "Item": "kniterp.api.item_search.smart_search"
}

# Global JS — Composer dialog + Link field intercept loaded on every desk page
app_include_js = [
    "/assets/kniterp/js/item_composer.js",
    ...
]

# Document events
doc_events = {
    "Item": {
        "before_save": "kniterp.api.item.enforce_batch_tracking_for_fabric_yarn",
        "after_insert": "kniterp.api.item_search.on_item_save",
        "on_update": "kniterp.api.item_search.on_item_save"
    },
}

# Fixtures (synced on bench migrate)
fixtures = [
    "Item Token",         # Full table export (121 records: count/fiber/lycra/modifier/state/structure)
    "Item Token Alias",   # Full table export (~248 records)
    ...
]
```

### Event Sequence on Item Save

```
1. CustomItem.autoname()          ← override_doctype_class
2. CustomItem.validate()          ← override_doctype_class
3. enforce_batch_tracking()       ← doc_events.before_save
4. [Item saved to DB]
5. CustomItem.after_insert()      ← override_doctype_class (first save only)
6. on_item_save()                 ← doc_events.after_insert / on_update
```

---

## 9. ignore_permissions Audit

| Location | Call | Justification |
|----------|------|---------------|
| `item.py:110` | `item_doc.insert(ignore_permissions=True)` | Creates the paired Base/CP yarn item. System-initiated automatic creation during after_insert — no user action. **Justified**: user already has permission to create the triggering item; the counterpart is a system-managed twin. |
| `item.py:120` | `alt.insert(ignore_permissions=True)` | Creates Item Alternative link between Base and CP. System-managed relationship. **Justified**: Item Alternative is a lookup record, not a security boundary. |
| `item_composer.py:335` | `doc.insert(ignore_permissions=True)` | Creates Item from Composer dialog. **Risk**: bypasses Item permissions entirely. Any user who can call the whitelisted API can create Items regardless of role. **Recommendation**: Replace with `doc.insert()` (respects permissions) or add explicit `frappe.has_permission("Item", "create")` check. |
| `item_composer.py:419` | `token_doc.insert(ignore_permissions=True)` | Creates Item Token from Composer. **Moderate risk**: Item Token has permissions for System Manager and Item Manager only. This bypasses that. **Recommendation**: Add role check or use `doc.insert()`. |
| `item_composer.py:430` | `alias.insert(ignore_permissions=True)` | Creates Item Token Alias from Composer. Same concern as above. |
| `item_search.py:448` | `doc.insert(ignore_permissions=True)` | Rebuilds search index tokens. System-managed index records. **Justified**: these are internal search records, not user-facing data. |
| `seed_aliases.py:304` | `doc.insert(ignore_permissions=True)` | Seed script, runs from bench console. **Justified**: admin-only operation. |
| `seed_item_tokens.py:165` | `doc.insert(ignore_permissions=True)` | Seed script. **Justified**: same as above. |

### Summary

- **3 calls need review**: `create_composer_item`, `add_new_token`, and its alias creation — these are user-facing whitelisted APIs that bypass permission checks.
- **5 calls are justified**: system-managed records (search index, paired items, seed scripts).

---

## 10. Edge Cases & Risks

### What happens if attributes are changed after item creation?

**Short answer: Nothing updates automatically.**

- Item names and codes are generated **once** at creation time and become the permanent `item_code` (which IS the document `name` for Fabric/Yarn items).
- If an Item Token's `short_code` or `canonical` is changed, existing items are NOT renamed or recoded.
- The **search index** WILL update on next item save (via `on_item_save` hook), but only if the `item_name` is manually changed to match.
- **Risk**: Renaming a Token creates a mismatch between the token vocabulary and existing item codes/names. Tokens should be treated as append-only in practice.

### Duplicate detection gaps

- Preview checks `item_code` exact match and `item_name` exact match
- Does NOT check partial name overlaps (e.g., two items with same attributes but different modifier order)
- Modifier order in code IS deterministic (mod1 before mod2 in code), but user could pick differently in two sessions

### Search index staleness

- Alias cache is in-memory with 60s TTL — new aliases take up to 60s to appear in search
- Search tokens are only rebuilt on Item save — if aliases are added/changed, existing items' search tokens don't update until their next save
- Full rebuild available via `rebuild_all_search_tokens()` API

### Yarn dual-creation edge cases

- If the after_insert for the first item (e.g., Base) creates the CP item, that CP item's after_insert also fires `ensure_dual_yarn_versions()` — but it sees the Base already exists, so no infinite loop
- If item creation fails midway (e.g., CP creation fails after Base is saved), you get an orphan without its pair
- The `allow_alternative_item` flag is set via `db_set` (bypasses validation) — if Item validation later checks this, it's already set

### Composer creates non-textile items without proper autoname

- "Other" classification items get `item_code` set by user in the Composer
- But `CustomItem.autoname()` only handles Fabric/Yarn — "Other" falls through to `super().autoname()` which uses ERPNext's naming series
- This means the user-provided `item_code` becomes both `item_code` AND input to ERPNext's naming — could conflict if ERPNext has a naming series for Items

### No rollback on commit

- `create_composer_item()` calls `frappe.db.commit()` explicitly after insert
- If a subsequent error occurs (e.g., in after_insert hooks), the item is already committed
- `add_new_token()` also calls explicit `frappe.db.commit()`

---

## 11. File Reference Index

### Python Files

| File | Path | Purpose |
|------|------|---------|
| CustomItem override | `kniterp/kniterp/overrides/item.py` | autoname, validate, after_insert, yarn dual-creation |
| Item API | `kniterp/api/item.py` | `enforce_batch_tracking_for_fabric_yarn` (1 method) |
| Item Composer API | `kniterp/api/item_composer.py` | `get_composer_options`, `resolve_for_composer`, `preview_item`, `create_composer_item`, `add_new_token`, `create_item_token` (6 methods) |
| Item Search API | `kniterp/api/item_search.py` | `smart_search`, `resolve_tokens`, `rebuild_search_index`, `on_item_save`, `rebuild_all_search_tokens` |
| Seed Aliases | `kniterp/api/seed_aliases.py` | 282 aliases from Busy data analysis |
| Seed Item Tokens | `kniterp/api/seed_item_tokens.py` | Derives Item Tokens from aliases with short code map |
| Seed Test Items | `kniterp/api/seed_test_items.py` | Test item fixtures covering all patterns |

### JavaScript Files

| File | Path | Purpose |
|------|------|---------|
| Item Composer | `kniterp/public/js/item_composer.js` | Global dialog (913 lines): Composer UI, Quick Fill, alias autocomplete, preview, create, Link field intercept |

### DocType JSONs

| DocType | Path | Records |
|---------|------|---------|
| Item Token | `kniterp/kniterp/doctype/item_token/item_token.json` | 121 master tokens (fixture) |
| Item Token Alias | `kniterp/kniterp/doctype/item_token_alias/item_token_alias.json` | ~248 aliases (fixture) |
| Item Search Token | `kniterp/kniterp/doctype/item_search_token/item_search_token.json` | Auto-populated index |

### Fixtures

| File | Contents |
|------|----------|
| `fixtures/item_token.json` | All 121 Item Token records with short_codes (synced on migrate) |
| `fixtures/item_token_alias.json` | All alias records (synced on migrate) |
| `fixtures/custom_field.json` | Job Card, Batch, SCR Item, SO/PO Item custom fields (no Item fields — `custom_item_classification` created via UI) |

---

## Appendix: Item Code Examples

| Classification | Selections | Item Name | Item Code |
|---------------|-----------|-----------|-----------|
| Fabric | 30's Cotton S/Jersey Raw | 30's Cotton S/Jersey Raw | `FB-30-CTN-SJ-RAW` |
| Fabric | 30's Cotton Slub S/Jersey Dyed | 30's Cotton Slub S/Jersey Dyed | `FB-30-CTN-SLB-SJ-DYED` |
| Fabric | 24's P.C. Fleece Lycra 20Dn Raw | 24's P.C. Fleece Lycra 20Dn Raw | `FB-24-PC-FLC-LYC-20D-RAW` |
| Yarn | 30's Cotton Raw | 30's Cotton Yarn Raw | `YR-30-CTN-RAW` |
| Yarn (CP) | 30's Cotton Raw (CP) | 30's Cotton Yarn Raw | `YR-30-CTN-RAW - CP` |
| Fabric | 30's Cotton BCI Melange Interlock Y/D | 30's Cotton BCI Melange Interlock Y/D | `FB-30-CTN-BCI-MEL-ILCK-YD` |
