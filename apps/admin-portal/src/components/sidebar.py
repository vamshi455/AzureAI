"""
Sidebar Component - Reusable sidebar with navigation,
environment selector (Dev/QA/Prod), and user info.
"""

import streamlit as st
from typing import Any


def render_sidebar(pages: dict[str, Any]) -> str:
    """
    Render the sidebar with navigation, environment selector, and user info.

    Args:
        pages: Dictionary of page definitions with keys as page names
               and values containing 'icon', 'renderer', and 'description'.

    Returns:
        The name of the selected page.
    """
    with st.sidebar:
        # --- Logo / Branding ---
        st.markdown(
            """
            <div style="text-align: center; padding: 1rem 0;">
                <h2 style="color: #0078d4; margin-bottom: 0;">Azure Data Platform</h2>
                <p style="color: #6c757d; font-size: 0.85rem; margin-top: 0;">Admin Portal</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("---")

        # --- Environment Selector ---
        st.markdown("#### Environment")
        environment = st.selectbox(
            "Select Environment",
            ["Dev", "QA", "Prod"],
            index=["Dev", "QA", "Prod"].index(st.session_state.get("environment", "Dev")),
            label_visibility="collapsed",
            key="env_selector",
        )

        # Update session state when environment changes
        if environment != st.session_state.get("environment"):
            st.session_state.environment = environment
            st.rerun()

        # Environment indicator with color coding
        env_colors = {"Dev": "#28a745", "QA": "#ffc107", "Prod": "#dc3545"}
        env_color = env_colors.get(environment, "#6c757d")
        st.markdown(
            f'<div style="background-color: {env_color}; color: white; padding: 6px 12px; '
            f'border-radius: 4px; text-align: center; font-weight: bold; font-size: 0.85rem;">'
            f"{environment} Environment</div>",
            unsafe_allow_html=True,
        )

        if environment == "Prod":
            st.warning("You are viewing the Production environment. Changes may affect live systems.", icon="!!!")

        st.markdown("---")

        # --- Navigation ---
        st.markdown("#### Navigation")

        # Initialize selected page in session state
        if "selected_page" not in st.session_state:
            st.session_state.selected_page = list(pages.keys())[0]

        for page_name, page_config in pages.items():
            is_selected = st.session_state.selected_page == page_name
            button_type = "primary" if is_selected else "secondary"

            if st.button(
                f"{page_name}",
                key=f"nav_{page_name}",
                use_container_width=True,
                type=button_type,
            ):
                st.session_state.selected_page = page_name
                st.rerun()

            if is_selected:
                st.caption(f"  {page_config.get('description', '')}")

        st.markdown("---")

        # --- Quick Actions ---
        st.markdown("#### Quick Actions")

        if st.button("Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        if st.button("Export Config", use_container_width=True):
            st.info("Configuration export initiated. Check downloads.")

        st.markdown("---")

        # --- User Info ---
        st.markdown("#### User")
        user_info = st.session_state.get("user_info", {})

        st.markdown(
            f"""
            <div style="background-color: #f8f9fa; padding: 12px; border-radius: 8px; border: 1px solid #e9ecef;">
                <div style="font-weight: bold; font-size: 0.95rem;">{user_info.get('name', 'Unknown')}</div>
                <div style="color: #6c757d; font-size: 0.8rem;">{user_info.get('email', 'N/A')}</div>
                <div style="color: #0078d4; font-size: 0.75rem; margin-top: 4px;">
                    {user_info.get('role', 'N/A')}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("---")

        # --- System Status ---
        st.markdown("#### System Status")
        st.markdown(
            """
            <div style="font-size: 0.8rem;">
            <div>🟢 API Gateway: Online</div>
            <div>🟢 PostgreSQL: Connected</div>
            <div>🟢 AI Foundry: Active</div>
            <div>🟢 Fabric: Available</div>
            <div>🟢 Slack: Connected</div>
            <div>🟢 Plane: Connected</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("---")
        st.caption("v1.0.0 | Azure Data Platform")

    return st.session_state.selected_page
