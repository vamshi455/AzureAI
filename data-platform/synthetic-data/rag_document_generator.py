"""Generate text documents for the RAG indexing pipeline.

Produces JSON, Markdown, and CSV files compatible with the existing RAG
indexing pipeline (``ai/rag/indexing/index_product_catalog.py``), which
expects ``.json``, ``.md``, and ``.csv`` files with metadata such as
``material_number``, ``product_name``, and ``category``.
"""

from __future__ import annotations

import csv
import json
import logging
import textwrap
from pathlib import Path
from typing import Any

from generators.base import SharedMasterData

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reusable specification templates keyed by material group code
# ---------------------------------------------------------------------------
_SPEC_TEMPLATES: dict[str, dict[str, Any]] = {
    "001": {  # Steel & Metal Products
        "material_grade": ["A36", "SS304", "SS316L", "6061-T6", "C45"],
        "surface_finish": ["Hot-rolled", "Cold-rolled", "Galvanized", "Brushed", "Polished"],
        "operating_temp_range": "-40 to 400 °C",
        "certifications": ["ISO 9001", "EN 10204 3.1", "ASTM A36", "RoHS"],
    },
    "002": {  # Bearings & Bushings
        "material_grade": ["Chrome Steel GCr15", "Stainless 440C", "Ceramic Si3N4"],
        "lubrication": ["Grease-packed", "Oil-lubricated", "Self-lubricating"],
        "operating_temp_range": "-30 to 120 °C",
        "certifications": ["ISO 9001", "ISO 492", "ABEC-5"],
    },
    "003": {  # Electric Motors
        "efficiency_class": ["IE1", "IE2", "IE3", "IE4"],
        "voltage_options": ["230V", "400V", "480V", "690V"],
        "protection_class": ["IP55", "IP65"],
        "certifications": ["IEC 60034", "UL", "CE", "CSA"],
    },
    "004": {  # Hydraulic Components
        "max_pressure_bar": [160, 250, 315, 350],
        "fluid_compatibility": ["Mineral oil", "HFC", "HFD-R", "Biodegradable"],
        "operating_temp_range": "-20 to 80 °C",
        "certifications": ["ISO 6020", "ISO 4401", "ATEX (optional)"],
    },
    "005": {  # Pneumatic Components
        "max_pressure_bar": [8, 10, 12, 16],
        "port_size": ["G1/8", "G1/4", "G3/8", "G1/2"],
        "operating_temp_range": "-10 to 60 °C",
        "certifications": ["ISO 15552", "ISO 6432", "CE"],
    },
    "006": {  # Fasteners & Hardware
        "material_grade": ["Grade 8.8", "Grade 10.9", "Grade 12.9", "A2-70", "A4-80"],
        "surface_treatment": ["Zinc-plated", "Hot-dip galvanized", "Dacromet", "Plain"],
        "certifications": ["ISO 898-1", "DIN 931", "DIN 912"],
    },
    "007": {  # Seals & Gaskets
        "material_options": ["NBR", "FKM/Viton", "EPDM", "PTFE", "Graphite"],
        "operating_temp_range": "-40 to 200 °C",
        "media_compatibility": ["Water", "Oil", "Steam", "Chemicals"],
        "certifications": ["FDA", "KTW", "WRAS", "ACS"],
    },
    "008": {  # Pumps & Valves
        "body_material": ["Cast Iron GG25", "Ductile Iron GGG40", "Stainless CF8M"],
        "connection_type": ["Flanged PN10/16", "Wafer", "Threaded BSP"],
        "certifications": ["ISO 5199", "API 610", "PED 2014/68/EU"],
    },
    "009": {  # Sensors & Instrumentation
        "accuracy_class": ["0.1%", "0.25%", "0.5%"],
        "output_signal": ["4-20 mA", "0-10 V", "HART", "Modbus RTU"],
        "protection_class": ["IP65", "IP67", "IP68"],
        "certifications": ["IECEx", "ATEX", "SIL 2", "CE"],
    },
    "010": {  # Industrial Chemicals
        "viscosity_options": ["ISO VG32", "ISO VG46", "ISO VG68"],
        "flash_point": "> 200 °C",
        "shelf_life": "24 months",
        "certifications": ["REACH", "SDS compliant", "ISO 12924"],
    },
}

