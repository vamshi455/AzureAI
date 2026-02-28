"""
AI Foundry Service - Handles AI agent interactions with Azure AI Foundry (Azure OpenAI).
Includes token management, retry logic, and response streaming.
"""

import os
import json
import time
import logging
import asyncio
from typing import Any, AsyncGenerator
from functools import lru_cache

import httpx
from azure.identity.aio import DefaultAzureCredential, ClientSecretCredential

logger = logging.getLogger(__name__)

# Configuration
AI_FOUNDRY_ENDPOINT = os.getenv("AI_FOUNDRY_ENDPOINT", "")
AI_FOUNDRY_API_KEY = os.getenv("AI_FOUNDRY_API_KEY", "")
AI_FOUNDRY_API_VERSION = os.getenv("AI_FOUNDRY_API_VERSION", "2024-12-01-preview")

# Retry configuration
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0
RETRY_MAX_DELAY = 30.0
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}

# Request timeout configuration
REQUEST_TIMEOUT = 60.0
STREAM_TIMEOUT = 120.0


class TokenManager:
    """Manages Azure AD tokens for AI Foundry authentication."""

    def __init__(self):
        self._token: str | None = None
        self._token_expiry: float = 0
        self._credential = None

    async def _get_credential(self):
        """Get or create the Azure credential."""
        if self._credential is None:
            tenant_id = os.getenv("AZURE_TENANT_ID", "")
            client_id = os.getenv("AZURE_CLIENT_ID", "")
            client_secret = os.getenv("AZURE_CLIENT_SECRET", "")

            if client_id and client_secret and tenant_id:
                self._credential = ClientSecretCredential(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    client_secret=client_secret,
                )
            else:
                self._credential = DefaultAzureCredential()
        return self._credential

    async def get_token(self) -> str:
        """
        Get a valid access token, refreshing if expired.
        Tokens are cached and refreshed 5 minutes before expiry.
        """
        # Check if current token is still valid (with 5-minute buffer)
        if self._token and time.time() < (self._token_expiry - 300):
            return self._token

        try:
            credential = await self._get_credential()
            token_response = await credential.get_token(
                "https://cognitiveservices.azure.com/.default"
            )
            self._token = token_response.token
            self._token_expiry = token_response.expires_on
            logger.info("Azure AD token refreshed successfully")
            return self._token
        except Exception as e:
            logger.error(f"Failed to acquire Azure AD token: {e}")
            raise

    async def close(self):
        """Close the credential client."""
        if self._credential:
            await self._credential.close()


