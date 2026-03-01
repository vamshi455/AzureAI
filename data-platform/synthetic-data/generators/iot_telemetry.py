"""IoT telemetry data generator for manufacturing equipment sensors.

Generates realistic sensor readings from temperature, pressure, vibration,
humidity, flow-rate, and power sensors deployed across multiple SAP plants
and production lines.

Readings follow an equipment lifecycle state machine that produces realistic
degradation patterns suitable for training predictive-maintenance ML models:

    HEALTHY -> DEGRADING -> WARNING -> CRITICAL -> FAILED -> MAINTAINED -> HEALTHY
"""

from __future__ import annotations

import json
import math
import random
from bisect import bisect_right
from datetime import datetime, timedelta

import numpy as np
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
    RANDOM_SEED,
)

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
np.random.seed(RANDOM_SEED)

# ---------------------------------------------------------------------------
# Normal operating baselines per sensor type
# ---------------------------------------------------------------------------
NORMAL_BASELINES = {
    "temperature": {"mean": 45.0, "std": 5.0},
    "pressure":    {"mean": 6.0,  "std": 1.0},
    "vibration":   {"mean": 2.5,  "std": 0.8},
    "humidity":    {"mean": 50.0, "std": 5.0},
    "flow_rate":   {"mean": 20.0, "std": 3.0},
    "power":       {"mean": 150.0, "std": 20.0},
}

# ---------------------------------------------------------------------------
# Health-state effects on sensor distributions
# ---------------------------------------------------------------------------
HEALTH_STATE_EFFECTS = {
    "HEALTHY":    {"mean_shift": 0.0,  "std_mult": 1.0,  "anomaly_rate": 0.005},
    "DEGRADING":  {"mean_shift": 0.15, "std_mult": 1.3,  "anomaly_rate": 0.02},
    "WARNING":    {"mean_shift": 0.30, "std_mult": 1.6,  "anomaly_rate": 0.05},
    "CRITICAL":   {"mean_shift": 0.50, "std_mult": 2.0,  "anomaly_rate": 0.10},
    "FAILED":     {"mean_shift": 0.80, "std_mult": 3.0,  "anomaly_rate": 0.30},
    "MAINTAINED": {"mean_shift": -0.05, "std_mult": 0.8, "anomaly_rate": 0.002},
}

# State transition durations (days) — sampled uniformly within the range
STATE_DURATIONS = {
    "DEGRADING":  (30, 90),
    "WARNING":    (7, 21),
    "CRITICAL":   (2, 7),
    "FAILED":     (1, 3),
    "MAINTAINED": (1, 3),
}

# Quality-flag distributions per health state
_QUALITY_DISTRIBUTIONS = {
    "HEALTHY":    {"GOOD": 0.95, "UNCERTAIN": 0.04, "BAD": 0.01},
    "DEGRADING":  {"GOOD": 0.85, "UNCERTAIN": 0.10, "BAD": 0.05},
    "WARNING":    {"GOOD": 0.70, "UNCERTAIN": 0.20, "BAD": 0.10},
    "CRITICAL":   {"GOOD": 0.60, "UNCERTAIN": 0.25, "BAD": 0.15},
    "FAILED":     {"GOOD": 0.30, "UNCERTAIN": 0.30, "BAD": 0.40},
    "MAINTAINED": {"GOOD": 0.98, "UNCERTAIN": 0.02, "BAD": 0.00},
}

