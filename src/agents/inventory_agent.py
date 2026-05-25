"""Inventory specialist: real-time stock lookup via SAP mock."""
import os

from langchain_core.messages import AIMessage
from langchain_openai import AzureChatOpenAI

from src.agents.state import SupplyChainState
from src.observability.instrumentation import agent_span, record_token_usage, set_cpg_span_attributes
from src.tools.sap_mock import get_all_low_stock, get_stock_level, get_warehouse_summary, search_inventory

_SYSTEM_PROMPT = """You are the inventory specialist for a global CPG supply chain.
You have access to real-time SAP inventory data.

When given inventory data, provide:
1. Current stock levels and locations
2. Whether any SKU is at or below reorder point
3. Stockout risk assessment (critical if < 50% of reorder point)
4. Recommended immediate actions

Be concise and precise. Flag critical issues clearly."""


def _build_llm() -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_KEY"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
        temperature=0,
    )


def inventory_node(state: SupplyChainState) -> dict:
    with agent_span("inventory", domain="supply_chain", risk_tier=state.get("risk_tier", "medium")) as span:
        query = state["query"]

        # Gather relevant inventory data
        sku = state.get("sku")
        if sku:
            data = {"sku_detail": get_stock_level(sku)}
            span.set_attribute("inventory.sku_queried", sku)
        else:
            low_stock = get_all_low_stock(threshold_pct=1.2)
            warehouse_summary = get_warehouse_summary()
            search_results = search_inventory(query)[:10]
            data = {
                "low_stock_items": low_stock,
                "warehouse_summary": warehouse_summary,
                "search_results": search_results,
            }

        span.set_attribute("inventory.items_retrieved", len(str(data)))
        span.set_attribute("tool", "sap_mock")

        llm = _build_llm()
        from langchain_core.messages import HumanMessage, SystemMessage
        response = llm.invoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=f"Query: {query}\n\nInventory data:\n{data}"),
        ])

        result = response.content
        span.set_attribute("inventory.response_length", len(result))
        usage = getattr(response, "usage_metadata", None) or {}
        record_token_usage(usage.get("input_tokens", 0), usage.get("output_tokens", 0), "inventory")

    return {
        "agent_outputs": {**state.get("agent_outputs", {}), "inventory": result},
        "messages": [AIMessage(content=f"[Inventory Agent]\n{result}")],
        "active_agent": "inventory",
    }
