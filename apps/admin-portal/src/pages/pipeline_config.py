"""
Pipeline Configuration Page - View and edit data pipeline configurations
including schedules, source connections, quality thresholds.
CRUD interface backed by config YAML.
"""

import streamlit as st
import yaml
import os
from datetime import datetime
from typing import Any

# Default pipeline configuration structure
DEFAULT_PIPELINE_CONFIG = {
    "pipelines": [
        {
            "id": "sales-ingestion",
            "name": "Sales Data Ingestion",
            "description": "Ingests sales transaction data from ERP system into Fabric lakehouse",
            "enabled": True,
            "schedule": {
                "cron": "0 */2 * * *",
                "timezone": "UTC",
                "description": "Every 2 hours",
            },
            "source": {
                "type": "sql_server",
                "connection_string_secret": "erp-sql-connection",
                "database": "SalesDB",
                "tables": ["Orders", "OrderItems", "Customers", "Products"],
                "incremental_column": "ModifiedDate",
            },
            "destination": {
                "type": "fabric_lakehouse",
                "workspace": "production-workspace",
                "lakehouse": "sales-lakehouse",
                "format": "delta",
            },
            "quality_thresholds": {
                "null_percentage_max": 5.0,
                "duplicate_percentage_max": 1.0,
                "freshness_max_hours": 4,
                "row_count_min": 100,
                "schema_drift_action": "alert",
            },
            "alerts": {
                "on_failure": True,
                "on_quality_violation": True,
                "slack_channel": "#data-pipeline-alerts",
                "email_recipients": ["data-team@company.com"],
            },
        },
        {
            "id": "manufacturing-telemetry",
            "name": "Manufacturing Telemetry",
            "description": "Streams IoT sensor data from manufacturing floor into real-time analytics",
            "enabled": True,
            "schedule": {
                "cron": "*/5 * * * *",
                "timezone": "UTC",
                "description": "Every 5 minutes",
            },
            "source": {
                "type": "iot_hub",
                "connection_string_secret": "iot-hub-connection",
                "consumer_group": "fabric-consumer",
                "event_hub_name": "manufacturing-events",
            },
            "destination": {
                "type": "fabric_lakehouse",
                "workspace": "production-workspace",
                "lakehouse": "manufacturing-lakehouse",
                "format": "delta",
            },
            "quality_thresholds": {
                "null_percentage_max": 2.0,
                "duplicate_percentage_max": 0.5,
                "freshness_max_hours": 1,
                "row_count_min": 500,
                "schema_drift_action": "block",
            },
            "alerts": {
                "on_failure": True,
                "on_quality_violation": True,
                "slack_channel": "#manufacturing-alerts",
                "email_recipients": ["manufacturing-team@company.com"],
            },
        },
        {
            "id": "demand-forecast",
            "name": "Demand Forecast Pipeline",
            "description": "Runs demand forecasting model and writes predictions to serving layer",
            "enabled": True,
            "schedule": {
                "cron": "0 6 * * *",
                "timezone": "America/New_York",
                "description": "Daily at 6 AM ET",
            },
            "source": {
                "type": "fabric_lakehouse",
                "workspace": "production-workspace",
                "lakehouse": "sales-lakehouse",
                "tables": ["fact_sales", "dim_products", "dim_stores"],
            },
            "destination": {
                "type": "postgresql",
                "connection_string_secret": "postgres-connection",
                "schema": "forecasts",
                "table": "demand_predictions",
            },
            "quality_thresholds": {
                "null_percentage_max": 0.0,
                "duplicate_percentage_max": 0.0,
                "freshness_max_hours": 24,
                "row_count_min": 1000,
                "schema_drift_action": "alert",
            },
            "alerts": {
                "on_failure": True,
                "on_quality_violation": True,
                "slack_channel": "#forecasting-alerts",
                "email_recipients": ["analytics-team@company.com"],
            },
        },
        {
            "id": "inventory-sync",
            "name": "Inventory Sync",
            "description": "Synchronizes inventory levels across warehouse management system and analytics",
            "enabled": True,
            "schedule": {
                "cron": "0 * * * *",
                "timezone": "UTC",
                "description": "Every hour",
            },
            "source": {
                "type": "rest_api",
                "base_url_secret": "wms-api-url",
                "auth_type": "oauth2",
                "auth_secret": "wms-client-credentials",
                "endpoints": ["/api/v1/inventory", "/api/v1/warehouses"],
            },
            "destination": {
                "type": "fabric_lakehouse",
                "workspace": "production-workspace",
                "lakehouse": "inventory-lakehouse",
                "format": "delta",
            },
            "quality_thresholds": {
                "null_percentage_max": 1.0,
                "duplicate_percentage_max": 0.0,
                "freshness_max_hours": 2,
                "row_count_min": 50,
                "schema_drift_action": "alert",
            },
            "alerts": {
                "on_failure": True,
                "on_quality_violation": True,
                "slack_channel": "#inventory-alerts",
                "email_recipients": ["supply-chain@company.com"],
            },
        },
    ]
}

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config")
CONFIG_FILE = os.path.join(CONFIG_DIR, "pipelines.yaml")


