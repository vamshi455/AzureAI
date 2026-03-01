"""Shared master data and utilities for all generators."""

import hashlib
import uuid
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
from faker import Faker

from config import (
    DATE_RANGE_START, DATE_RANGE_END, RANDOM_SEED,
    SAP_PLANTS, SAP_SALES_ORGS, SAP_DIST_CHANNELS, SAP_DIVISIONS,
    SAP_STORAGE_LOCATIONS, MATERIAL_GROUPS, MATERIAL_TYPES,
    SF_INDUSTRIES, VOLUMES,
)

fake = Faker()
Faker.seed(RANDOM_SEED)

# ============================================================================
# Manufacturing product catalog - realistic industrial products
# ============================================================================
PRODUCT_CATALOG = [
    {"name": "Carbon Steel Coil HR 2.0mm", "group": "001", "type": "ROH", "uom": "KG", "base_price": 0.85},
    {"name": "Stainless Steel Sheet 304 1.5mm", "group": "001", "type": "ROH", "uom": "KG", "base_price": 3.20},
    {"name": "Aluminum Extrusion Profile T6", "group": "001", "type": "HALB", "uom": "M", "base_price": 12.50},
    {"name": "Galvanized Steel Pipe DN50", "group": "001", "type": "ROH", "uom": "M", "base_price": 8.75},
    {"name": "Copper Wire 2.5mm²", "group": "001", "type": "ROH", "uom": "M", "base_price": 1.95},
    {"name": "Deep Groove Ball Bearing 6205", "group": "002", "type": "ERSA", "uom": "EA", "base_price": 8.50},
    {"name": "Tapered Roller Bearing 32010", "group": "002", "type": "ERSA", "uom": "EA", "base_price": 24.00},
    {"name": "Spherical Roller Bearing 22210", "group": "002", "type": "ERSA", "uom": "EA", "base_price": 45.00},
    {"name": "Linear Ball Bushing LM20UU", "group": "002", "type": "ERSA", "uom": "EA", "base_price": 6.80},
    {"name": "Needle Roller Bearing NK20/16", "group": "002", "type": "ERSA", "uom": "EA", "base_price": 3.90},
    {"name": "AC Induction Motor 5.5kW IE3", "group": "003", "type": "FERT", "uom": "EA", "base_price": 580.00},
    {"name": "Servo Motor 1.5kW with Encoder", "group": "003", "type": "FERT", "uom": "EA", "base_price": 1250.00},
    {"name": "DC Brushless Motor 48V 750W", "group": "003", "type": "FERT", "uom": "EA", "base_price": 320.00},
    {"name": "Stepper Motor NEMA 23 2.8A", "group": "003", "type": "FERT", "uom": "EA", "base_price": 85.00},
    {"name": "Gear Motor 0.75kW 1:30 Ratio", "group": "003", "type": "FERT", "uom": "EA", "base_price": 420.00},
    {"name": "Hydraulic Cylinder 63/36-500", "group": "004", "type": "FERT", "uom": "EA", "base_price": 380.00},
    {"name": "Hydraulic Power Unit 15kW", "group": "004", "type": "FERT", "uom": "EA", "base_price": 4500.00},
    {"name": "Hydraulic Hose DN12 350bar", "group": "004", "type": "HIBE", "uom": "M", "base_price": 15.60},
    {"name": "Directional Control Valve 4/3", "group": "004", "type": "ERSA", "uom": "EA", "base_price": 290.00},
    {"name": "Hydraulic Filter Element 10µm", "group": "004", "type": "HIBE", "uom": "EA", "base_price": 42.00},
    {"name": "Pneumatic Cylinder DNC 50-200", "group": "005", "type": "FERT", "uom": "EA", "base_price": 125.00},
    {"name": "Air Preparation Unit FRL 1/2\"", "group": "005", "type": "ERSA", "uom": "EA", "base_price": 95.00},
    {"name": "Solenoid Valve 5/2 Way 24VDC", "group": "005", "type": "ERSA", "uom": "EA", "base_price": 68.00},
    {"name": "PU Tubing 8x5mm Blue", "group": "005", "type": "HIBE", "uom": "M", "base_price": 0.85},
    {"name": "Push-in Fitting Straight 8mm", "group": "005", "type": "HIBE", "uom": "EA", "base_price": 2.40},
    {"name": "Hex Head Bolt M12x50 Grade 8.8", "group": "006", "type": "HIBE", "uom": "EA", "base_price": 0.35},
    {"name": "Socket Head Cap Screw M8x30", "group": "006", "type": "HIBE", "uom": "EA", "base_price": 0.22},
    {"name": "Spring Washer M10 DIN 127", "group": "006", "type": "HIBE", "uom": "EA", "base_price": 0.05},
    {"name": "Hex Nut M16 Grade 10", "group": "006", "type": "HIBE", "uom": "EA", "base_price": 0.18},
    {"name": "Dowel Pin 8x40 Hardened", "group": "006", "type": "HIBE", "uom": "EA", "base_price": 0.45},
    {"name": "O-Ring NBR 25x3.5mm", "group": "007", "type": "HIBE", "uom": "EA", "base_price": 0.30},
    {"name": "Mechanical Seal 35mm Cartridge", "group": "007", "type": "ERSA", "uom": "EA", "base_price": 185.00},
    {"name": "Gasket Sheet Graphite 1.5mm", "group": "007", "type": "ROH", "uom": "M2", "base_price": 45.00},
    {"name": "Oil Seal TC 50x72x10 NBR", "group": "007", "type": "HIBE", "uom": "EA", "base_price": 3.80},
    {"name": "V-Ring Seal VA-55 NBR", "group": "007", "type": "HIBE", "uom": "EA", "base_price": 2.10},
    {"name": "Centrifugal Pump DN80 15kW", "group": "008", "type": "FERT", "uom": "EA", "base_price": 2800.00},
    {"name": "Gate Valve DN100 PN16 CF8M", "group": "008", "type": "FERT", "uom": "EA", "base_price": 420.00},
    {"name": "Ball Valve DN50 PN40 Full Bore", "group": "008", "type": "FERT", "uom": "EA", "base_price": 180.00},
    {"name": "Butterfly Valve DN200 PN10", "group": "008", "type": "FERT", "uom": "EA", "base_price": 350.00},
    {"name": "Diaphragm Pump Air-Op DN25", "group": "008", "type": "FERT", "uom": "EA", "base_price": 950.00},
    {"name": "Pressure Transmitter 0-10bar", "group": "009", "type": "ERSA", "uom": "EA", "base_price": 280.00},
    {"name": "Temperature Sensor PT100 Class A", "group": "009", "type": "ERSA", "uom": "EA", "base_price": 45.00},
    {"name": "Flow Meter Electromagnetic DN50", "group": "009", "type": "FERT", "uom": "EA", "base_price": 1650.00},
    {"name": "Level Transmitter Ultrasonic", "group": "009", "type": "ERSA", "uom": "EA", "base_price": 520.00},
    {"name": "Vibration Sensor ICP 100mV/g", "group": "009", "type": "ERSA", "uom": "EA", "base_price": 380.00},
    {"name": "Cutting Fluid Emulsion 5%", "group": "010", "type": "HIBE", "uom": "L", "base_price": 4.50},
    {"name": "Hydraulic Oil ISO VG46", "group": "010", "type": "HIBE", "uom": "L", "base_price": 3.20},
    {"name": "Rust Preventive Coating WD-40", "group": "010", "type": "HIBE", "uom": "L", "base_price": 12.00},
    {"name": "Industrial Degreaser Concentrate", "group": "010", "type": "HIBE", "uom": "L", "base_price": 8.50},
    {"name": "Lubricating Grease EP2 180kg", "group": "010", "type": "HIBE", "uom": "KG", "base_price": 5.80},
    # --- Additional products (51-100) to reduce variant ratio at 2K materials ---
    {"name": "Tool Steel Round Bar D2", "group": "001", "type": "ROH", "uom": "KG", "base_price": 6.50},
    {"name": "Brass Sheet CuZn37 0.8mm", "group": "001", "type": "ROH", "uom": "KG", "base_price": 9.80},
    {"name": "Titanium Plate Grade 5 3mm", "group": "001", "type": "ROH", "uom": "KG", "base_price": 45.00},
    {"name": "Cast Iron Block GG25", "group": "001", "type": "ROH", "uom": "KG", "base_price": 2.10},
    {"name": "Spring Steel Strip C75S 0.5mm", "group": "001", "type": "ROH", "uom": "KG", "base_price": 4.30},
    {"name": "Angular Contact Bearing 7206B", "group": "002", "type": "ERSA", "uom": "EA", "base_price": 32.00},
    {"name": "Thrust Ball Bearing 51108", "group": "002", "type": "ERSA", "uom": "EA", "base_price": 12.50},
    {"name": "Cam Follower CF12 VBUUR", "group": "002", "type": "ERSA", "uom": "EA", "base_price": 18.90},
    {"name": "Pillow Block Bearing UCP205", "group": "002", "type": "ERSA", "uom": "EA", "base_price": 28.00},
    {"name": "Rod End Bearing SI 16 ES", "group": "002", "type": "ERSA", "uom": "EA", "base_price": 15.60},
    {"name": "Explosion-Proof Motor 7.5kW", "group": "003", "type": "FERT", "uom": "EA", "base_price": 1850.00},
    {"name": "Variable Frequency Drive 15kW", "group": "003", "type": "FERT", "uom": "EA", "base_price": 980.00},
    {"name": "Brake Motor 3kW with Disc Brake", "group": "003", "type": "FERT", "uom": "EA", "base_price": 720.00},
    {"name": "Soft Starter 22kW 3-Phase", "group": "003", "type": "FERT", "uom": "EA", "base_price": 450.00},
    {"name": "Linear Actuator 24V 300mm Stroke", "group": "003", "type": "FERT", "uom": "EA", "base_price": 195.00},
    {"name": "Hydraulic Accumulator 10L Bladder", "group": "004", "type": "FERT", "uom": "EA", "base_price": 680.00},
    {"name": "Proportional Valve 4WRZ10", "group": "004", "type": "ERSA", "uom": "EA", "base_price": 1250.00},
    {"name": "Hydraulic Motor OMR 80", "group": "004", "type": "FERT", "uom": "EA", "base_price": 520.00},
    {"name": "Pressure Relief Valve DBDS6K", "group": "004", "type": "ERSA", "uom": "EA", "base_price": 185.00},
    {"name": "Hydraulic Quick Coupling 1/2\"", "group": "004", "type": "HIBE", "uom": "EA", "base_price": 22.00},
    {"name": "Vacuum Generator Ejector ZH10", "group": "005", "type": "ERSA", "uom": "EA", "base_price": 78.00},
    {"name": "Rotary Actuator DSR-25-180", "group": "005", "type": "FERT", "uom": "EA", "base_price": 310.00},
    {"name": "Pressure Regulator LR-1/4-DB", "group": "005", "type": "ERSA", "uom": "EA", "base_price": 52.00},
    {"name": "Pneumatic Gripper HGP-16", "group": "005", "type": "FERT", "uom": "EA", "base_price": 420.00},
    {"name": "Air Blowgun with Safety Nozzle", "group": "005", "type": "HIBE", "uom": "EA", "base_price": 18.50},
    {"name": "Stud Bolt M20x120 B7/2H", "group": "006", "type": "HIBE", "uom": "EA", "base_price": 2.80},
    {"name": "T-Slot Nut M12 DIN 508", "group": "006", "type": "HIBE", "uom": "EA", "base_price": 1.20},
    {"name": "Clevis Pin 10x50 with Split Pin", "group": "006", "type": "HIBE", "uom": "EA", "base_price": 0.65},
    {"name": "Circlip External DIN 471 25mm", "group": "006", "type": "HIBE", "uom": "EA", "base_price": 0.12},
    {"name": "Blind Rivet 4.8x12 Al/Steel", "group": "006", "type": "HIBE", "uom": "EA", "base_price": 0.03},
    {"name": "Lip Seal BABSL 40x62x7 FKM", "group": "007", "type": "HIBE", "uom": "EA", "base_price": 8.50},
    {"name": "Spiral Wound Gasket DN80 PN16", "group": "007", "type": "HIBE", "uom": "EA", "base_price": 24.00},
    {"name": "PTFE Packing Set 16x16mm", "group": "007", "type": "HIBE", "uom": "M", "base_price": 32.00},
    {"name": "Hydraulic Piston Seal 63x53x6", "group": "007", "type": "HIBE", "uom": "EA", "base_price": 14.50},
    {"name": "Expansion Joint Rubber DN100", "group": "007", "type": "FERT", "uom": "EA", "base_price": 165.00},
    {"name": "Screw Pump Progressive Cavity", "group": "008", "type": "FERT", "uom": "EA", "base_price": 3200.00},
    {"name": "Check Valve Swing DN80 PN16", "group": "008", "type": "FERT", "uom": "EA", "base_price": 280.00},
    {"name": "Control Valve Globe DN50 PN40", "group": "008", "type": "FERT", "uom": "EA", "base_price": 1450.00},
    {"name": "Y-Strainer DN100 PN16 SS304", "group": "008", "type": "FERT", "uom": "EA", "base_price": 220.00},
    {"name": "Pressure Reducing Valve DN25", "group": "008", "type": "FERT", "uom": "EA", "base_price": 380.00},
    {"name": "Proximity Sensor Inductive M18", "group": "009", "type": "ERSA", "uom": "EA", "base_price": 65.00},
    {"name": "Encoder Incremental 1024 PPR", "group": "009", "type": "ERSA", "uom": "EA", "base_price": 210.00},
    {"name": "Thermocouple Type K 300mm", "group": "009", "type": "ERSA", "uom": "EA", "base_price": 28.00},
    {"name": "Load Cell 500kg S-Type", "group": "009", "type": "ERSA", "uom": "EA", "base_price": 340.00},
    {"name": "pH Sensor Industrial Inline", "group": "009", "type": "ERSA", "uom": "EA", "base_price": 480.00},
    {"name": "Thread Cutting Oil Neat", "group": "010", "type": "HIBE", "uom": "L", "base_price": 15.00},
    {"name": "Anti-Seize Compound Nickel", "group": "010", "type": "HIBE", "uom": "KG", "base_price": 42.00},
    {"name": "Corrosion Inhibitor VCI Paper", "group": "010", "type": "HIBE", "uom": "M2", "base_price": 1.80},
    {"name": "Penetrating Oil Spray 500ml", "group": "010", "type": "HIBE", "uom": "EA", "base_price": 8.90},
    {"name": "Compressor Oil PAO 100", "group": "010", "type": "HIBE", "uom": "L", "base_price": 12.50},
]


