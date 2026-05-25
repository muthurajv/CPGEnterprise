"""Run once to generate shipment_history.json mock data."""
import json
import random
import math
from datetime import date, timedelta

random.seed(42)

SKUS = [f"SKU-{str(i).zfill(3)}" for i in range(1, 21)]
REGIONS = ["EMEA", "AMER", "APAC"]
BASE_DEMAND = {
    "SKU-001": 800, "SKU-002": 500, "SKU-003": 400, "SKU-004": 600,
    "SKU-005": 300, "SKU-006": 350, "SKU-007": 900, "SKU-008": 250,
    "SKU-009": 200, "SKU-010": 280, "SKU-011": 450, "SKU-012": 700,
    "SKU-013": 320, "SKU-014": 380, "SKU-015": 290, "SKU-016": 210,
    "SKU-017": 190, "SKU-018": 410, "SKU-019": 480, "SKU-020": 230,
}
REGION_SPLIT = {"EMEA": 0.45, "AMER": 0.35, "APAC": 0.20}

records = []
start = date(2024, 11, 1)
for sku in SKUS:
    base = BASE_DEMAND.get(sku, 300)
    for week in range(78):
        week_date = start + timedelta(weeks=week)
        # Seasonal factor: Q4 holiday bump, summer bump for beverages
        month = week_date.month
        seasonal = 1.0
        if month in [11, 12]:
            seasonal = 1.35
        elif month in [6, 7, 8] and sku in ["SKU-001", "SKU-002", "SKU-003", "SKU-007"]:
            seasonal = 1.20
        # Slight upward trend over 18 months
        trend = 1.0 + (week / 78) * 0.08
        for region in REGIONS:
            region_factor = REGION_SPLIT[region]
            noise = random.gauss(1.0, 0.07)
            demand = max(10, int(base * region_factor * seasonal * trend * noise))
            shipped = min(demand, int(demand * random.uniform(0.95, 1.0)))
            records.append({
                "sku": sku,
                "week_start": week_date.isoformat(),
                "region": region,
                "demand": demand,
                "quantity_shipped": shipped,
                "fill_rate": round(shipped / demand, 4),
            })

with open("shipment_history.json", "w") as f:
    json.dump(records, f, indent=2)

print(f"Generated {len(records)} shipment records.")
