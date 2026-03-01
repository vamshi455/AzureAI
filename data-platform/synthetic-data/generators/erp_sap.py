"""SAP SD (Sales & Distribution) synthetic data generator.

Generates realistic data for 9 SAP SD tables used in a
Manufacturing + Sales data platform:

    KNA1  - Customer Master
    MARA  - Material Master
    MARD  - Plant Stock / Inventory
    VBAK  - Sales Order Headers
    VBAP  - Sales Order Items
    VBRK  - Billing Document Headers
    VBRP  - Billing Document Items
    LIKP  - Delivery Headers
    LIPS  - Delivery Items
"""

import random

import pandas as pd
from tqdm import tqdm

from generators.base import (
    SharedMasterData,
    bronze_metadata,
    row_hash,
    random_sap_date,
    random_sap_time,
    fake,
)
from config import (
    VOLUMES,
    SAP_PLANTS,
    SAP_SALES_ORGS,
    SAP_DIST_CHANNELS,
    SAP_DIVISIONS,
    SAP_STORAGE_LOCATIONS,
    SAP_SHIPPING_POINTS,
    SAP_DOC_TYPES,
    SAP_CURRENCIES,
    DATE_RANGE_START,
    DATE_RANGE_END,
)


class SAPSDGenerator:
    """Generate synthetic data for SAP Sales & Distribution tables.

    Each ``generate_*`` method returns a :class:`pandas.DataFrame` whose
    columns mirror the real SAP table structure.  All *source* columns
    are stored as Python ``str`` values so that they match a bronze-layer
    schema where every column is STRING.

    Bronze metadata columns (``_bronze_*``) and a row-level hash
    (``_bronze_row_hash``) are appended to every row.
    """

    # Document-number starting points (10-digit SAP document numbers)
    _VBAK_START = 100_001          # Sales orders:     0000100001 ...
    _VBRK_START = 90_100_001       # Billing docs:     0090100001 ...
    _LIKP_START = 80_100_001       # Delivery docs:    0080100001 ...

    def __init__(self, master: SharedMasterData) -> None:
        self.master = master

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _add_bronze(rows: list[dict], source_table: str) -> list[dict]:
        """Append bronze metadata and row hash to every row in *rows*."""
        meta = bronze_metadata(source_system="SAP", source_table=source_table)
        for row in rows:
            row.update(meta)
            row["_bronze_row_hash"] = row_hash(row)
        return rows

    @staticmethod
    def _to_str_df(rows: list[dict], source_cols: list[str]) -> pd.DataFrame:
        """Build a DataFrame, casting all *source_cols* to ``str``."""
        df = pd.DataFrame(rows)
        for col in source_cols:
            if col in df.columns:
                df[col] = df[col].astype(str)
        return df

    # ------------------------------------------------------------------
    # 1. KNA1 - Customer Master
    # ------------------------------------------------------------------

    def generate_kna1(self) -> pd.DataFrame:
        """Customer Master -- one row per customer from shared master data."""
        rows: list[dict] = []
        for c in tqdm(self.master.customers, desc="KNA1 - Customer Master"):
            created = c["created_date"]
            erdat = (
                created.strftime("%Y%m%d")
                if hasattr(created, "strftime")
                else str(created).replace("-", "")
            )
            row = {
                "KUNNR": c["kunnr"],
                "NAME1": c["name"],
                "NAME2": "",
                "SORTL": c["name"][:10].upper(),
                "STRAS": c["street"],
                "ORT01": c["city"],
                "REGIO": c["state"],
                "PSTLZ": c["postal_code"],
                "LAND1": c["country"],
                "TELF1": c["phone"],
                "SMTP_ADDR": c["email"],
                "BRSCH": c["industry_code"],
                "KTOKD": fake.random_element(["0001", "0002", "0003"]),
                "ERDAT": erdat,
                "AEDAT": random_sap_date(),
            }
            rows.append(row)

        source_cols = [
            "KUNNR", "NAME1", "NAME2", "SORTL", "STRAS", "ORT01",
            "REGIO", "PSTLZ", "LAND1", "TELF1", "SMTP_ADDR",
            "BRSCH", "KTOKD", "ERDAT", "AEDAT",
        ]
        self._add_bronze(rows, "KNA1")
        return self._to_str_df(rows, source_cols)

    # ------------------------------------------------------------------
    # 2. MARA - Material Master
    # ------------------------------------------------------------------

    def generate_mara(self) -> pd.DataFrame:
        """Material Master -- one row per material from shared master data."""
        rows: list[dict] = []
        for m in tqdm(self.master.materials, desc="MARA - Material Master"):
            row = {
                "MATNR": m["matnr"],
                "MAKTX": m["name"],
                "MTART": m["type"],
                "MATKL": m["group"],
                "MEINS": m["uom"],
                "BRGEW": str(m["weight"]),
                "GEWEI": "KG",
                "ERDAT": random_sap_date(
                    start=DATE_RANGE_START, end=DATE_RANGE_END
                ),
                "AEDAT": random_sap_date(),
            }
            rows.append(row)

        source_cols = [
            "MATNR", "MAKTX", "MTART", "MATKL", "MEINS",
            "BRGEW", "GEWEI", "ERDAT", "AEDAT",
        ]
        self._add_bronze(rows, "MARA")
        return self._to_str_df(rows, source_cols)

    # ------------------------------------------------------------------
    # 3. MARD - Plant Stock / Inventory
    # ------------------------------------------------------------------

    def generate_mard(self) -> pd.DataFrame:
        """Plant stock -- 1-3 rows per material across plants and storage locations."""
        rows: list[dict] = []
        for m in tqdm(self.master.materials, desc="MARD - Plant Stock"):
            num_entries = fake.random_int(min=1, max=3)
            plants = fake.random_elements(SAP_PLANTS, length=num_entries, unique=True)
            for plant in plants:
                row = {
                    "MATNR": m["matnr"],
                    "WERKS": plant,
                    "LGORT": fake.random_element(SAP_STORAGE_LOCATIONS),
                    "LABST": str(round(fake.pyfloat(min_value=0, max_value=5000), 3)),
                    "UMLME": str(round(fake.pyfloat(min_value=0, max_value=200), 3)),
                    "INSME": str(round(fake.pyfloat(min_value=0, max_value=100), 3)),
                    "EINME": str(round(fake.pyfloat(min_value=0, max_value=50), 3)),
                    "SPEME": str(round(fake.pyfloat(min_value=0, max_value=50), 3)),
                    "RETME": str(round(fake.pyfloat(min_value=0, max_value=30), 3)),
                    "AEDAT": random_sap_date(),
                }
                rows.append(row)

        source_cols = [
            "MATNR", "WERKS", "LGORT", "LABST", "UMLME",
            "INSME", "EINME", "SPEME", "RETME", "AEDAT",
        ]
        self._add_bronze(rows, "MARD")
        return self._to_str_df(rows, source_cols)

    # ------------------------------------------------------------------
    # 4. VBAK - Sales Order Headers
    # ------------------------------------------------------------------

    def generate_vbak(self) -> pd.DataFrame:
        """Sales order headers -- ``VOLUMES['vbak']`` orders."""
        num_orders = VOLUMES["vbak"]
        rows: list[dict] = []
        for i in tqdm(range(num_orders), desc="VBAK - Sales Order Headers"):
            vbeln = f"{self._VBAK_START + i:010d}"
            customer = fake.random_element(self.master.customers)
            erdat = random_sap_date()
            row = {
                "VBELN": vbeln,
                "ERDAT": erdat,
                "ERZET": random_sap_time(),
                "ERNAM": fake.user_name()[:12].upper(),
                "AUART": fake.random_element(SAP_DOC_TYPES),
                "VKORG": fake.random_element(SAP_SALES_ORGS),
                "VTWEG": fake.random_element(SAP_DIST_CHANNELS),
                "SPART": fake.random_element(SAP_DIVISIONS),
                "KUNNR": customer["kunnr"],
                "BSTNK": f"PO-{fake.bothify('??###-####').upper()}",
                "BSTDK": erdat,
                "NETWR": "0.00",
                "WAERK": fake.random_element(SAP_CURRENCIES),
                "VDATU": random_sap_date(start=erdat[:4] + "-" + erdat[4:6] + "-" + erdat[6:],
                                          end=DATE_RANGE_END),
                "LIFSK": "",
                "FAKSK": "",
                "ABSTK": fake.random_element(["", "", "", "", "A"]),
                "AEDAT": random_sap_date(),
            }
            rows.append(row)

        source_cols = [
            "VBELN", "ERDAT", "ERZET", "ERNAM", "AUART", "VKORG",
            "VTWEG", "SPART", "KUNNR", "BSTNK", "BSTDK", "NETWR",
            "WAERK", "VDATU", "LIFSK", "FAKSK", "ABSTK", "AEDAT",
        ]
        self._add_bronze(rows, "VBAK")
        return self._to_str_df(rows, source_cols)

    # ------------------------------------------------------------------
    # 5. VBAP - Sales Order Items
    # ------------------------------------------------------------------

    def generate_vbap(self, vbak_df: pd.DataFrame) -> pd.DataFrame:
        """Sales order items -- 1-5 line items per header.

        After generation the *vbak_df* ``NETWR`` column is updated
        in-place to reflect the sum of its line items.
        """
        rows: list[dict] = []
        order_totals: dict[str, float] = {}

        for _, header in tqdm(
            vbak_df.iterrows(), total=len(vbak_df), desc="VBAP - Sales Order Items"
        ):
            vbeln = str(header["VBELN"])
            waerk = str(header["WAERK"])
            num_items = fake.random_int(min=1, max=5)
            order_net = 0.0

            for seq in range(1, num_items + 1):
                material = fake.random_element(self.master.materials)
                qty = fake.random_int(min=1, max=500)
                price_factor = round(random.uniform(0.8, 1.2), 4)
                netwr = round(qty * material["base_price"] * price_factor, 2)
                order_net += netwr

                # ~5% rejection reason
                abgru = (
                    fake.random_element(["01", "02", "03", "04", "05"])
                    if fake.pyfloat(min_value=0, max_value=1) < 0.05
                    else ""
                )

                row = {
                    "VBELN": vbeln,
                    "POSNR": f"{seq * 10:06d}",
                    "MATNR": material["matnr"],
                    "MATKL": material["group"],
                    "ARKTX": material["name"],
                    "KWMENG": str(qty),
                    "VRKME": material["uom"],
                    "NETWR": str(netwr),
                    "WAERK": waerk,
                    "WERKS": fake.random_element(SAP_PLANTS),
                    "LGORT": fake.random_element(SAP_STORAGE_LOCATIONS),
                    "ABGRU": abgru,
                    "AEDAT": random_sap_date(),
                }
                rows.append(row)

            order_totals[vbeln] = round(order_net, 2)

        # Update VBAK NETWR to sum of items
        vbak_df["NETWR"] = vbak_df["VBELN"].map(
            lambda v: str(order_totals.get(str(v), 0.0))
        )

        source_cols = [
            "VBELN", "POSNR", "MATNR", "MATKL", "ARKTX",
            "KWMENG", "VRKME", "NETWR", "WAERK", "WERKS",
            "LGORT", "ABGRU", "AEDAT",
        ]
        self._add_bronze(rows, "VBAP")
        return self._to_str_df(rows, source_cols)

    # ------------------------------------------------------------------
    # 6. VBRK - Billing Document Headers
    # ------------------------------------------------------------------

    def generate_vbrk(self, vbak_df: pd.DataFrame) -> pd.DataFrame:
        """Billing headers -- ~80 % of sales orders get billed."""
        billed_orders = vbak_df.sample(frac=0.80, random_state=42)
        rows: list[dict] = []

        for idx, (_, order) in tqdm(
            enumerate(billed_orders.iterrows()),
            total=len(billed_orders),
            desc="VBRK - Billing Headers",
        ):
            vbeln_bill = f"{self._VBRK_START + idx:010d}"
            erdat = str(order["ERDAT"])
            # Billing date is on or after the order date
            fkdat = random_sap_date(
                start=erdat[:4] + "-" + erdat[4:6] + "-" + erdat[6:],
                end=DATE_RANGE_END,
            )
            row = {
                "VBELN": vbeln_bill,
                "FKART": fake.random_element(["F2", "L2", "RE", "S1", "G2"]),
                "FKDAT": fkdat,
                "KUNAG": str(order["KUNNR"]),
                "NETWR": str(order["NETWR"]),
                "WAERK": str(order["WAERK"]),
                "BUKRS": fake.random_element(["1000", "2000", "3000"]),
                "VBELN_VBA": str(order["VBELN"]),
            }
            rows.append(row)

        source_cols = [
            "VBELN", "FKART", "FKDAT", "KUNAG", "NETWR",
            "WAERK", "BUKRS", "VBELN_VBA",
        ]
        self._add_bronze(rows, "VBRK")
        return self._to_str_df(rows, source_cols)

    # ------------------------------------------------------------------
    # 7. VBRP - Billing Document Items
    # ------------------------------------------------------------------

    def generate_vbrp(
        self, vbrk_df: pd.DataFrame, vbap_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Billing items -- copies line items from referenced sales orders."""
        # Build lookup using groupby (O(1) per order vs O(n) iterrows at 300K rows)
        vbap_grouped = {
            str(vbeln): group.to_dict("records")
            for vbeln, group in vbap_df.groupby("VBELN")
        }

        rows: list[dict] = []
        for _, bill in tqdm(
            vbrk_df.iterrows(), total=len(vbrk_df), desc="VBRP - Billing Items"
        ):
            vbeln_bill = str(bill["VBELN"])
            vbeln_order = str(bill["VBELN_VBA"])
            items = vbap_grouped.get(vbeln_order, [])

            for seq, item in enumerate(items, start=1):
                row = {
                    "VBELN": vbeln_bill,
                    "POSNR": f"{seq * 10:06d}",
                    "MATNR": str(item["MATNR"]),
                    "ARKTX": str(item["ARKTX"]),
                    "FKIMG": str(item["KWMENG"]),
                    "VRKME": str(item["VRKME"]),
                    "NETWR": str(item["NETWR"]),
                    "VBELN_VBA": vbeln_order,
                    "POSNR_VBA": str(item["POSNR"]),
                }
                rows.append(row)

        source_cols = [
            "VBELN", "POSNR", "MATNR", "ARKTX", "FKIMG",
            "VRKME", "NETWR", "VBELN_VBA", "POSNR_VBA",
        ]
        self._add_bronze(rows, "VBRP")
        return self._to_str_df(rows, source_cols)

    # ------------------------------------------------------------------
    # 8. LIKP - Delivery Headers
    # ------------------------------------------------------------------

    def generate_likp(self, vbak_df: pd.DataFrame) -> pd.DataFrame:
        """Delivery headers -- ~85 % of sales orders get delivered."""
        delivered_orders = vbak_df.sample(frac=0.85, random_state=43)
        rows: list[dict] = []

        for idx, (_, order) in tqdm(
            enumerate(delivered_orders.iterrows()),
            total=len(delivered_orders),
            desc="LIKP - Delivery Headers",
        ):
            vbeln_del = f"{self._LIKP_START + idx:010d}"
            erdat = str(order["ERDAT"])
            # Planned goods issue date is on or after the order date
            wadat = random_sap_date(
                start=erdat[:4] + "-" + erdat[4:6] + "-" + erdat[6:],
                end=DATE_RANGE_END,
            )
            # Actual goods issue is on or after planned (or same day)
            wadat_ist = random_sap_date(
                start=wadat[:4] + "-" + wadat[4:6] + "-" + wadat[6:],
                end=DATE_RANGE_END,
            )
            row = {
                "VBELN": vbeln_del,
                "WADAT": wadat,
                "WADAT_IST": wadat_ist,
                "KUNNR": str(order["KUNNR"]),
                "VSTEL": fake.random_element(SAP_SHIPPING_POINTS),
                "ERDAT": erdat,
                "ERZET": random_sap_time(),
                "VBELN_VBA": str(order["VBELN"]),   # reference to sales order
            }
            rows.append(row)

        source_cols = [
            "VBELN", "WADAT", "WADAT_IST", "KUNNR", "VSTEL",
            "ERDAT", "ERZET", "VBELN_VBA",
        ]
        self._add_bronze(rows, "LIKP")
        return self._to_str_df(rows, source_cols)

    # ------------------------------------------------------------------
    # 9. LIPS - Delivery Items
    # ------------------------------------------------------------------

    def generate_lips(
        self, likp_df: pd.DataFrame, vbap_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Delivery items -- copies line items from referenced sales orders."""
        # Build lookup using groupby (O(1) per order vs O(n) iterrows at 300K rows)
        vbap_grouped = {
            str(vbeln): group.to_dict("records")
            for vbeln, group in vbap_df.groupby("VBELN")
        }

        rows: list[dict] = []
        for _, delivery in tqdm(
            likp_df.iterrows(), total=len(likp_df), desc="LIPS - Delivery Items"
        ):
            vbeln_del = str(delivery["VBELN"])
            vbeln_order = str(delivery["VBELN_VBA"])
            items = vbap_grouped.get(vbeln_order, [])

            for seq, item in enumerate(items, start=1):
                row = {
                    "VBELN": vbeln_del,
                    "POSNR": f"{seq * 10:06d}",
                    "MATNR": str(item["MATNR"]),
                    "ARKTX": str(item["ARKTX"]),
                    "LFIMG": str(item["KWMENG"]),
                    "MEINS": str(item["VRKME"]),
                    "VGBEL": vbeln_order,
                    "VGPOS": str(item["POSNR"]),
                }
                rows.append(row)

        source_cols = [
            "VBELN", "POSNR", "MATNR", "ARKTX", "LFIMG",
            "MEINS", "VGBEL", "VGPOS",
        ]
        self._add_bronze(rows, "LIPS")
        return self._to_str_df(rows, source_cols)

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def generate_all(self) -> dict[str, pd.DataFrame]:
        """Generate all 9 SAP SD tables in dependency order.

        Returns a dict mapping table names (lower-case) to DataFrames::

            {
                "kna1": ..., "mara": ..., "mard": ...,
                "vbak": ..., "vbap": ...,
                "vbrk": ..., "vbrp": ...,
                "likp": ..., "lips": ...,
            }
        """
        print("\n=== Generating SAP SD tables ===\n")

        # Independent master-data tables
        kna1 = self.generate_kna1()
        mara = self.generate_mara()
        mard = self.generate_mard()

        # Sales order flow (header -> items, then update header totals)
        vbak = self.generate_vbak()
        vbap = self.generate_vbap(vbak)

        # Billing (depends on orders + items)
        vbrk = self.generate_vbrk(vbak)
        vbrp = self.generate_vbrp(vbrk, vbap)

        # Delivery (depends on orders + items)
        likp = self.generate_likp(vbak)
        lips = self.generate_lips(likp, vbap)

        tables = {
            "kna1": kna1,
            "mara": mara,
            "mard": mard,
            "vbak": vbak,
            "vbap": vbap,
            "vbrk": vbrk,
            "vbrp": vbrp,
            "likp": likp,
            "lips": lips,
        }

        print("\n=== SAP SD generation complete ===")
        for name, df in tables.items():
            print(f"  {name.upper():6s}  {len(df):>8,} rows  |  {len(df.columns)} cols")
        print()

        return tables
