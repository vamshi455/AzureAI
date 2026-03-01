#!/usr/bin/env python3
"""Predictive Maintenance ML Pipeline.

Reads IoT telemetry and equipment lifecycle events from bronze Parquet,
engineers features, trains a Random Forest classifier for failure risk
prediction, and exports health scores per equipment.

Usage:
    python predictive_maintenance.py           # Run full pipeline (train + predict)
    python predictive_maintenance.py --train   # Train model only
    python predictive_maintenance.py --predict # Generate predictions only (requires trained model)
"""

import argparse
import json
import random
import time
from datetime import datetime, timedelta

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from tqdm import tqdm

from config import (
    OUTPUT_BRONZE,
    OUTPUT_GOLD,
    OUTPUT_ML_FEATURES,
    OUTPUT_ML_MODELS,
    PM_FEATURE_WINDOW_DAYS,
    PM_MODEL_PARAMS,
    PM_PREDICTION_HORIZON_DAYS,
    RANDOM_SEED,
    DATE_RANGE_END,
)

# Reproducibility
np.random.seed(RANDOM_SEED)
random.seed(RANDOM_SEED)


# ---------------------------------------------------------------------------
# Helper: load bronze Parquet (mirrors pattern in chunk_for_rag.py)
# ---------------------------------------------------------------------------
def load_bronze_parquet(source_system: str, table: str) -> pd.DataFrame:
    """Load a Parquet file from the local bronze output directory."""
    path = OUTPUT_BRONZE / source_system / table / f"{table}.parquet"
    if not path.exists():
        print(f"  WARNING: {path} not found, returning empty DataFrame")
        return pd.DataFrame()
    df = pd.read_parquet(path)
    print(f"  Loaded {table}: {len(df):,} rows")
    return df


# ============================================================================
# 1. FeatureEngineer
# ============================================================================


