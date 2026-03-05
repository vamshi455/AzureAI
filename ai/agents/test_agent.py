"""
Integration tests for the Equipment Health Agent on Azure AI Foundry.

Sends test queries to the registered agent, handles tool execution,
and verifies responses contain expected content.

Usage:
    export PGHOST=dp-psql-dev.postgres.database.azure.com
    export PGUSER=dpadmin
    export PGPASSWORD=<password>
    python test_agent.py
"""

import json
import logging
import os
import sys
import time

from azure.ai.agents import AgentsClient
from azure.ai.agents.models import MessageTextContent, ToolOutput
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from equipment_tools_sync import EquipmentToolsSync

load_dotenv()

logging.basicConfig(level=logging.WARNING)

DEFAULT_ENDPOINT = "https://dp-ais-dev.openai.azure.com/openai"
API_VERSION = "2024-12-01-preview"

TEST_CASES = [
    {
        "name": "get_equipment_status",
        "query": "What is the health status of equipment EQ-1100-A-001?",
        "expect_contains": ["EQ-1100-A-001"],
    },
    {
        "name": "list_equipment_by_risk",
        "query": "List all equipment with Critical risk level",
        "expect_contains": ["Critical"],
    },
    {
        "name": "get_sensor_readings",
        "query": "Show me the latest temperature readings for EQ-2100-B-007",
        "expect_contains": ["EQ-2100-B-007"],
    },
    {
        "name": "get_equipment_anomalies",
        "query": "Are there any anomalous sensor readings for EQ-1100-A-003 in the last 30 days?",
        "expect_contains": ["EQ-1100-A-003"],
    },
    {
        "name": "search_maintenance_docs",
        "query": "Search for maintenance documents about bearing failures",
        "expect_contains": [],
    },
]


def execute_tool(tools: EquipmentToolsSync, name: str, arguments: dict) -> str:
    handler = getattr(tools, name, None)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        result = handler(**arguments)
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def run_single_query(client: AgentsClient, agent_id: str, tools: EquipmentToolsSync, query: str) -> str:
    """Send a query and return the agent's final response text."""
    thread = client.create_thread()
    client.create_message(thread_id=thread.id, role="user", content=query)
    run = client.create_run(thread_id=thread.id, assistant_id=agent_id)

    max_iterations = 20
    iteration = 0
    while run.status in ("queued", "in_progress", "requires_action") and iteration < max_iterations:
        iteration += 1
        if run.status == "requires_action":
            tool_outputs = []
            for tc in run.required_action.submit_tool_outputs.tool_calls:
                args = json.loads(tc.function.arguments)
                result = execute_tool(tools, tc.function.name, args)
                tool_outputs.append(ToolOutput(tool_call_id=tc.id, output=result))
            run = client.submit_tool_outputs_to_run(
                thread_id=thread.id, run_id=run.id, tool_outputs=tool_outputs
            )
        else:
            time.sleep(0.5)
            run = client.get_run(thread_id=thread.id, run_id=run.id)

    if run.status != "completed":
        return f"[ERROR: run status={run.status}]"

    for msg in client.list_messages(thread_id=thread.id):
        if msg.role == "assistant":
            for block in msg.content:
                if isinstance(block, MessageTextContent):
                    return block.text.value
    return "[ERROR: no assistant message]"


def main():
    endpoint = os.getenv("AI_FOUNDRY_ENDPOINT", DEFAULT_ENDPOINT)
    credential = DefaultAzureCredential()
    client = AgentsClient(endpoint=endpoint, credential=credential, api_version=API_VERSION)

    # Find the agent
    agent_id = None
    for a in client.list_agents():
        if a.name == "equipment-health-agent":
            agent_id = a.id
            break
    if not agent_id:
        print("ERROR: No equipment-health-agent found. Run register_agent.py first.")
        sys.exit(1)
    print(f"Agent: {agent_id}\n")

    # Connect to PostgreSQL
    tools = EquipmentToolsSync()
    tools.connect()

    passed = 0
    failed = 0

    for tc in TEST_CASES:
        print(f"Test: {tc['name']}")
        print(f"  Query: {tc['query']}")

        try:
            response = run_single_query(client, agent_id, tools, tc["query"])
            print(f"  Response: {response[:200]}...")

            all_found = True
            for expected in tc["expect_contains"]:
                if expected.lower() not in response.lower():
                    print(f"  FAIL: Expected '{expected}' not found in response")
                    all_found = False

            if all_found and "[ERROR" not in response:
                print(f"  PASS")
                passed += 1
            else:
                print(f"  FAIL")
                failed += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1

        print()

    tools.close()

    print(f"Results: {passed} passed, {failed} failed, {len(TEST_CASES)} total")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
