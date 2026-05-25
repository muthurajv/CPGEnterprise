"""Tests for the supervisor routing logic."""
import pytest
from unittest.mock import MagicMock, patch

from src.agents.state import SupplyChainState


def _make_state(query: str, sku: str = None, region: str = None) -> SupplyChainState:
    from langchain_core.messages import HumanMessage
    return SupplyChainState(
        messages=[HumanMessage(content=query)],
        query=query,
        session_id="test-session",
        active_agent="",
        agent_outputs={},
        risk_tier="medium",
        region=region,
        sku=sku,
        next_agent="",
    )


class TestSupervisorRouting:
    @patch("src.agents.supervisor._build_llm")
    def test_routes_inventory_query(self, mock_build_llm):
        from src.agents.supervisor import supervisor_node, RoutingDecision

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = RoutingDecision(
            next_agent="inventory",
            reasoning="User asked about stock levels",
        )
        mock_build_llm.return_value = mock_llm

        state = _make_state("What is the stock level for SKU-001?", sku="SKU-001")
        result = supervisor_node(state)

        assert result["next_agent"] == "inventory"
        assert result["active_agent"] == "inventory"

    @patch("src.agents.supervisor._build_llm")
    def test_routes_procurement_query(self, mock_build_llm):
        from src.agents.supervisor import supervisor_node, RoutingDecision

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = RoutingDecision(
            next_agent="procurement",
            reasoning="User asked about ordering",
        )
        mock_build_llm.return_value = mock_llm

        state = _make_state("Which vendor should we use for SKU-015?", sku="SKU-015")
        result = supervisor_node(state)

        assert result["next_agent"] == "procurement"

    @patch("src.agents.supervisor._build_llm")
    def test_routes_rag_query(self, mock_build_llm):
        from src.agents.supervisor import supervisor_node, RoutingDecision

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = RoutingDecision(
            next_agent="rag",
            reasoning="User asking about policy",
        )
        mock_build_llm.return_value = mock_llm

        state = _make_state("What is the approval threshold for orders above $50,000?")
        result = supervisor_node(state)

        assert result["next_agent"] == "rag"

    @patch("src.agents.supervisor._build_llm")
    def test_routes_to_finish(self, mock_build_llm):
        from src.agents.supervisor import supervisor_node, RoutingDecision

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = RoutingDecision(
            next_agent="FINISH",
            reasoning="Question has been fully answered",
        )
        mock_build_llm.return_value = mock_llm

        state = _make_state("Thanks, that's all I needed")
        result = supervisor_node(state)

        assert result["next_agent"] == "FINISH"


class TestGraphConstruction:
    def test_build_graph_returns_compiled(self):
        # Pre-import all agent modules so patch can resolve them
        import src.agents.inventory_agent
        import src.agents.demand_forecasting_agent
        import src.agents.procurement_agent
        import src.agents.rag_agent
        import src.agents.executive_analytics_agent

        with (
            patch("src.agents.supervisor._build_llm"),
            patch("src.agents.inventory_agent._build_llm"),
            patch("src.agents.demand_forecasting_agent._build_llm"),
            patch("src.agents.procurement_agent._build_llm"),
            patch("src.agents.rag_agent._build_llm"),
            patch("src.agents.executive_analytics_agent._build_llm"),
        ):
            from src.agents.supervisor import build_graph
            graph = build_graph()
            assert graph is not None
