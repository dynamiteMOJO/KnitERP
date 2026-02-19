# KNITERP Architecture Review (Frappe v16)

This document is derived from static code/fixture discovery of `frappe-bench/apps/kniterp` and maps runtime architecture, data model, hook behavior, and end-to-end business flows.

## 1) System Architecture Diagram

```mermaid
flowchart LR
    subgraph UI["Desk UI / Client Layer"]
        PW["Page: production_wizard.js"]
        AC["Page: action_center.js"]
        BD["Page: bom_designer.js"]
        KH["Page: kniterp_home.js"]
        SEL["Global JS: kniterp_item_selector.js"]
        SOJS["Form JS: sales_order.js + item_selector_form_botton.js"]
        MATJS["Form JS: machine_attendance_tool.js"]
    end

    subgraph API["Whitelisted/API Layer"]
        APW["kniterp.api.production_wizard.*"]
        AAC["kniterp.api.action_center.*"]
        ABOM["kniterp.api.bom_tool.*"]
        AIS["kniterp.api.item_selector.*"]
        ASUB["kniterp.api.subcontracting.*"]
        ATH["kniterp.api.textile_attributes.*"]
        AHOME["kniterp.kniterp.page.kniterp_home.get_dashboard_metrics"]
        AMAT["machine_attendance_tool.generate_attendance"]
    end

    subgraph Hooks["Hook/Override Runtime Layer"]
        HOOKS["hooks.py"]
        ODC["override_doctype_class"]
        OWM["override_whitelisted_methods"]
        DEV["doc_events"]
        MP1["Monkey patch: SubcontractingReceipt.validate"]
        MP2["Monkey patch: stock_reservation_entry.*"]
    end

    subgraph ERP["ERPNext/Frappe Core Objects"]
        ITEM["Item (+ Item Alternative)"]
        BOM["BOM / Subcontracting BOM"]
        MFG["Work Order / Job Card"]
        SUBC["PO / SCO / SCR / SCIO"]
        STOCK["Stock Entry / SRE / Bin"]
        SALE["Sales Order / Delivery Note / Sales Invoice"]
        BUY["Purchase Invoice / Purchase Receipt"]
        HR["Salary Slip / Attendance / Employee"]
    end

    subgraph CustomData["Custom DocTypes & Fixtures"]
        T1["Textile Attribute + Value"]
        T2["Item Textile Attribute"]
        T3["Machine Attendance + Tool"]
        T4["Monthly Conveyance"]
        T5["Production Wizard Note"]
        FX["fixtures/*.json\n(Custom Field, Property Setter, Client Script, Page, Workspace Sidebar)"]
    end

    PW --> APW
    AC --> AAC
    AC --> APW
    BD --> ABOM
    BD --> APW
    KH --> AHOME
    SEL --> AIS
    SOJS --> ASUB
    SOJS --> AIS
    SOJS --> ATH
    MATJS --> AMAT

    APW --> MFG
    APW --> SUBC
    APW --> STOCK
    APW --> SALE
    APW --> BUY
    APW --> T5
    APW --> BOM

    AAC --> BUY
    AAC --> SALE
    ABOM --> BOM
    AIS --> ITEM
    ASUB --> SUBC
    AHOME --> SALE
    AHOME --> BUY
    AHOME --> HR
    AMAT --> T3

    HOOKS --> ODC
    HOOKS --> OWM
    HOOKS --> DEV
    HOOKS --> MP1
    HOOKS --> MP2

    ODC --> ITEM
    ODC --> MFG
    ODC --> SUBC
    OWM --> SUBC
    DEV --> HR
    DEV --> MFG
    DEV --> STOCK
    DEV --> SUBC

    T1 --> T2
    T2 --> ITEM
    T4 --> HR
    FX --> ITEM
    FX --> MFG
    FX --> SUBC
```

Key anchors:
- `kniterp/hooks.py:34`, `kniterp/hooks.py:46`, `kniterp/hooks.py:53`, `kniterp/hooks.py:57`
- `kniterp/__init__.py:4`
- `kniterp/api/production_wizard.py:938`, `kniterp/api/action_center.py:6`, `kniterp/api/bom_tool.py:7`

## 2) ER Diagram (All Custom DocTypes)

