"""
Azure Client Utilities - Centralized Azure SDK connections:
Key Vault client, Fabric REST API client, AI Foundry client, PostgreSQL client.
"""

import os
import logging
from typing import Any, Optional
from functools import lru_cache

import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from azure.identity import DefaultAzureCredential, ClientSecretCredential
from azure.keyvault.secrets import SecretClient
from msal import ConfidentialClientApplication

logger = logging.getLogger(__name__)

# Environment variable configuration
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")
KEY_VAULT_URL = os.getenv("KEY_VAULT_URL", "")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "dataplatform")
POSTGRES_USER = os.getenv("POSTGRES_USER", "")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
FABRIC_API_BASE = os.getenv("FABRIC_API_BASE", "https://api.fabric.microsoft.com/v1")
AI_FOUNDRY_ENDPOINT = os.getenv("AI_FOUNDRY_ENDPOINT", "")
AI_FOUNDRY_API_KEY = os.getenv("AI_FOUNDRY_API_KEY", "")
AI_FOUNDRY_API_VERSION = os.getenv("AI_FOUNDRY_API_VERSION", "2024-12-01-preview")


class AzureCredentialManager:
    """Manages Azure credentials using DefaultAzureCredential or Service Principal."""

    _instance: Optional["AzureCredentialManager"] = None
    _credential = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def credential(self):
        """Get or create Azure credential."""
        if self._credential is None:
            if AZURE_CLIENT_ID and AZURE_CLIENT_SECRET and AZURE_TENANT_ID:
                logger.info("Using ClientSecretCredential for authentication.")
                self._credential = ClientSecretCredential(
                    tenant_id=AZURE_TENANT_ID,
                    client_id=AZURE_CLIENT_ID,
                    client_secret=AZURE_CLIENT_SECRET,
                )
            else:
                logger.info("Using DefaultAzureCredential for authentication.")
                self._credential = DefaultAzureCredential()
        return self._credential

    def get_access_token(self, scope: str = "https://management.azure.com/.default") -> str:
        """Get an access token for the specified scope."""
        token = self.credential.get_token(scope)
        return token.token


class KeyVaultClient:
    """Client for Azure Key Vault secret operations."""

    def __init__(self, vault_url: str | None = None):
        self._vault_url = vault_url or KEY_VAULT_URL
        self._client: SecretClient | None = None

    @property
    def client(self) -> SecretClient:
        """Lazy-initialize the Key Vault SecretClient."""
        if self._client is None:
            if not self._vault_url:
                raise ValueError(
                    "Key Vault URL not configured. Set KEY_VAULT_URL environment variable."
                )
            credential = AzureCredentialManager().credential
            self._client = SecretClient(vault_url=self._vault_url, credential=credential)
            logger.info(f"Key Vault client initialized for {self._vault_url}")
        return self._client

    def get_secret(self, name: str) -> str:
        """Retrieve a secret value from Key Vault."""
        try:
            secret = self.client.get_secret(name)
            return secret.value
        except Exception as e:
            logger.error(f"Failed to retrieve secret '{name}': {e}")
            raise

    def list_secrets(self) -> list[dict[str, Any]]:
        """List all secrets in the Key Vault (names only, no values)."""
        try:
            secrets = []
            for secret_properties in self.client.list_properties_of_secrets():
                secrets.append(
                    {
                        "name": secret_properties.name,
                        "content_type": secret_properties.content_type,
                        "enabled": secret_properties.enabled,
                        "created_on": secret_properties.created_on.isoformat()
                        if secret_properties.created_on
                        else None,
                        "expires_on": secret_properties.expires_on.isoformat()
                        if secret_properties.expires_on
                        else None,
                        "updated_on": secret_properties.updated_on.isoformat()
                        if secret_properties.updated_on
                        else None,
                    }
                )
            return secrets
        except Exception as e:
            logger.error(f"Failed to list secrets: {e}")
            raise

    def set_secret(self, name: str, value: str, content_type: str | None = None) -> None:
        """Set a secret in Key Vault."""
        try:
            self.client.set_secret(name, value, content_type=content_type)
            logger.info(f"Secret '{name}' set successfully.")
        except Exception as e:
            logger.error(f"Failed to set secret '{name}': {e}")
            raise


