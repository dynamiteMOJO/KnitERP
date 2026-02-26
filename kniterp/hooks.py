import kniterp.kniterp.overrides.job_card
import kniterp.kniterp.overrides.sre_dashboard_fix  # guarded patch — see module docstring


app_name = "kniterp"
app_title = "Kniterp"
app_publisher = "Kartik"
app_description = "customization related to Knitting manufacturing unit."
app_email = "krtksng@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "kniterp",
# 		"logo": "/assets/kniterp/logo.png",
# 		"title": "Kniterp",
# 		"route": "/kniterp",
# 		"has_permission": "kniterp.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/kniterp/css/kniterp.css"
# app_include_js = "/assets/kniterp/js/kniterp.js"

app_include_js = [
    "/assets/kniterp/js/item_composer.js",
    "/assets/kniterp/js/item_client_script.js",
    "/assets/kniterp/js/sales_order_subcontracting_fix.js",
    "/assets/kniterp/js/sales_order.js",
    "/assets/kniterp/js/purchase_order.js",
]

app_include_css = [
    "/assets/kniterp/css/kniterp.css"
]

override_doctype_class = {
    "Item": "kniterp.kniterp.overrides.item.CustomItem",
    "Job Card": "kniterp.kniterp.overrides.job_card.CustomJobCard",
    "Subcontracting Inward Order": "kniterp.kniterp.overrides.subcontracting_inward_order.CustomSubcontractingInwardOrder",
    "Work Order": "kniterp.kniterp.overrides.work_order.CustomWorkOrder"
}

override_whitelisted_methods = {
    "erpnext.manufacturing.doctype.job_card.job_card.make_subcontracting_po": "kniterp.kniterp.overrides.job_card.make_subcontracting_po"
}

# All Item link-field searches use our smart fuzzy search
standard_queries = {
    "Item": "kniterp.api.item_search.smart_search"
}

doc_events = {
    "Item": {
        "before_save": "kniterp.api.item.enforce_batch_tracking_for_fabric_yarn",
        "after_insert": "kniterp.api.item_search.on_item_save",
        "on_update": "kniterp.api.item_search.on_item_save"
    },
    "Salary Slip": {
        "before_save": "kniterp.payroll.calculate_variable_pay"
    },
    "Sales Order": {
        "on_update": "kniterp.api.transaction_parameters.sync_so_params",
        "on_update_after_submit": "kniterp.api.transaction_parameters.sync_so_params"
    },
    "Purchase Order": {
        "on_update": "kniterp.api.transaction_parameters.sync_po_params",
        "on_update_after_submit": "kniterp.api.transaction_parameters.sync_po_params"
    },
    "Work Order": {
        "before_submit": "kniterp.kniterp.overrides.work_order.set_planned_qty_on_work_order"
    },
    "Job Card": {
        "before_insert": "kniterp.kniterp.overrides.job_card.set_job_card_qty_from_planned_qty",
    },
    "Purchase Receipt": {
        "on_submit": "kniterp.subcontracting.on_pr_submit_complete_job_cards"
    },
    "Subcontracting Receipt": {
        "before_validate": "kniterp.kniterp.overrides.subcontracting_receipt.before_validate_set_customer_warehouse",
        "on_submit": "kniterp.kniterp.overrides.subcontracting_receipt.on_submit_complete_job_cards"
    },
    "Stock Entry": {
        "on_submit": "kniterp.subcontracting.on_se_submit_update_job_card_transferred",
        "on_cancel": "kniterp.subcontracting.on_se_cancel_update_job_card_transferred"
    }
}


fixtures = [
    "Textile Attribute",
    "Textile Attribute Value",
    "Transaction Parameter",
    "Item Token Alias",
    "Item Attribute Applies To Values",
    {
        "doctype": "Designation",
        "filters": [["name", "in", ["Master", "Helper", "Operator"]]]
    },
    {
        "doctype": "Client Script",
        "filters": [["module", "=", "Kniterp"]]
    },
    {
        "doctype": "Property Setter",
        "filters": [["module", "=", "Kniterp"]]
    },
    {
        "doctype": "Custom Field",
        "filters": [["module", "=", "Kniterp"]]
    }
]

# include js, css files in header of web template
# web_include_css = "/assets/kniterp/css/kniterp.css"
# web_include_js = "/assets/kniterp/js/kniterp.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "kniterp/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "kniterp/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "kniterp.utils.jinja_methods",
# 	"filters": "kniterp.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "kniterp.install.before_install"
# after_install = "kniterp.install.after_install"
after_install = "kniterp.kniterp.install.after_migrate"
after_migrate = "kniterp.kniterp.install.after_migrate"

# Uninstallation
# ------------

# before_uninstall = "kniterp.uninstall.before_uninstall"
# after_uninstall = "kniterp.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "kniterp.utils.before_app_install"
# after_app_install = "kniterp.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "kniterp.utils.before_app_uninstall"
# after_app_uninstall = "kniterp.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "kniterp.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }



# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"kniterp.tasks.all"
# 	],
# 	"daily": [
# 		"kniterp.tasks.daily"
# 	],
# 	"hourly": [
# 		"kniterp.tasks.hourly"
# 	],
# 	"weekly": [
# 		"kniterp.tasks.weekly"
# 	],
# 	"monthly": [
# 		"kniterp.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "kniterp.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "kniterp.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "kniterp.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["kniterp.utils.before_request"]
# after_request = ["kniterp.utils.after_request"]

# Job Events
# ----------
# before_job = ["kniterp.utils.before_job"]
# after_job = ["kniterp.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"kniterp.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