class AIFoundryService:
    """
    Service for Azure AI Foundry (Azure OpenAI) agent interactions.
    Handles authentication, retries, and streaming.
    """

    def __init__(self):
        self._endpoint = AI_FOUNDRY_ENDPOINT.rstrip("/")
        self._api_key = AI_FOUNDRY_API_KEY
        self._api_version = AI_FOUNDRY_API_VERSION
        self._token_manager = TokenManager() if not self._api_key else None
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=10.0),
                limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
            )
        return self._client

    async def _get_auth_headers(self) -> dict[str, str]:
        """Get authentication headers (API key or Azure AD token)."""
        headers = {"Content-Type": "application/json"}

        if self._api_key:
            headers["api-key"] = self._api_key
        elif self._token_manager:
            token = await self._token_manager.get_token()
            headers["Authorization"] = f"Bearer {token}"
        else:
            raise ValueError(
                "No authentication configured. Set AI_FOUNDRY_API_KEY or "
                "Azure AD credentials (AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET)."
            )

        return headers

    def _build_url(self, deployment_name: str) -> str:
        """Build the chat completions URL for a deployment."""
        return (
            f"{self._endpoint}/openai/deployments/{deployment_name}"
            f"/chat/completions?api-version={self._api_version}"
        )

    async def _retry_request(
        self,
        method: str,
        url: str,
        headers: dict,
        json_data: dict,
        stream: bool = False,
    ) -> httpx.Response:
        """
        Execute an HTTP request with exponential backoff retry logic.

        Retries on:
        - 429 (Rate Limited): Uses Retry-After header if present
        - 500, 502, 503, 504 (Server Errors): Exponential backoff
        - Connection errors: Exponential backoff
        """
        client = await self._get_client()
        last_exception: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                if stream:
                    response = await client.send(
                        client.build_request(method, url, headers=headers, json=json_data),
                        stream=True,
                    )
                else:
                    response = await client.request(
                        method, url, headers=headers, json=json_data
                    )

                # Check for retryable status codes
                if response.status_code in RETRY_STATUS_CODES and attempt < MAX_RETRIES:
                    retry_after = _parse_retry_after(response)
                    delay = max(retry_after, RETRY_BASE_DELAY * (2**attempt))
                    delay = min(delay, RETRY_MAX_DELAY)

                    logger.warning(
                        f"Request returned {response.status_code}, "
                        f"retrying in {delay:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                    if not stream:
                        await response.aclose()
                    await asyncio.sleep(delay)
                    continue

                response.raise_for_status()
                return response

            except httpx.ConnectError as e:
                last_exception = e
                if attempt < MAX_RETRIES:
                    delay = min(RETRY_BASE_DELAY * (2**attempt), RETRY_MAX_DELAY)
                    logger.warning(
                        f"Connection error, retrying in {delay:.1f}s "
                        f"(attempt {attempt + 1}/{MAX_RETRIES}): {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Connection failed after {MAX_RETRIES} retries: {e}")

            except httpx.HTTPStatusError as e:
                last_exception = e
                if e.response.status_code not in RETRY_STATUS_CODES or attempt >= MAX_RETRIES:
                    logger.error(
                        f"HTTP error {e.response.status_code}: {e.response.text[:500]}"
                    )
                    raise

            except Exception as e:
                last_exception = e
                logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")
                if attempt >= MAX_RETRIES:
                    raise

        raise last_exception or Exception("Request failed after all retries")

    async def chat_completion(
        self,
        deployment_name: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = False,
        tools: list[dict] | None = None,
        top_p: float = 1.0,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
    ) -> dict[str, Any]:
        """
        Send a chat completion request to AI Foundry.

        Args:
            deployment_name: The model deployment name (e.g., "gpt-4o").
            messages: List of message objects with 'role' and 'content'.
            temperature: Sampling temperature (0.0 to 1.0).
            max_tokens: Maximum tokens in the response.
            stream: Whether to use streaming (use chat_completion_stream instead).
            tools: Optional list of tool definitions for function calling.
            top_p: Nucleus sampling parameter.
            frequency_penalty: Frequency penalty (-2.0 to 2.0).
            presence_penalty: Presence penalty (-2.0 to 2.0).

        Returns:
            The API response as a dictionary.
        """
        url = self._build_url(deployment_name)
        headers = await self._get_auth_headers()

        payload: dict[str, Any] = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty,
            "stream": False,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        logger.info(
            f"Chat completion request: deployment={deployment_name}, "
            f"messages={len(messages)}, max_tokens={max_tokens}"
        )

        response = await self._retry_request("POST", url, headers, payload)
        result = response.json()

        logger.info(
            f"Chat completion response: tokens={result.get('usage', {}).get('total_tokens', 'N/A')}, "
            f"finish_reason={result.get('choices', [{}])[0].get('finish_reason', 'N/A')}"
        )

        return result

    async def chat_completion_stream(
        self,
        deployment_name: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        tools: list[dict] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Send a streaming chat completion request to AI Foundry.

        Yields chunks of the response as they arrive via SSE.

        Args:
            deployment_name: The model deployment name.
            messages: List of message objects.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens.
            tools: Optional tool definitions.

        Yields:
            Dictionaries with 'type' and 'content' keys.
            Types: 'content' (text chunk), 'done' (completion signal).
        """
        url = self._build_url(deployment_name)
        headers = await self._get_auth_headers()

        payload: dict[str, Any] = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        logger.info(f"Starting streaming completion: deployment={deployment_name}")

        full_content = ""

        try:
            response = await self._retry_request(
                "POST", url, headers, payload, stream=True
            )

            async for line in response.aiter_lines():
                if not line:
                    continue

                if line.startswith("data: "):
                    data_str = line[6:].strip()

                    if data_str == "[DONE]":
                        yield {"type": "done", "full_content": full_content}
                        break

                    try:
                        data = json.loads(data_str)
                        choices = data.get("choices", [])

                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content")

                            if content:
                                full_content += content
                                yield {"type": "content", "content": content}

                            # Check for finish reason
                            finish_reason = choices[0].get("finish_reason")
                            if finish_reason:
                                yield {"type": "done", "full_content": full_content}
                                break

                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse SSE data: {data_str[:100]}")
                        continue

            await response.aclose()

        except Exception as e:
            logger.error(f"Streaming error: {e}", exc_info=True)
            yield {"type": "error", "content": str(e)}
            yield {"type": "done", "full_content": full_content}

        logger.info(
            f"Streaming completed: deployment={deployment_name}, "
            f"content_length={len(full_content)}"
        )

    async def close(self):
        """Close HTTP client and credential manager."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        if self._token_manager:
            await self._token_manager.close()


def _parse_retry_after(response: httpx.Response) -> float:
    """Parse the Retry-After header from a response."""
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            pass
    return 0.0