# ---------------------------------------------------------------------------
# Measurement profiles per device type (kept from original)
# ---------------------------------------------------------------------------
MEASUREMENT_PROFILES: dict[str, dict] = {
    "temperature": {
        "unit": "\u00b0C",
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
    """Generate IoT telemetry data with realistic equipment degradation.

    The generator first registers a fleet of ~200 devices distributed evenly
    across the configured SAP plants and production lines, builds a full
    equipment lifecycle timeline for each unique equipment_id, then produces
    ``VOLUMES["iot_telemetry"]`` telemetry rows whose sensor distributions
    reflect the health state of the equipment at each point in time.
    """

    def __init__(self, master: SharedMasterData) -> None:
        self.master = master
        self.devices: list[dict] = []
        self._register_devices()

        # Lifecycle data populated by _generate_equipment_lifecycles()
        self.equipment_lifecycles: dict[str, list[tuple[datetime, datetime, str]]] = {}
        self.lifecycle_events_df: pd.DataFrame = pd.DataFrame()

        # Pre-computed lookup accelerators (populated lazily)
        self._lifecycle_starts: dict[str, list[float]] = {}
        self._lifecycle_states: dict[str, list[str]] = {}

        self._generate_equipment_lifecycles()

    # ------------------------------------------------------------------
    # Device registration (unchanged)
    # ------------------------------------------------------------------
    def _register_devices(self) -> None:
        """Register ~200 devices spread across plants, lines, and types."""
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
    # Equipment lifecycle state machine
    # ------------------------------------------------------------------
    def _generate_equipment_lifecycles(self) -> None:
        """Build a full lifecycle timeline for every unique equipment_id.

        Each equipment cycles through:
            HEALTHY -> DEGRADING -> WARNING -> CRITICAL -> FAILED
                                                         -> MAINTAINED -> HEALTHY
        with probabilistic maintenance interventions at WARNING or CRITICAL.
        """
        range_start = datetime.fromisoformat(DATE_RANGE_START)
        range_end = datetime.fromisoformat(DATE_RANGE_END)

        unique_equipment_ids = sorted({d["equipment_id"] for d in self.devices})

        lifecycle_events: list[dict] = []

        for eq_id in unique_equipment_ids:
            age_factor = float(
                np.random.choice(
                    [0.5, 0.7, 1.0, 1.3, 2.0],
                    p=[0.1, 0.2, 0.4, 0.2, 0.1],
                )
            )

            intervals: list[tuple[datetime, datetime, str]] = []
            cursor = range_start
            state = "HEALTHY"

            while cursor < range_end:
                if state == "HEALTHY":
                    days = max(30, int(np.random.gamma(4, 60) / age_factor))
                else:
                    lo, hi = STATE_DURATIONS[state]
                    days = np.random.randint(lo, hi + 1)

                interval_end = min(cursor + timedelta(days=days), range_end)
                intervals.append((cursor, interval_end, state))

                if interval_end >= range_end:
                    break

                prev_state = state
                # Determine next state
                if state == "HEALTHY":
                    next_state = "DEGRADING"
                    event_type = "degradation_start"
                elif state == "DEGRADING":
                    next_state = "WARNING"
                    event_type = "warning"
                elif state == "WARNING":
                    # 70% chance of maintenance intervention
                    if np.random.random() < 0.70:
                        next_state = "MAINTAINED"
                        event_type = "maintenance_start"
                    else:
                        next_state = "CRITICAL"
                        event_type = "critical"
                elif state == "CRITICAL":
                    # 70% chance of maintenance intervention
                    if np.random.random() < 0.70:
                        next_state = "MAINTAINED"
                        event_type = "maintenance_start"
                    else:
                        next_state = "FAILED"
                        event_type = "failure"
                elif state == "FAILED":
                    next_state = "MAINTAINED"
                    event_type = "maintenance_start"
                elif state == "MAINTAINED":
                    next_state = "HEALTHY"
                    event_type = "maintenance_complete"
                else:
                    next_state = "HEALTHY"
                    event_type = "maintenance_complete"

                lifecycle_events.append(
                    {
                        "equipment_id": eq_id,
                        "event_date": interval_end.isoformat(),
                        "state_from": prev_state,
                        "state_to": next_state,
                        "event_type": event_type,
                    }
                )

                cursor = interval_end
                state = next_state

            self.equipment_lifecycles[eq_id] = intervals

            # Build binary-search accelerator for this equipment
            self._lifecycle_starts[eq_id] = [
                iv[0].timestamp() for iv in intervals
            ]
            self._lifecycle_states[eq_id] = [iv[2] for iv in intervals]

        if lifecycle_events:
            self.lifecycle_events_df = pd.DataFrame(lifecycle_events)
        else:
            self.lifecycle_events_df = pd.DataFrame(
                columns=[
                    "equipment_id",
                    "event_date",
                    "state_from",
                    "state_to",
                    "event_type",
                ]
            )

    # ------------------------------------------------------------------
    # State lookup via binary search
    # ------------------------------------------------------------------
    def _get_equipment_state(self, equipment_id: str, timestamp: datetime) -> str:
        """Return the health state for *equipment_id* at *timestamp*.

        Uses a pre-built sorted list of interval start timestamps per
        equipment and ``bisect_right`` for O(log n) lookup.
        """
        starts = self._lifecycle_starts.get(equipment_id)
        states = self._lifecycle_states.get(equipment_id)
        if starts is None or states is None:
            return "HEALTHY"

        ts = timestamp.timestamp()
        idx = bisect_right(starts, ts) - 1
        if idx < 0:
            return "HEALTHY"
        return states[idx]

    # ------------------------------------------------------------------
    # Reading generation with degradation-aware distributions
    # ------------------------------------------------------------------
    @staticmethod
    def _generate_reading(
        device_type: str,
        equipment_state: str,
        timestamp: datetime,
    ) -> tuple[float, str]:
        """Generate a sensor value influenced by equipment health state.

        The value is drawn from a normal distribution whose mean and variance
        are shifted according to HEALTH_STATE_EFFECTS.  Seasonal and diurnal
        components are added for temperature and power respectively.  Anomaly
        spikes are injected probabilistically based on the anomaly rate for
        the current state.
        """
        baseline = NORMAL_BASELINES[device_type]
        effects = HEALTH_STATE_EFFECTS[equipment_state]
        profile = MEASUREMENT_PROFILES[device_type]

        adjusted_mean = baseline["mean"] * (1 + effects["mean_shift"])
        adjusted_std = baseline["std"] * effects["std_mult"]

        # Seasonal component for temperature
        if device_type == "temperature":
            day_of_year = timestamp.timetuple().tm_yday
            adjusted_mean += 5 * math.sin(2 * math.pi * day_of_year / 365)

        # Diurnal component for power (peak at noon)
        if device_type == "power":
            adjusted_mean += 20 * math.sin(
                2 * math.pi * timestamp.hour / 24 - math.pi / 2
            )

        value = float(np.random.normal(adjusted_mean, adjusted_std))

        # Anomaly spike
        if np.random.random() < effects["anomaly_rate"]:
            value += abs(float(np.random.normal(0, baseline["std"] * 3)))

        # Clip to physical limits
        value = max(profile["min"], min(profile["max"], value))
        value = round(value, profile["decimals"])

        return value, profile["unit"]

    # ------------------------------------------------------------------
    # Quality flag with state-dependent distribution
    # ------------------------------------------------------------------
    @staticmethod
    def _get_quality_flag(equipment_state: str) -> str:
        """Return a quality flag sampled from the state-dependent distribution."""
        dist = _QUALITY_DISTRIBUTIONS[equipment_state]
        labels = list(dist.keys())
        probs = list(dist.values())
        return str(np.random.choice(labels, p=probs))

    # ------------------------------------------------------------------
    # Telemetry generation
    # ------------------------------------------------------------------
    def generate_telemetry(self) -> pd.DataFrame:
        """Generate IoT telemetry readings in chronological order per device.

        Each device produces readings at semi-random intervals (~30 min to
        ~2 hrs) across the full date range.  The sensor distribution at each
        timestamp is determined by the equipment's health state at that
        moment.
        """
        from tqdm import tqdm

        num_rows = VOLUMES["iot_telemetry"]
        num_devices = len(self.devices)
        readings_per_device = num_rows // num_devices  # ~2500

        range_start = datetime.fromisoformat(DATE_RANGE_START)
        range_end = datetime.fromisoformat(DATE_RANGE_END)

        batch_size = 100_000
        all_dfs: list[pd.DataFrame] = []
        rows: list[dict] = []

        total_generated = 0

        for device_idx in tqdm(range(num_devices), desc="IoT Telemetry (devices)"):
            device = self.devices[device_idx]
            device_type = device["device_type"]
            equipment_id = device["equipment_id"]

            cursor = range_start
            device_readings = 0

            while cursor < range_end and device_readings < readings_per_device:
                # Semi-random interval: average ~1 hr (30 min to 2 hrs)
                interval_minutes = np.random.randint(30, 121)
                cursor = cursor + timedelta(minutes=int(interval_minutes))

                if cursor >= range_end:
                    break

                equipment_state = self._get_equipment_state(equipment_id, cursor)

                measurement_value, measurement_unit = self._generate_reading(
                    device_type, equipment_state, cursor,
                )

                enqueue_delay = timedelta(
                    milliseconds=random.randint(50, 5000)
                )
                enqueued_ts = cursor + enqueue_delay

                quality_flag = self._get_quality_flag(equipment_state)

                raw_payload = json.dumps(
                    {
                        "deviceId": device["device_id"],
                        "type": device_type,
                        "value": measurement_value,
                        "unit": measurement_unit,
                        "quality": quality_flag,
                        "ts": cursor.isoformat(),
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
                    "equipment_id": equipment_id,
                    "equipment_state": equipment_state,
                    "measurement_type": device_type,
                    "measurement_value": measurement_value,
                    "measurement_unit": measurement_unit,
                    "event_timestamp": cursor.isoformat(),
                    "event_enqueued_timestamp": enqueued_ts.isoformat(),
                    "quality_flag": quality_flag,
                    "raw_payload": raw_payload,
                    **meta,
                }
                row["_bronze_row_hash"] = row_hash(row)
                rows.append(row)

                device_readings += 1
                total_generated += 1

                # Flush batch for memory efficiency
                if len(rows) >= batch_size:
                    all_dfs.append(pd.DataFrame(rows))
                    rows = []

        # Flush any remaining rows
        if rows:
            all_dfs.append(pd.DataFrame(rows))

        if all_dfs:
            return pd.concat(all_dfs, ignore_index=True)
        return pd.DataFrame()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def generate_all(self) -> dict[str, pd.DataFrame]:
        """Generate all IoT datasets.

        Returns
        -------
        dict[str, pd.DataFrame]
            ``{"iot_telemetry": DataFrame,
               "equipment_lifecycle_events": DataFrame}``
        """
        return {
            "iot_telemetry": self.generate_telemetry(),
            "equipment_lifecycle_events": self.lifecycle_events_df,
        }