# Application examples per group
_APPLICATIONS: dict[str, list[str]] = {
    "001": [
        "Structural fabrication",
        "Automotive body panels",
        "Pressure vessel manufacturing",
        "General mechanical engineering",
        "Pipe and tube manufacturing",
    ],
    "002": [
        "Electric motor support",
        "Conveyor systems",
        "Gearbox assemblies",
        "Pump and compressor shafts",
        "CNC spindle assemblies",
    ],
    "003": [
        "Conveyor belt drives",
        "Pump and fan drives",
        "CNC machine tool spindles",
        "Packaging machinery",
        "Material handling systems",
    ],
    "004": [
        "Press brakes and stamping presses",
        "Injection molding machines",
        "Mobile hydraulic equipment",
        "Industrial lifting systems",
        "Steel mill roll adjustment",
    ],
    "005": [
        "Pick-and-place automation",
        "Clamping and gripping",
        "Assembly line actuators",
        "Packaging machinery",
        "Labeling and sorting systems",
    ],
    "006": [
        "Structural steel connections",
        "Machine tool assembly",
        "Automotive chassis fastening",
        "Flange bolting",
        "General mechanical assembly",
    ],
    "007": [
        "Pump shaft sealing",
        "Pipe flange gaskets",
        "Hydraulic cylinder sealing",
        "Food-grade process sealing",
        "Chemical processing equipment",
    ],
    "008": [
        "Water treatment plants",
        "Chemical dosing systems",
        "HVAC circulation systems",
        "Process fluid transfer",
        "Fire protection systems",
    ],
    "009": [
        "Process control monitoring",
        "Predictive maintenance systems",
        "Environmental monitoring",
        "Quality assurance testing",
        "SCADA / DCS integration",
    ],
    "010": [
        "CNC machining operations",
        "Hydraulic system maintenance",
        "Bearing and chain lubrication",
        "Corrosion prevention",
        "Parts cleaning and degreasing",
    ],
}

# Compliance standards per group
_COMPLIANCE: dict[str, list[str]] = {
    "001": ["ISO 9001:2015", "EN 10204 Type 3.1", "RoHS Directive 2011/65/EU"],
    "002": ["ISO 9001:2015", "ISO 492:2014", "REACH Regulation (EC) 1907/2006"],
    "003": ["IEC 60034", "EU Regulation 2019/1781 (Ecodesign)", "UL 60034", "CE"],
    "004": ["ISO 4413:2010", "Machinery Directive 2006/42/EC", "PED 2014/68/EU"],
    "005": ["ISO 4414:2010", "Machinery Directive 2006/42/EC", "CE Marking"],
    "006": ["ISO 898-1:2013", "EN 14399", "ASTM F568M"],
    "007": ["FDA 21 CFR 177", "EC 1935/2004 (Food Contact)", "TA Luft"],
    "008": ["PED 2014/68/EU", "API 610 / API 600", "ATEX 2014/34/EU"],
    "009": ["IEC 61508 (SIL)", "ATEX 2014/34/EU", "EMC Directive 2014/30/EU"],
    "010": ["REACH (EC) 1907/2006", "CLP Regulation (EC) 1272/2008", "ISO 12924"],
}