class SharedMasterData:
    """Generates and holds shared master data referenced by all generators."""

    def __init__(self):
        self.customers: list[dict] = []
        self.materials: list[dict] = []
        self._customer_sap_to_sf: dict[str, str] = {}

    def generate(self):
        """Generate all shared master data."""
        self._generate_materials()
        self._generate_customers()
        return self

    def _generate_materials(self):
        """Generate material master data (shared between SAP MARA and SF Products)."""
        num_materials = VOLUMES["mara"]
        # Use all 50 catalog items, then generate more with variations
        self.materials = []
        for i in range(num_materials):
            idx = i % len(PRODUCT_CATALOG)
            base = PRODUCT_CATALOG[idx]
            variant = i // len(PRODUCT_CATALOG)
            matnr = f"{(i + 1):010d}"
            name = base["name"] if variant == 0 else f"{base['name']} V{variant}"
            price_mult = 1.0 + (fake.random.random() * 0.4 - 0.2)  # ±20%
            self.materials.append({
                "matnr": matnr,
                "name": name,
                "group": base["group"],
                "group_name": MATERIAL_GROUPS[base["group"]],
                "type": base["type"] if variant == 0 else fake.random_element(MATERIAL_TYPES),
                "uom": base["uom"],
                "base_price": round(base["base_price"] * price_mult, 2),
                "weight": round(fake.pyfloat(min_value=0.01, max_value=500.0), 2),
            })

    def _generate_customers(self):
        """Generate customer master data (shared between SAP KNA1 and SF Accounts)."""
        num_customers = VOLUMES["kna1"]
        self.customers = []
        for i in range(num_customers):
            kunnr = f"{(i + 1):010d}"
            sf_id = str(uuid.uuid4()).replace("-", "")[:18]
            self._customer_sap_to_sf[kunnr] = sf_id

            industry = fake.random_element(SF_INDUSTRIES)
            company = fake.company()
            self.customers.append({
                "kunnr": kunnr,
                "sf_account_id": sf_id,
                "name": company,
                "street": fake.street_address(),
                "city": fake.city(),
                "state": fake.state_abbr(),
                "postal_code": fake.zipcode(),
                "country": fake.random_element(["US", "US", "US", "CA", "GB", "DE", "JP"]),
                "phone": fake.phone_number(),
                "email": fake.company_email(),
                "industry": industry,
                "industry_code": str(SF_INDUSTRIES.index(industry) + 1),
                "revenue": round(fake.pyfloat(min_value=100_000, max_value=50_000_000), 2),
                "employees": fake.random_int(min=10, max=10000),
                "sales_org": fake.random_element(SAP_SALES_ORGS),
                "dist_channel": fake.random_element(SAP_DIST_CHANNELS),
                "division": fake.random_element(SAP_DIVISIONS),
                "created_date": fake.date_between(start_date=date(2019, 1, 1), end_date=date.fromisoformat(DATE_RANGE_START)),
            })

    def get_sf_account_id(self, kunnr: str) -> str:
        return self._customer_sap_to_sf.get(kunnr, "")


