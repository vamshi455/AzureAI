"""
Register the Equipment Health Agent in Azure AI Foundry Agent Service.

Usage:
    export AI_FOUNDRY_PROJECT_ENDPOINT="https://<ai-services>.services.ai.azure.com/api/projects/<project>"
    python register_agent.py

Prerequisites:
    pip install -r requirements.txt
    az login
"""

import os
import sys
from pathlib import Path

import yaml
from azure.ai.agents.models import FunctionDefinition, FunctionToolDefinition
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

# Paths relative to this script
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent.parent
SYSTEM_PROMPT = REPO_ROOT / "ai" / "prompts" / "system" / "equipment_health.md"
AGENT_CONFIG = SCRIPT_DIR / "configs" / "equipment_health_agent.yaml"

MODEL_DEPLOYMENT = os.getenv("MODEL_DEPLOYMENT", "gpt-4o-equipment-health")


def load_system_prompt() -> str:
    """Load system prompt and append operational rules from YAML config."""
    prompt = SYSTEM_PROMPT.read_text()

    config = yaml.safe_load(AGENT_CONFIG.read_text())
    additional = config.get("instructions", {}).get("additional_instructions", "")
    if additional:
        prompt += "\n\n" + additional.strip()

    return prompt


def load_tool_definitions() -> list[FunctionToolDefinition]:
    """Convert YAML tool definitions to SDK FunctionToolDefinition objects."""
    config = yaml.safe_load(AGENT_CONFIG.read_text())
    tools = config.get("tools", [])

    definitions = []
    for tool in tools:
        if tool.get("type") != "function":
            continue

        params = tool.get("parameters", {})
        schema = {
            "type": params.get("type", "object"),
            "properties": {},
            "required": params.get("required", []),
        }
        for prop_name, prop_def in params.get("properties", {}).items():
            schema["properties"][prop_name] = {
                k: v for k, v in prop_def.items() if k != "default"
            }

        definitions.append(
            FunctionToolDefinition(
                function=FunctionDefinition(
                    name=tool["name"],
                    description=tool.get("description", "").strip(),
                    parameters=schema,
                )
            )
        )

    return definitions


def main():
    endpoint = os.getenv("AI_FOUNDRY_ENDPOINT", "https://dp-ais-dev.openai.azure.com/openai")

    print(f"Connecting to AI Foundry: {endpoint}")
    credential = DefaultAzureCredential()

    from azure.ai.agents import AgentsClient
    agents_client = AgentsClient(
        endpoint=endpoint,
        credential=credential,
        api_version="2024-12-01-preview",
    )

    instructions = load_system_prompt()
    tool_defs = load_tool_definitions()

    print(f"System prompt: {len(instructions)} chars")
    print(f"Tools: {[t.function.name for t in tool_defs]}")

    agent = agents_client.create_agent(
        model=MODEL_DEPLOYMENT,
        name="equipment-health-agent",
        instructions=instructions,
        tools=tool_defs,
    )

    print(f"\nAgent registered successfully!")
    print(f"  Agent ID:   {agent.id}")
    print(f"  Name:       {agent.name}")
    print(f"  Model:      {agent.model}")
    print(f"  Tools:      {len(tool_defs)} function tools")
    print(f"\nThe agent is now visible in Azure AI Foundry Studio.")


if __name__ == "__main__":
    main()