def _load_config() -> dict[str, Any]:
    """Load pipeline config from YAML file, or create default if not exists."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return yaml.safe_load(f) or DEFAULT_PIPELINE_CONFIG
    return DEFAULT_PIPELINE_CONFIG


def _save_config(config: dict[str, Any]):
    """Save pipeline config to YAML file."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, indent=2)


def _render_pipeline_list(config: dict):
    """Render the pipeline list with status indicators."""
    st.subheader("Configured Pipelines")

    for i, pipeline in enumerate(config.get("pipelines", [])):
        status_icon = "🟢" if pipeline.get("enabled") else "🔴"
        with st.expander(
            f"{status_icon} {pipeline['name']} ({pipeline['id']})", expanded=False
        ):
            col1, col2, col3 = st.columns([2, 2, 1])

            with col1:
                st.markdown(f"**Description:** {pipeline.get('description', 'N/A')}")
                st.markdown(f"**Source Type:** `{pipeline.get('source', {}).get('type', 'N/A')}`")
                st.markdown(
                    f"**Destination:** `{pipeline.get('destination', {}).get('type', 'N/A')}` "
                    f"/ `{pipeline.get('destination', {}).get('lakehouse', pipeline.get('destination', {}).get('table', 'N/A'))}`"
                )

            with col2:
                schedule = pipeline.get("schedule", {})
                st.markdown(f"**Schedule:** `{schedule.get('cron', 'N/A')}`")
                st.markdown(f"**Timezone:** {schedule.get('timezone', 'UTC')}")
                st.markdown(f"**Frequency:** {schedule.get('description', 'N/A')}")

            with col3:
                quality = pipeline.get("quality_thresholds", {})
                st.markdown(f"**Max Nulls:** {quality.get('null_percentage_max', 'N/A')}%")
                st.markdown(f"**Max Dupes:** {quality.get('duplicate_percentage_max', 'N/A')}%")
                st.markdown(f"**Freshness:** {quality.get('freshness_max_hours', 'N/A')}h")

            # Action buttons
            btn_col1, btn_col2, btn_col3 = st.columns(3)
            with btn_col1:
                if st.button(f"Edit", key=f"edit_{pipeline['id']}"):
                    st.session_state[f"editing_pipeline"] = pipeline["id"]
                    st.rerun()
            with btn_col2:
                toggle_label = "Disable" if pipeline.get("enabled") else "Enable"
                if st.button(toggle_label, key=f"toggle_{pipeline['id']}"):
                    config["pipelines"][i]["enabled"] = not pipeline.get("enabled", True)
                    _save_config(config)
                    st.success(f"Pipeline '{pipeline['name']}' {'disabled' if pipeline.get('enabled') else 'enabled'}.")
                    st.rerun()
            with btn_col3:
                if st.button("Delete", key=f"delete_{pipeline['id']}", type="secondary"):
                    st.session_state[f"confirm_delete_{pipeline['id']}"] = True
                    st.rerun()

            # Confirm deletion
            if st.session_state.get(f"confirm_delete_{pipeline['id']}", False):
                st.warning(f"Are you sure you want to delete '{pipeline['name']}'?")
                dc1, dc2 = st.columns(2)
                with dc1:
                    if st.button("Confirm Delete", key=f"confirm_del_{pipeline['id']}", type="primary"):
                        config["pipelines"].pop(i)
                        _save_config(config)
                        del st.session_state[f"confirm_delete_{pipeline['id']}"]
                        st.success(f"Pipeline '{pipeline['name']}' deleted.")
                        st.rerun()
                with dc2:
                    if st.button("Cancel", key=f"cancel_del_{pipeline['id']}"):
                        del st.session_state[f"confirm_delete_{pipeline['id']}"]
                        st.rerun()


