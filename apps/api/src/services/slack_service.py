"""
Slack Integration Service - Send alerts, pipeline notifications,
and incident updates via Slack webhooks and Slack SDK.
"""

import os
import json
import logging
from typing import Any
from enum import Enum

import httpx

logger = logging.getLogger(__name__)

# Configuration
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_DEFAULT_CHANNEL = os.getenv("SLACK_DEFAULT_CHANNEL", "#data-platform-alerts")
SLACK_API_BASE = "https://slack.com/api"


class AlertSeverity(str, Enum):
    """Alert severity levels with corresponding Slack styling."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# Color mapping for Slack attachments
SEVERITY_COLORS = {
    AlertSeverity.INFO: "#2196F3",
    AlertSeverity.WARNING: "#FF9800",
    AlertSeverity.ERROR: "#F44336",
    AlertSeverity.CRITICAL: "#9C27B0",
}

SEVERITY_EMOJI = {
    AlertSeverity.INFO: ":information_source:",
    AlertSeverity.WARNING: ":warning:",
    AlertSeverity.ERROR: ":red_circle:",
    AlertSeverity.CRITICAL: ":rotating_light:",
}


class SlackService:
    """
    Slack integration service for sending notifications.
    Supports both webhook-based and API-based message delivery.
    """

    def __init__(self):
        self._webhook_url = SLACK_WEBHOOK_URL
        self._bot_token = SLACK_BOT_TOKEN
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        return self._client

    # ---------------------------------------------------------------
    # Webhook-based messaging
    # ---------------------------------------------------------------

    async def send_webhook_message(
        self,
        text: str,
        blocks: list[dict] | None = None,
        attachments: list[dict] | None = None,
        webhook_url: str | None = None,
    ) -> bool:
        """
        Send a message via Slack Incoming Webhook.

        Args:
            text: Fallback text for notifications.
            blocks: Slack Block Kit blocks for rich formatting.
            attachments: Legacy attachments (for color-coded messages).
            webhook_url: Override webhook URL (defaults to SLACK_WEBHOOK_URL).

        Returns:
            True if the message was sent successfully.
        """
        url = webhook_url or self._webhook_url
        if not url:
            logger.warning("Slack webhook URL not configured, skipping notification")
            return False

        payload: dict[str, Any] = {"text": text}
        if blocks:
            payload["blocks"] = blocks
        if attachments:
            payload["attachments"] = attachments

        try:
            client = await self._get_client()
            response = await client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            logger.info(f"Slack webhook message sent successfully")
            return True
        except httpx.HTTPError as e:
            logger.error(f"Failed to send Slack webhook message: {e}")
            return False

    # ---------------------------------------------------------------
    # Slack API-based messaging (using Bot Token)
    # ---------------------------------------------------------------

    async def send_message(
        self,
        channel: str,
        text: str,
        blocks: list[dict] | None = None,
        thread_ts: str | None = None,
        unfurl_links: bool = False,
    ) -> dict | None:
        """
        Send a message via Slack Web API (chat.postMessage).

        Args:
            channel: Slack channel ID or name (e.g., "#alerts" or "C0123456789").
            text: Message text (used as fallback in notifications).
            blocks: Block Kit blocks for rich formatting.
            thread_ts: Thread timestamp to reply in a thread.
            unfurl_links: Whether to unfurl URLs in the message.

        Returns:
            Slack API response dict, or None on failure.
        """
        if not self._bot_token:
            logger.warning("Slack bot token not configured, falling back to webhook")
            await self.send_webhook_message(text, blocks)
            return None

        payload: dict[str, Any] = {
            "channel": channel,
            "text": text,
            "unfurl_links": unfurl_links,
        }
        if blocks:
            payload["blocks"] = blocks
        if thread_ts:
            payload["thread_ts"] = thread_ts

        try:
            client = await self._get_client()
            response = await client.post(
                f"{SLACK_API_BASE}/chat.postMessage",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._bot_token}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("ok"):
                logger.error(f"Slack API error: {data.get('error', 'unknown')}")
                return None

            logger.info(f"Message sent to {channel}: ts={data.get('ts')}")
            return data
        except httpx.HTTPError as e:
            logger.error(f"Failed to send Slack message: {e}")
            return None

    async def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
        blocks: list[dict] | None = None,
    ) -> dict | None:
        """Update an existing Slack message."""
        if not self._bot_token:
            logger.warning("Slack bot token not configured, cannot update message")
            return None

        payload: dict[str, Any] = {
            "channel": channel,
            "ts": ts,
            "text": text,
        }
        if blocks:
            payload["blocks"] = blocks

        try:
            client = await self._get_client()
            response = await client.post(
                f"{SLACK_API_BASE}/chat.update",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._bot_token}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("ok"):
                logger.error(f"Slack API update error: {data.get('error')}")
                return None

            return data
        except httpx.HTTPError as e:
            logger.error(f"Failed to update Slack message: {e}")
            return None

    # ---------------------------------------------------------------
    # Pre-built notification templates
    # ---------------------------------------------------------------

    async def send_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity,
        source: str,
        channel: str | None = None,
        details: dict | None = None,
    ) -> bool:
        """
        Send a formatted alert notification.

        Args:
            title: Alert title.
            message: Alert description.
            severity: Alert severity level.
            source: Source system (e.g., "Microsoft Fabric", "AI Foundry").
            channel: Target channel (defaults to SLACK_DEFAULT_CHANNEL).
            details: Additional key-value details to include.
        """
        target_channel = channel or SLACK_DEFAULT_CHANNEL
        emoji = SEVERITY_EMOJI.get(severity, ":bell:")
        color = SEVERITY_COLORS.get(severity, "#808080")

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {title}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message,
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:* {severity.value.upper()} | *Source:* {source}",
                    },
                ],
            },
        ]

        if details:
            detail_lines = [f"*{k}:* {v}" for k, v in details.items()]
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "\n".join(detail_lines),
                    },
                }
            )

        blocks.append({"type": "divider"})

        attachments = [{"color": color, "blocks": blocks}]

        if self._bot_token:
            result = await self.send_message(
                channel=target_channel,
                text=f"[{severity.value.upper()}] {title}: {message}",
                blocks=blocks,
            )
            return result is not None
        else:
            return await self.send_webhook_message(
                text=f"[{severity.value.upper()}] {title}: {message}",
                attachments=attachments,
            )

    async def send_pipeline_notification(
        self,
        pipeline_name: str,
        status: str,
        duration_minutes: int | None = None,
        records_processed: int | None = None,
        error_message: str | None = None,
        channel: str | None = None,
    ) -> bool:
        """
        Send a data pipeline status notification.

        Args:
            pipeline_name: Name of the pipeline.
            status: Pipeline status (succeeded, failed, running).
            duration_minutes: Execution duration in minutes.
            records_processed: Number of records processed.
            error_message: Error message if the pipeline failed.
            channel: Target Slack channel.
        """
        status_config = {
            "succeeded": {"emoji": ":white_check_mark:", "color": "#28a745", "label": "Succeeded"},
            "failed": {"emoji": ":x:", "color": "#dc3545", "label": "Failed"},
            "running": {"emoji": ":arrow_forward:", "color": "#0078d4", "label": "Running"},
        }

        config = status_config.get(status, {"emoji": ":grey_question:", "color": "#6c757d", "label": status.title()})

        fields = []
        if duration_minutes is not None:
            fields.append(f"*Duration:* {duration_minutes} min")
        if records_processed is not None:
            fields.append(f"*Records:* {records_processed:,}")

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{config['emoji']} *Pipeline: {pipeline_name}*\n"
                        f"Status: *{config['label']}*"
                    ),
                },
            },
        ]

        if fields:
            blocks.append(
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": " | ".join(fields)}],
                }
            )

        if error_message:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f":warning: *Error:*\n```{error_message}```",
                    },
                }
            )

        target_channel = channel or SLACK_DEFAULT_CHANNEL
        fallback_text = f"Pipeline {pipeline_name}: {config['label']}"

        if self._bot_token:
            result = await self.send_message(
                channel=target_channel,
                text=fallback_text,
                blocks=blocks,
            )
            return result is not None
        else:
            return await self.send_webhook_message(
                text=fallback_text,
                blocks=blocks,
            )

    async def send_incident_update(
        self,
        incident_id: str,
        title: str,
        update: str,
        status: str,
        channel: str | None = None,
        thread_ts: str | None = None,
    ) -> dict | None:
        """
        Send an incident update notification.

        Args:
            incident_id: Incident identifier.
            title: Incident title.
            update: Latest update message.
            status: Current incident status (investigating, identified, monitoring, resolved).
            channel: Target Slack channel.
            thread_ts: Thread timestamp to keep updates in a thread.

        Returns:
            Slack API response (for threading follow-up updates).
        """
        status_emoji = {
            "investigating": ":mag:",
            "identified": ":point_right:",
            "monitoring": ":eyes:",
            "resolved": ":white_check_mark:",
        }

        emoji = status_emoji.get(status, ":bell:")

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Incident {incident_id}: {title}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{emoji} *Status: {status.upper()}*\n\n{update}",
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Incident ID: {incident_id} | Use thread for updates",
                    },
                ],
            },
            {"type": "divider"},
        ]

        target_channel = channel or SLACK_DEFAULT_CHANNEL
        fallback_text = f"[{status.upper()}] Incident {incident_id}: {title} - {update}"

        if self._bot_token:
            return await self.send_message(
                channel=target_channel,
                text=fallback_text,
                blocks=blocks,
                thread_ts=thread_ts,
            )
        else:
            await self.send_webhook_message(text=fallback_text, blocks=blocks)
            return None

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Singleton instance
_slack_service: SlackService | None = None


def get_slack_service() -> SlackService:
    """Get the singleton Slack service instance."""
    global _slack_service
    if _slack_service is None:
        _slack_service = SlackService()
    return _slack_service
