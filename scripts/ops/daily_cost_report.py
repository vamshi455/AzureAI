"""
Daily Azure Cost Report Generator.
Queries Azure Cost Management API and outputs a formatted Markdown report.
Designed to run in GitHub Actions with Azure OIDC authentication.

Usage:
    python daily_cost_report.py
    python daily_cost_report.py --output report.md
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone


def az_rest(method: str, uri: str, body: dict | None = None) -> dict:
    """Call Azure REST API via az CLI."""
    cmd = ["az", "rest", "--method", method, "--uri", uri, "-o", "json"]
    if body:
        cmd += ["--body", json.dumps(body)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}", file=sys.stderr)
        return {}
    return json.loads(result.stdout) if result.stdout.strip() else {}


def get_costs_by_service(subscription_id: str) -> list[tuple[str, float]]:
    """Get month-to-date costs grouped by service."""
    uri = f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.CostManagement/query?api-version=2023-11-01"
    body = {
        "type": "ActualCost",
        "timeframe": "MonthToDate",
        "dataset": {
            "granularity": "None",
            "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
            "grouping": [{"type": "Dimension", "name": "ServiceName"}],
        },
    }
    data = az_rest("post", uri, body)
    rows = data.get("properties", {}).get("rows", [])
    return [(row[1], row[0]) for row in sorted(rows, key=lambda x: -x[0]) if row[0] > 0.001]


def get_costs_by_resource(subscription_id: str) -> list[tuple[str, float]]:
    """Get month-to-date costs grouped by resource."""
    uri = f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.CostManagement/query?api-version=2023-11-01"
    body = {
        "type": "ActualCost",
        "timeframe": "MonthToDate",
        "dataset": {
            "granularity": "None",
            "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
            "grouping": [{"type": "Dimension", "name": "ResourceId"}],
        },
    }
    data = az_rest("post", uri, body)
    rows = data.get("properties", {}).get("rows", [])
    results = []
    for row in sorted(rows, key=lambda x: -x[0]):
        if row[0] > 0.01:
            name = row[1].split("/")[-1] if "/" in row[1] else row[1]
            results.append((name, row[0]))
    return results


def get_daily_costs(subscription_id: str, days: int = 7) -> list[tuple[str, float]]:
    """Get daily costs for the last N days."""
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
    end = datetime.now(timezone.utc).strftime("%Y-%m-%dT23:59:59Z")
    uri = f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.CostManagement/query?api-version=2023-11-01"
    body = {
        "type": "ActualCost",
        "timeframe": "Custom",
        "timePeriod": {"from": start, "to": end},
        "dataset": {
            "granularity": "Daily",
            "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
        },
    }
    data = az_rest("post", uri, body)
    rows = data.get("properties", {}).get("rows", [])
    results = []
    for row in sorted(rows, key=lambda x: x[1]):
        date_str = str(row[1])
        formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
        if row[0] > 0:
            results.append((formatted, row[0]))
    return results


def get_budget_status(subscription_id: str) -> dict:
    """Get budget current spend."""
    cmd = [
        "az", "consumption", "budget", "list",
        "--query", "[0].{name:name,amount:amount,spent:currentSpend.amount}",
        "-o", "json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        return json.loads(result.stdout)
    return {}


def generate_report(subscription_id: str) -> str:
    """Generate the full cost report as Markdown."""
    now = datetime.now(timezone.utc)
    report_date = now.strftime("%Y-%m-%d")
    days_in_month = (now.replace(month=now.month % 12 + 1, day=1) - timedelta(days=1)).day
    day_of_month = now.day

    lines = [
        f"# Azure Cost Report - {report_date}",
        "",
        f"> **Subscription:** `{subscription_id}`  ",
        f"> **Resource Group:** `dp-rg-dev` (East US 2)  ",
        f"> **Report generated:** {now.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]

    # Budget status
    budget = get_budget_status(subscription_id)
    if budget:
        spent = float(budget.get("spent", 0))
        amount = float(budget.get("amount", 100))
        pct = (spent / amount) * 100 if amount > 0 else 0
        projected = (spent / day_of_month) * days_in_month if day_of_month > 0 else 0
        bar_filled = int(pct / 5)
        bar = "█" * bar_filled + "░" * (20 - bar_filled)

        lines += [
            "## Budget Status",
            "",
            f"| | |",
            f"|---|---|",
            f"| **Budget** | ${amount:.0f}/month |",
            f"| **Spent (MTD)** | **${spent:.2f}** ({pct:.1f}%) |",
            f"| **Projected (EOM)** | ${projected:.2f} |",
            f"| **Progress** | `{bar}` {pct:.1f}% |",
            "",
        ]

    # Cost by service
    services = get_costs_by_service(subscription_id)
    if services:
        total = sum(c for _, c in services)
        lines += [
            "## Cost by Service (Month-to-Date)",
            "",
            "| Service | Cost (USD) | % |",
            "|---|---:|---:|",
        ]
        for svc, cost in services:
            pct = (cost / total) * 100 if total > 0 else 0
            lines.append(f"| {svc} | ${cost:.2f} | {pct:.0f}% |")
        lines += [f"| **TOTAL** | **${total:.2f}** | |", ""]

    # Top resources
    resources = get_costs_by_resource(subscription_id)
    if resources:
        lines += [
            "## Top Resources by Cost",
            "",
            "| Resource | Cost (USD) |",
            "|---|---:|",
        ]
        for name, cost in resources[:10]:
            lines.append(f"| `{name}` | ${cost:.4f} |")
        lines.append("")

    # Daily trend
    daily = get_daily_costs(subscription_id)
    if daily:
        lines += [
            "## Daily Cost Trend",
            "",
            "| Date | Cost (USD) |",
            "|---|---:|",
        ]
        for date, cost in daily:
            lines.append(f"| {date} | ${cost:.2f} |")
        lines.append("")

    # Cost optimization tips
    lines += [
        "## Cost Optimization Tips",
        "",
        "- Stop PostgreSQL when not in use: `az postgres flexible-server stop --name dp-psql-dev -g dp-rg-dev`",
        "- Private Endpoints are the largest cost driver (~$7.50/endpoint/month)",
        "- Container Registry Premium is needed for PE support; consider Basic if PE not needed",
        "- Azure OpenAI is usage-based — $0 when idle",
        "",
        "---",
        "*Generated by [daily-cost-report](../../.github/workflows/daily-cost-report.yml)*",
    ]

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate Azure daily cost report")
    parser.add_argument("--subscription-id", default=os.getenv(
        "AZURE_SUBSCRIPTION_ID", "9d9e6de8-899f-4fbe-8e31-4925d1356457"
    ))
    parser.add_argument("--output", default=None, help="Write report to file")
    args = parser.parse_args()

    report = generate_report(args.subscription_id)

    if args.output:
        with open(args.output, "w") as f:
            f.write(report)
        print(f"Report written to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
