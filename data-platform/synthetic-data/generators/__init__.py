"""Synthetic data generators for Manufacturing + Sales data platform."""

from .base import SharedMasterData
from .erp_sap import SAPSDGenerator
from .crm_salesforce import SalesforceGenerator
from .iot_telemetry import IoTTelemetryGenerator