```mermaid
erDiagram
    TEXTILE_ATTRIBUTE {
        string name PK
        string kniterp_attribute_name
        string kniterp_attribute_code
        string kniterp_field_type
        int kniterp_sequence
        int kniterp_affects_naming
        int kniterp_affects_code
        int kniterp_use_value_master
        int kniterp_is_active
    }

    TEXTILE_ATTRIBUTE_VALUE {
        string name PK
        string kniterp_attribute FK
        string kniterp_value
        string kniterp_short_code
        int kniterp_sort_order
        int kniterp_is_active
    }

    ITEM_ATTRIBUTE_APPLIES_TO_VALUES {
        string name PK
        string type_of_item
    }

    ITEM_ATTRIBUTE_APPLIES_TO {
        string parent FK
        string item_attribute_applies_to FK
    }

    ITEM_TEXTILE_ATTRIBUTE {
        string parent FK
        string kniterp_attribute FK
        string kniterp_value FK
        float kniterp_numeric_value
        string kniterp_display_value
        int kniterp_sequence
        int kniterp_affects_naming
        int kniterp_affects_code
        string kniterp_short_code
    }

    ITEM_TYPES_FOR_ATTRIBUTES {
        string name PK
        string item_types_for_attributes
    }

    MACHINE_ATTENDANCE_TOOL {
        string name PK
        date date
        string company FK
    }

    MACHINE_ATTENDANCE_ENTRY {
        string parent FK
        string machine FK
        string morning_employee FK
        float morning_production_kg
        string night_employee FK
        float night_production_kg
    }

    MACHINE_ATTENDANCE {
        string name PK
        string employee FK
        date date
        string shift FK
        string machine FK
        string company FK
        float production_qty_kg
    }

    MONTHLY_CONVEYANCE {
        string name PK
        string employee FK
        date month
        int total_km
        currency rate_per_km
        currency amount
    }

    PRODUCTION_WIZARD_NOTE {
        string name PK
        string sales_order FK
        string sales_order_item
        string item_code FK
        text note
    }

    ITEM {
        string name PK
        string custom_item_classification
    }

    SALES_ORDER {
        string name PK
    }

    EMPLOYEE {
        string name PK
    }

    WORKSTATION {
        string name PK
    }

    SHIFT_TYPE {
        string name PK
    }

    COMPANY {
        string name PK
    }

    TEXTILE_ATTRIBUTE ||--o{ TEXTILE_ATTRIBUTE_VALUE : "kniterp_attribute"
    TEXTILE_ATTRIBUTE ||--o{ ITEM_ATTRIBUTE_APPLIES_TO : "kniterp_applies_to"
    ITEM_ATTRIBUTE_APPLIES_TO_VALUES ||--o{ ITEM_ATTRIBUTE_APPLIES_TO : "item_attribute_applies_to"

    ITEM ||--o{ ITEM_TEXTILE_ATTRIBUTE : "custom_textile_attributes"
    TEXTILE_ATTRIBUTE ||--o{ ITEM_TEXTILE_ATTRIBUTE : "kniterp_attribute"
    TEXTILE_ATTRIBUTE_VALUE ||--o{ ITEM_TEXTILE_ATTRIBUTE : "kniterp_value"

    MACHINE_ATTENDANCE_TOOL ||--o{ MACHINE_ATTENDANCE_ENTRY : "entries"
    WORKSTATION ||--o{ MACHINE_ATTENDANCE_ENTRY : "machine"
    EMPLOYEE ||--o{ MACHINE_ATTENDANCE_ENTRY : "morning/night"

    EMPLOYEE ||--o{ MACHINE_ATTENDANCE : "employee"
    WORKSTATION ||--o{ MACHINE_ATTENDANCE : "machine"
    SHIFT_TYPE ||--o{ MACHINE_ATTENDANCE : "shift"
    COMPANY ||--o{ MACHINE_ATTENDANCE : "company"

    EMPLOYEE ||--o{ MONTHLY_CONVEYANCE : "employee"

    SALES_ORDER ||--o{ PRODUCTION_WIZARD_NOTE : "sales_order"
    ITEM ||--o{ PRODUCTION_WIZARD_NOTE : "item_code"
```

Key anchors:
- `kniterp/kniterp/doctype/*/*.json`
- `kniterp/fixtures/custom_field.json:75`, `kniterp/fixtures/custom_field.json:255`

## 3) Hook Interaction Diagram

