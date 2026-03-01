"""IoT telemetry data generator for manufacturing equipment sensors.

Generates realistic sensor readings from temperature, pressure, vibration,
humidity, flow-rate, and power sensors deployed across multiple SAP plants
and production lines.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta

import pandas as pd

from generators.base import SharedMasterData, bronze_metadata, row_hash, fake
from config import (
    VOLUMES,
    SAP_PLANTS,
    IOT_DEVICE_TYPES,
    IOT_PRODUCTION_LINES,
    IOT_DEVICE_COUNT,
    DATE_RANGE_START,
    DATE_RANGE_END,
)

# ---------------------------------------------------------------------------
# Measurement profiles per device type
# ---------------------------------------------------------------------------
# Each profile specifies the unit, realistic min/max range, and the number
# of decimal places to use when rounding the generated value.
MEASUREMENT_PROFILES: dict[str, dict] = {
    "temperature": {
        "unit": "°C",
        "min": 15.0,
        "max": 95.0,
        "decimals": 1,
    },
    "pressure": {
        "unit": "bar",
        "min": 0.5,
        "max": 15.0,
        "decimals": 2,
    },
    "vibration": {
        "unit": "mm/s",
        "min": 0.1,
        "max": 25.0,
        "decimals": 2,
    },
    "humidity": {
        "unit": "%RH",
        "min": 20.0,
        "max": 85.0,
        "decimals": 1,
    },
    "flow_rate": {
        "unit": "L/min",
        "min": 0.5,
        "max": 50.0,
        "decimals": 2,
    },
    "power": {
        "unit": "kW",
        "min": 0.1,
        "max": 500.0,
        "decimals": 2,
    },
}


class IoTTelemetryGenerator:
    """Generate IoT telemetry data from manufacturing equipment sensors.

    The generator first registers a fleet of ~200 devices distributed evenly
    across the configured SAP plants and production lines, then produces
    ``VOLUMES["iot_telemetry"]`` telemetry rows referencing those devices.
    """

    # Quality flag distribution: 90% GOOD, 8% UNCERTAIN, 2% BAD
    _QUALITY_FLAGS = ["GOOD"] * 90 + ["UNCERTAIN"] * 8 + ["BAD"] * 2

    def __init__(self, master: SharedMasterData) -> None:
        self.master = master
        self.devices: list[dict] = []
        self._register_devices()

    # ------------------------------------------------------------------
    # Device registration
    # ------------------------------------------------------------------
    def _register_devices(self) -> None:
        """Register ~100 devices spread across plants, lines, and types."""
        device_seq = 1
        target_count = IOT_DEVICE_COUNT

        # Distribute devices as evenly as possible across plants
        devices_per_plant = max(1, target_count // len(SAP_PLANTS))

        for plant in SAP_PLANTS:
            for _ in range(devices_per_plant):
                if len(self.devices) >= target_count:
                    break

                line = fake.random_element(IOT_PRODUCTION_LINES)
                device_type = fake.random_element(IOT_DEVICE_TYPES)
                type_suffix = device_type[:4].upper()  # e.g. TEMP, PRES

                device_id = (
                    f"SENS-{plant}-{line[-1]}-{type_suffix}-"
                    f"{device_seq:03d}"
                )
                equipment_id = (
                    f"EQ-{plant}-{line[-1]}-{fake.random_int(min=1, max=50):03d}"
                )

                self.devices.append(
                    {
                        "device_id": device_id,
                        "device_type": device_type,
                        "plant_code": plant,
                        "production_line": line,
                        "equipment_id": equipment_id,
                    }
                )
                device_seq += 1

            if len(self.devices) >= target_count:
                break

        # If the loop finished before reaching target_count, fill remaining
        while len(self.devices) < target_count:
            plant = fake.random_element(SAP_PLANTS)
            line = fake.random_element(IOT_PRODUCTION_LINES)
            device_type = fake.random_element(IOT_DEVICE_TYPES)
            type_suffix = device_type[:4].upper()

            device_id = (
                f"SENS-{plant}-{line[-1]}-{type_suffix}-"
                f"{device_seq:03d}"
            )
            equipment_id = (
                f"EQ-{plant}-{line[-1]}-{fake.random_int(min=1, max=50):03d}"
            )

            self.devices.append(
                {
                    "device_id": device_id,
                    "device_type": device_type,
                    "plant_code": plant,
                    "production_line": line,
                    "equipment_id": equipment_id,
                }
            )
            device_seq += 1

    # ------------------------------------------------------------------
    # Telemetry generation
    # ------------------------------------------------------------------
    def _random_timestamp(self) -> datetime:
        """Return a random datetime within the configured date range."""
        start = datetime.fromisoformat(DATE_RANGE_START)
        end = datetime.fromisoformat(DATE_RANGE_END)
        delta_seconds = int((end - start).total_seconds())
        offset = random.randint(0, delta_seconds)
        return start + timedelta(seconds=offset)

    def _generate_reading(self, device_type: str) -> tuple[float, str]:
        """Generate a realistic measurement value and its unit for a device type."""
        profile = MEASUREMENT_PROFILES[device_type]
        value = round(
            random.uniform(profile["min"], profile["max"]),
            profile["decimals"],
        )
        return value, profile["unit"]

    def generate_telemetry(self) -> pd.DataFrame:
        """Generate IoT telemetry readings in batches for memory efficiency."""
        from tqdm import tqdm

        num_rows = VOLUMES["iot_telemetry"]
        batch_size = 100_000
        all_dfs: list[pd.DataFrame] = []

        for batch_start in tqdm(range(0, num_rows, batch_size), desc="IoT Telemetry (batches)"):
            batch_end = min(batch_start + batch_size, num_rows)
            rows: list[dict] = []

            for _ in range(batch_end - batch_start):
                device = fake.random_element(self.devices)
                device_type = device["device_type"]
                measurement_value, measurement_unit = self._generate_reading(device_type)

                event_ts = self._random_timestamp()
                enqueue_delay = timedelta(
                    milliseconds=random.randint(50, 5000)
                )
                enqueued_ts = event_ts + enqueue_delay

                quality_flag = random.choice(self._QUALITY_FLAGS)

                raw_payload = json.dumps(
                    {
                        "deviceId": device["device_id"],
                        "type": device_type,
                        "value": measurement_value,
                        "unit": measurement_unit,
                        "quality": quality_flag,
                        "ts": event_ts.isoformat(),
                    },
                    separators=(",", ":"),
                )

                meta = bronze_metadata(
                    source_system="iot",
                    source_table="iot_telemetry",
                    load_type="incremental",
                )

                row = {
                    "device_id": device["device_id"],
                    "device_type": device_type,
                    "plant_code": device["plant_code"],
                    "production_line": device["production_line"],
                    "equipment_id": device["equipment_id"],
                    "measurement_type": device_type,
                    "measurement_value": measurement_value,
                    "measurement_unit": measurement_unit,
                    "event_timestamp": event_ts.isoformat(),
                    "event_enqueued_timestamp": enqueued_ts.isoformat(),
                    "quality_flag": quality_flag,
                    "raw_payload": raw_payload,
                    **meta,
                }
                row["_bronze_row_hash"] = row_hash(row)
                rows.append(row)

            all_dfs.append(pd.DataFrame(rows))

        return pd.concat(all_dfs, ignore_index=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def generate_all(self) -> dict[str, pd.DataFrame]:
        """Generate all IoT datasets.

        Returns
        -------
        dict[str, pd.DataFrame]
            ``{"iot_telemetry": DataFrame}``
        """
        return {"iot_telemetry": self.generate_telemetry()}