class FeatureEngineer:
    """Transform raw telemetry into ML features per equipment per week."""

    SENSOR_TYPES = ["temperature", "pressure", "vibration", "humidity", "flow_rate", "power"]

    def compute_features(self, telemetry_df: pd.DataFrame) -> pd.DataFrame:
        """Group telemetry by (equipment_id, week) and compute features.

        For each sensor type attached to an equipment, compute over the week:
        - {sensor}_mean, {sensor}_std, {sensor}_min, {sensor}_max
        - {sensor}_range  (max - min)
        - {sensor}_trend  (linear slope of values over time)

        Aggregate features:
        - anomaly_count:   readings where quality_flag != 'GOOD'
        - bad_reading_pct: BAD / total_readings
        - total_readings:  count of all readings in window

        Returns
        -------
        pd.DataFrame
            Columns: equipment_id, week_end, [sensor features...], anomaly_count,
            bad_reading_pct, total_readings
        """
        start = time.time()

        # Parse timestamps
        df = telemetry_df.copy()
        df["event_timestamp"] = pd.to_datetime(df["event_timestamp"])

        # week_end = Sunday ending each ISO week
        # pd.Timestamp.isocalendar gives (year, week, day). We compute the
        # Sunday that ends the ISO week for each reading.
        df["week_end"] = df["event_timestamp"].dt.to_period("W").apply(lambda p: p.end_time.date())

        # -------------------------------------------------------------------
        # Sensor-level statistics (mean, std, min, max, range) via groupby/agg
        # -------------------------------------------------------------------
        print("  Computing sensor-level aggregates...")
        sensor_agg = (
            df.groupby(["equipment_id", "week_end", "measurement_type"])["measurement_value"]
            .agg(["mean", "std", "min", "max"])
            .reset_index()
        )
        sensor_agg["range"] = sensor_agg["max"] - sensor_agg["min"]
        sensor_agg["std"] = sensor_agg["std"].fillna(0)

        # Pivot so each sensor type becomes its own set of columns
        feature_frames = []
        for sensor in self.SENSOR_TYPES:
            subset = sensor_agg[sensor_agg["measurement_type"] == sensor].copy()
            if subset.empty:
                continue
            subset = subset.rename(
                columns={
                    "mean": f"{sensor}_mean",
                    "std": f"{sensor}_std",
                    "min": f"{sensor}_min",
                    "max": f"{sensor}_max",
                    "range": f"{sensor}_range",
                }
            )
            subset = subset.drop(columns=["measurement_type"])
            feature_frames.append(subset)

        # -------------------------------------------------------------------
        # Sensor-level trend (linear slope via numpy polyfit)
        # -------------------------------------------------------------------
        print("  Computing sensor trends...")
        trend_rows = []
        grouped = df.groupby(["equipment_id", "week_end", "measurement_type"])
        for (eq_id, wk, sensor), grp in tqdm(grouped, desc="  Trends", leave=False):
            if sensor not in self.SENSOR_TYPES:
                continue
            if len(grp) < 2:
                trend_rows.append(
                    {"equipment_id": eq_id, "week_end": wk, "sensor": sensor, "trend": 0.0}
                )
                continue

            # Ordinal time axis (seconds from first reading in group)
            ts = grp["event_timestamp"].astype(np.int64) / 1e9  # seconds
            ts_norm = ts - ts.min()
            values = grp["measurement_value"].values
            try:
                slope, _ = np.polyfit(ts_norm.values, values, 1)
            except (np.linalg.LinAlgError, ValueError):
                slope = 0.0
            trend_rows.append(
                {"equipment_id": eq_id, "week_end": wk, "sensor": sensor, "trend": slope}
            )

        trend_df = pd.DataFrame(trend_rows)
        # Pivot trends into columns per sensor
        if not trend_df.empty:
            trend_pivot = trend_df.pivot_table(
                index=["equipment_id", "week_end"],
                columns="sensor",
                values="trend",
                aggfunc="first",
            ).reset_index()
            trend_pivot.columns = [
                f"{c}_trend" if c not in ("equipment_id", "week_end") else c
                for c in trend_pivot.columns
            ]
            feature_frames.append(trend_pivot)

        # -------------------------------------------------------------------
        # Aggregate quality features
        # -------------------------------------------------------------------
        print("  Computing quality features...")
        quality_agg = (
            df.groupby(["equipment_id", "week_end"])
            .agg(
                total_readings=("measurement_value", "count"),
                anomaly_count=("quality_flag", lambda x: (x != "GOOD").sum()),
                bad_count=("quality_flag", lambda x: (x == "BAD").sum()),
            )
            .reset_index()
        )
        quality_agg["bad_reading_pct"] = (
            quality_agg["bad_count"] / quality_agg["total_readings"]
        ).fillna(0)
        quality_agg = quality_agg.drop(columns=["bad_count"])
        feature_frames.append(quality_agg)

        # -------------------------------------------------------------------
        # Merge all feature frames on (equipment_id, week_end)
        # -------------------------------------------------------------------
        print("  Merging feature frames...")
        if not feature_frames:
            return pd.DataFrame(columns=["equipment_id", "week_end"])

        merged = feature_frames[0]
        for frame in feature_frames[1:]:
            merged = merged.merge(frame, on=["equipment_id", "week_end"], how="outer")

        # Fill missing sensor features with 0 (not all equipment has all sensors)
        feature_cols = [c for c in merged.columns if c not in ("equipment_id", "week_end")]
        merged[feature_cols] = merged[feature_cols].fillna(0)

        elapsed = time.time() - start
        print(f"  Feature engineering complete: {len(merged):,} rows, {len(feature_cols)} features ({elapsed:.1f}s)")
        return merged


# ============================================================================
# 2. MaintenanceModelTrainer
# ============================================================================