```mermaid
flowchart TD
    BOOT["App import / site boot"] --> H1["kniterp/hooks.py"]
    BOOT --> H2["kniterp/__init__.py"]

    H1 --> I1["import overrides.subcontracting_receipt"]
    I1 --> P1["SubcontractingReceipt.validate = patched_validate"]

    H2 --> I2["import overrides.sre_dashboard_fix"]
    I2 --> P2["stock_reservation_entry fn reassignment"]

    H1 --> ODC["override_doctype_class"]
    ODC --> ODC1["Item -> CustomItem"]
    ODC --> ODC2["Job Card -> CustomJobCard"]
    ODC --> ODC3["Work Order -> CustomWorkOrder"]
    ODC --> ODC4["SCIO -> CustomSubcontractingInwardOrder"]

    H1 --> OWM["override_whitelisted_methods"]
    OWM --> OWM1["erpnext...make_subcontracting_po -> kniterp override"]

    H1 --> DEV["doc_events"]
    DEV --> E1["Salary Slip.before_save -> payroll.calculate_variable_pay"]
    DEV --> E2["Work Order.before_submit -> set_planned_qty_on_work_order"]
    DEV --> E3["Job Card.before_insert -> set_job_card_qty_from_planned_qty"]
    DEV --> E4["Purchase Receipt.on_submit -> subcontracting.on_pr_submit_complete_job_cards"]
    DEV --> E5["Subcontracting Receipt.on_submit -> overrides.subcontracting_receipt.on_submit_complete_job_cards"]
    DEV --> E6["Stock Entry.on_submit/on_cancel -> subcontracting.update_job_card_transferred"]

    H1 --> SCH["scheduler_events"]
    SCH --> NONE["No active scheduler hooks (commented template only)"]
```

Key anchors:
- `kniterp/hooks.py:1`, `kniterp/hooks.py:2`, `kniterp/hooks.py:46`, `kniterp/hooks.py:53`, `kniterp/hooks.py:57`, `kniterp/hooks.py:232`
- `kniterp/__init__.py:4`
- `kniterp/kniterp/overrides/subcontracting_receipt.py:21`
- `kniterp/kniterp/overrides/sre_dashboard_fix.py:64`

## 4) Item Lifecycle Flow

```mermaid
flowchart TD
    A["SO/PO/DN row or BOM Designer\nopens item selector dialog"] --> B["search_textile_attribute_values\n(kniterp.api.item_selector)"]
    B --> C["User selects attribute set"]
    C --> D["find_exact_items\n(kniterp.api.item_selector)"]

    D --> E{"Exact item exists?"}
    E -- Yes --> F["Pick existing item\nset item_code on row"]

    E -- No / Create New --> G["Store payload in sessionStorage\nkniterp_new_item_payload"]
    G --> H["Open Item new form"]
    H --> I["item_client_script.js onload\npre-fills classification + textile rows"]

    I --> J["Save Item"]
    J --> K["CustomItem.validate\nprocess_textile_attributes + build_textile_name"]
    J --> L["CustomItem.autoname\nbuild_textile_code + classification prefix"]

    K --> M{"Classification = Yarn?"}
    L --> M
    M -- No --> N["Item created"]
    M -- Yes --> O["after_insert.ensure_dual_yarn_versions"]
    O --> P["create base/CP paired Item\ninsert(ignore_permissions=True)"]
    O --> Q["create Item Alternative\ntwo_way=1"]
    P --> N
    Q --> N
```

Key anchors:
- `kniterp/public/js/kniterp_item_selector.js:89`, `kniterp/public/js/kniterp_item_selector.js:201`, `kniterp/public/js/kniterp_item_selector.js:292`
- `kniterp/public/js/item_client_script.js:4`, `kniterp/public/js/item_client_script.js:13`, `kniterp/public/js/item_client_script.js:57`
- `kniterp/kniterp/overrides/item.py:7`, `kniterp/kniterp/overrides/item.py:23`, `kniterp/kniterp/overrides/item.py:120`, `kniterp/kniterp/overrides/item.py:218`

## 5) Manufacturing / Subcontracting Flow

