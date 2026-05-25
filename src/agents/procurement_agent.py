"""Procurement specialist: vendor selection, order quantity, and urgency scoring."""
import json
import os
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from src.agents.state import SupplyChainState
from src.observability.instrumentation import agent_span
from src.tools.sap_mock import get_stock_level

_VENDOR_PATH = Path(__file__).parent.parent / "data" / "vendor_catalog.json"

_SYSTEM_PROMPT = """You are the procurement specialist for a global CPG supply chain.
Given inventory data and vendor catalog, recommend:
1. Optimal vendor (highest reliability within cost tolerance)
2. Recommended order quantity (formula: reorder_point × 2.5 - current_stock, respect vendor MOQ)
3. Estimated order value (quantity × unit_cost)
4. Urgency score (1-10, where 10 = stockout imminent)
5. Expected delivery date (today + lead_time_days)

End with a JSON block:
{"vendor_id": "...", "vendor_name": "...", "order_qty": <int>, "unit_cost_usd": <float>,
 "total_cost_usd": <float>, "urgency_score": <int>, "lead_time_days": <int>}"""


def _find_vendors_for_sku(sku: str, catalog: list[dict]) -> list[dict]:
    return [v for v in catalog if sku.upper() in v.get("skus_supplied", [])]


def _build_llm() -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_KEY"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
        temperature=0,
    )


def procurement_node(state: SupplyChainState) -> dict:
    with agent_span("procurement", domain="procurement", risk_tier=state.get("risk_tier", "medium")) as span:
        sku = state.get("sku")
        query = state["query"]
        catalog = json.loads(_VENDOR_PATH.read_text())

        if sku:
            inventory_item = get_stock_level(sku)
            vendors = _find_vendors_for_sku(sku, catalog)
        else:
            inventory_item = {"note": "No specific SKU — providing general procurement guidance"}
            vendors = catalog[:3]  # sample vendors

        span.set_attribute("procurement.sku", sku or "general")
        span.set_attribute("procurement.vendors_evaluated", len(vendors))

        context = {
            "inventory_status": inventory_item,
            "available_vendors": vendors,
            "prior_demand_forecast": state.get("agent_outputs", {}).get("demand_forecasting", "Not available"),
        }

        llm = _build_llm()
        response = llm.invoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=f"Query: {query}\n\nContext:\n{json.dumps(context, indent=2)}"),
        ])

        result = response.content
        span.set_attribute("procurement.response_length", len(result))
        span.set_attribute("business.domain", "procurement")

    return {
        "agent_outputs": {**state.get("agent_outputs", {}), "procurement": result},
        "messages": [AIMessage(content=f"[Procurement Agent]\n{result}")],
        "active_agent": "procurement",
    }
