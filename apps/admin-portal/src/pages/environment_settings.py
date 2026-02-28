"""
Environment Settings Page - Manage environment configurations,
toggle feature flags, view resource group status, manage secrets
(read-only display from Key Vault).
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Any


# Feature flags configuration per environment
FEATURE_FLAGS: dict[str, dict[str, Any]] = {
    "enable_ai_chat": {
        "name": "AI Chat Interface",
        "description": "Enable the AI-powered chat interface for external users",
        "category": "AI Features",
        "Dev": True,
        "QA": True,
        "Prod": True,
    },
    "enable_demand_forecast": {
        "name": "Demand Forecasting",
        "description": "Enable AI-driven demand forecasting pipeline and dashboard",
        "category": "AI Features",
        "Dev": True,
        "QA": True,
        "Prod": True,
    },
    "enable_streaming_responses": {
        "name": "Streaming Chat Responses",
        "description": "Enable SSE streaming for AI chat responses",
        "category": "AI Features",
        "Dev": True,
        "QA": True,
        "Prod": False,
    },
    "enable_manufacturing_qa_agent": {
        "name": "Manufacturing QA Agent",
        "description": "Enable the manufacturing quality assurance AI agent",
        "category": "AI Features",
        "Dev": True,
        "QA": True,
        "Prod": True,
    },
    "enable_real_time_telemetry": {
        "name": "Real-time Telemetry Dashboard",
        "description": "Show real-time manufacturing sensor data on dashboards",
        "category": "Data Platform",
        "Dev": True,
        "QA": False,
        "Prod": False,
    },
    "enable_pgvector_search": {
        "name": "Vector Search (pgvector)",
        "description": "Enable semantic search using pgvector in PostgreSQL",
        "category": "Data Platform",
        "Dev": True,
        "QA": True,
        "Prod": True,
    },
    "enable_fabric_direct_lake": {
        "name": "Fabric Direct Lake Mode",
        "description": "Use Direct Lake mode for Fabric datasets instead of import",
        "category": "Data Platform",
        "Dev": True,
        "QA": True,
        "Prod": False,
    },
    "enable_slack_notifications": {
        "name": "Slack Notifications",
        "description": "Send pipeline alerts and notifications to Slack channels",
        "category": "Integrations",
        "Dev": True,
        "QA": True,
        "Prod": True,
    },
    "enable_plane_integration": {
        "name": "Plane Ticket Integration",
        "description": "Enable ticket creation and tracking via Plane API",
        "category": "Integrations",
        "Dev": True,
        "QA": True,
        "Prod": True,
    },
    "enable_cost_alerts": {
        "name": "Azure Cost Alerts",
        "description": "Enable automated Azure cost threshold alerts",
        "category": "Operations",
        "Dev": False,
        "QA": False,
        "Prod": True,
    },
    "enable_auto_scaling": {
        "name": "Auto-scaling",
        "description": "Enable auto-scaling for App Service and Container Apps",
        "category": "Operations",
        "Dev": False,
        "QA": True,
        "Prod": True,
    },
}

# Resource group configuration per environment
RESOURCE_GROUPS: dict[str, list[dict]] = {
    "Dev": [
        {
            "name": "rg-dataplatform-dev",
            "location": "East US",
            "status": "Active",
            "resources": 24,
            "monthly_cost": "$487.20",
            "tags": {"environment": "dev", "project": "data-platform", "team": "engineering"},
        },
        {
            "name": "rg-ai-foundry-dev",
            "location": "East US",
            "status": "Active",
            "resources": 8,
            "monthly_cost": "$215.40",
            "tags": {"environment": "dev", "project": "ai-agents", "team": "ml-engineering"},
        },
    ],
    "QA": [
        {
            "name": "rg-dataplatform-qa",
            "location": "East US",
            "status": "Active",
            "resources": 22,
            "monthly_cost": "$542.80",
            "tags": {"environment": "qa", "project": "data-platform", "team": "engineering"},
        },
        {
            "name": "rg-ai-foundry-qa",
            "location": "East US",
            "status": "Active",
            "resources": 8,
            "monthly_cost": "$198.60",
            "tags": {"environment": "qa", "project": "ai-agents", "team": "ml-engineering"},
        },
    ],
    "Prod": [
        {
            "name": "rg-dataplatform-prod",
            "location": "East US",
            "status": "Active",
            "resources": 38,
            "monthly_cost": "$2,145.60",
            "tags": {"environment": "prod", "project": "data-platform", "team": "engineering"},
        },
        {
            "name": "rg-ai-foundry-prod",
            "location": "East US",
            "status": "Active",
            "resources": 12,
            "monthly_cost": "$1,024.30",
            "tags": {"environment": "prod", "project": "ai-agents", "team": "ml-engineering"},
        },
        {
            "name": "rg-networking-prod",
            "location": "East US",
            "status": "Active",
            "resources": 15,
            "monthly_cost": "$312.40",
            "tags": {"environment": "prod", "project": "networking", "team": "platform"},
        },
    ],
}

# Key Vault secrets (read-only display -- values are masked)
KEY_VAULT_SECRETS: dict[str, list[dict]] = {
    "Dev": [
        {"name": "erp-sql-connection", "content_type": "connection-string", "created": "2026-01-15", "expires": "2027-01-15", "enabled": True},
        {"name": "iot-hub-connection", "content_type": "connection-string", "created": "2026-01-15", "expires": "2027-01-15", "enabled": True},
        {"name": "postgres-connection", "content_type": "connection-string", "created": "2026-01-10", "expires": "2027-01-10", "enabled": True},
        {"name": "ai-foundry-api-key", "content_type": "api-key", "created": "2026-02-01", "expires": "2026-08-01", "enabled": True},
        {"name": "slack-webhook-url", "content_type": "webhook-url", "created": "2026-01-20", "expires": "2027-01-20", "enabled": True},
        {"name": "slack-bot-token", "content_type": "api-token", "created": "2026-01-20", "expires": "2027-01-20", "enabled": True},
        {"name": "plane-api-key", "content_type": "api-key", "created": "2026-02-10", "expires": "2027-02-10", "enabled": True},
        {"name": "msal-client-secret", "content_type": "client-secret", "created": "2026-01-05", "expires": "2027-01-05", "enabled": True},
        {"name": "wms-client-credentials", "content_type": "oauth-credentials", "created": "2026-01-25", "expires": "2027-01-25", "enabled": True},
        {"name": "fabric-service-principal", "content_type": "client-secret", "created": "2026-02-01", "expires": "2027-02-01", "enabled": True},
    ],
    "QA": [
        {"name": "erp-sql-connection", "content_type": "connection-string", "created": "2026-01-15", "expires": "2027-01-15", "enabled": True},
        {"name": "iot-hub-connection", "content_type": "connection-string", "created": "2026-01-15", "expires": "2027-01-15", "enabled": True},
        {"name": "postgres-connection", "content_type": "connection-string", "created": "2026-01-10", "expires": "2027-01-10", "enabled": True},
        {"name": "ai-foundry-api-key", "content_type": "api-key", "created": "2026-02-01", "expires": "2026-08-01", "enabled": True},
        {"name": "slack-webhook-url", "content_type": "webhook-url", "created": "2026-01-20", "expires": "2027-01-20", "enabled": True},
        {"name": "slack-bot-token", "content_type": "api-token", "created": "2026-01-20", "expires": "2027-01-20", "enabled": True},
        {"name": "plane-api-key", "content_type": "api-key", "created": "2026-02-10", "expires": "2027-02-10", "enabled": True},
        {"name": "msal-client-secret", "content_type": "client-secret", "created": "2026-01-05", "expires": "2027-01-05", "enabled": True},
    ],
    "Prod": [
        {"name": "erp-sql-connection", "content_type": "connection-string", "created": "2026-01-15", "expires": "2027-01-15", "enabled": True},
        {"name": "iot-hub-connection", "content_type": "connection-string", "created": "2026-01-15", "expires": "2027-01-15", "enabled": True},
        {"name": "postgres-connection", "content_type": "connection-string", "created": "2026-01-10", "expires": "2027-01-10", "enabled": True},
        {"name": "ai-foundry-api-key", "content_type": "api-key", "created": "2026-02-01", "expires": "2026-08-01", "enabled": True},
        {"name": "slack-webhook-url", "content_type": "webhook-url", "created": "2026-01-20", "expires": "2027-01-20", "enabled": True},
        {"name": "slack-bot-token", "content_type": "api-token", "created": "2026-01-20", "expires": "2027-01-20", "enabled": True},
        {"name": "plane-api-key", "content_type": "api-key", "created": "2026-02-10", "expires": "2027-02-10", "enabled": True},
        {"name": "msal-client-secret", "content_type": "client-secret", "created": "2026-01-05", "expires": "2027-01-05", "enabled": True},
        {"name": "wms-client-credentials", "content_type": "oauth-credentials", "created": "2026-01-25", "expires": "2027-01-25", "enabled": True},
        {"name": "fabric-service-principal", "content_type": "client-secret", "created": "2026-02-01", "expires": "2027-02-01", "enabled": True},
        {"name": "datadog-api-key", "content_type": "api-key", "created": "2026-02-15", "expires": "2027-02-15", "enabled": True},
    ],
}

# Environment-specific configuration
ENV_CONFIG: dict[str, dict] = {
    "Dev": {
        "subscription_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        "tenant_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        "key_vault_name": "kv-dataplatform-dev",
        "app_service_plan": "asp-dev-eastus",
        "fabric_workspace": "dev-workspace",
        "ai_foundry_project": "ai-platform-dev",
        "postgres_server": "psql-dataplatform-dev.postgres.database.azure.com",
        "log_analytics_workspace": "law-dataplatform-dev",
    },
    "QA": {
        "subscription_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        "tenant_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        "key_vault_name": "kv-dataplatform-qa",
        "app_service_plan": "asp-qa-eastus",
        "fabric_workspace": "qa-workspace",
        "ai_foundry_project": "ai-platform-qa",
        "postgres_server": "psql-dataplatform-qa.postgres.database.azure.com",
        "log_analytics_workspace": "law-dataplatform-qa",
    },
    "Prod": {
        "subscription_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        "tenant_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        "key_vault_name": "kv-dataplatform-prod",
        "app_service_plan": "asp-prod-eastus",
        "fabric_workspace": "production-workspace",
        "ai_foundry_project": "ai-platform-prod",
        "postgres_server": "psql-dataplatform-prod.postgres.database.azure.com",
        "log_analytics_workspace": "law-dataplatform-prod",
    },
}


def _render_feature_flags():
    """Render feature flag toggles grouped by category."""
    st.subheader("Feature Flags")
    env = st.session_state.environment

    categories = sorted(set(f["category"] for f in FEATURE_FLAGS.values()))

    for category in categories:
        st.markdown(f"#### {category}")

        category_flags = {k: v for k, v in FEATURE_FLAGS.items() if v["category"] == category}

        for flag_key, flag in category_flags.items():
            col1, col2, col3 = st.columns([1, 3, 1])
            with col1:
                current_value = flag.get(env, False)
                new_value = st.toggle(
                    flag["name"],
                    value=current_value,
                    key=f"flag_{flag_key}_{env}",
                )
            with col2:
                st.caption(flag["description"])
            with col3:
                # Show status across all environments
                statuses = []
                for e in ["Dev", "QA", "Prod"]:
                    icon = "🟢" if flag.get(e, False) else "🔴"
                    statuses.append(f"{e}: {icon}")
                st.caption(" | ".join(statuses))

            if new_value != current_value:
                FEATURE_FLAGS[flag_key][env] = new_value
                st.success(f"Flag '{flag['name']}' {'enabled' if new_value else 'disabled'} in {env}.")

        st.markdown("---")


def _render_resource_groups():
    """Render resource group status for current environment."""
    st.subheader("Resource Groups")
    env = st.session_state.environment

    groups = RESOURCE_GROUPS.get(env, [])

    if not groups:
        st.info(f"No resource groups configured for {env} environment.")
        return

    for rg in groups:
        with st.expander(f"{rg['name']} ({rg['location']})", expanded=True):
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                status_icon = "🟢" if rg["status"] == "Active" else "🔴"
                st.metric("Status", f"{status_icon} {rg['status']}")
            with col2:
                st.metric("Resources", rg["resources"])
            with col3:
                st.metric("Monthly Cost", rg["monthly_cost"])
            with col4:
                st.metric("Location", rg["location"])

            st.markdown("**Tags:**")
            tag_cols = st.columns(len(rg["tags"]))
            for i, (key, value) in enumerate(rg["tags"].items()):
                with tag_cols[i]:
                    st.code(f"{key}: {value}")


def _render_key_vault_secrets():
    """Render Key Vault secrets in read-only view."""
    st.subheader("Key Vault Secrets (Read-Only)")
    env = st.session_state.environment
    env_config = ENV_CONFIG.get(env, {})

    st.info(
        f"Secrets are managed in Azure Key Vault: **{env_config.get('key_vault_name', 'N/A')}**. "
        f"Values cannot be displayed for security. Use Azure Portal or CLI to manage secret values."
    )

    secrets = KEY_VAULT_SECRETS.get(env, [])

    if not secrets:
        st.warning(f"No secrets found for {env} environment.")
        return

    # Convert to DataFrame for display
    df = pd.DataFrame(secrets)

    # Add expiry status
    today = datetime.now().date()
    df["days_until_expiry"] = df["expires"].apply(
        lambda x: (datetime.strptime(x, "%Y-%m-%d").date() - today).days
    )

    def _expiry_status(days: int) -> str:
        if days < 0:
            return "EXPIRED"
        elif days < 30:
            return "EXPIRING SOON"
        elif days < 90:
            return "Warning"
        return "OK"

    df["expiry_status"] = df["days_until_expiry"].apply(_expiry_status)

    st.dataframe(
        df[["name", "content_type", "created", "expires", "days_until_expiry", "expiry_status", "enabled"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "name": st.column_config.TextColumn("Secret Name"),
            "content_type": st.column_config.TextColumn("Type"),
            "created": st.column_config.TextColumn("Created"),
            "expires": st.column_config.TextColumn("Expires"),
            "days_until_expiry": st.column_config.NumberColumn("Days Until Expiry"),
            "expiry_status": st.column_config.TextColumn("Status"),
            "enabled": st.column_config.CheckboxColumn("Enabled"),
        },
    )

    # Highlight expiring secrets
    expiring = df[df["days_until_expiry"] < 90]
    if not expiring.empty:
        st.warning(
            f"{len(expiring)} secret(s) expiring within 90 days: "
            + ", ".join(expiring["name"].tolist())
        )


def _render_environment_config():
    """Render environment-specific configuration details."""
    st.subheader("Environment Configuration")
    env = st.session_state.environment
    config = ENV_CONFIG.get(env, {})

    if not config:
        st.warning(f"No configuration found for {env} environment.")
        return

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Azure Identity")
        st.text_input("Subscription ID", value=config.get("subscription_id", ""), disabled=True)
        st.text_input("Tenant ID", value=config.get("tenant_id", ""), disabled=True)
        st.text_input("Key Vault", value=config.get("key_vault_name", ""), disabled=True)
        st.text_input("App Service Plan", value=config.get("app_service_plan", ""), disabled=True)

    with col2:
        st.markdown("#### Service Endpoints")
        st.text_input("Fabric Workspace", value=config.get("fabric_workspace", ""), disabled=True)
        st.text_input("AI Foundry Project", value=config.get("ai_foundry_project", ""), disabled=True)
        st.text_input("PostgreSQL Server", value=config.get("postgres_server", ""), disabled=True)
        st.text_input("Log Analytics", value=config.get("log_analytics_workspace", ""), disabled=True)


def _render_environment_comparison():
    """Render a comparison view across all environments."""
    st.subheader("Environment Comparison")

    comparison_data = []
    for env_name, config in ENV_CONFIG.items():
        rg_count = len(RESOURCE_GROUPS.get(env_name, []))
        secret_count = len(KEY_VAULT_SECRETS.get(env_name, []))
        flag_count = sum(1 for f in FEATURE_FLAGS.values() if f.get(env_name, False))
        total_flags = len(FEATURE_FLAGS)

        comparison_data.append(
            {
                "Environment": env_name,
                "Key Vault": config.get("key_vault_name", "N/A"),
                "Resource Groups": rg_count,
                "Secrets": secret_count,
                "Feature Flags": f"{flag_count}/{total_flags}",
                "Fabric Workspace": config.get("fabric_workspace", "N/A"),
                "AI Foundry Project": config.get("ai_foundry_project", "N/A"),
            }
        )

    st.dataframe(
        pd.DataFrame(comparison_data),
        use_container_width=True,
        hide_index=True,
    )


def render_environment_settings():
    """Main environment settings renderer."""
    st.markdown('<p class="main-header">Environment Settings</p>', unsafe_allow_html=True)
    st.caption(
        f"Current Environment: **{st.session_state.environment}** | "
        f"Key Vault: **{ENV_CONFIG.get(st.session_state.environment, {}).get('key_vault_name', 'N/A')}**"
    )

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Feature Flags",
        "Resource Groups",
        "Key Vault Secrets",
        "Environment Config",
        "Environment Comparison",
    ])

    with tab1:
        _render_feature_flags()

    with tab2:
        _render_resource_groups()

    with tab3:
        _render_key_vault_secrets()

    with tab4:
        _render_environment_config()

    with tab5:
        _render_environment_comparison()
