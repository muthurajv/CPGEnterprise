"""Unit tests for specialist agent tools and deterministic agents."""
import pytest

from src.tools.sap_mock import get_stock_level, get_all_low_stock, get_warehouse_summary, search_inventory
from src.tools.kpi_calculator import compute_all_kpis, compute_fill_rate, compute_mape
from src.agents.policy_approval_agent import _evaluate_policy


class TestSAPMock:
    def test_get_known_sku(self):
        result = get_stock_level("SKU-001")
        assert result["sku"] == "SKU-001"
        assert result["stock_level"] > 0
        assert "warehouse_location" in result
        assert "below_reorder_point" in result

    def test_get_unknown_sku(self):
        result = get_stock_level("SKU-999")
        assert "error" in result

    def test_case_insensitive(self):
        result = get_stock_level("sku-001")
        assert result["sku"] == "SKU-001"

    def test_get_all_low_stock_returns_list(self):
        low = get_all_low_stock(threshold_pct=1.0)
        assert isinstance(low, list)
        for item in low:
            assert item["pct_of_reorder"] <= 1.0

    def test_get_all_low_stock_sorted(self):
        low = get_all_low_stock(threshold_pct=2.0)
        pcts = [item["pct_of_reorder"] for item in low]
        assert pcts == sorted(pcts)

    def test_warehouse_summary_structure(self):
        summary = get_warehouse_summary()
        assert isinstance(summary, dict)
        for wh, data in summary.items():
            assert "total_skus" in data
            assert "skus_below_rop" in data
            assert "critical_skus" in data

    def test_search_inventory_by_name(self):
        results = search_inventory("cola")
        assert len(results) > 0
        assert any("Cola" in r["name"] for r in results)

    def test_search_inventory_by_category(self):
        results = search_inventory("beverages")
        assert len(results) > 0

    def test_sku_015_is_critical(self):
        result = get_stock_level("SKU-015")
        assert result["stockout_risk"] is True


class TestKPICalculator:
    def test_compute_all_kpis_returns_dict(self):
        kpis = compute_all_kpis()
        assert isinstance(kpis, dict)
        assert "fill_rate_pct" in kpis
        assert "mape_pct" in kpis
        assert "stockout_count" in kpis
        assert "skus_below_reorder_point" in kpis

    def test_fill_rate_in_valid_range(self):
        kpis = compute_all_kpis()
        assert 0 <= kpis["fill_rate_pct"] <= 100

    def test_mape_non_negative(self):
        kpis = compute_all_kpis()
        assert kpis["mape_pct"] >= 0

    def test_compute_fill_rate_with_known_data(self):
        records = [
            {"demand": 100, "quantity_shipped": 95},
            {"demand": 200, "quantity_shipped": 200},
        ]
        fill = compute_fill_rate(records)
        # (95+200)/(100+200) = 295/300 = 98.33%
        assert fill == pytest.approx(98.33, abs=0.1)

    def test_compute_mape_with_perfect_fill(self):
        records = [{"fill_rate": 1.0}, {"fill_rate": 1.0}]
        mape = compute_mape(records)
        assert mape == 0.0

    def test_region_filter(self):
        kpis_emea = compute_all_kpis(region="EMEA")
        kpis_global = compute_all_kpis()
        assert kpis_emea["region"] == "EMEA"
        assert kpis_global["region"] == "global"


class TestPolicyApproval:
    def test_auto_approve_small_order(self):
        result = _evaluate_policy(5_000, "low", 0.97, "SKU-012")
        assert result["decision"] == "auto_approve"
        assert result["approval_level_required"] == "AI_SYSTEM"

    def test_human_review_medium_order(self):
        # $25k is between $10k and $50k → Procurement Manager
        result = _evaluate_policy(25_000, "medium", 0.95, "SKU-001")
        assert result["decision"] == "human_review"
        assert result["approval_level_required"] == "PROCUREMENT_MANAGER"

    def test_human_review_large_order(self):
        # $150k is between $50k and $250k → VP Supply Chain + Finance
        result = _evaluate_policy(150_000, "medium", 0.96, "SKU-001")
        assert result["decision"] == "human_review"
        assert result["approval_level_required"] == "VP_FINANCE"

    def test_csuite_approval_very_large_order(self):
        # Over $250k → C-Suite
        result = _evaluate_policy(300_000, "medium", 0.96, "SKU-001")
        assert result["decision"] == "human_review"
        assert result["approval_level_required"] == "C_SUITE"

    def test_deny_unreliable_vendor(self):
        result = _evaluate_policy(5_000, "medium", 0.75, "SKU-001")
        assert result["decision"] == "deny"
        assert any("reliability" in r.lower() for r in result["reasons"])

    def test_high_risk_sku_triggers_human_review(self):
        result = _evaluate_policy(3_000, "high", 0.99, "SKU-046")
        assert result["decision"] == "human_review"

    def test_auto_approve_high_risk_small_order(self):
        result = _evaluate_policy(1_500, "high", 0.99, "SKU-046")
        assert result["decision"] == "auto_approve"

    def test_policy_version_present(self):
        result = _evaluate_policy(5_000, "medium", 0.95, "SKU-001")
        assert result["policy_version"] == "SCM-THRESH-2026-v2"
