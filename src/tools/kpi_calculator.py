"""KPI computation for the Executive Analytics agent."""
import json
import statistics
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).parent.parent / "data"


def _load_shipment_history() -> list[dict]:
    path = _DATA_DIR / "shipment_history.json"
    return json.loads(path.read_text())


def _load_inventory() -> list[dict]:
    path = _DATA_DIR / "inventory.json"
    return json.loads(path.read_text())


def compute_mape(records: list[dict]) -> float:
    """Mean Absolute Percentage Error of fill_rate as proxy for forecast accuracy."""
    errors = [abs(1.0 - r["fill_rate"]) for r in records if r["fill_rate"] > 0]
    return round(statistics.mean(errors) * 100, 2) if errors else 0.0


def compute_fill_rate(records: list[dict]) -> float:
    total_demand = sum(r["demand"] for r in records)
    total_shipped = sum(r["quantity_shipped"] for r in records)
    return round(total_shipped / total_demand * 100, 2) if total_demand else 0.0


def compute_stockout_count(inventory: list[dict]) -> int:
    return sum(1 for item in inventory if item["stock_level"] == 0)


def compute_below_rop_count(inventory: list[dict]) -> int:
    return sum(1 for item in inventory if item["stock_level"] <= item["reorder_point"])


def compute_inventory_turnover(shipment_records: list[dict], inventory: list[dict]) -> float:
    """Annualised: (total weekly demand × 52) / average inventory value proxy."""
    weeks = len({r["week_start"] for r in shipment_records})
    if weeks == 0:
        return 0.0
    total_weekly_demand = sum(r["demand"] for r in shipment_records) / weeks
    annualised_demand = total_weekly_demand * 52
    avg_stock = statistics.mean(item["stock_level"] for item in inventory) if inventory else 1
    return round(annualised_demand / avg_stock, 2)


def compute_all_kpis(region: str | None = None) -> dict[str, Any]:
    history = _load_shipment_history()
    inventory = _load_inventory()

    if region:
        history = [r for r in history if r["region"].upper() == region.upper()]

    # Last 13 weeks (≈ 1 quarter) for recency
    weeks_sorted = sorted({r["week_start"] for r in history}, reverse=True)
    recent_weeks = set(weeks_sorted[:13])
    recent = [r for r in history if r["week_start"] in recent_weeks]

    return {
        "period": "last_13_weeks",
        "region": region or "global",
        "fill_rate_pct": compute_fill_rate(recent),
        "mape_pct": compute_mape(recent),
        "stockout_count": compute_stockout_count(inventory),
        "skus_below_reorder_point": compute_below_rop_count(inventory),
        "inventory_turnover_annualised": compute_inventory_turnover(history, inventory),
        "total_skus_tracked": len(inventory),
        "weeks_of_data_analysed": len(recent_weeks),
    }