class FabricClient:
    """REST API client for Microsoft Fabric operations."""

    def __init__(self, base_url: str | None = None):
        self._base_url = base_url or FABRIC_API_BASE
        self._session = requests.Session()
        self._token: str | None = None

    def _ensure_auth(self):
        """Ensure the session has a valid auth token."""
        if self._token is None:
            credential_manager = AzureCredentialManager()
            self._token = credential_manager.get_access_token(
                "https://api.fabric.microsoft.com/.default"
            )
            self._session.headers.update(
                {
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                }
            )

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """Make an authenticated request to the Fabric API."""
        self._ensure_auth()
        url = f"{self._base_url}{path}"
        try:
            response = self._session.request(method, url, timeout=30, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.exceptions.HTTPError as e:
            logger.error(f"Fabric API error: {e.response.status_code} - {e.response.text}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Fabric API request failed: {e}")
            raise

    def list_workspaces(self) -> list[dict]:
        """List all Fabric workspaces accessible to the service principal."""
        result = self._request("GET", "/workspaces")
        return result.get("value", [])

    def get_workspace(self, workspace_id: str) -> dict:
        """Get details of a specific workspace."""
        return self._request("GET", f"/workspaces/{workspace_id}")

    def list_lakehouses(self, workspace_id: str) -> list[dict]:
        """List lakehouses in a workspace."""
        result = self._request("GET", f"/workspaces/{workspace_id}/lakehouses")
        return result.get("value", [])

    def list_pipelines(self, workspace_id: str) -> list[dict]:
        """List data pipelines in a workspace."""
        result = self._request("GET", f"/workspaces/{workspace_id}/dataPipelines")
        return result.get("value", [])

    def get_pipeline_run(self, workspace_id: str, pipeline_id: str) -> dict:
        """Get the latest run status of a pipeline."""
        return self._request(
            "GET",
            f"/workspaces/{workspace_id}/dataPipelines/{pipeline_id}/pipelineRuns",
        )

    def trigger_pipeline(self, workspace_id: str, pipeline_id: str) -> dict:
        """Trigger a pipeline run."""
        return self._request(
            "POST",
            f"/workspaces/{workspace_id}/dataPipelines/{pipeline_id}/pipelineRuns",
        )


class AIFoundryClient:
    """Client for Azure AI Foundry (Azure OpenAI) interactions."""

    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        api_version: str | None = None,
    ):
        self._endpoint = (endpoint or AI_FOUNDRY_ENDPOINT).rstrip("/")
        self._api_key = api_key or AI_FOUNDRY_API_KEY
        self._api_version = api_version or AI_FOUNDRY_API_VERSION
        self._session = requests.Session()

        if self._api_key:
            self._session.headers.update({"api-key": self._api_key})
        else:
            # Use managed identity / DefaultAzureCredential
            credential_manager = AzureCredentialManager()
            token = credential_manager.get_access_token(
                "https://cognitiveservices.azure.com/.default"
            )
            self._session.headers.update({"Authorization": f"Bearer {token}"})

        self._session.headers.update({"Content-Type": "application/json"})

    def chat_completion(
        self,
        deployment_name: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = False,
        tools: list[dict] | None = None,
    ) -> dict | requests.Response:
        """Send a chat completion request to AI Foundry."""
        url = (
            f"{self._endpoint}/openai/deployments/{deployment_name}"
            f"/chat/completions?api-version={self._api_version}"
        )

        payload: dict[str, Any] = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        if tools:
            payload["tools"] = tools

        try:
            response = self._session.post(url, json=payload, stream=stream, timeout=60)
            response.raise_for_status()

            if stream:
                return response  # Return raw response for SSE processing
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"AI Foundry request failed: {e}")
            raise

    def list_deployments(self) -> list[dict]:
        """List model deployments in the AI Foundry resource."""
        url = f"{self._endpoint}/openai/deployments?api-version={self._api_version}"
        try:
            response = self._session.get(url, timeout=30)
            response.raise_for_status()
            return response.json().get("data", [])
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to list deployments: {e}")
            raise


class PostgreSQLClient:
    """Client for PostgreSQL with pgvector support."""

    def __init__(
        self,
        host: str | None = None,
        port: str | None = None,
        database: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ):
        self._host = host or POSTGRES_HOST
        self._port = port or POSTGRES_PORT
        self._database = database or POSTGRES_DB
        self._user = user or POSTGRES_USER
        self._password = password or POSTGRES_PASSWORD
        self._conn = None

    @property
    def connection(self):
        """Get or create a PostgreSQL connection."""
        if self._conn is None or self._conn.closed:
            if not all([self._host, self._user, self._password]):
                raise ValueError(
                    "PostgreSQL connection parameters not configured. "
                    "Set POSTGRES_HOST, POSTGRES_USER, POSTGRES_PASSWORD environment variables."
                )
            self._conn = psycopg2.connect(
                host=self._host,
                port=self._port,
                dbname=self._database,
                user=self._user,
                password=self._password,
                sslmode="require",
                connect_timeout=10,
            )
            self._conn.autocommit = True
            logger.info(f"PostgreSQL connection established to {self._host}")
        return self._conn

    def execute_query(self, query: str, params: tuple | None = None) -> list[dict]:
        """Execute a query and return results as list of dicts."""
        try:
            with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                if cursor.description:
                    return [dict(row) for row in cursor.fetchall()]
                return []
        except Exception as e:
            logger.error(f"PostgreSQL query failed: {e}")
            raise

    def execute_command(self, query: str, params: tuple | None = None) -> int:
        """Execute a command (INSERT/UPDATE/DELETE) and return affected row count."""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.rowcount
        except Exception as e:
            logger.error(f"PostgreSQL command failed: {e}")
            raise

    def vector_search(
        self,
        table: str,
        embedding: list[float],
        limit: int = 10,
        similarity_threshold: float = 0.7,
    ) -> list[dict]:
        """Perform a vector similarity search using pgvector."""
        query = f"""
            SELECT *, 1 - (embedding <=> %s::vector) AS similarity
            FROM {table}
            WHERE 1 - (embedding <=> %s::vector) >= %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        return self.execute_query(
            query, (embedding, embedding, similarity_threshold, embedding, limit)
        )

    def health_check(self) -> bool:
        """Check if PostgreSQL connection is healthy."""
        try:
            result = self.execute_query("SELECT 1 AS health")
            return len(result) > 0 and result[0].get("health") == 1
        except Exception:
            return False

    def close(self):
        """Close the PostgreSQL connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()
            logger.info("PostgreSQL connection closed.")


# --- Convenience factory functions ---

@lru_cache(maxsize=1)
def get_keyvault_client() -> KeyVaultClient:
    """Get a cached Key Vault client instance."""
    return KeyVaultClient()


@lru_cache(maxsize=1)
def get_fabric_client() -> FabricClient:
    """Get a cached Fabric client instance."""
    return FabricClient()


@lru_cache(maxsize=1)
def get_ai_foundry_client() -> AIFoundryClient:
    """Get a cached AI Foundry client instance."""
    return AIFoundryClient()


def get_postgres_client() -> PostgreSQLClient:
    """Get a new PostgreSQL client instance (not cached due to connection state)."""
    return PostgreSQLClient()