def bronze_metadata(source_system: str, source_table: str, load_type: str = "full") -> dict[str, Any]:
    """Generate bronze metadata columns matching the existing schema."""
    return {
        "_bronze_ingestion_timestamp": datetime.utcnow().isoformat(),
        "_bronze_batch_id": str(uuid.uuid4()),
        "_bronze_pipeline_run_id": f"synthetic-{str(uuid.uuid4())[:8]}",
        "_bronze_source_system": source_system,
        "_bronze_source_table": source_table,
        "_bronze_load_type": load_type,
        "_bronze_file_path": f"synthetic/{source_table}/data.parquet",
    }


def row_hash(row: dict, exclude_prefixes: tuple = ("_bronze_",)) -> str:
    """Compute SHA-256 hash of source columns (excluding metadata)."""
    source_cols = {k: str(v) for k, v in row.items() if not any(k.startswith(p) for p in exclude_prefixes)}
    hash_input = "|".join(f"{k}={v}" for k, v in sorted(source_cols.items()))
    return hashlib.sha256(hash_input.encode()).hexdigest()


def random_sap_date(start: str = DATE_RANGE_START, end: str = DATE_RANGE_END) -> str:
    """Generate a random date in SAP format YYYYMMDD."""
    d = fake.date_between(start_date=date.fromisoformat(start), end_date=date.fromisoformat(end))
    return d.strftime("%Y%m%d")


def random_sap_time() -> str:
    """Generate a random time in SAP format HHMMSS."""
    return fake.time(pattern="%H%M%S")
