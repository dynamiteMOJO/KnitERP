# Item Composer — Edit Existing Token

**Date**: 2026-03-26
**Scope**: `kniterp/public/js/item_composer.js`, `kniterp/api/item_composer.py`

---

## Problem

After a token is created via the Item Composer's "+ Add New" flow, there is no way to fix mistakes (wrong canonical name, wrong short code, missing aliases). Users must go directly to the Item Token DocType form. This is friction for non-technical users.

---

## Solution

Add an "✏️ Edit" button next to each autocomplete dimension field. The button is hidden when the field is empty and visible when a token is selected. Clicking it opens a pre-populated edit dialog.

---

## Frontend Changes (`item_composer.js`)

### 1. New HTML field slots in dialog definition

Three fields that currently have no button slot need a new HTML slot:

| New field name      | Position in dialog                      |
|---------------------|-----------------------------------------|
| `modifier2_edit_btn`| After `modifier2` autocomplete field    |
| `lycra_edit_btn`    | After `lycra` autocomplete field        |
| `state_edit_btn`    | After `state` autocomplete, before Column Break |

Fields that already have a `*_add_btn` slot (count, fiber, modifier1, structure) render the edit button in the same slot alongside "+ Add New".

### 2. Button rendering

A new function `_setup_edit_buttons(dialog)` is called after `_setup_add_new_buttons`.

**Fields with shared slots** (`count_add_btn`, `fiber_add_btn`, `modifier_add_btn`, `structure_add_btn`):
```
[+ Add New]  [✏️ Edit]
```
The existing slot HTML is extended to include the edit button alongside the add button.

**Fields with edit-only slots** (`modifier2_edit_btn`, `lycra_edit_btn`, `state_edit_btn`):
```
[✏️ Edit]
```

### 3. Show/hide logic

`_setup_edit_buttons` attaches to each autocomplete field's `onchange`. When the field value is non-empty, the corresponding edit button is shown. When cleared, it is hidden.

The edit button starts hidden (`style="display:none"`).

Since the existing `onchange` callbacks already call `_update_preview`, the edit button show/hide is added alongside without replacing anything.

### 4. Edit token dialog

Function: `_open_edit_token_dialog(canonical, dimension, parent_dialog)`

The dialog is pre-populated from the already-loaded `parent_dialog._composer_options` — no extra API call to fetch token data.

Fields:
| Field      | Type       | Behaviour                     |
|------------|------------|-------------------------------|
| `dimension`| Data       | Read-only                     |
| `canonical`| Data       | Editable (display name)       |
| `short_code`| Data      | Editable                      |
| `aliases`  | Small Text | Editable, comma-separated     |

A visible warning is shown when the canonical field has been changed:
> ⚠️ Renaming the display name diverges from fixtures — run `bench export-fixtures` after saving.

The warning is shown dynamically (hidden until user types in the canonical field).

Primary action label: **Save Changes**

On success:
1. `frappe.show_alert` with green indicator
2. Close edit dialog
3. Call `_refresh_autocomplete(parent_dialog, dimension, new_canonical)` to reload dropdown
4. The refreshed autocomplete sets the field to `new_canonical` (handles rename case)
5. `_update_preview` fires via the existing refresh flow

---

## Backend Changes (`item_composer.py`)

### New API: `update_item_token`

```python
@frappe.whitelist()
def update_item_token(canonical, new_canonical, new_short_code, new_aliases=""):
```

**Arguments:**
- `canonical` — current canonical name (used to find the record)
- `new_canonical` — updated display name (may equal `canonical` if unchanged)
- `new_short_code` — updated short code
- `new_aliases` — comma-separated alias string

**Steps:**

1. **Validate inputs** — strip whitespace, uppercase `new_short_code`

2. **Short code conflict check** — if `new_short_code` differs from current, check no other token in same dimension already uses it

3. **Rename if canonical changed:**
   - `frappe.rename_doc("Item Token", canonical, new_canonical)` — renames the record; Frappe auto-updates the `token` Link field in all `Item Token Alias` rows
   - Batch-update `Item Token Alias.canonical` (Data field, not auto-updated by rename):
     ```python
     frappe.db.sql(
         "UPDATE `tabItem Token Alias` SET canonical=%s WHERE canonical=%s",
         (new_canonical, canonical)
     )
     ```

4. **Update short code:**
   ```python
   frappe.db.set_value("Item Token", new_canonical, "short_code", new_short_code)
   ```

5. **Reconcile aliases:**
   - Parse `new_aliases` into a list (lowercase, strip, deduplicate)
   - Always include `new_canonical.lower()` in the alias list
   - Fetch existing aliases for this token
   - Delete aliases that are no longer in the new list
   - Insert aliases that are new — skip any that already map to a different token (log a warning, don't throw)

6. **Commit and return:**
   ```python
   frappe.db.commit()
   return {"canonical": new_canonical, "dimension": dimension, "short_code": new_short_code, "aliases": alias_list}
   ```

**Error cases:**
- Token not found → `frappe.throw`
- `new_canonical` already exists as a different token → `frappe.throw`
- Short code conflict in same dimension → `frappe.throw`

---

## What Does NOT Change

- Existing item codes are unaffected (they embed `short_code`, not canonical)
- Existing item names (stored strings) are unaffected — only future items use the updated canonical
- `Item Search Token` index is stale until items re-save, which is acceptable
- The "+ Add New" button behaviour is unchanged

---

## Fixture Warning

`Item Token` is a fixture (`fixtures/item_token.json`, 121 records). If a canonical is renamed in the DB without re-exporting fixtures, the next `bench migrate` will re-insert the old canonical. The edit dialog shows a warning when the canonical field is edited. The developer must run `bench export-fixtures` after any rename.

---

## Files Changed

| File | Change |
|------|--------|
| `kniterp/public/js/item_composer.js` | Add 3 HTML field slots; `_setup_edit_buttons()`; `_open_edit_token_dialog()` |
| `kniterp/api/item_composer.py` | New `update_item_token()` whitelisted method |