def _render_pipeline_editor(config: dict, pipeline_id: str | None = None):
    """Render the pipeline editor form."""
    editing = False
    pipeline_data: dict[str, Any] = {}

    if pipeline_id:
        for p in config.get("pipelines", []):
            if p["id"] == pipeline_id:
                pipeline_data = p
                editing = True
                break

    title = f"Edit Pipeline: {pipeline_data.get('name', '')}" if editing else "Create New Pipeline"
    st.subheader(title)

    with st.form("pipeline_form"):
        # Basic Info
        st.markdown("#### Basic Information")
        col1, col2 = st.columns(2)
        with col1:
            p_id = st.text_input(
                "Pipeline ID",
                value=pipeline_data.get("id", ""),
                disabled=editing,
                help="Unique identifier (lowercase, hyphens only)",
            )
            p_name = st.text_input("Pipeline Name", value=pipeline_data.get("name", ""))
        with col2:
            p_desc = st.text_area("Description", value=pipeline_data.get("description", ""), height=100)
            p_enabled = st.toggle("Enabled", value=pipeline_data.get("enabled", True))

        # Schedule
        st.markdown("#### Schedule")
        sched = pipeline_data.get("schedule", {})
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            s_cron = st.text_input("Cron Expression", value=sched.get("cron", "0 * * * *"))
        with sc2:
            s_tz = st.selectbox(
                "Timezone",
                ["UTC", "America/New_York", "America/Chicago", "America/Los_Angeles", "Europe/London"],
                index=["UTC", "America/New_York", "America/Chicago", "America/Los_Angeles", "Europe/London"].index(
                    sched.get("timezone", "UTC")
                )
                if sched.get("timezone", "UTC")
                in ["UTC", "America/New_York", "America/Chicago", "America/Los_Angeles", "Europe/London"]
                else 0,
            )
        with sc3:
            s_desc = st.text_input("Schedule Description", value=sched.get("description", ""))

        # Source Configuration
        st.markdown("#### Source Configuration")
        src = pipeline_data.get("source", {})
        src_col1, src_col2 = st.columns(2)
        with src_col1:
            source_type = st.selectbox(
                "Source Type",
                ["sql_server", "iot_hub", "rest_api", "fabric_lakehouse", "blob_storage"],
                index=["sql_server", "iot_hub", "rest_api", "fabric_lakehouse", "blob_storage"].index(
                    src.get("type", "sql_server")
                )
                if src.get("type", "sql_server")
                in ["sql_server", "iot_hub", "rest_api", "fabric_lakehouse", "blob_storage"]
                else 0,
            )
            source_secret = st.text_input(
                "Connection Secret Name (Key Vault)",
                value=src.get("connection_string_secret", src.get("base_url_secret", "")),
            )
        with src_col2:
            source_extra = st.text_area(
                "Additional Source Config (YAML)",
                value=yaml.dump(
                    {k: v for k, v in src.items() if k not in ("type", "connection_string_secret", "base_url_secret")},
                    default_flow_style=False,
                )
                if src
                else "",
                height=120,
            )

        # Destination Configuration
        st.markdown("#### Destination Configuration")
        dest = pipeline_data.get("destination", {})
        dest_col1, dest_col2 = st.columns(2)
        with dest_col1:
            dest_type = st.selectbox(
                "Destination Type",
                ["fabric_lakehouse", "postgresql", "blob_storage"],
                index=["fabric_lakehouse", "postgresql", "blob_storage"].index(
                    dest.get("type", "fabric_lakehouse")
                )
                if dest.get("type", "fabric_lakehouse") in ["fabric_lakehouse", "postgresql", "blob_storage"]
                else 0,
            )
        with dest_col2:
            dest_extra = st.text_area(
                "Additional Destination Config (YAML)",
                value=yaml.dump(
                    {k: v for k, v in dest.items() if k != "type"},
                    default_flow_style=False,
                )
                if dest
                else "",
                height=120,
            )

        # Quality Thresholds
        st.markdown("#### Quality Thresholds")
        qt = pipeline_data.get("quality_thresholds", {})
        qt_col1, qt_col2, qt_col3, qt_col4 = st.columns(4)
        with qt_col1:
            qt_null = st.number_input(
                "Max Null %", min_value=0.0, max_value=100.0, value=qt.get("null_percentage_max", 5.0), step=0.5
            )
        with qt_col2:
            qt_dup = st.number_input(
                "Max Duplicate %", min_value=0.0, max_value=100.0, value=qt.get("duplicate_percentage_max", 1.0), step=0.5
            )
        with qt_col3:
            qt_fresh = st.number_input(
                "Freshness Max (hours)", min_value=1, max_value=168, value=qt.get("freshness_max_hours", 4)
            )
        with qt_col4:
            qt_drift = st.selectbox(
                "Schema Drift Action",
                ["alert", "block", "ignore"],
                index=["alert", "block", "ignore"].index(qt.get("schema_drift_action", "alert"))
                if qt.get("schema_drift_action", "alert") in ["alert", "block", "ignore"]
                else 0,
            )

        # Alerts
        st.markdown("#### Alert Configuration")
        al = pipeline_data.get("alerts", {})
        al_col1, al_col2 = st.columns(2)
        with al_col1:
            al_failure = st.checkbox("Alert on Failure", value=al.get("on_failure", True))
            al_quality = st.checkbox("Alert on Quality Violation", value=al.get("on_quality_violation", True))
        with al_col2:
            al_slack = st.text_input("Slack Channel", value=al.get("slack_channel", "#data-pipeline-alerts"))
            al_email = st.text_input(
                "Email Recipients (comma-separated)",
                value=", ".join(al.get("email_recipients", [])),
            )

        # Submit
        col_submit, col_cancel = st.columns(2)
        with col_submit:
            submitted = st.form_submit_button("Save Pipeline", type="primary")
        with col_cancel:
            cancelled = st.form_submit_button("Cancel")

    if cancelled:
        if "editing_pipeline" in st.session_state:
            del st.session_state["editing_pipeline"]
        st.rerun()

    if submitted:
        # Parse extra YAML configs
        try:
            extra_src = yaml.safe_load(source_extra) or {} if source_extra else {}
        except yaml.YAMLError:
            extra_src = {}

        try:
            extra_dest = yaml.safe_load(dest_extra) or {} if dest_extra else {}
        except yaml.YAMLError:
            extra_dest = {}

        new_pipeline = {
            "id": p_id,
            "name": p_name,
            "description": p_desc,
            "enabled": p_enabled,
            "schedule": {
                "cron": s_cron,
                "timezone": s_tz,
                "description": s_desc,
            },
            "source": {
                "type": source_type,
                "connection_string_secret": source_secret,
                **extra_src,
            },
            "destination": {
                "type": dest_type,
                **extra_dest,
            },
            "quality_thresholds": {
                "null_percentage_max": qt_null,
                "duplicate_percentage_max": qt_dup,
                "freshness_max_hours": qt_fresh,
                "row_count_min": qt.get("row_count_min", 100),
                "schema_drift_action": qt_drift,
            },
            "alerts": {
                "on_failure": al_failure,
                "on_quality_violation": al_quality,
                "slack_channel": al_slack,
                "email_recipients": [e.strip() for e in al_email.split(",") if e.strip()],
            },
        }

        if editing:
            for i, p in enumerate(config.get("pipelines", [])):
                if p["id"] == pipeline_id:
                    config["pipelines"][i] = new_pipeline
                    break
        else:
            # Check for duplicate ID
            existing_ids = {p["id"] for p in config.get("pipelines", [])}
            if p_id in existing_ids:
                st.error(f"Pipeline ID '{p_id}' already exists. Please use a unique ID.")
                return
            config["pipelines"].append(new_pipeline)

        _save_config(config)
        st.success(f"Pipeline '{p_name}' saved successfully.")

        if "editing_pipeline" in st.session_state:
            del st.session_state["editing_pipeline"]
        st.rerun()