class RAGDocumentGenerator:
    """Generate RAG-compatible documents from shared master data.

    Output files are structured for consumption by
    ``ai/rag/indexing/index_product_catalog.py``.

    Parameters
    ----------
    master : SharedMasterData
        Shared master data instance (must have been generated already).
    output_dir : Path
        Root directory where generated RAG documents will be saved.
    """

    def __init__(self, master: SharedMasterData, output_dir: Path) -> None:
        self.master = master
        self.output_dir = Path(output_dir)

    # ------------------------------------------------------------------
    # Product catalog (JSON per material)
    # ------------------------------------------------------------------
    def generate_product_catalogs(self) -> int:
        """Create a JSON file per material in ``output_dir/product-catalog/``.

        Each JSON file contains:
        - ``material_number``, ``product_name``, ``category``
        - ``description`` with detailed technical specs, applications, and certifications
        - ``specifications`` dict (dimensions, weight, material_grade, operating_temp, etc.)
        - ``applications`` list
        - ``compliance`` list

        Returns
        -------
        int
            Number of JSON files created.
        """
        catalog_dir = self.output_dir / "product-catalog"
        catalog_dir.mkdir(parents=True, exist_ok=True)

        count = 0
        for mat in self.master.materials:
            group = mat["group"]
            spec_template = _SPEC_TEMPLATES.get(group, _SPEC_TEMPLATES["006"])
            applications = _APPLICATIONS.get(group, _APPLICATIONS["006"])
            compliance = _COMPLIANCE.get(group, _COMPLIANCE["006"])

            # Build a specifications dict
            specs: dict[str, Any] = {
                "weight_kg": mat["weight"],
                "unit_of_measure": mat["uom"],
                "base_price_usd": mat["base_price"],
            }
            for key, val in spec_template.items():
                if key == "certifications":
                    continue  # handled separately as compliance
                if isinstance(val, list):
                    specs[key] = val[count % len(val)]
                else:
                    specs[key] = val

            # Build a rich description
            description = (
                f"{mat['name']} is a high-quality {mat['group_name'].lower()} product "
                f"(SAP material type: {mat['type']}). "
                f"This product is widely used in {', '.join(applications[:3])} applications. "
                f"It meets industry standards including {', '.join(compliance[:2])}. "
                f"Supplied in units of {mat['uom']} with a standard lead time of "
                f"{(count % 10) + 3} business days."
            )

            document: dict[str, Any] = {
                "material_number": mat["matnr"],
                "product_name": mat["name"],
                "category": mat["group_name"],
                "description": description,
                "specifications": specs,
                "applications": applications,
                "compliance": compliance,
            }

            file_name = f"material_{mat['matnr']}.json"
            file_path = catalog_dir / file_name
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(document, f, indent=2, ensure_ascii=False)

            count += 1

        logger.info("Generated %d product catalog JSON files.", count)
        return count

    # ------------------------------------------------------------------
    # Customer profiles (Markdown)
    # ------------------------------------------------------------------
    def generate_customer_profiles(self) -> int:
        """Create a Markdown file per top-200 customer (by revenue).

        Each file contains: company overview, industry, location, key stats,
        order history summary, and preferred products.

        Saves to ``output_dir/customer-profiles/``.

        Returns
        -------
        int
            Number of Markdown files created.
        """
        profiles_dir = self.output_dir / "customer-profiles"
        profiles_dir.mkdir(parents=True, exist_ok=True)

        # Sort customers by revenue descending and take top 200
        sorted_customers = sorted(
            self.master.customers,
            key=lambda c: c["revenue"],
            reverse=True,
        )
        top_customers = sorted_customers[:200]

        count = 0
        for cust in top_customers:
            # Pick a few "preferred products" from the material catalog
            num_preferred = min(5, len(self.master.materials))
            preferred_indices = [
                (hash(cust["kunnr"]) + i) % len(self.master.materials)
                for i in range(num_preferred)
            ]
            preferred_products = [
                self.master.materials[idx]["name"]
                for idx in preferred_indices
            ]

            # Estimate order history stats from revenue
            avg_order_value = max(500, cust["revenue"] / max(1, cust["employees"] // 5))
            estimated_orders = max(1, int(cust["revenue"] / avg_order_value))

            content = textwrap.dedent(f"""\
                # {cust['name']}

                ## Company Overview

                **{cust['name']}** is a {cust['industry'].lower()} company
                headquartered in {cust['city']}, {cust['state']}, {cust['country']}.
                The company employs approximately {cust['employees']:,} people and
                generates annual revenue of ${cust['revenue']:,.2f}.

                ## Key Information

                | Field | Value |
                |-------|-------|
                | SAP Customer Number (KUNNR) | `{cust['kunnr']}` |
                | Salesforce Account ID | `{cust['sf_account_id']}` |
                | Industry | {cust['industry']} |
                | City | {cust['city']} |
                | State / Region | {cust['state']} |
                | Country | {cust['country']} |
                | Postal Code | {cust['postal_code']} |
                | Phone | {cust['phone']} |
                | Email | {cust['email']} |
                | Employees | {cust['employees']:,} |
                | Annual Revenue | ${cust['revenue']:,.2f} |
                | SAP Sales Org | {cust['sales_org']} |
                | SAP Distribution Channel | {cust['dist_channel']} |
                | SAP Division | {cust['division']} |
                | Customer Since | {cust['created_date']} |

                ## Order History Summary

                - **Estimated total orders:** {estimated_orders:,}
                - **Average order value:** ${avg_order_value:,.2f}
                - **Total lifetime revenue:** ${cust['revenue']:,.2f}

                ## Preferred Products

            """)

            for product in preferred_products:
                content += f"- {product}\n"

            file_name = f"customer_{cust['kunnr']}.md"
            file_path = profiles_dir / file_name
            file_path.write_text(content, encoding="utf-8")
            count += 1

        logger.info("Generated %d customer profile Markdown files.", count)
        return count

    # ------------------------------------------------------------------
    # Catalog master CSV (all materials)
    # ------------------------------------------------------------------
    def generate_product_catalog_csv(self) -> int:
        """Create a single CSV with all materials for bulk RAG indexing.

        Saves to ``output_dir/product-catalog/catalog_master.csv``.

        Returns
        -------
        int
            Number of rows written (excluding header).
        """
        catalog_dir = self.output_dir / "product-catalog"
        catalog_dir.mkdir(parents=True, exist_ok=True)

        csv_path = catalog_dir / "catalog_master.csv"
        fieldnames = [
            "material_number",
            "product_name",
            "category",
            "material_type",
            "unit_of_measure",
            "base_price_usd",
            "weight_kg",
            "description",
        ]

        count = 0
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for mat in self.master.materials:
                group = mat["group"]
                applications = _APPLICATIONS.get(group, _APPLICATIONS["006"])

                short_description = (
                    f"{mat['name']} - {mat['group_name']}. "
                    f"Applications: {', '.join(applications[:3])}."
                )

                writer.writerow(
                    {
                        "material_number": mat["matnr"],
                        "product_name": mat["name"],
                        "category": mat["group_name"],
                        "material_type": mat["type"],
                        "unit_of_measure": mat["uom"],
                        "base_price_usd": mat["base_price"],
                        "weight_kg": mat["weight"],
                        "description": short_description,
                    }
                )
                count += 1

        logger.info("Generated catalog_master.csv with %d rows.", count)
        return count

    # ------------------------------------------------------------------
    # Aggregate generator
    # ------------------------------------------------------------------
    def generate_all(self) -> int:
        """Run all RAG document generators.

        Note: Customer profiles are now generated by ``chunk_for_rag.py``
        which produces richer Customer 360 documents from actual bronze data.

        Returns
        -------
        int
            Total count of files generated (JSON + 1 CSV).
        """
        json_count = self.generate_product_catalogs()
        csv_count = 1 if self.generate_product_catalog_csv() > 0 else 0

        total = json_count + csv_count
        logger.info(
            "RAG document generation complete: %d total files "
            "(%d JSON, %d CSV). Customer 360 profiles via chunk_for_rag.py.",
            total,
            json_count,
            csv_count,
        )
        return total
