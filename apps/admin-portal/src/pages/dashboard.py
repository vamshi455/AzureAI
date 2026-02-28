"""
Dashboard Page - Overview of platform health, pipeline status, AI agent health,
resource costs, and recent alerts.
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta
import random


def _generate_pipeline_status_data() -> pd.DataFrame:
    """Generate sample pipeline status data."""
    pipelines = [
        "Sales Data Ingestion",
        "Manufacturing Telemetry",
        "Demand Forecast Pipeline",
        "Inventory Sync",
        "Customer 360 ETL",
        "Quality Metrics Aggregation",
        "Financial Reconciliation",
        "Supplier Data Integration",
    ]
    statuses = ["Succeeded", "Succeeded", "Succeeded", "Running", "Failed", "Succeeded", "Succeeded", "Succeeded"]
    durations = [12, 45, 28, 15, 0, 8, 33, 22]
    last_runs = [
        datetime.now() - timedelta(minutes=random.randint(5, 120)) for _ in pipelines
    ]

    return pd.DataFrame(
        {
            "Pipeline": pipelines,
            "Status": statuses,
            "Duration (min)": durations,
            "Last Run": last_runs,
            "Records Processed": [
                random.randint(10000, 500000) for _ in pipelines
            ],
        }
    )


def _generate_cost_data() -> pd.DataFrame:
    """Generate sample cost data for the past 30 days."""
    dates = pd.date_range(end=datetime.now(), periods=30, freq="D")
    return pd.DataFrame(
        {
            "Date": dates,
            "Fabric Compute": [random.uniform(80, 150) for _ in dates],
            "AI Foundry": [random.uniform(40, 100) for _ in dates],
            "PostgreSQL": [random.uniform(20, 35) for _ in dates],
            "App Service": [random.uniform(15, 30) for _ in dates],
        }
    )


def _generate_agent_health_data() -> list[dict]:
    """Generate AI agent health data."""
    return [
        {
            "Agent": "Sales Forecasting Agent",
            "Status": "Healthy",
            "Avg Latency (ms)": 342,
            "Success Rate": 99.2,
            "Requests (24h)": 1847,
        },
        {
            "Agent": "Customer Support Agent",
            "Status": "Healthy",
            "Avg Latency (ms)": 512,
            "Success Rate": 97.8,
            "Requests (24h)": 3204,
        },
        {
            "Agent": "Manufacturing QA Agent",
            "Status": "Degraded",
            "Avg Latency (ms)": 1205,
            "Success Rate": 89.4,
            "Requests (24h)": 956,
        },
        {
            "Agent": "Inventory Optimization Agent",
            "Status": "Healthy",
            "Avg Latency (ms)": 287,
            "Success Rate": 99.7,
            "Requests (24h)": 421,
        },
    ]


def _render_kpi_metrics():
    """Render top-level KPI metrics."""
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric(
            label="Active Pipelines",
            value="8",
            delta="1 new this week",
        )
    with col2:
        st.metric(
            label="Pipeline Success Rate",
            value="94.2%",
            delta="-1.3%",
            delta_color="inverse",
        )
    with col3:
        st.metric(
            label="AI Agents Online",
            value="4/4",
            delta="All healthy",
        )
    with col4:
        st.metric(
            label="Daily Cost (USD)",
            value="$287.40",
            delta="-$12.30",
            delta_color="inverse",
        )
    with col5:
        st.metric(
            label="Open Alerts",
            value="3",
            delta="2 new",
            delta_color="inverse",
        )


def _render_pipeline_status_chart(df: pd.DataFrame):
    """Render pipeline status as a horizontal bar chart with color coding."""
    color_map = {"Succeeded": "#28a745", "Running": "#0078d4", "Failed": "#dc3545"}
    colors = [color_map.get(s, "#6c757d") for s in df["Status"]]

    fig = go.Figure(
        go.Bar(
            x=df["Duration (min)"],
            y=df["Pipeline"],
            orientation="h",
            marker_color=colors,
            text=df["Status"],
            textposition="inside",
        )
    )
    fig.update_layout(
        title="Pipeline Execution Status",
        xaxis_title="Duration (minutes)",
        yaxis_title="",
        height=350,
        margin=dict(l=10, r=10, t=40, b=30),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_cost_trend_chart(df: pd.DataFrame):
    """Render resource cost trend as a stacked area chart."""
    fig = go.Figure()

    for col in ["Fabric Compute", "AI Foundry", "PostgreSQL", "App Service"]:
        fig.add_trace(
            go.Scatter(
                x=df["Date"],
                y=df[col],
                mode="lines",
                stackgroup="one",
                name=col,
            )
        )

    fig.update_layout(
        title="Daily Resource Costs (USD) - Last 30 Days",
        xaxis_title="Date",
        yaxis_title="Cost (USD)",
        height=350,
        margin=dict(l=10, r=10, t=40, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_agent_health_table(agents: list[dict]):
    """Render AI agent health as a styled dataframe."""
    df = pd.DataFrame(agents)

    def _style_status(val):
        color_map = {"Healthy": "#28a745", "Degraded": "#ffc107", "Offline": "#dc3545"}
        color = color_map.get(val, "#6c757d")
        return f"color: {color}; font-weight: bold"

    styled = df.style.applymap(_style_status, subset=["Status"])
    st.dataframe(styled, use_container_width=True, hide_index=True)


def _render_recent_alerts():
    """Render recent platform alerts."""
    alerts = [
        {
            "time": "2 min ago",
            "severity": "WARNING",
            "message": "Manufacturing QA Agent latency exceeds 1000ms threshold",
            "source": "AI Foundry",
        },
        {
            "time": "18 min ago",
            "severity": "ERROR",
            "message": "Customer 360 ETL pipeline failed - PostgreSQL connection timeout",
            "source": "Microsoft Fabric",
        },
        {
            "time": "1 hour ago",
            "severity": "INFO",
            "message": "Demand Forecast Pipeline completed successfully - 245,891 records processed",
            "source": "Microsoft Fabric",
        },
        {
            "time": "3 hours ago",
            "severity": "WARNING",
            "message": "Daily Azure spend approaching 90% of budget threshold",
            "source": "Azure Cost Management",
        },
        {
            "time": "5 hours ago",
            "severity": "INFO",
            "message": "Sales Forecasting Agent model updated to v2.4.1",
            "source": "AI Foundry",
        },
    ]

    for alert in alerts:
        severity = alert["severity"]
        icon_map = {"ERROR": "🔴", "WARNING": "🟡", "INFO": "🔵"}
        icon = icon_map.get(severity, "⚪")

        st.markdown(
            f"**{icon} [{severity}]** {alert['message']}  \n"
            f"<small style='color: #6c757d;'>{alert['time']} | Source: {alert['source']}</small>",
            unsafe_allow_html=True,
        )
        st.markdown("---")


def _render_throughput_chart():
    """Render records processed throughput over time."""
    hours = pd.date_range(end=datetime.now(), periods=24, freq="h")
    data = pd.DataFrame(
        {
            "Hour": hours,
            "Sales": [random.randint(5000, 25000) for _ in hours],
            "Manufacturing": [random.randint(10000, 50000) for _ in hours],
            "Inventory": [random.randint(2000, 15000) for _ in hours],
        }
    )

    fig = px.line(
        data,
        x="Hour",
        y=["Sales", "Manufacturing", "Inventory"],
        title="Records Processed per Hour (Last 24h)",
    )
    fig.update_layout(
        height=300,
        margin=dict(l=10, r=10, t=40, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_dashboard():
    """Main dashboard renderer."""
    st.markdown('<p class="main-header">Platform Dashboard</p>', unsafe_allow_html=True)
    st.caption(f"Environment: **{st.session_state.environment}** | Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # --- KPI Metrics Row ---
    _render_kpi_metrics()

    st.markdown("---")

    # --- Pipeline Status & Cost Trends ---
    col_left, col_right = st.columns(2)

    pipeline_data = _generate_pipeline_status_data()
    cost_data = _generate_cost_data()

    with col_left:
        _render_pipeline_status_chart(pipeline_data)

    with col_right:
        _render_cost_trend_chart(cost_data)

    # --- Pipeline Details Table ---
    with st.expander("Pipeline Execution Details", expanded=False):
        st.dataframe(
            pipeline_data,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Last Run": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
                "Records Processed": st.column_config.NumberColumn(format="%d"),
            },
        )

    st.markdown("---")

    # --- AI Agent Health & Throughput ---
    col_left2, col_right2 = st.columns(2)

    with col_left2:
        st.subheader("AI Agent Health")
        agent_data = _generate_agent_health_data()
        _render_agent_health_table(agent_data)

    with col_right2:
        _render_throughput_chart()

    st.markdown("---")

    # --- Recent Alerts ---
    st.subheader("Recent Alerts")
    _render_recent_alerts()