def _render_yaml_viewer(config: dict):
    """Render raw YAML view of configuration."""
    st.subheader("Raw Configuration (YAML)")
    yaml_str = yaml.dump(config, default_flow_style=False, sort_keys=False, indent=2)
    st.code(yaml_str, language="yaml")

    if st.button("Download Configuration"):
        st.download_button(
            label="Download pipelines.yaml",
            data=yaml_str,
            file_name="pipelines.yaml",
            mime="application/x-yaml",
        )


def render_pipeline_config():
    """Main pipeline configuration renderer."""
    st.markdown('<p class="main-header">Pipeline Configuration</p>', unsafe_allow_html=True)
    st.caption(f"Environment: **{st.session_state.environment}** | Config file: `{CONFIG_FILE}`")

    config = _load_config()

    # Check if we're in edit mode
    editing_pipeline_id = st.session_state.get("editing_pipeline", None)

    # Tabs
    if editing_pipeline_id:
        _render_pipeline_editor(config, editing_pipeline_id)
    else:
        tab1, tab2, tab3 = st.tabs(["Pipeline List", "Create New", "YAML View"])

        with tab1:
            _render_pipeline_list(config)

        with tab2:
            _render_pipeline_editor(config, pipeline_id=None)

        with tab3:
            _render_yaml_viewer(config)