```mermaid
flowchart LR
    SOI["Sales Order Item"] --> BOMD["BOM Designer\ncreate_multilevel_bom"]
    BOMD --> SOBOM["update_so_item_bom"]

    SOI --> SCIO["create_subcontracting_inward_order\n(optional subcontract path)"]
    SOI --> WO["create_work_order"]
    SCIO --> WO

    WO --> START["start_work_order\n(submit WO + create Job Cards)"]
    START --> JC["Job Cards per operation"]

    JC --> OP{"Operation type"}

    OP -- In-house --> COP["complete_operation\nadd time log + Manufacture SE"]
    COP --> JCUP["update Job Card + Work Order qty/status"]

    OP -- Subcontracted --> CPO["create_subcontracting_order\n(PO + SCO)"]
    CPO --> SEND["transfer_materials_to_subcontractor\nStock Entry: Send to Subcontractor"]
    CPO --> RCV["receive_subcontracted_goods\ncreate SCR (+ optional PR submit)"]
    RCV --> HUP["doc_events + overrides\nupdate JC manufactured/consumed/status"]

    JCUP --> CJC["complete_job_card (manual close path)"]
    HUP --> CJC

    CJC --> DN["create_delivery_note"]
    DN --> SI1["create_sales_invoice"]
    DN --> SI2["create_scio_sales_invoice"]
```

Key anchors:
- `kniterp/api/production_wizard.py:938`, `kniterp/api/production_wizard.py:1135`, `kniterp/api/production_wizard.py:1229`, `kniterp/api/production_wizard.py:1507`, `kniterp/api/production_wizard.py:2079`, `kniterp/api/production_wizard.py:2326`, `kniterp/api/production_wizard.py:2499`, `kniterp/api/production_wizard.py:2628`, `kniterp/api/production_wizard.py:2737`
- `kniterp/subcontracting.py:86`, `kniterp/subcontracting.py:100`
- `kniterp/kniterp/overrides/subcontracting_receipt.py:24`

## 6) Payroll / HR Flow

```mermaid
flowchart TD
    MATUI["Machine Attendance Tool UI"] --> MAPI["generate_attendance (whitelist)"]
    MAPI --> MINs["Insert Machine Attendance\nignore_permissions=True"]
    MINs --> MVAL["MachineAttendance.validate\n(no duplicate, Operator-only, qty checks)"]

    SS["Salary Slip save"] --> HOOK["doc_events: Salary Slip.before_save"]
    HOOK --> PAY["payroll.calculate_variable_pay"]

    PAY --> SSA["Salary Structure Assignment\n(base + variable)"]
    PAY --> ATT["Attendance\nSunday, dual shift, absent/present"]
    PAY --> MA["Machine Attendance\nextra pay logic"]
    PAY --> MC["Monthly Conveyance\namount aggregation"]
    PAY --> HOL["Holiday + adjacent absence checks"]

    SSA --> COMP["Set salary components\nSunday/DualShift/Machine/Conveyance/Tea/Rejected Holiday"]
    ATT --> COMP
    MA --> COMP
    MC --> COMP
    HOL --> COMP

    COMP --> NET["slip.calculate_net_pay()"]
    NET --> DONE["Salary Slip persisted"]
```

Key anchors:
- `kniterp/hooks.py:59`
- `kniterp/payroll.py:9`, `kniterp/payroll.py:76`, `kniterp/payroll.py:118`, `kniterp/payroll.py:137`
- `kniterp/kniterp/doctype/machine_attendance_tool/machine_attendance_tool.py:10`, `kniterp/kniterp/doctype/machine_attendance_tool/machine_attendance_tool.py:43`
- `kniterp/kniterp/doctype/machine_attendance/machine_attendance.py:11`

## 7) Stock Impact Flow

```mermaid
flowchart TD
    WO["SCIO-linked Work Order\nreserve_stock=1"] --> C1["complete_operation"]
    C1 --> SE["Manufacture Stock Entry submit"]

    SE --> FG_SRE["Manual FG SRE creation\nfor SCIO voucher"]
    SE --> BIN1["Direct Bin db_set\nreserved_qty_for_production/projected_qty"]
    SE --> JCQ["Job Card manufactured_qty/consumption sync"]

    SENDSE["Send to Subcontractor SE"] --> DEV["doc_events Stock Entry on_submit/on_cancel"]
    DEV --> JCT["Recompute Job Card transferred_qty"]

    REV["revert_production_entry"] --> SRECAN["Cancel linked SREs\n(or db_set reserved_qty)"]
    REV --> SECAN["Cancel Stock Entry"]
    REV --> BIN2["Recompute Bin reserves\n+ direct db_set adjustments"]
    REV --> TLDEL["Delete Job Card Time Log\nignore_permissions=True"]

    SREPATCH["Runtime patch: stock_reservation_entry.*"] --> DASH["SRE dashboard reservation math\n(reserved - delivered - consumed)"]
```

