"""
AI Agent Management Page - View deployed agents, test prompts,
view evaluation metrics, update system prompts.
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta
import json
import random
from typing import Any


# Sample agent registry data
AGENT_REGISTRY: list[dict[str, Any]] = [
    {
        "id": "sales-forecast-agent",
        "name": "Sales Forecasting Agent",
        "model": "gpt-4o",
        "deployment": "ai-foundry-eastus",
        "version": "2.4.1",
        "status": "active",
        "endpoint": "https://ai-foundry-eastus.openai.azure.com/",
        "system_prompt": (
            "You are a sales forecasting analyst. Analyze historical sales data, "
            "seasonal trends, and market indicators to provide accurate demand forecasts. "
            "Always cite your data sources and provide confidence intervals for predictions. "
            "Format numerical outputs in tables when appropriate."
        ),
        "temperature": 0.3,
        "max_tokens": 2048,
        "tools": ["sql_query", "time_series_forecast", "anomaly_detection"],
        "knowledge_base": "sales-knowledge-index",
        "metrics": {
            "avg_latency_ms": 342,
            "p95_latency_ms": 890,
            "success_rate": 99.2,
            "requests_24h": 1847,
            "avg_tokens_per_request": 1250,
            "user_satisfaction": 4.6,
            "cost_24h_usd": 23.45,
        },
    },
    {
        "id": "customer-support-agent",
        "name": "Customer Support Agent",
        "model": "gpt-4o",
        "deployment": "ai-foundry-eastus",
        "version": "3.1.0",
        "status": "active",
        "endpoint": "https://ai-foundry-eastus.openai.azure.com/",
        "system_prompt": (
            "You are a customer support assistant for a manufacturing and sales company. "
            "Help customers with order inquiries, product information, warranty claims, "
            "and technical support. Be empathetic, concise, and always confirm understanding "
            "before providing solutions. Escalate to human agents when confidence is low."
        ),
        "temperature": 0.5,
        "max_tokens": 1024,
        "tools": ["order_lookup", "product_catalog", "ticket_creation"],
        "knowledge_base": "support-knowledge-index",
        "metrics": {
            "avg_latency_ms": 512,
            "p95_latency_ms": 1340,
            "success_rate": 97.8,
            "requests_24h": 3204,
            "avg_tokens_per_request": 890,
            "user_satisfaction": 4.2,
            "cost_24h_usd": 41.20,
        },
    },
    {
        "id": "manufacturing-qa-agent",
        "name": "Manufacturing QA Agent",
        "model": "gpt-4o-mini",
        "deployment": "ai-foundry-eastus",
        "version": "1.8.3",
        "status": "degraded",
        "endpoint": "https://ai-foundry-eastus.openai.azure.com/",
        "system_prompt": (
            "You are a manufacturing quality assurance specialist. Analyze sensor data, "
            "production metrics, and quality control reports to identify defects, predict "
            "equipment failures, and recommend corrective actions. Provide structured "
            "reports with severity classifications and root cause analysis."
        ),
        "temperature": 0.2,
        "max_tokens": 4096,
        "tools": ["sensor_data_query", "defect_classifier", "maintenance_scheduler"],
        "knowledge_base": "manufacturing-knowledge-index",
        "metrics": {
            "avg_latency_ms": 1205,
            "p95_latency_ms": 3400,
            "success_rate": 89.4,
            "requests_24h": 956,
            "avg_tokens_per_request": 2100,
            "user_satisfaction": 3.8,
            "cost_24h_usd": 15.80,
        },
    },
    {
        "id": "inventory-optimization-agent",
        "name": "Inventory Optimization Agent",
        "model": "gpt-4o-mini",
        "deployment": "ai-foundry-westus",
        "version": "1.2.0",
        "status": "active",
        "endpoint": "https://ai-foundry-westus.openai.azure.com/",
        "system_prompt": (
            "You are an inventory optimization specialist. Analyze stock levels, "
            "reorder points, lead times, and demand patterns to recommend optimal "
            "inventory strategies. Consider carrying costs, stockout risks, and "
            "supplier reliability. Provide actionable recommendations with expected ROI."
        ),
        "temperature": 0.3,
        "max_tokens": 2048,
        "tools": ["inventory_query", "supplier_api", "demand_model"],
        "knowledge_base": "inventory-knowledge-index",
        "metrics": {
            "avg_latency_ms": 287,
            "p95_latency_ms": 650,
            "success_rate": 99.7,
            "requests_24h": 421,
            "avg_tokens_per_request": 980,
            "user_satisfaction": 4.8,
            "cost_24h_usd": 8.90,
        },
    },
]


def _render_agent_overview():
    """Render the agent overview cards."""
    st.subheader("Deployed Agents")

    cols = st.columns(len(AGENT_REGISTRY))
    for i, agent in enumerate(AGENT_REGISTRY):
        with cols[i]:
            status_color = {
                "active": "🟢",
                "degraded": "🟡",
                "offline": "🔴",
            }.get(agent["status"], "⚪")

            st.markdown(
                f"### {status_color} {agent['name']}\n"
                f"**Model:** `{agent['model']}`  \n"
                f"**Version:** `{agent['version']}`  \n"
                f"**Status:** {agent['status'].title()}"
            )

            metrics = agent["metrics"]
            st.metric("Avg Latency", f"{metrics['avg_latency_ms']}ms")
            st.metric("Success Rate", f"{metrics['success_rate']}%")
            st.metric("Requests (24h)", f"{metrics['requests_24h']:,}")
            st.metric("Cost (24h)", f"${metrics['cost_24h_usd']:.2f}")


def _render_agent_metrics(agent: dict):
    """Render detailed metrics for a specific agent."""
    metrics = agent["metrics"]

    # Latency distribution chart
    latency_data = [random.gauss(metrics["avg_latency_ms"], metrics["avg_latency_ms"] * 0.3) for _ in range(200)]
    fig_latency = go.Figure(data=go.Histogram(x=latency_data, nbinsx=30, marker_color="#0078d4"))
    fig_latency.update_layout(
        title=f"Latency Distribution - {agent['name']}",
        xaxis_title="Latency (ms)",
        yaxis_title="Count",
        height=300,
        margin=dict(l=10, r=10, t=40, b=30),
    )
    fig_latency.add_vline(x=metrics["avg_latency_ms"], line_dash="dash", line_color="red", annotation_text="Mean")
    fig_latency.add_vline(x=metrics["p95_latency_ms"], line_dash="dash", line_color="orange", annotation_text="P95")
    st.plotly_chart(fig_latency, use_container_width=True)

    # Request volume over time
    hours = pd.date_range(end=datetime.now(), periods=24, freq="h")
    hourly_requests = [max(0, int(metrics["requests_24h"] / 24 + random.gauss(0, metrics["requests_24h"] / 48))) for _ in hours]

    fig_volume = px.bar(
        x=hours,
        y=hourly_requests,
        title=f"Hourly Request Volume - {agent['name']}",
        labels={"x": "Hour", "y": "Requests"},
    )
    fig_volume.update_layout(
        height=300,
        margin=dict(l=10, r=10, t=40, b=30),
    )
    st.plotly_chart(fig_volume, use_container_width=True)

    # Evaluation metrics table
    st.markdown("#### Evaluation Metrics")
    eval_data = pd.DataFrame(
        {
            "Metric": [
                "Groundedness",
                "Relevance",
                "Coherence",
                "Fluency",
                "Answer Correctness",
                "Context Recall",
                "Faithfulness",
            ],
            "Score": [
                round(random.uniform(0.80, 0.98), 3),
                round(random.uniform(0.85, 0.99), 3),
                round(random.uniform(0.90, 0.99), 3),
                round(random.uniform(0.92, 0.99), 3),
                round(random.uniform(0.75, 0.95), 3),
                round(random.uniform(0.80, 0.97), 3),
                round(random.uniform(0.82, 0.96), 3),
            ],
            "Threshold": [0.80, 0.85, 0.85, 0.90, 0.80, 0.75, 0.80],
            "Status": [],
        }
    )
    eval_data["Status"] = eval_data.apply(
        lambda row: "Pass" if row["Score"] >= row["Threshold"] else "Fail", axis=1
    )
    st.dataframe(eval_data, use_container_width=True, hide_index=True)


def _render_prompt_tester(agent: dict):
    """Render the prompt testing interface."""
    st.markdown(f"#### Test Prompt - {agent['name']}")
    st.info(
        "Send a test query to this agent and see the response. "
        "This uses the current system prompt and model configuration."
    )

    # Show current system prompt
    with st.expander("Current System Prompt"):
        st.code(agent["system_prompt"], language=None)

    # Test input
    test_prompt = st.text_area(
        "Enter test prompt",
        placeholder="e.g., What are the sales projections for Q3 2026 in the Northeast region?",
        height=100,
        key=f"test_prompt_{agent['id']}",
    )

    col1, col2 = st.columns(2)
    with col1:
        test_temp = st.slider(
            "Temperature Override",
            min_value=0.0,
            max_value=1.0,
            value=agent["temperature"],
            step=0.1,
            key=f"test_temp_{agent['id']}",
        )
    with col2:
        test_max_tokens = st.number_input(
            "Max Tokens Override",
            min_value=100,
            max_value=8192,
            value=agent["max_tokens"],
            key=f"test_tokens_{agent['id']}",
        )

    if st.button("Send Test Query", key=f"test_btn_{agent['id']}", type="primary"):
        if not test_prompt:
            st.warning("Please enter a test prompt.")
            return

        with st.spinner("Querying agent..."):
            # Simulate agent response (in production, this calls AI Foundry)
            import time

            time.sleep(1.5)

            simulated_response = (
                f"Based on analysis of historical sales data and current market trends, "
                f"here is the response to your query:\n\n"
                f"**Query:** {test_prompt}\n\n"
                f"**Analysis:**\n"
                f"- The data indicates a positive trajectory with seasonal adjustments\n"
                f"- Key factors include market demand shifts and supply chain optimization\n"
                f"- Confidence interval: 85-92% based on available data\n\n"
                f"*Note: This is a simulated response. In production, this connects to AI Foundry.*"
            )

            st.markdown("**Response:**")
            st.markdown(simulated_response)

            # Show metadata
            with st.expander("Response Metadata"):
                st.json(
                    {
                        "model": agent["model"],
                        "temperature": test_temp,
                        "max_tokens": test_max_tokens,
                        "tokens_used": random.randint(200, 1500),
                        "latency_ms": random.randint(200, 800),
                        "finish_reason": "stop",
                    }
                )


def _render_system_prompt_editor(agent: dict):
    """Render the system prompt editor."""
    st.markdown(f"#### System Prompt Editor - {agent['name']}")

    with st.form(f"prompt_form_{agent['id']}"):
        new_prompt = st.text_area(
            "System Prompt",
            value=agent["system_prompt"],
            height=200,
            key=f"prompt_edit_{agent['id']}",
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            new_temp = st.slider(
                "Temperature",
                min_value=0.0,
                max_value=1.0,
                value=agent["temperature"],
                step=0.1,
            )
        with col2:
            new_max_tokens = st.number_input(
                "Max Tokens",
                min_value=100,
                max_value=8192,
                value=agent["max_tokens"],
            )
        with col3:
            new_model = st.selectbox(
                "Model",
                ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
                index=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"].index(agent["model"])
                if agent["model"] in ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]
                else 0,
            )

        st.markdown("**Available Tools:**")
        tool_options = [
            "sql_query", "time_series_forecast", "anomaly_detection",
            "order_lookup", "product_catalog", "ticket_creation",
            "sensor_data_query", "defect_classifier", "maintenance_scheduler",
            "inventory_query", "supplier_api", "demand_model",
        ]
        selected_tools = st.multiselect(
            "Enabled Tools",
            tool_options,
            default=agent.get("tools", []),
        )

        submitted = st.form_submit_button("Update Agent Configuration", type="primary")

    if submitted:
        st.success(
            f"Agent '{agent['name']}' configuration updated successfully.\n\n"
            f"Changes: model={new_model}, temperature={new_temp}, max_tokens={new_max_tokens}, "
            f"tools={selected_tools}"
        )
        st.info(
            "In production, this updates the agent configuration in AI Foundry "
            "and triggers a redeployment if the model changed."
        )

    # Version history
    with st.expander("Prompt Version History"):
        history = pd.DataFrame(
            {
                "Version": ["2.4.1", "2.4.0", "2.3.0", "2.2.0", "2.1.0"],
                "Date": [
                    "2026-02-25",
                    "2026-02-18",
                    "2026-02-01",
                    "2026-01-15",
                    "2026-01-02",
                ],
                "Author": [
                    "admin@company.com",
                    "admin@company.com",
                    "ml-engineer@company.com",
                    "ml-engineer@company.com",
                    "ml-engineer@company.com",
                ],
                "Change Summary": [
                    "Added confidence interval requirements",
                    "Updated citation format",
                    "Improved table formatting instructions",
                    "Added anomaly detection tool",
                    "Initial deployment",
                ],
            }
        )
        st.dataframe(history, use_container_width=True, hide_index=True)


def render_ai_agents():
    """Main AI agent management renderer."""
    st.markdown('<p class="main-header">AI Agent Management</p>', unsafe_allow_html=True)
    st.caption(f"Environment: **{st.session_state.environment}** | AI Foundry Region: East US / West US")

    # Agent overview cards
    _render_agent_overview()

    st.markdown("---")

    # Agent detail view
    agent_names = [a["name"] for a in AGENT_REGISTRY]
    selected_agent_name = st.selectbox("Select Agent for Details", agent_names)
    selected_agent = next(a for a in AGENT_REGISTRY if a["name"] == selected_agent_name)

    tab1, tab2, tab3 = st.tabs(["Metrics & Evaluation", "Test Prompt", "Edit Configuration"])

    with tab1:
        _render_agent_metrics(selected_agent)

    with tab2:
        _render_prompt_tester(selected_agent)

    with tab3:
        _render_system_prompt_editor(selected_agent)
