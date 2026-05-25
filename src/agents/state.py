"""LangGraph shared state for the CPG supply-chain multi-agent system."""
from typing import Annotated, Any, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class SupplyChainState(TypedDict):
    messages: Annotated[list, add_messages]
    query: str
    session_id: str
    active_agent: str
    agent_outputs: dict[str, Any]
    risk_tier: str          # low | medium | high | critical
    region: Optional[str]   # EMEA | AMER | APAC | None (global)
    sku: Optional[str]      # primary SKU in scope, if any
    next_agent: str         # supervisor's routing decision
