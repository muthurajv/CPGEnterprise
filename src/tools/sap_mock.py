"""Simulated SAP inventory API."""
import json
from pathlib import Path
from typing import Optional

_DATA_PATH = Path(__file__).parent.parent / "data" / "inventory.json"
_inventory: dict[str, dict] = {}


def _load() -> None:
    global _inventory
    if not _inventory:
        items = json.loads(_DATA_PATH.read_text())
        _inventory = {item["sku"]: item for item in items}


def get_stock_level(sku: str) -> dict:
    _load()
    item = _inventory.get(sku.upper())
    if not item:
        return {"error": f"SKU {sku} not found in inventory system"}
    return {
        "sku": item["sku"],
        "name": item["name"],
        "stock_level": item["stock_level"],
        "reorder_point": item["reorder_point"],
        "warehouse_location": item["warehouse_location"],
        "unit": item["unit"],
        "last_updated": item["last_updated"],
        "below_reorder_point": item["stock_level"] <= item["reorder_point"],
        "stockout_risk": item["stock_level"] < item["reorder_point"] * 0.5,
    }


def get_all_low_stock(threshold_pct: float = 1.0) -> list[dict]:
    """Return all SKUs at or below reorder_point * threshold_pct."""
    _load()
    results = []
    for item in _inventory.values():
        if item["stock_level"] <= item["reorder_point"] * threshold_pct:
            results.append({
                "sku": item["sku"],
                "name": item["name"],
                "stock_level": item["stock_level"],
                "reorder_point": item["reorder_point"],
                "warehouse_location": item["warehouse_location"],
                "pct_of_reorder": round(item["stock_level"] / item["reorder_point"], 2),
            })
    return sorted(results, key=lambda x: x["pct_of_reorder"])


def get_warehouse_summary() -> dict:
    _load()
    by_warehouse: dict[str, dict] = {}
    for item in _inventory.values():
        wh = item["warehouse_location"]
        if wh not in by_warehouse:
            by_warehouse[wh] = {"total_skus": 0, "skus_below_rop": 0, "critical_skus": 0}
        by_warehouse[wh]["total_skus"] += 1
        if item["stock_level"] <= item["reorder_point"]:
            by_warehouse[wh]["skus_below_rop"] += 1
        if item["stock_level"] < item["reorder_point"] * 0.5:
            by_warehouse[wh]["critical_skus"] += 1
    return by_warehouse


def search_inventory(query: str) -> list[dict]:
    """Search by SKU or product name fragment."""
    _load()
    q = query.lower()
    return [
        {k: v for k, v in item.items()}
        for item in _inventory.values()
        if q in item["sku"].lower() or q in item["name"].lower() or q in item.get("category", "").lower()
    ]
