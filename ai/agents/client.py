"""
Interactive client for the Equipment Health Agent on Azure AI Foundry.

Handles the tool execution loop: receives tool_calls from the agent,
executes them locally against PostgreSQL, and submits results back.

Usage:
    export PGHOST=dp-psql-dev.postgres.database.azure.com
    export PGUSER=dpadmin
    export PGPASSWORD=<password>
    python client.py [--agent-id <id>]
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

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://dp-ais-dev.openai.azure.com/openai"
API_VERSION = "2024-12-01-preview"


def execute_tool(tools: EquipmentToolsSync, name: str, arguments: dict) -> str:
    """Execute a tool by name and return JSON result."""
    handler = getattr(tools, name, None)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {name}"})

    try:
        result = handler(**arguments)
        return json.dumps(result, default=str)
    except Exception as e:
        logger.error("Tool %s failed: %s", name, e)
        return json.dumps({"error": str(e)})


def run_conversation(client: AgentsClient, agent_id: str, tools: EquipmentToolsSync):
    """Run an interactive multi-turn conversation with the agent."""
    thread = client.create_thread()
    print(f"Thread created: {thread.id}")
    print("Type your questions (or 'quit' to exit, 'new' for a new thread):\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            break
        if user_input.lower() == "new":
            thread = client.create_thread()
            print(f"New thread: {thread.id}\n")
            continue

        # Add user message to thread
        client.create_message(thread_id=thread.id, role="user", content=user_input)

        # Run the agent
        run = client.create_run(thread_id=thread.id, assistant_id=agent_id)

        # Poll until complete, handling tool calls
        while run.status in ("queued", "in_progress", "requires_action"):
            if run.status == "requires_action":
                tool_outputs = []
                for tc in run.required_action.submit_tool_outputs.tool_calls:
                    args = json.loads(tc.function.arguments)
                    logger.info("Tool call: %s(%s)", tc.function.name, args)
                    result = execute_tool(tools, tc.function.name, args)
                    tool_outputs.append(ToolOutput(tool_call_id=tc.id, output=result))

                run = client.submit_tool_outputs_to_run(
                    thread_id=thread.id, run_id=run.id, tool_outputs=tool_outputs
                )
            else:
                time.sleep(0.5)
                run = client.get_run(thread_id=thread.id, run_id=run.id)

        if run.status == "failed":
            print(f"Agent error: {run.last_error}\n")
            continue

        # Get the latest assistant message
        messages = client.list_messages(thread_id=thread.id)
        for msg in messages:
            if msg.role == "assistant":
                for block in msg.content:
                    if isinstance(block, MessageTextContent):
                        print(f"\nAgent: {block.text.value}\n")
                break

    print("Session ended.")


def main():
    endpoint = os.getenv("AI_FOUNDRY_ENDPOINT", DEFAULT_ENDPOINT)

    agent_id = None
    if "--agent-id" in sys.argv:
        idx = sys.argv.index("--agent-id")
        agent_id = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None

    print(f"Connecting to AI Foundry: {endpoint}")
    credential = DefaultAzureCredential()
    client = AgentsClient(endpoint=endpoint, credential=credential, api_version=API_VERSION)

    # If no agent ID provided, find the equipment-health-agent
    if not agent_id:
        for a in client.list_agents():
            if a.name == "equipment-health-agent":
                agent_id = a.id
                break
        if not agent_id:
            print("ERROR: No equipment-health-agent found. Run register_agent.py first.")
            sys.exit(1)

    print(f"Using agent: {agent_id}")

    # Connect to PostgreSQL for tool execution
    tools = EquipmentToolsSync()
    tools.connect()
    print("PostgreSQL connected.\n")

    try:
        run_conversation(client, agent_id, tools)
    finally:
        tools.close()


if __name__ == "__main__":
    main()