Key anchors:
- `kniterp/api/production_wizard.py:1674`, `kniterp/api/production_wizard.py:1713`, `kniterp/api/production_wizard.py:1915`, `kniterp/api/production_wizard.py:1967`, `kniterp/api/production_wizard.py:1992`, `kniterp/api/production_wizard.py:2014`
- `kniterp/subcontracting.py:100`, `kniterp/subcontracting.py:106`, `kniterp/subcontracting.py:136`
- `kniterp/kniterp/overrides/sre_dashboard_fix.py:64`

## 8) API Interaction Map

```mermaid
flowchart LR
    subgraph JS["Page/Form JS Callers"]
        PWJS["production_wizard.js"]
        ACJS["action_center.js"]
        BDJS["bom_designer.js"]
        SOJS["sales_order.js"]
        SELJS["kniterp_item_selector.js + item_client_script.js"]
        MAJS["machine_attendance_tool.js"]
        KHJS["kniterp_home.js"]
    end

    subgraph APIS["Whitelisted Methods"]
        PWAPI["kniterp.api.production_wizard\n(get_* / create_* / complete_* / revert_* / update_*)"]
        ACAPI["kniterp.api.action_center\n(get_action_items, get_fix_details, create_purchase_invoice, submit_purchase_invoice)"]
        BOMAPI["kniterp.api.bom_tool\n(get_multilevel_bom, create_multilevel_bom)"]
        SUBAPI["kniterp.api.subcontracting\n(get_subcontract_po_items, make_subcontract_purchase_order)"]
        ISAPI["kniterp.api.item_selector\n(search_textile_attribute_values, find_exact_items)"]
        MAAPI["generate_attendance"]
        HOMEAPI["get_dashboard_metrics"]
    end

    subgraph Mut["Downstream Mutation Surface"]
        M1["Work Order / Job Card"]
        M2["BOM / Subcontracting BOM"]
        M3["PO / SCO / SCR / PR / PI"]
        M4["Stock Entry / SRE / Bin"]
        M5["Delivery Note / Sales Invoice"]
        M6["Subcontracting Inward Order / Warehouse"]
        M7["Production Wizard Note"]
        M8["Machine Attendance"]
        R1["Read-only datasets\n(Item selector, dashboard metrics, status summaries)"]
    end

    PWJS --> PWAPI
    ACJS --> ACAPI
    ACJS --> PWAPI
    BDJS --> BOMAPI
    BDJS --> PWAPI
    SOJS --> SUBAPI
    SELJS --> ISAPI
    MAJS --> MAAPI
    KHJS --> HOMEAPI

    PWAPI --> M1
    PWAPI --> M3
    PWAPI --> M4
    PWAPI --> M5
    PWAPI --> M6
    PWAPI --> M7
    PWAPI --> R1

    ACAPI --> M3
    BOMAPI --> M2
    BOMAPI --> M1
    SUBAPI --> M3
    ISAPI --> R1
    HOMEAPI --> R1
    MAAPI --> M8
```

High-risk API note:
- `kniterp.api.production_wizard.complete_job_card` is defined twice (`production_wizard.py:1761` and `production_wizard.py:3092`); later definition wins at import time.

Primary caller anchors:
- `kniterp/kniterp/page/production_wizard/production_wizard.js:213`
- `kniterp/kniterp/page/action_center/action_center.js:68`
- `kniterp/kniterp/page/bom_designer/bom_designer.js:35`
- `kniterp/public/js/sales_order.js:19`
- `kniterp/public/js/kniterp_item_selector.js:90`
- `kniterp/kniterp/doctype/machine_attendance_tool/machine_attendance_tool.js:93`
- `kniterp/kniterp/page/kniterp_home/kniterp_home.js:245`

---

## Architecture Observations (for review context)

1. Kniterp is organized as a custom operational control layer on top of ERPNext manufacturing/subcontracting, with `production_wizard` as the dominant orchestration entrypoint.
2. Runtime behavior is altered by three mechanisms simultaneously: doctype class overrides, doc_event hooks, and monkey patches at import time.
3. Stock reservation and subcontracting flows are deeply customized, including manual SRE creation/cancellation and direct Bin field mutation.
4. Item governance and SKU generation are strongly attribute-driven, but creation pathways are distributed across JS preload, Item override logic, and fixture-level field/property behavior.
5. Payroll/HR custom logic is concentrated in a single Salary Slip `before_save` hook plus custom machine attendance capture, creating a narrow but high-impact modification surface.
