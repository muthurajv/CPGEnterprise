"""Executive analytics specialist: KPI computation + CFO-ready narrative."""
import json
import os

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from src.agents.state import SupplyChainState
from src.observability.instrumentation import agent_span, record_token_usage
from src.tools.kpi_calculator import compute_all_kpis

_SYSTEM_PROMPT = """You are the executive analytics specialist for a global CPG enterprise.
You translate operational KPIs into concise, CFO-ready narratives.

Your report must include:
1. **Executive Summary** (2-3 sentences, plain English, business impact focus)
2. **KPI Scorecard** (table format: Metric | Value | Target | Status)
3. **Key Risks** (top 3 risks with potential revenue impact)
4. **Recommended Actions** (top 3, prioritised by urgency)
5. **Outlook** (1 paragraph: next 90 days)

Targets:
- Fill Rate: ≥ 98.5%
- MAPE: ≤ 8%
- Inventory Turnover: ≥ 8x/year
- Stockout Rate: < 0.5% of SKUs"""


def _build_llm() -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_KEY"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
        temperature=0.2,
    )


def executive_analytics_node(state: SupplyChainState) -> dict:
    with agent_span("executive_analytics", domain="analytics", risk_tier="low") as span:
        region = state.get("region")
        query = state["query"]

        kpis = compute_all_kpis(region=region)
        span.set_attribute("analytics.output", "executive_kpi")
        span.set_attribute("analytics.region", region or "global")
        span.set_attribute("analytics.fill_rate_pct", kpis.get("fill_rate_pct", 0))
        span.set_attribute("analytics.mape_pct", kpis.get("mape_pct", 0))
        span.set_attribute("analytics.stockout_count", kpis.get("stockout_count", 0))

        llm = _build_llm()
        response = llm.invoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=f"Query: {query}\n\nCurrent KPIs:\n{json.dumps(kpis, indent=2)}"),
        ])

        result = response.content
        span.set_attribute("analytics.response_length", len(result))
        usage = getattr(response, "usage_metadata", None) or {}
        record_token_usage(usage.get("input_tokens", 0), usage.get("output_tokens", 0), "executive_analytics")

    return {
        "agent_outputs": {**state.get("agent_outputs", {}), "executive_analytics": result},
        "messages": [AIMessage(content=f"[Executive Analytics Agent]\n{result}")],
        "active_agent": "executive_analytics",
    }
