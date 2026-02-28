"""
Azure Data Platform - Admin Portal
Main Streamlit application with multi-page navigation.
"""

import streamlit as st
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from components.sidebar import render_sidebar
from pages.dashboard import render_dashboard
from pages.pipeline_config import render_pipeline_config
from pages.ai_agents import render_ai_agents
from pages.environment_settings import render_environment_settings

# --- Page Configuration ---
st.set_page_config(
    page_title="Azure Data Platform - Admin Portal",
    page_icon="<--ICON_FACTORY-->",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Custom CSS ---
st.markdown(
    """
    <style>
    .main-header {
        font-size: 1.8rem;
        font-weight: 700;
        color: #0078d4;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid #0078d4;
        margin-bottom: 1.5rem;
    }
    .stMetric {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 12px;
        border: 1px solid #e9ecef;
    }
    .block-container {
        padding-top: 2rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Session State Initialization ---
if "environment" not in st.session_state:
    st.session_state.environment = "Dev"
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_info" not in st.session_state:
    st.session_state.user_info = {
        "name": "Admin User",
        "email": "admin@company.com",
        "role": "Platform Administrator",
    }

# --- Navigation Pages ---
PAGES = {
    "Dashboard": {
        "icon": "bar-chart",
        "renderer": render_dashboard,
        "description": "Platform overview and monitoring",
    },
    "Pipeline Config": {
        "icon": "git-merge",
        "renderer": render_pipeline_config,
        "description": "Data pipeline management",
    },
    "AI Agent Management": {
        "icon": "cpu",
        "renderer": render_ai_agents,
        "description": "AI agent deployment and testing",
    },
    "Environment Settings": {
        "icon": "settings",
        "renderer": render_environment_settings,
        "description": "Environment configuration and secrets",
    },
}

# --- Render Sidebar ---
selected_page = render_sidebar(PAGES)

# --- Render Selected Page ---
if selected_page in PAGES:
    PAGES[selected_page]["renderer"]()
else:
    st.error(f"Page '{selected_page}' not found.")


# --- Footer ---
st.markdown("---")
st.caption(
    f"Azure Data Platform Admin Portal | Environment: **{st.session_state.environment}** | "
    f"User: {st.session_state.user_info['email']}"
)
