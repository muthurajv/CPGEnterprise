"""Supervisor agent: routes queries to the correct specialist via LangGraph StateGraph."""
import os
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI
from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from src.agents.state import SupplyChainState
from src.observability.instrumentation import supervisor_span

AGENTS = [
    "inventory",
    "demand_forecasting",
    "procurement",
    "policy_approval",
    "rag",
    "executive_analytics",
]

NextAgent = Literal[
    "inventory",
    "demand_forecasting",
    "procurement",
    "policy_approval",
    "rag",
    "executive_analytics",
    "FINISH",
]


class RoutingDecision(BaseModel):
    next_agent: NextAgent
    reasoning: str


_SYSTEM_PROMPT = """You are the supply chain AI supervisor for a global CPG enterprise.
You route incoming queries to the most appropriate specialist agent.

Available agents:
- inventory: Real-time stock levels, warehouse locations, low-stock alerts (SAP data)
- demand_forecasting: 90-day demand forecast using 18-month shipment history and LLM reasoning
- procurement: Vendor selection, order quantities, cost analysis, urgency scoring
- policy_approval: Deterministic policy rule evaluation — approves, flags for human review, or denies orders
- rag: Hybrid semantic search over CPG policy documents, SOPs, and contracts
- executive_analytics: Scheduled KPI computation (fill rate, MAPE, inventory turnover) with CFO narrative

Rules:
1. Route to the single most relevant agent for the user's query.
2. After an agent responds, decide whether the answer is complete (FINISH) or another agent is needed.
3. Never route to the same agent twice in one conversation unless the user explicitly asks.
4. For compound questions (e.g. "stockout risk + what to order"), start with inventory, then demand_forecasting.
5. Respond ONLY with a RoutingDecision JSON — no other text.
"""


def _build_llm() -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_KEY"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
        temperature=0,
    ).with_structured_output(RoutingDecision)


def supervisor_node(state: SupplyChainState) -> dict:
    llm = _build_llm()
    messages = [SystemMessage(content=_SYSTEM_PROMPT)] + list(state["messages"])
    decision: RoutingDecision = llm.invoke(messages)

    with supervisor_span(decision.next_agent, state.get("session_id", "")):
        pass  # span records the routing decision as attribute

    return {
        "next_agent": decision.next_agent,
        "active_agent": decision.next_agent,
        "messages": [HumanMessage(content=f"[Supervisor] Routing to: {decision.next_agent}. Reason: {decision.reasoning}")],
    }


def route_after_supervisor(state: SupplyChainState) -> str:
    return state["next_agent"]


def build_graph() -> StateGraph:
    from src.agents.inventory_agent import inventory_node
    from src.agents.demand_forecasting_agent import demand_forecasting_node
    from src.agents.procurement_agent import procurement_node
    from src.agents.policy_approval_agent import policy_approval_node
    from src.agents.rag_agent import rag_node
    from src.agents.executive_analytics_agent import executive_analytics_node

    graph = StateGraph(SupplyChainState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("inventory", inventory_node)
    graph.add_node("demand_forecasting", demand_forecasting_node)
    graph.add_node("procurement", procurement_node)
    graph.add_node("policy_approval", policy_approval_node)
    graph.add_node("rag", rag_node)
    graph.add_node("executive_analytics", executive_analytics_node)

    graph.set_entry_point("supervisor")

    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {
            "inventory": "inventory",
            "demand_forecasting": "demand_forecasting",
            "procurement": "procurement",
            "policy_approval": "policy_approval",
            "rag": "rag",
            "executive_analytics": "executive_analytics",
            "FINISH": END,
        },
    )

    # All specialist agents route back to supervisor for multi-step queries
    for agent in AGENTS:
        graph.add_edge(agent, "supervisor")

    return graph.compile()
