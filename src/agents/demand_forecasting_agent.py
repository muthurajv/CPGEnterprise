"""Demand forecasting specialist: LLM reasoning over 18-month shipment history."""
import json
import os
import statistics
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from src.agents.state import SupplyChainState
from src.observability.instrumentation import agent_span

_DATA_PATH = Path(__file__).parent.parent / "data" / "shipment_history.json"

_SYSTEM_PROMPT = """You are the demand forecasting specialist for a global CPG supply chain.
You analyse 18 months of weekly shipment data to forecast demand.

For each analysis, provide:
1. Recent demand trend (last 13 weeks vs prior 13 weeks — growth or decline %)
2. Seasonal patterns identified
3. 90-day forward demand forecast with confidence score (0-1)
4. Key risk factors that could affect the forecast
5. MAPE (Mean Absolute Percentage Error) estimate for your forecast

Format your output clearly with sections. End with a JSON block:
{"forecast_units_90d": <int>, "confidence": <float>, "mape_estimate_pct": <float>, "trend": "growing|stable|declining"}"""


def _load_sku_history(sku: str | None, region: str | None) -> list[dict]:
    history = json.loads(_DATA_PATH.read_text())
    if sku:
        history = [r for r in history if r["sku"] == sku.upper()]
    if region:
        history = [r for r in history if r["region"].upper() == region.upper()]
    return sorted(history, key=lambda r: r["week_start"])


def _summarise_history(records: list[dict]) -> dict:
    if not records:
        return {"error": "No records found"}
    weeks = sorted({r["week_start"] for r in records})
    recent_13 = set(weeks[-13:]) if len(weeks) >= 13 else set(weeks)
    prior_13 = set(weeks[-26:-13]) if len(weeks) >= 26 else set()
    recent_demand = [r["demand"] for r in records if r["week_start"] in recent_13]
    prior_demand = [r["demand"] for r in records if r["week_start"] in prior_13]
    avg_recent = statistics.mean(recent_demand) if recent_demand else 0
    avg_prior = statistics.mean(prior_demand) if prior_demand else avg_recent
    trend_pct = ((avg_recent - avg_prior) / avg_prior * 100) if avg_prior else 0
    return {
        "total_weeks": len(weeks),
        "date_range": f"{weeks[0]} to {weeks[-1]}",
        "avg_weekly_demand_recent_13w": round(avg_recent, 1),
        "avg_weekly_demand_prior_13w": round(avg_prior, 1),
        "trend_pct": round(trend_pct, 1),
        "peak_week_demand": max((r["demand"] for r in records), default=0),
        "min_week_demand": min((r["demand"] for r in records), default=0),
        "avg_fill_rate": round(statistics.mean(r["fill_rate"] for r in records), 4),
        "sample_records_last_8w": sorted(records, key=lambda r: r["week_start"])[-8 * len({r["region"] for r in records}):],
    }


def _build_llm() -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_KEY"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
        temperature=0.1,
    )


def demand_forecasting_node(state: SupplyChainState) -> dict:
    with agent_span("demand_forecasting", domain="supply_chain", risk_tier=state.get("risk_tier", "medium")) as span:
        sku = state.get("sku")
        region = state.get("region")
        query = state["query"]

        records = _load_sku_history(sku, region)
        summary = _summarise_history(records)

        span.set_attribute("demand_forecasting.sku", sku or "all")
        span.set_attribute("demand_forecasting.region", region or "global")
        span.set_attribute("demand_forecasting.record_count", len(records))
        span.set_attribute("forecast.horizon", "90d")

        llm = _build_llm()
        response = llm.invoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=f"Query: {query}\n\nSKU: {sku or 'all'} | Region: {region or 'global'}\n\nHistorical summary:\n{json.dumps(summary, indent=2)}"),
        ])

        result = response.content
        span.set_attribute("demand_forecasting.response_length", len(result))

    return {
        "agent_outputs": {**state.get("agent_outputs", {}), "demand_forecasting": result},
        "messages": [AIMessage(content=f"[Demand Forecasting Agent]\n{result}")],
        "active_agent": "demand_forecasting",
    }