class MaintenanceModelTrainer:
    """Train Random Forest classifier for failure risk."""

    RISK_LABELS = ["Low", "Medium", "High", "Critical"]

    # Map lifecycle event types to severity for labeling
    _EVENT_SEVERITY: dict[str, str] = {
        "failure": "Critical",
        "maintenance_start": "Critical",
        "critical": "Critical",
        "warning": "High",
        "degradation_start": "Medium",
    }

    def prepare_labels(
        self, lifecycle_df: pd.DataFrame, features_df: pd.DataFrame
    ) -> pd.Series:
        """Determine risk label for each (equipment_id, week_end) feature row.

        For each lifecycle event, look back PM_PREDICTION_HORIZON_DAYS to see
        which feature rows fall in the window (event_date - horizon, event_date).
        Those rows receive the appropriate severity label.  Rows not covered by
        any window default to "Low".  When multiple events overlap, the most
        severe label wins.

        Parameters
        ----------
        lifecycle_df : pd.DataFrame
            Equipment lifecycle events with columns: equipment_id, event_type,
            event_date (or event_timestamp).
        features_df : pd.DataFrame
            Features with columns: equipment_id, week_end, ...

        Returns
        -------
        pd.Series
            Risk label strings aligned with features_df index.
        """
        severity_order = {label: i for i, label in enumerate(self.RISK_LABELS)}
        # Start with everything as Low (index 0)
        labels = pd.Series(["Low"] * len(features_df), index=features_df.index)

        if lifecycle_df.empty:
            print("  No lifecycle events found; all labels set to 'Low'.")
            return labels

        # Normalise lifecycle dates
        lc = lifecycle_df.copy()
        date_col = "event_date" if "event_date" in lc.columns else "event_timestamp"
        lc["event_date"] = pd.to_datetime(lc[date_col]).dt.date

        horizon = timedelta(days=PM_PREDICTION_HORIZON_DAYS)

        # Build a lookup: equipment_id -> list of (window_start_date, severity)
        eq_events: dict[str, list[tuple]] = {}
        for _, row in lc.iterrows():
            event_type = str(row.get("event_type", "")).lower()
            severity = self._EVENT_SEVERITY.get(event_type)
            if severity is None:
                continue
            eq_id = row["equipment_id"]
            event_date = row["event_date"]
            window_start = event_date - horizon
            eq_events.setdefault(eq_id, []).append((window_start, event_date, severity))

        # Assign labels
        for idx, frow in features_df.iterrows():
            eq_id = frow["equipment_id"]
            wk_end = frow["week_end"]
            # Ensure wk_end is a date object for comparison
            if hasattr(wk_end, "date"):
                wk_end = wk_end.date()
            elif isinstance(wk_end, str):
                wk_end = datetime.fromisoformat(wk_end).date()

            events = eq_events.get(eq_id, [])
            best_severity = "Low"
            best_rank = severity_order["Low"]
            for window_start, event_date, severity in events:
                if window_start <= wk_end <= event_date:
                    rank = severity_order[severity]
                    if rank > best_rank:
                        best_severity = severity
                        best_rank = rank
            labels.at[idx] = best_severity

        dist = labels.value_counts()
        print("  Label distribution:")
        for label in self.RISK_LABELS:
            count = dist.get(label, 0)
            pct = count / len(labels) * 100 if len(labels) > 0 else 0
            print(f"    {label}: {count:,} ({pct:.1f}%)")

        return labels

    def train(self, features_df: pd.DataFrame, labels: pd.Series) -> dict:
        """Train a Random Forest classifier and persist artifacts.

        Steps:
        1. Drop non-feature columns (equipment_id, week_end).
        2. Fill NaN with 0.
        3. StandardScaler fit_transform.
        4. 80/20 stratified train/test split (random_state=42).
        5. RandomForestClassifier with PM_MODEL_PARAMS from config.
        6. 5-fold stratified cross-validation, print mean accuracy.
        7. Fit on full training set.
        8. Evaluate on test set.
        9. Save model, scaler, and training report.

        Returns
        -------
        dict
            Keys: accuracy, f1_macro, classification_report, feature_importances
        """
        # 1. Prepare feature matrix
        drop_cols = [c for c in ("equipment_id", "week_end") if c in features_df.columns]
        X = features_df.drop(columns=drop_cols).copy()
        feature_names = list(X.columns)

        # 2. Fill NaN
        X = X.fillna(0).values

        # 3. Scale
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # Encode labels
        le = LabelEncoder()
        le.classes_ = np.array(self.RISK_LABELS)
        y = le.transform(labels.values)

        # 4. Stratified split
        X_train, X_test, y_train, y_test = train_test_split(
            X_scaled, y, test_size=0.2, random_state=42, stratify=y
        )

        # 5. Model
        clf = RandomForestClassifier(**PM_MODEL_PARAMS)

        # 6. Cross-validation
        print("  Running 5-fold stratified cross-validation...")
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        cv_scores = cross_val_score(clf, X_train, y_train, cv=cv, scoring="accuracy")
        print(f"  CV accuracy: {cv_scores.mean():.3f} (+/- {cv_scores.std():.3f})")

        # 7. Fit on full training set
        print("  Training final model...")
        clf.fit(X_train, y_train)

        # 8. Evaluate on test set
        y_pred = clf.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        f1_macro = f1_score(y_test, y_pred, average="macro")
        cls_report = classification_report(
            y_test, y_pred, target_names=self.RISK_LABELS, zero_division=0
        )
        conf_matrix = confusion_matrix(y_test, y_pred).tolist()

        print(f"  Test accuracy: {acc:.3f}")
        print(f"  Test F1 macro: {f1_macro:.3f}")
        print(f"\n{cls_report}")

        # Feature importances
        importances = dict(zip(feature_names, clf.feature_importances_.tolist()))
        importances_sorted = dict(
            sorted(importances.items(), key=lambda kv: kv[1], reverse=True)
        )

        # 9. Save artifacts
        OUTPUT_ML_MODELS.mkdir(parents=True, exist_ok=True)

        model_path = OUTPUT_ML_MODELS / "predictive_maintenance_rf.joblib"
        scaler_path = OUTPUT_ML_MODELS / "predictive_maintenance_scaler.joblib"
        report_path = OUTPUT_ML_MODELS / "training_report.json"

        joblib.dump(clf, model_path)
        joblib.dump(scaler, scaler_path)
        print(f"  Saved model  -> {model_path}")
        print(f"  Saved scaler -> {scaler_path}")

        report = {
            "trained_at": datetime.now().isoformat(),
            "n_train": len(y_train),
            "n_test": len(y_test),
            "n_features": len(feature_names),
            "feature_names": feature_names,
            "accuracy": round(acc, 4),
            "f1_macro": round(f1_macro, 4),
            "cv_mean_accuracy": round(cv_scores.mean(), 4),
            "cv_std_accuracy": round(cv_scores.std(), 4),
            "classification_report": cls_report,
            "confusion_matrix": conf_matrix,
            "feature_importances": importances_sorted,
            "model_params": PM_MODEL_PARAMS,
        }
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        print(f"  Saved report -> {report_path}")

        return {
            "accuracy": acc,
            "f1_macro": f1_macro,
            "classification_report": cls_report,
            "feature_importances": importances_sorted,
        }


