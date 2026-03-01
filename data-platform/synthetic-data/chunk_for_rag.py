#!/usr/bin/env python3
"""
Hybrid RAG Chunking Pipeline.

Reads bronze-layer Parquet files and generates two types of RAG documents:
  1. Customer 360 profiles (Markdown) - one per customer aggregating all SAP + Salesforce data
  2. Transaction-level documents (JSON) - one per significant sales order with full lifecycle

Usage:
    python chunk_for_rag.py                  # Generate RAG docs from local bronze data
    python chunk_for_rag.py --upload         # Generate and upload to ADLS Gen2
    python chunk_for_rag.py --upload-only    # Upload only (docs already generated)
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from config import (
    OUTPUT_BRONZE,
    OUTPUT_RAG,
    OUTPUT_GOLD,
    DATE_RANGE_END,
    RAG_LARGE_ORDER_THRESHOLD,
    RAG_RECENT_MONTHS,
    HEALTH_SCORE_THRESHOLDS,
)


def load_bronze_parquet(source_system: str, table: str) -> pd.DataFrame:
    """Load a Parquet file from the local bronze output directory."""
    path = OUTPUT_BRONZE / source_system / table / f"{table}.parquet"
    if not path.exists():
        print(f"  WARNING: {path} not found, returning empty DataFrame")
        return pd.DataFrame()
    df = pd.read_parquet(path)
    print(f"  Loaded {table}: {len(df):,} rows")
    return df


class Customer360Generator:
    """Generate Customer 360 Markdown documents aggregating SAP + Salesforce data."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir / "customer-360"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self) -> int:
        """Generate Customer 360 docs for all customers. Returns count."""
        print("\n--- Loading bronze data for Customer 360 ---")
        kna1 = load_bronze_parquet("erp_sap", "kna1")
        vbak = load_bronze_parquet("erp_sap", "vbak")
        vbap = load_bronze_parquet("erp_sap", "vbap")
        accounts = load_bronze_parquet("crm_salesforce", "accounts")
        opportunities = load_bronze_parquet("crm_salesforce", "opportunities")
        cases = load_bronze_parquet("crm_salesforce", "cases")
        contacts = load_bronze_parquet("crm_salesforce", "contacts")

        if kna1.empty:
            print("  No customer data found. Skipping Customer 360.")
            return 0

        # Pre-aggregate order data by customer
        print("\n--- Aggregating order data ---")
        # Join VBAP to VBAK to get customer on each item
        if not vbak.empty and not vbap.empty:
            vbap_with_customer = vbap.merge(
                vbak[["VBELN", "KUNNR", "ERDAT", "WAERK"]],
                on="VBELN",
                how="left",
                suffixes=("", "_hdr"),
            )
            # Convert NETWR to float for aggregation
            vbap_with_customer["NETWR_FLOAT"] = pd.to_numeric(
                vbap_with_customer["NETWR"], errors="coerce"
            ).fillna(0)

            # Order-level aggregation
            order_agg = vbak.copy()
            order_agg["NETWR_FLOAT"] = pd.to_numeric(order_agg["NETWR"], errors="coerce").fillna(0)
            customer_orders = order_agg.groupby("KUNNR").agg(
                total_orders=("VBELN", "count"),
                total_revenue=("NETWR_FLOAT", "sum"),
                avg_order_value=("NETWR_FLOAT", "mean"),
                first_order=("ERDAT", "min"),
                last_order=("ERDAT", "max"),
            ).reset_index()

            # Top products per customer (top 5 by revenue)
            product_revenue = vbap_with_customer.groupby(["KUNNR", "ARKTX"]).agg(
                product_revenue=("NETWR_FLOAT", "sum")
            ).reset_index()
            top_products_by_customer = {}
            for kunnr, group in product_revenue.groupby("KUNNR"):
                top5 = group.nlargest(5, "product_revenue")
                total = group["product_revenue"].sum()
                top_products_by_customer[kunnr] = [
                    {"name": row["ARKTX"], "pct": round(row["product_revenue"] / total * 100, 1) if total > 0 else 0}
                    for _, row in top5.iterrows()
                ]

            # Recent orders (last 6 months)
            cutoff = (datetime.fromisoformat(DATE_RANGE_END) - timedelta(days=RAG_RECENT_MONTHS * 30)).strftime("%Y%m%d")
            recent_orders_df = order_agg[order_agg["ERDAT"] >= cutoff].sort_values("ERDAT", ascending=False)
            recent_by_customer = {}
            for kunnr, group in recent_orders_df.groupby("KUNNR"):
                recent_by_customer[kunnr] = group.head(10).to_dict("records")
        else:
            customer_orders = pd.DataFrame()
            top_products_by_customer = {}
            recent_by_customer = {}

        # Salesforce opportunity aggregation
        opp_by_account = {}
        if not opportunities.empty and not accounts.empty:
            # Map SF AccountId -> SAP KUNNR via accounts
            acct_to_kunnr = dict(zip(accounts["Id"], accounts.get("SAPCustomerNumber", accounts.get("AccountNumber", ""))))
            opportunities["KUNNR"] = opportunities["AccountId"].map(acct_to_kunnr)
            opportunities["AMOUNT_FLOAT"] = pd.to_numeric(opportunities["Amount"], errors="coerce").fillna(0)
            for kunnr, group in opportunities.groupby("KUNNR"):
                won = group[group["StageName"] == "Closed Won"]
                lost = group[group["StageName"] == "Closed Lost"]
                open_opps = group[~group["StageName"].isin(["Closed Won", "Closed Lost"])]
                total_decided = len(won) + len(lost)
                opp_by_account[kunnr] = {
                    "open_count": len(open_opps),
                    "open_value": round(open_opps["AMOUNT_FLOAT"].sum(), 2),
                    "won_count": len(won),
                    "won_value": round(won["AMOUNT_FLOAT"].sum(), 2),
                    "lost_count": len(lost),
                    "lost_value": round(lost["AMOUNT_FLOAT"].sum(), 2),
                    "win_rate": round(len(won) / total_decided * 100, 1) if total_decided > 0 else 0,
                }

        # Cases aggregation
        case_by_account = {}
        if not cases.empty and not accounts.empty:
            acct_to_kunnr = dict(zip(accounts["Id"], accounts.get("SAPCustomerNumber", accounts.get("AccountNumber", ""))))
            cases["KUNNR"] = cases["AccountId"].map(acct_to_kunnr)
            for kunnr, group in cases.groupby("KUNNR"):
                open_cases = group[group["Status"] != "Closed"]
                type_counts = group["Type"].value_counts().head(3)
                case_by_account[kunnr] = {
                    "total": len(group),
                    "open": len(open_cases),
                    "open_high": len(open_cases[open_cases["Priority"].isin(["High", "Critical"])]),
                    "top_types": [f"{t} ({c})" for t, c in type_counts.items()],
                }

        # Contacts by customer
        contacts_by_account = {}
        if not contacts.empty and not accounts.empty:
            acct_to_kunnr = dict(zip(accounts["Id"], accounts.get("SAPCustomerNumber", accounts.get("AccountNumber", ""))))
            contacts["KUNNR"] = contacts["AccountId"].map(acct_to_kunnr)
            for kunnr, group in contacts.groupby("KUNNR"):
                contacts_by_account[kunnr] = group.head(5)[["FirstName", "LastName", "Title", "Email"]].to_dict("records")

        # Build customer lookup from KNA1
        customer_orders_map = {}
        if not customer_orders.empty:
            customer_orders_map = dict(zip(customer_orders["KUNNR"], customer_orders.to_dict("records")))

        # SF account info
        sf_account_map = {}
        if not accounts.empty:
            kunnr_col = "SAPCustomerNumber" if "SAPCustomerNumber" in accounts.columns else "AccountNumber"
            for _, row in accounts.iterrows():
                sf_account_map[row[kunnr_col]] = {
                    "sf_id": row["Id"],
                    "industry": row.get("Industry", ""),
                    "revenue": row.get("AnnualRevenue", ""),
                    "employees": row.get("NumberOfEmployees", ""),
                }

        # Generate one Markdown per customer
        print(f"\n--- Generating Customer 360 documents ({len(kna1):,} customers) ---")
        count = 0
        for _, cust in tqdm(kna1.iterrows(), total=len(kna1), desc="Customer 360"):
            kunnr = str(cust["KUNNR"])
            name = str(cust["NAME1"])
            city = str(cust["ORT01"])
            country = str(cust["LAND1"])
            state = str(cust.get("REGIO", ""))

            sf_info = sf_account_map.get(kunnr, {})
            order_info = customer_orders_map.get(kunnr, {})
            opp_info = opp_by_account.get(kunnr, {})
            case_info = case_by_account.get(kunnr, {})
            contact_list = contacts_by_account.get(kunnr, [])
            top_prods = top_products_by_customer.get(kunnr, [])
            recent = recent_by_customer.get(kunnr, [])

            # Calculate YoY trend
            yoy_trend = ""
            if not vbak.empty and order_info:
                yr1_orders = vbak[(vbak["KUNNR"] == kunnr) & (vbak["ERDAT"] < "20250101")]
                yr2_orders = vbak[(vbak["KUNNR"] == kunnr) & (vbak["ERDAT"] >= "20250101")]
                yr1_val = pd.to_numeric(yr1_orders["NETWR"], errors="coerce").sum()
                yr2_val = pd.to_numeric(yr2_orders["NETWR"], errors="coerce").sum()
                if yr1_val > 0:
                    change = round((yr2_val - yr1_val) / yr1_val * 100, 1)
                    arrow = "\u2191" if change > 0 else "\u2193" if change < 0 else "\u2192"
                    yoy_trend = f"{arrow} {abs(change)}% YoY"

            md = f"# Customer 360: {name}\n\n"
            md += "## Overview\n\n"
            md += "| Field | Value |\n|-------|-------|\n"
            md += f"| SAP Customer (KUNNR) | {kunnr} |\n"
            if sf_info:
                md += f"| Salesforce Account ID | {sf_info.get('sf_id', '')} |\n"
                md += f"| Industry | {sf_info.get('industry', '')} |\n"
            md += f"| City / Country | {city}, {state} / {country} |\n"
            if sf_info.get("revenue"):
                md += f"| Annual Revenue | ${float(sf_info['revenue']):,.0f} |\n"
            if sf_info.get("employees"):
                md += f"| Employees | {sf_info['employees']} |\n"

            if order_info:
                md += f"\n## Order Summary ({order_info.get('first_order', 'N/A')} to {order_info.get('last_order', 'N/A')})\n\n"
                md += f"- **Total Orders:** {order_info.get('total_orders', 0):,}\n"
                md += f"- **Total Revenue:** ${order_info.get('total_revenue', 0):,.2f}\n"
                md += f"- **Average Order Value:** ${order_info.get('avg_order_value', 0):,.2f}\n"
                if top_prods:
                    prods_str = ", ".join(f"{p['name']} ({p['pct']}%)" for p in top_prods[:3])
                    md += f"- **Top Products:** {prods_str}\n"
                if yoy_trend:
                    md += f"- **Order Trend:** {yoy_trend}\n"
            else:
                md += "\n## Order Summary\n\nNo orders recorded in this period.\n"

            if recent:
                md += "\n## Recent Orders (Last 6 months)\n\n"
                md += "| Order # | Date | Value | Currency |\n|---------|------|-------|----------|\n"
                for order in recent[:8]:
                    md += f"| {order.get('VBELN', '')} | {order.get('ERDAT', '')} | ${order.get('NETWR_FLOAT', 0):,.2f} | {order.get('WAERK', 'USD')} |\n"

            if opp_info:
                md += "\n## Salesforce Pipeline\n\n"
                md += f"- **Open Opportunities:** {opp_info.get('open_count', 0)} (${opp_info.get('open_value', 0):,.0f} total)\n"
                md += f"- **Won:** {opp_info.get('won_count', 0)} (${opp_info.get('won_value', 0):,.0f})\n"
                md += f"- **Lost:** {opp_info.get('lost_count', 0)} (${opp_info.get('lost_value', 0):,.0f})\n"
                md += f"- **Win Rate:** {opp_info.get('win_rate', 0)}%\n"

            if case_info:
                md += "\n## Support History\n\n"
                md += f"- **Total Cases:** {case_info.get('total', 0)}\n"
                md += f"- **Open:** {case_info.get('open', 0)}"
                if case_info.get('open_high', 0) > 0:
                    md += f" ({case_info['open_high']} High/Critical)"
                md += "\n"
                if case_info.get("top_types"):
                    md += f"- **Top Issue Types:** {', '.join(case_info['top_types'])}\n"

            if contact_list:
                md += "\n## Key Contacts\n\n"
                md += "| Name | Title | Email |\n|------|-------|-------|\n"
                for c in contact_list:
                    md += f"| {c.get('FirstName', '')} {c.get('LastName', '')} | {c.get('Title', '')} | {c.get('Email', '')} |\n"

            # Write file
            file_path = self.output_dir / f"customer_{kunnr}.md"
            file_path.write_text(md, encoding="utf-8")
            count += 1

        print(f"  Generated {count:,} Customer 360 documents")
        return count