# ============================================================================
# 3. HealthScorePredictor
# ============================================================================


class HealthScorePredictor:
    """Generate health scores from trained model."""

    # Weights for health score calculation
    _SCORE_WEIGHTS = {
        "Low": 100,
        "Medium": 70,
        "High": 30,
        "Critical": 0,
    }

    _RECOMMENDED_ACTIONS = {
        "Low": "Continue routine monitoring",
        "Medium": "Schedule inspection within 60 days",
        "High": "Schedule maintenance within 2 weeks",
        "Critical": "Immediate maintenance required",
    }

    RISK_LABELS = ["Low", "Medium", "High", "Critical"]

    def predict(
        self,
        model: RandomForestClassifier,
        scaler: StandardScaler,
        features_df: pd.DataFrame,
        lifecycle_df: pd.DataFrame,
        telemetry_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """Generate health scores for all equipment using the latest feature window.

        For each equipment, selects the most recent week_end, runs
        model.predict_proba, and derives:
        - health_score (weighted sum of class probabilities)
        - failure_risk (argmax class label)
        - failure_probability (1 - P(Low))
        - estimated_rul_days (calibrated from failure_probability)
        - top_risk_factors (top 3 features by value * importance)
        - recommended_action
        - last_maintenance_date and next_recommended_date
        - sensor_summary (latest reading per sensor type)

        Saves result to config.OUTPUT_GOLD / "equipment_health_scores.parquet".

        Returns
        -------
        pd.DataFrame
            One row per equipment with health assessment columns.
        """
        start = time.time()

        # Identify feature columns (exclude equipment_id and week_end)
        drop_cols = [c for c in ("equipment_id", "week_end") if c in features_df.columns]
        feature_cols = [c for c in features_df.columns if c not in drop_cols]

        # Get latest feature window per equipment
        latest_idx = features_df.groupby("equipment_id")["week_end"].idxmax()
        latest_features = features_df.loc[latest_idx].reset_index(drop=True)

        # Prepare feature matrix
        X = latest_features[feature_cols].fillna(0).values
        X_scaled = scaler.transform(X)

        # Predict probabilities  (class order matches RISK_LABELS)
        probas = model.predict_proba(X_scaled)

        # Build mapping from model classes (int) to label positions
        # model.classes_ are encoded ints; map them back to RISK_LABELS order
        le_classes = {label: i for i, label in enumerate(self.RISK_LABELS)}
        # model.classes_ are integers 0..N corresponding to LabelEncoder order
        class_to_label = {cls_int: self.RISK_LABELS[cls_int] for cls_int in model.classes_}
        # Map model column indices to our RISK_LABELS indices
        prob_by_label = np.zeros((len(probas), len(self.RISK_LABELS)))
        for col_idx, cls_int in enumerate(model.classes_):
            label_idx = le_classes[class_to_label[cls_int]]
            prob_by_label[:, label_idx] = probas[:, col_idx]

        # Build equipment metadata lookup from telemetry
        eq_meta = (
            telemetry_df.groupby("equipment_id")
            .agg(
                plant_code=("plant_code", "first"),
                production_line=("production_line", "first"),
                device_ids=("device_id", lambda x: ",".join(sorted(x.unique()))),
            )
            .reset_index()
        )
        eq_meta_map = {row["equipment_id"]: row for _, row in eq_meta.iterrows()}

        # Last maintenance date from lifecycle events
        last_maint_map: dict[str, str] = {}
        if not lifecycle_df.empty:
            lc = lifecycle_df.copy()
            date_col = "event_date" if "event_date" in lc.columns else "event_timestamp"
            lc["event_date"] = pd.to_datetime(lc[date_col])
            maint_events = lc[lc["event_type"].str.lower() == "maintenance_complete"]
            if not maint_events.empty:
                last_maint = (
                    maint_events.sort_values("event_date")
                    .groupby("equipment_id")["event_date"]
                    .last()
                )
                last_maint_map = {
                    eq: d.strftime("%Y-%m-%d") for eq, d in last_maint.items()
                }

        # Latest sensor readings per equipment
        tel = telemetry_df.copy()
        tel["event_timestamp"] = pd.to_datetime(tel["event_timestamp"])
        latest_sensor = (
            tel.sort_values("event_timestamp")
            .groupby(["equipment_id", "measurement_type"])
            .last()
            .reset_index()
        )
        sensor_summary_map: dict[str, dict] = {}
        for eq_id, grp in latest_sensor.groupby("equipment_id"):
            summary = {}
            for _, row in grp.iterrows():
                summary[row["measurement_type"]] = {
                    "value": row["measurement_value"],
                    "unit": row["measurement_unit"],
                    "timestamp": str(row["event_timestamp"]),
                }
            sensor_summary_map[eq_id] = summary

        # Anomaly count in last 30 days per equipment
        cutoff_30d = pd.to_datetime(DATE_RANGE_END) - timedelta(days=30)
        recent_tel = tel[tel["event_timestamp"] >= cutoff_30d]
        anomaly_30d = (
            recent_tel[recent_tel["quality_flag"] != "GOOD"]
            .groupby("equipment_id")
            .size()
        )

        # Feature importances for top_risk_factors
        feat_importances = model.feature_importances_

        # Cap date
        cap_date = datetime.fromisoformat(DATE_RANGE_END).date()
        today = datetime.now().date()

        # Assemble results
        results = []
        for i, (_, row) in enumerate(
            tqdm(latest_features.iterrows(), total=len(latest_features), desc="  Health scores")
        ):
            eq_id = row["equipment_id"]
            probs = prob_by_label[i]
            p_low, p_med, p_high, p_crit = probs

            # Health score: weighted sum
            health_score = int(round(
                self._SCORE_WEIGHTS["Low"] * p_low
                + self._SCORE_WEIGHTS["Medium"] * p_med
                + self._SCORE_WEIGHTS["High"] * p_high
                + self._SCORE_WEIGHTS["Critical"] * p_crit
            ))

            # Failure risk: argmax
            failure_risk = self.RISK_LABELS[int(np.argmax(probs))]

            # Failure probability
            failure_probability = round(1.0 - p_low, 4)

            # Estimated RUL
            p = failure_probability
            if p < 0.2:
                rul = random.randint(180, 365)
            elif p < 0.4:
                rul = random.randint(90, 180)
            elif p < 0.6:
                rul = random.randint(30, 90)
            elif p < 0.8:
                rul = random.randint(7, 30)
            else:
                rul = random.randint(1, 7)

            # Top risk factors: top 3 features by (feature_value * importance)
            feat_vals = latest_features.iloc[i][feature_cols].fillna(0).values.astype(float)
            risk_scores = np.abs(feat_vals) * feat_importances
            top_indices = np.argsort(risk_scores)[-3:][::-1]
            top_risk_factors = [
                {"feature": feature_cols[idx], "score": round(float(risk_scores[idx]), 4)}
                for idx in top_indices
            ]

            # Equipment metadata
            meta = eq_meta_map.get(eq_id, {})
            plant_code = meta.get("plant_code", "") if isinstance(meta, dict) else meta.plant_code if hasattr(meta, "plant_code") else ""
            production_line = meta.get("production_line", "") if isinstance(meta, dict) else ""
            device_ids = meta.get("device_ids", "") if isinstance(meta, dict) else ""

            # Dates
            last_maint_date = last_maint_map.get(eq_id, "")
            next_date = today + timedelta(days=rul)
            if next_date > cap_date:
                next_date = cap_date
            next_recommended_date = next_date.isoformat()

            results.append(
                {
                    "equipment_id": eq_id,
                    "plant_code": plant_code,
                    "production_line": production_line,
                    "device_ids": device_ids,
                    "health_score": health_score,
                    "failure_risk": failure_risk,
                    "failure_probability": round(failure_probability, 4),
                    "estimated_rul_days": rul,
                    "last_maintenance_date": last_maint_date,
                    "next_recommended_date": next_recommended_date,
                    "recommended_action": self._RECOMMENDED_ACTIONS[failure_risk],
                    "anomaly_count_30d": int(anomaly_30d.get(eq_id, 0)),
                    "top_risk_factors": json.dumps(top_risk_factors),
                    "sensor_summary": json.dumps(sensor_summary_map.get(eq_id, {})),
                }
            )

        health_df = pd.DataFrame(results)

        # Save to gold layer
        OUTPUT_GOLD.mkdir(parents=True, exist_ok=True)
        out_path = OUTPUT_GOLD / "equipment_health_scores.parquet"
        health_df.to_parquet(out_path, index=False)
        elapsed = time.time() - start
        print(f"  Saved {len(health_df):,} equipment health scores -> {out_path} ({elapsed:.1f}s)")

        return health_df


# ============================================================================
# 4. Pipeline orchestration
# ============================================================================


def run_full_pipeline() -> dict:
    """Run complete pipeline: features -> train -> predict. Called from generate_all.py."""

    print("--- Loading telemetry data ---")
    telemetry = pd.read_parquet(
        OUTPUT_BRONZE / "iot" / "telemetry" / "iot_telemetry.parquet"
    )
    print(f"  Telemetry: {len(telemetry):,} rows")

    lifecycle_path = OUTPUT_BRONZE / "iot" / "telemetry" / "equipment_lifecycle_events.parquet"
    if lifecycle_path.exists():
        lifecycle = pd.read_parquet(lifecycle_path)
        print(f"  Lifecycle events: {len(lifecycle):,} rows")
    else:
        print(f"  WARNING: {lifecycle_path} not found, using empty lifecycle DataFrame")
        lifecycle = pd.DataFrame(
            columns=["equipment_id", "event_type", "event_date"]
        )

    print("\n--- Feature engineering ---")
    fe = FeatureEngineer()
    features = fe.compute_features(telemetry)

    # Save features
    OUTPUT_ML_FEATURES.mkdir(parents=True, exist_ok=True)
    features.to_parquet(OUTPUT_ML_FEATURES / "equipment_features.parquet", index=False)
    print(f"  Saved features -> {OUTPUT_ML_FEATURES / 'equipment_features.parquet'}")

    print("\n--- Training model ---")
    trainer = MaintenanceModelTrainer()
    labels = trainer.prepare_labels(lifecycle, features)
    results = trainer.train(features, labels)
    print(f"  Model accuracy: {results['accuracy']:.3f}")
    print(f"  F1 macro: {results['f1_macro']:.3f}")

    print("\n--- Generating predictions ---")
    predictor = HealthScorePredictor()
    model = joblib.load(OUTPUT_ML_MODELS / "predictive_maintenance_rf.joblib")
    scaler = joblib.load(OUTPUT_ML_MODELS / "predictive_maintenance_scaler.joblib")
    health_df = predictor.predict(model, scaler, features, lifecycle, telemetry)

    # Print distribution summary
    print(f"\n  Equipment health distribution:")
    for risk, count in health_df["failure_risk"].value_counts().items():
        print(f"    {risk}: {count} ({count / len(health_df) * 100:.0f}%)")

    return results


def main():
    parser = argparse.ArgumentParser(description="Predictive Maintenance ML Pipeline")
    parser.add_argument("--train", action="store_true", help="Train model only")
    parser.add_argument("--predict", action="store_true", help="Generate predictions only (requires trained model)")
    parser.add_argument("--all", action="store_true", default=True, help="Run full pipeline (default)")
    args = parser.parse_args()

    pipeline_start = time.time()
    print("=" * 60)
    print("Predictive Maintenance ML Pipeline")
    print("=" * 60)

    run_full_pipeline()

    elapsed = time.time() - pipeline_start
    print("\n" + "=" * 60)
    print(f"Pipeline complete in {elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