class TransactionDocGenerator:
    """Generate transaction-level JSON RAG documents for significant sales orders."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir / "transactions"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self) -> int:
        """Generate transaction lifecycle docs. Returns count."""
        print("\n--- Loading bronze data for Transaction docs ---")
        vbak = load_bronze_parquet("erp_sap", "vbak")
        vbap = load_bronze_parquet("erp_sap", "vbap")
        vbrk = load_bronze_parquet("erp_sap", "vbrk")
        vbrp = load_bronze_parquet("erp_sap", "vbrp")
        likp = load_bronze_parquet("erp_sap", "likp")
        kna1 = load_bronze_parquet("erp_sap", "kna1")

        if vbak.empty:
            print("  No order data found. Skipping transaction docs.")
            return 0

        # Convert NETWR to float
        vbak["NETWR_FLOAT"] = pd.to_numeric(vbak["NETWR"], errors="coerce").fillna(0)

        # Filter to significant orders
        cutoff_date = (
            datetime.fromisoformat(DATE_RANGE_END) - timedelta(days=RAG_RECENT_MONTHS * 30)
        ).strftime("%Y%m%d")

        large_orders = vbak[vbak["NETWR_FLOAT"] > RAG_LARGE_ORDER_THRESHOLD]
        recent_orders = vbak[vbak["ERDAT"] >= cutoff_date]
        significant = pd.concat([large_orders, recent_orders]).drop_duplicates(subset=["VBELN"])
        print(f"  Significant orders: {len(significant):,} (large: {len(large_orders):,}, recent: {len(recent_orders):,})")

        # Build lookups
        customer_map = {}
        if not kna1.empty:
            customer_map = {str(row["KUNNR"]): row for _, row in kna1.iterrows()}

        vbap_grouped = {str(v): g.to_dict("records") for v, g in vbap.groupby("VBELN")} if not vbap.empty else {}

        # Billing lookup: sales order VBELN -> billing doc
        billing_map = {}
        if not vbrk.empty and "VBELN_VBA" in vbrk.columns:
            for _, row in vbrk.iterrows():
                billing_map[str(row["VBELN_VBA"])] = {
                    "billing_doc": str(row["VBELN"]),
                    "billing_date": str(row.get("FKDAT", "")),
                    "net_value": float(pd.to_numeric(row.get("NETWR", 0), errors="coerce") or 0),
                }

        # Delivery lookup
        delivery_map = {}
        if not likp.empty and "VBELN_VBA" in likp.columns:
            for _, row in likp.iterrows():
                delivery_map[str(row["VBELN_VBA"])] = {
                    "delivery_doc": str(row["VBELN"]),
                    "planned_gi_date": str(row.get("WADAT", "")),
                    "actual_gi_date": str(row.get("WADAT_IST", "")),
                    "shipping_point": str(row.get("VSTEL", "")),
                }

        # Material name lookup
        material_names = {}
        if not vbap.empty:
            for _, row in vbap[["MATNR", "ARKTX"]].drop_duplicates().iterrows():
                material_names[str(row["MATNR"])] = str(row["ARKTX"])

        # Generate documents
        print(f"\n--- Generating Transaction documents ({len(significant):,} orders) ---")
        count = 0
        for _, order in tqdm(significant.iterrows(), total=len(significant), desc="Transaction Docs"):
            vbeln = str(order["VBELN"])
            kunnr = str(order["KUNNR"])
            cust = customer_map.get(kunnr, {})

            # Line items
            items_raw = vbap_grouped.get(vbeln, [])
            line_items = []
            for item in items_raw:
                line_items.append({
                    "item": str(item.get("POSNR", "")),
                    "material": str(item.get("MATNR", "")),
                    "material_name": str(item.get("ARKTX", "")),
                    "quantity": str(item.get("KWMENG", "")),
                    "unit": str(item.get("VRKME", "")),
                    "net_value": float(pd.to_numeric(item.get("NETWR", 0), errors="coerce") or 0),
                    "plant": str(item.get("WERKS", "")),
                })

            # Determine status
            has_billing = vbeln in billing_map
            has_delivery = vbeln in delivery_map
            if has_billing and has_delivery:
                status = "Delivered and Billed"
            elif has_delivery:
                status = "Delivered, Pending Billing"
            elif has_billing:
                status = "Billed, Pending Delivery"
            else:
                status = "Open"

            doc = {
                "document_type": "sales_order_lifecycle",
                "order_number": vbeln,
                "customer": {
                    "kunnr": kunnr,
                    "name": str(cust.get("NAME1", "")),
                    "city": str(cust.get("ORT01", "")),
                    "country": str(cust.get("LAND1", "")),
                },
                "order_header": {
                    "created_date": str(order.get("ERDAT", "")),
                    "order_type": str(order.get("AUART", "")),
                    "sales_org": str(order.get("VKORG", "")),
                    "net_value": round(order.get("NETWR_FLOAT", 0), 2),
                    "currency": str(order.get("WAERK", "")),
                    "customer_po": str(order.get("BSTNK", "")),
                },
                "line_items": line_items,
                "billing": billing_map.get(vbeln),
                "delivery": delivery_map.get(vbeln),
                "status": status,
            }

            file_path = self.output_dir / f"order_{vbeln}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2, ensure_ascii=False)
            count += 1

        print(f"  Generated {count:,} transaction documents")
        return count


class EquipmentHealthGenerator:
    """Generate Equipment Health Report Markdown documents for RAG indexing.

    Reads ML predictions from gold/equipment_health_scores.parquet and IoT
    telemetry from bronze to produce one Markdown file per equipment.
    """

    # Normal operating ranges for status labels
    NORMAL_RANGES = {
        "temperature": (20.0, 60.0),
        "pressure": (2.0, 10.0),
        "vibration": (0.5, 8.0),
        "humidity": (30.0, 70.0),
        "flow_rate": (5.0, 40.0),
        "power": (50.0, 300.0),
    }

    SENSOR_UNITS = {
        "temperature": "C", "pressure": "bar", "vibration": "mm/s",
        "humidity": "%RH", "flow_rate": "L/min", "power": "kW",
    }

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir / "equipment-health"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _health_label(self, score: float) -> str:
        if score < HEALTH_SCORE_THRESHOLDS["Critical"]:
            return "Critical"
        elif score < HEALTH_SCORE_THRESHOLDS["Warning"]:
            return "Warning"
        elif score < HEALTH_SCORE_THRESHOLDS["Good"]:
            return "Good"
        return "Excellent"

    def _sensor_status(self, sensor_type: str, value: float) -> str:
        lo, hi = self.NORMAL_RANGES.get(sensor_type, (0, 999999))
        if value > hi * 1.2 or value < lo * 0.8:
            return "Critical"
        elif value > hi or value < lo:
            return "Elevated"
        return "Normal"

    def generate(self) -> int:
        """Generate equipment health Markdown docs. Returns count."""
        health_path = OUTPUT_GOLD / "equipment_health_scores.parquet"
        if not health_path.exists():
            print("  WARNING: equipment_health_scores.parquet not found. Run predictive_maintenance.py first.")
            return 0

        print("\n--- Loading data for Equipment Health docs ---")
        health_df = pd.read_parquet(health_path)
        # Telemetry is stored under iot/telemetry/ (not iot/iot_telemetry/)
        tel_path = OUTPUT_BRONZE / "iot" / "telemetry" / "iot_telemetry.parquet"
        if tel_path.exists():
            telemetry = pd.read_parquet(tel_path)
            print(f"  Loaded iot_telemetry: {len(telemetry):,} rows")
        else:
            print(f"  WARNING: {tel_path} not found, returning empty DataFrame")
            telemetry = pd.DataFrame()

        # Load lifecycle events if available
        lifecycle_path = OUTPUT_BRONZE / "iot" / "telemetry" / "equipment_lifecycle_events.parquet"
        lifecycle = pd.read_parquet(lifecycle_path) if lifecycle_path.exists() else pd.DataFrame()

        # Pre-compute recent telemetry per equipment (last 90 days)
        recent_telemetry = {}
        anomaly_readings = {}
        if not telemetry.empty and "event_timestamp" in telemetry.columns:
            telemetry["_ts"] = pd.to_datetime(telemetry["event_timestamp"])
            cutoff_90d = telemetry["_ts"].max() - timedelta(days=90)
            recent = telemetry[telemetry["_ts"] >= cutoff_90d]

            for eq_id, group in recent.groupby("equipment_id"):
                recent_telemetry[eq_id] = group

                # Anomalies: non-GOOD readings
                anomalies = group[group["quality_flag"] != "GOOD"].nlargest(10, "_ts")
                if not anomalies.empty:
                    anomaly_readings[eq_id] = anomalies

        # Lifecycle events per equipment
        lifecycle_by_equip = {}
        if not lifecycle.empty:
            for eq_id, group in lifecycle.groupby("equipment_id"):
                lifecycle_by_equip[eq_id] = group.sort_values("event_date", ascending=False).head(10)

        print(f"\n--- Generating Equipment Health documents ({len(health_df):,} equipment) ---")
        count = 0
        for _, equip in tqdm(health_df.iterrows(), total=len(health_df), desc="Equipment Health"):
            eq_id = equip["equipment_id"]
            plant = equip.get("plant_code", "")
            line = equip.get("production_line", "")
            score = equip.get("health_score", 0)
            risk = equip.get("failure_risk", "Unknown")
            rul = equip.get("estimated_rul_days", 0)
            last_maint = equip.get("last_maintenance_date", "N/A")
            action = equip.get("recommended_action", "")

            label = self._health_label(score)

            # Parse sensor summary
            sensor_summary = {}
            raw_summary = equip.get("sensor_summary", "{}")
            if isinstance(raw_summary, str):
                try:
                    sensor_summary = json.loads(raw_summary)
                except (json.JSONDecodeError, TypeError):
                    pass

            # Parse risk factors
            risk_factors = []
            raw_factors = equip.get("top_risk_factors", "[]")
            if isinstance(raw_factors, str):
                try:
                    risk_factors = json.loads(raw_factors)
                except (json.JSONDecodeError, TypeError):
                    pass

            # Build Markdown
            lines = []
            lines.append(f"# Equipment Health Report: {eq_id}\n")

            # Overview
            lines.append("## Overview\n")
            lines.append("| Field | Value |")
            lines.append("|-------|-------|")
            lines.append(f"| Equipment ID | {eq_id} |")
            lines.append(f"| Plant | {plant} |")
            lines.append(f"| Production Line | {line} |")
            lines.append(f"| Health Score | {int(score)}/100 ({label}) |")
            lines.append(f"| Failure Risk | {risk} |")
            lines.append(f"| Estimated RUL | {rul} days |")
            lines.append(f"| Last Maintenance | {last_maint} |")
            lines.append("")

            # Current Sensor Readings
            if sensor_summary:
                lines.append("## Current Sensor Readings (Latest)\n")
                lines.append("| Sensor | Value | Normal Range | Status |")
                lines.append("|--------|-------|-------------|--------|")
                for stype, sval in sensor_summary.items():
                    # sval may be a dict {"value": ..., "unit": ..., "timestamp": ...} or a scalar
                    if isinstance(sval, dict):
                        value = float(sval.get("value", 0))
                        unit = sval.get("unit", self.SENSOR_UNITS.get(stype, ""))
                    else:
                        value = float(sval)
                        unit = self.SENSOR_UNITS.get(stype, "")
                    lo, hi = self.NORMAL_RANGES.get(stype, (0, 999))
                    status = self._sensor_status(stype, value)
                    lines.append(f"| {stype.replace('_', ' ').title()} | {value:.1f} {unit} | {lo}-{hi} {unit} | {status} |")
                lines.append("")

            # Trend Analysis (from recent telemetry)
            eq_recent = recent_telemetry.get(eq_id)
            if eq_recent is not None and not eq_recent.empty:
                lines.append("## Trend Analysis (Last 90 Days)\n")
                for stype in ["vibration", "temperature", "pressure", "power"]:
                    sensor_data = eq_recent[eq_recent["measurement_type"] == stype]
                    if len(sensor_data) >= 2:
                        first_half = sensor_data.iloc[:len(sensor_data)//2]["measurement_value"].mean()
                        second_half = sensor_data.iloc[len(sensor_data)//2:]["measurement_value"].mean()
                        if first_half > 0:
                            pct_change = ((second_half - first_half) / first_half) * 100
                            arrow = "+" if pct_change > 0 else ""
                            trend = "increasing" if pct_change > 5 else "decreasing" if pct_change < -5 else "stable"
                            lines.append(f"- **{stype.replace('_', ' ').title()}**: {arrow}{pct_change:.0f}% ({trend})")
                lines.append("")

            # Anomaly History
            eq_anomalies = anomaly_readings.get(eq_id)
            if eq_anomalies is not None and not eq_anomalies.empty:
                lines.append("## Anomaly History (Recent)\n")
                lines.append("| Date | Sensor | Value | Quality |")
                lines.append("|------|--------|-------|---------|")
                for _, anom in eq_anomalies.head(5).iterrows():
                    ts_str = str(anom.get("event_timestamp", ""))[:10]
                    lines.append(
                        f"| {ts_str} | {anom.get('measurement_type', '')} "
                        f"| {anom.get('measurement_value', '')} {anom.get('measurement_unit', '')} "
                        f"| {anom.get('quality_flag', '')} |"
                    )
                lines.append("")

            # Maintenance History
            eq_lifecycle = lifecycle_by_equip.get(eq_id)
            if eq_lifecycle is not None and not eq_lifecycle.empty:
                maint_events = eq_lifecycle[
                    eq_lifecycle["event_type"].isin(["maintenance_start", "maintenance_complete", "failure"])
                ]
                if not maint_events.empty:
                    lines.append("## Maintenance History\n")
                    lines.append("| Date | Event | From State | To State |")
                    lines.append("|------|-------|-----------|----------|")
                    for _, evt in maint_events.head(5).iterrows():
                        lines.append(
                            f"| {str(evt.get('event_date', ''))[:10]} "
                            f"| {evt.get('event_type', '')} "
                            f"| {evt.get('state_from', '')} "
                            f"| {evt.get('state_to', '')} |"
                        )
                    lines.append("")

            # Recommended Actions
            lines.append("## Recommended Actions\n")
            if action:
                lines.append(f"1. **{action}**")
            if risk_factors:
                for i, factor in enumerate(risk_factors[:3], start=2):
                    fname = factor.get("feature", factor) if isinstance(factor, dict) else factor
                    lines.append(f"{i}. Monitor: {str(fname).replace('_', ' ').title()}")
            lines.append("")

            # Risk Factors
            if risk_factors:
                lines.append("## Top Risk Factors\n")
                for factor in risk_factors[:5]:
                    if isinstance(factor, dict):
                        fname = factor.get("feature", "unknown").replace("_", " ").title()
                        fscore = factor.get("score", 0)
                        lines.append(f"- **{fname}** (risk score: {fscore:.4f})")
                    else:
                        lines.append(f"- {factor}")
                lines.append("")

            md_content = "\n".join(lines)
            safe_eq_id = eq_id.replace("/", "_")
            file_path = self.output_dir / f"equipment_{safe_eq_id}.md"
            file_path.write_text(md_content, encoding="utf-8")
            count += 1

        print(f"  Generated {count:,} equipment health documents")
        return count


def main():
    parser = argparse.ArgumentParser(description="Hybrid RAG Chunking Pipeline")
    parser.add_argument("--upload", action="store_true", help="Upload to ADLS Gen2 after generation")
    parser.add_argument("--upload-only", action="store_true", help="Skip generation, upload only")
    args = parser.parse_args()

    if args.upload_only:
        from upload_to_lakehouse import LakehouseUploader
        LakehouseUploader().upload_all()
        return

    start = time.time()
    print("=" * 60)
    print("Hybrid RAG Chunking Pipeline")
    print("=" * 60)

    # Step 1: Customer 360
    print("\n[1/3] Customer 360 Documents")
    c360 = Customer360Generator(OUTPUT_RAG)
    c360_count = c360.generate()

    # Step 2: Transaction-level
    print("\n[2/3] Transaction-Level Documents")
    txn = TransactionDocGenerator(OUTPUT_RAG)
    txn_count = txn.generate()

    # Step 3: Equipment Health
    print("\n[3/3] Equipment Health Documents")
    equip = EquipmentHealthGenerator(OUTPUT_RAG)
    equip_count = equip.generate()

    elapsed = time.time() - start
    print("\n" + "=" * 60)
    print(f"RAG chunking complete in {elapsed:.1f}s")
    print(f"  Customer 360:      {c360_count:,} documents")
    print(f"  Transactions:      {txn_count:,} documents")
    print(f"  Equipment Health:  {equip_count:,} documents")
    print(f"  Total:             {c360_count + txn_count + equip_count:,} documents")
    print("=" * 60)

    if args.upload:
        from upload_to_lakehouse import LakehouseUploader
        LakehouseUploader().upload_all()


if __name__ == "__main__":
    main()
